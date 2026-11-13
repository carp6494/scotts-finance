"""Where each transaction happened.

Resolution order for every row the user has not set by hand:
  1. a merchant_places override for the merchant (source user)
  2. Plaid's location block when it has a city or coordinates (source plaid)
  3. the built-in headquarters table by website domain, else by merchant name (source hq)
  4. nothing (source none)
"""
import json
import logging
import re

import db
from places_seed import HQ
from rules import merchant_key

log = logging.getLogger("places")
FIELDS = ("place_address", "place_city", "place_region", "place_postal", "place_country", "place_lat", "place_lon", "place_store")


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


_HQ_BY_NAME = {_norm(v[0]): v for v in HQ.values()}


def domain_of(website):
    if not website:
        return None
    w = str(website).strip().lower()
    w = re.sub(r"^[a-z][a-z0-9+.-]*:(//)?", "", w).lstrip("/")
    w = w.split("/")[0].split(":")[0]
    if w.startswith("www."):
        w = w[4:]
    return w or None


def _s(v):
    return None if v is None else str(v)


def extract(raw):
    """Plaid's location block as a dict, or None when it has neither a city nor coordinates."""
    try:
        r = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(r, dict):
        return None
    loc = r.get("location")
    if not isinstance(loc, dict):
        return None
    out = {k: loc.get(k) for k in ("address", "city", "region", "postal_code", "country", "lat", "lon", "store_number")}
    for k in ("address", "city", "region", "postal_code", "country", "store_number"):
        out[k] = _s(out[k])
    if not (out["city"] or (out["lat"] is not None and out["lon"] is not None)):
        return None
    return out


def _website(t, raw):
    if t.get("website"):
        return t["website"]
    try:
        cps = (json.loads(raw or "{}") or {}).get("counterparties") or []
    except (TypeError, ValueError, AttributeError):
        return None
    return cps[0].get("website") if cps and isinstance(cps[0], dict) else None


def _hq(t, raw):
    dom = domain_of(_website(t, raw))
    if dom and dom in HQ:
        return HQ[dom]
    key = _norm(t.get("merchant_name"))
    return _HQ_BY_NAME.get(key) if key else None


def resolve(t, overrides):
    """Return (values dict keyed by FIELDS, source)."""
    mk = merchant_key(t)
    o = overrides.get(mk) if mk else None
    if o:
        lat = o.get("lat") if o.get("lat") is not None else t.get("place_lat")
        lon = o.get("lon") if o.get("lon") is not None else t.get("place_lon")
        return {"place_address": o.get("address"), "place_city": o.get("city"), "place_region": o.get("region"), "place_postal": o.get("postal"),
                "place_country": o.get("country"), "place_lat": lat, "place_lon": lon, "place_store": None}, "user"
    raw = t.get("raw")
    p = extract(raw)
    if p:
        return {"place_address": p["address"], "place_city": p["city"], "place_region": p["region"], "place_postal": p["postal_code"],
                "place_country": p["country"], "place_lat": p["lat"], "place_lon": p["lon"], "place_store": p["store_number"]}, "plaid"
    h = _hq(t, raw)
    if h:
        name, city, region, country, lat, lon = h
        return {"place_address": None, "place_city": city, "place_region": region or None, "place_postal": None,
                "place_country": country, "place_lat": lat, "place_lon": lon, "place_store": None}, "hq"
    return {k: None for k in FIELDS}, "none"


def _rows(transaction_ids):
    cols = "transaction_id, name, merchant_name, website, raw, place_source, " + ", ".join(FIELDS)
    base = f"SELECT {cols} FROM transactions WHERE COALESCE(place_source,'') != 'user'"
    if transaction_ids is None:
        return db.q(base)
    ids = list(dict.fromkeys(transaction_ids))
    rows = []
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows += db.q(f"{base} AND transaction_id IN ({','.join('?' * len(chunk))})", chunk)
    return rows


def fill(transaction_ids=None) -> int:
    """Resolve and write places for non-user rows. Returns how many rows changed."""
    overrides = {m["merchant_key"]: m for m in db.q("SELECT * FROM merchant_places")}
    updates = []
    for t in _rows(transaction_ids):
        try:
            vals, source = resolve(t, overrides)
            before = tuple(t.get(k) for k in FIELDS) + (t.get("place_source"),)
            after = tuple(vals[k] for k in FIELDS) + (source,)
            if before != after:
                updates.append(tuple(vals[k] for k in FIELDS) + (source, t["transaction_id"]))
        except Exception:
            log.exception("could not place %s", t["transaction_id"])
            continue
    if updates:
        db.many(f"UPDATE transactions SET {', '.join(k + '=?' for k in FIELDS)}, place_source=? "
                "WHERE transaction_id=? AND COALESCE(place_source,'') != 'user'", updates)
    log.info("placed %s rows", len(updates))
    return len(updates)


def missing_ids():
    return [r["transaction_id"] for r in db.q("SELECT transaction_id FROM transactions WHERE place_source IS NULL")]


def _merchant_rows(transaction_id):
    t = db.one("SELECT merchant_name, name FROM transactions WHERE transaction_id=?", (transaction_id,))
    if not t:
        return None, []
    key = merchant_key(t)
    if not key:
        return None, [transaction_id]
    rows = db.q("SELECT transaction_id FROM transactions WHERE LOWER(TRIM(COALESCE(NULLIF(merchant_name,''), name, ''))) = ?", (key,))
    return key, [r["transaction_id"] for r in rows]


def set_user_place(transaction_id, place: dict):
    """Store the user's place for this merchant and apply it to every row of the merchant."""
    key, ids = _merchant_rows(transaction_id)
    if not ids:
        return 0
    vals = {k: str(place.get(k) or "").strip() or None for k in ("address", "city", "region", "postal", "country")}
    lat, lon = _coord(place.get("lat"), 90), _coord(place.get("lon"), 180)
    if key:
        db.run("""INSERT INTO merchant_places (merchant_key, name, address, city, region, postal, country, lat, lon, kind, updated_at)
                  VALUES (?,?,?,?,?,?,?,?,?,'user', datetime('now'))
                  ON CONFLICT(merchant_key) DO UPDATE SET address=excluded.address, city=excluded.city, region=excluded.region,
                  postal=excluded.postal, country=excluded.country, lat=excluded.lat, lon=excluded.lon, updated_at=datetime('now')""",
               (key, key, vals["address"], vals["city"], vals["region"], vals["postal"], vals["country"], lat, lon))
        _unlock(ids)
        fill(ids)
        return len(ids)
    # No merchant key: write just this row, keeping any coordinates it already had.
    db.run("""UPDATE transactions SET place_address=?, place_city=?, place_region=?, place_postal=?, place_country=?,
              place_lat=COALESCE(?, place_lat), place_lon=COALESCE(?, place_lon), place_store=NULL, place_source='user'
              WHERE transaction_id=?""", (vals["address"], vals["city"], vals["region"], vals["postal"], vals["country"], lat, lon, transaction_id))
    return 1


def _coord(v, limit):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if -limit <= f <= limit else None


def _unlock(ids):
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        db.run(f"UPDATE transactions SET place_source=NULL WHERE transaction_id IN ({','.join('?' * len(chunk))})", chunk)


def clear_user_place(transaction_id):
    """Remove the merchant override and re-resolve every row of the merchant."""
    key, ids = _merchant_rows(transaction_id)
    if key:
        db.run("DELETE FROM merchant_places WHERE merchant_key=?", (key,))
    _unlock(ids)
    return fill(ids)


def line(r) -> str:
    """One readable line for the UI."""
    src = r.get("place_source")
    if src in (None, "none"):
        return ""
    city = ", ".join(x for x in (r.get("place_city"), r.get("place_region")) if x)
    if src == "hq":
        return f"{city} · headquarters" if city else ""
    addr = r.get("place_address")
    return ", ".join(x for x in (addr, city) if x)


def coverage():
    out = {"plaid": 0, "hq": 0, "user": 0, "none": 0, "total": 0}
    for r in db.q("SELECT COALESCE(place_source,'none') AS s, COUNT(*) AS n FROM transactions GROUP BY 1"):
        s = r["s"]
        if s not in out:
            log.warning("unrecognized place_source %r", s)
            s = "none"
        out[s] += r["n"]
        out["total"] += r["n"]
    return out
