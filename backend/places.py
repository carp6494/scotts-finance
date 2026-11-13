"""Where each transaction happened.

Resolution order for every row the user has not set by hand:
  1. a merchant_places override for the merchant (source user)
  2. Plaid's location block when it has a city or coordinates (source plaid).
     A bank row missing its street address or coordinates takes the missing parts from
     the one Overture place with the same name in the same city. When the bank gave
     only a city, that Overture place supplies the whole spot (source overture).
  3. the built-in headquarters table by website domain, else by merchant name (source hq)
  4. the one Overture place with that name anywhere in the extract, for purchases
     not made online (source overture)
  5. the one place the same merchant's other purchases agree on (source history)
  6. nothing (source none)

Rows that end up with a place but no coordinates get them from the GeoNames file: the
zip center, else the city center. place_precision records which: exact, zip, city or hq.
It is "likely" when several branches of a chain fit and the app picked the nearest one.
"""
import json
import logging
import math
import re

import db
import geo
import overture
from places_seed import HQ
from rules import merchant_key

log = logging.getLogger("places")
FIELDS = ("place_address", "place_city", "place_region", "place_postal", "place_country", "place_lat", "place_lon", "place_store",
          "place_website", "place_precision")


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


def _blank():
    return {k: None for k in FIELDS}


def _name(t):
    return t.get("merchant_name") or t.get("name")


def _has_coords(v):
    return v.get("place_lat") is not None and v.get("place_lon") is not None


def _from_overture(m):
    v = _blank()
    v.update(place_address=m.get("address"), place_city=m.get("city"), place_region=m.get("region"), place_postal=m.get("postal"),
             place_country=m.get("country"), place_lat=m.get("lat"), place_lon=m.get("lon"), place_website=m.get("website"))
    return v


def _pick(t, overrides):
    mk = merchant_key(t)
    o = overrides.get(mk) if mk else None
    if o:
        v = _blank()
        v.update(place_address=o.get("address"), place_city=o.get("city"), place_region=o.get("region"),
                 place_postal=o.get("postal"), place_country=o.get("country"), place_lat=o.get("lat"), place_lon=o.get("lon"))
        # Keep coordinates the row already had only when they were a real spot, not a zip or city center.
        if not _has_coords(v) and t.get("place_precision") in (None, "exact"):
            v["place_lat"], v["place_lon"] = t.get("place_lat"), t.get("place_lon")
        return v, "user"
    raw = t.get("raw")
    p = extract(raw)
    if p:
        v = _blank()
        v.update(place_address=p["address"], place_city=p["city"], place_region=p["region"], place_postal=p["postal_code"],
                 place_country=p["country"], place_lat=p["lat"], place_lon=p["lon"], place_store=p["store_number"])
        if p["city"] and not (p["address"] and _has_coords(v)):
            us = (p["country"] or "US").strip().upper() in ("US", "USA", "UNITED STATES")
            center = geo.by_city(p["city"], p["region"], home_state()) if us else None
            m = overture.match(_name(t), p["city"], p["region"], center)
            if m and not p["address"] and not _has_coords(v):
                found = _from_overture(m)
                found["place_store"] = p["store_number"]
                return found, "overture"
            if m:
                v["place_address"] = v["place_address"] or m.get("address")
                v["place_postal"] = v["place_postal"] or m.get("postal")
                v["place_website"] = m.get("website")
                if not _has_coords(v):
                    v["place_lat"], v["place_lon"] = m.get("lat"), m.get("lon")
            if not m:
                guess = _nearest_branch(t, p, v, center)
                if guess:
                    return guess
        return v, "plaid"
    h = _hq(t, raw)
    if h:
        name, city, region, country, lat, lon = h
        v = _blank()
        v.update(place_city=city, place_region=region or None, place_country=country, place_lat=lat, place_lon=lon)
        return v, "hq"
    if (t.get("payment_channel") or "").lower() != "online":
        m = overture.match(_name(t))
        if m:
            return _from_overture(m), "overture"
    return _blank(), "none"


SAME_SPOT = 0.005  # degrees, about 500 m


def _gap(a_lat, a_lon, b_lat, b_lon):
    """Rough distance in degrees of latitude. Good enough to rank nearby branches."""
    return math.hypot(a_lat - b_lat, (a_lon - b_lon) * math.cos(math.radians(a_lat)))


def _nearest_branch(t, p, v, center):
    """Several branches share the name. Pick one, or return None.

    The bank gave coordinates: take the street address of the branch at that spot.
    The bank gave only a city: take the branch nearest the owner's usual area and mark
    the row "likely", because the bank never said which branch it was.
    """
    branches = [b for b in overture.candidates(_name(t), p["city"], p["region"], center)
                if b.get("lat") is not None and b.get("lon") is not None]
    if len(branches) < 2:
        return None
    if _has_coords(v):
        if v["place_address"]:
            return None
        b = min(branches, key=lambda b: _gap(v["place_lat"], v["place_lon"], b["lat"], b["lon"]))
        if _gap(v["place_lat"], v["place_lon"], b["lat"], b["lon"]) <= SAME_SPOT:
            v["place_address"], v["place_postal"], v["place_website"] = b.get("address"), v["place_postal"] or b.get("postal"), b.get("website")
        return None
    home = home_point()
    if v["place_address"] or not home:
        return None
    b = min(branches, key=lambda b: (_gap(home[0], home[1], b["lat"], b["lon"]), b.get("address") or ""))
    found = _from_overture(b)
    found["place_store"] = p["store_number"]
    found["place_precision"] = "likely"
    return found, "overture"


_home = None
_home_point = None


def home_state(refresh=False):
    """The state most of the located purchases are in. It breaks ties for a city that came with no state."""
    global _home, _home_point
    if _home is None or refresh:
        r = db.one("""SELECT UPPER(place_region) AS s, COUNT(*) AS n FROM transactions
                      WHERE place_source IN ('plaid','user') AND COALESCE(place_region,'') != '' GROUP BY 1 ORDER BY n DESC LIMIT 1""")
        _home = (r["s"] if r else "") or ""
        # The middle of the purchases whose spot the bank itself gave. Guessed spots never feed it.
        spots = db.q("""SELECT place_lat AS lat, place_lon AS lon FROM transactions
                        WHERE place_source='plaid' AND place_precision='exact' AND place_lat IS NOT NULL AND place_lon IS NOT NULL""")
        if len(spots) >= 3:
            lats, lons = sorted(s["lat"] for s in spots), sorted(s["lon"] for s in spots)
            _home_point = (lats[len(lats) // 2], lons[len(lons) // 2])
        else:
            _home_point = None
    return _home or None


def home_point():
    """(lat, lon) at the middle of the owner's purchases, or None when there are too few to tell."""
    if _home is None:
        home_state()
    return _home_point


def _locate(v, source):
    """Fill missing coordinates from the zip or city, and label how precise the spot is."""
    if source == "none" or v.get("place_precision") == "likely":
        return v
    if source == "hq":
        v["place_precision"] = "hq"
    elif _has_coords(v):
        v["place_precision"] = "exact"
    elif (v.get("place_country") or "US").strip().upper() in ("US", "USA", "UNITED STATES"):
        spot, how = geo.by_zip(v.get("place_postal")), "zip"
        if not spot:
            spot, how = geo.by_city(v.get("place_city"), v.get("place_region"), home_state()), "city"
        if spot:
            v["place_lat"], v["place_lon"], v["place_precision"] = spot[0], spot[1], how
    return v


def resolve(t, overrides):
    """Return (values dict keyed by FIELDS, source)."""
    v, source = _pick(t, overrides)
    return _locate(v, source), source


def _rows(transaction_ids):
    cols = "transaction_id, name, merchant_name, website, payment_channel, raw, place_source, " + ", ".join(FIELDS)
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
    changed = _fill_once(transaction_ids)
    before = _home_point
    home_state(refresh=True)
    if _home_point != before:
        # The pass just written moved the owner's usual area, which the nearest-branch pick depends on.
        changed += _fill_once(transaction_ids)
    return changed


def _fill_once(transaction_ids=None) -> int:
    overrides = {m["merchant_key"]: m for m in db.q("SELECT * FROM merchant_places")}
    home_state(refresh=True)
    results = {}
    for t in _rows(transaction_ids):
        try:
            results[t["transaction_id"]] = (t,) + resolve(t, overrides)
        except Exception:
            log.exception("could not place %s", t["transaction_id"])
            continue
    # A merchant with no place of its own borrows the one place its other purchases agree on.
    known = _history(results)
    updates = []
    for tid, (t, vals, source) in results.items():
        if source == "none":
            spot = known.get(merchant_key(t))
            if spot:
                vals, source = dict(spot, place_store=None), "history"
        before = tuple(t.get(k) for k in FIELDS) + (t.get("place_source"),)
        after = tuple(vals[k] for k in FIELDS) + (source,)
        if before != after:
            updates.append(tuple(vals[k] for k in FIELDS) + (source, tid))
    if updates:
        db.many(f"UPDATE transactions SET {', '.join(k + '=?' for k in FIELDS)}, place_source=? "
                "WHERE transaction_id=? AND COALESCE(place_source,'') != 'user'", updates)
    if transaction_ids is None:
        _locate_user_rows()
    log.info("placed %s rows", len(updates))
    return len(updates)


_SPOT_SOURCES = ("plaid", "overture", "user")


def _history(results):
    """merchant key -> place values, for merchants whose located purchases all point at one spot.

    One spot means one city and at most one street address. A chain with purchases in
    two cities, or at two addresses, gets nothing.
    """
    seen = {}

    def note(t, vals, source):
        if source in _SPOT_SOURCES and (vals.get("place_city") or "").strip():
            mk = merchant_key(t)
            if mk:
                seen.setdefault(mk, []).append(vals)

    for t, vals, source in results.values():
        note(t, vals, source)
    marks = ",".join("?" * len(_SPOT_SOURCES))
    for r in db.q(f"SELECT transaction_id, name, merchant_name, place_source, {', '.join(FIELDS)} FROM transactions "
                  f"WHERE place_source IN ({marks}) AND COALESCE(place_city,'') != ''", _SPOT_SOURCES):
        if r["transaction_id"] not in results:
            note(r, {k: r[k] for k in FIELDS}, r["place_source"])
    out = {}
    for mk, spots in seen.items():
        cities = {geo.norm_city(v["place_city"]) for v in spots}
        streets = {_norm(v["place_address"]) for v in spots if v.get("place_address")}
        if len(cities) == 1 and len(streets) <= 1:
            out[mk] = max(spots, key=lambda v: (bool(v.get("place_address")), _has_coords(v), v.get("place_precision") == "exact"))
    return out


def _locate_user_rows():
    """Hand-entered rows are never re-resolved, so give them coordinates and a precision here."""
    rows = db.q(f"SELECT transaction_id, {', '.join(FIELDS)} FROM transactions WHERE place_source='user' AND place_precision IS NULL")
    updates = []
    for r in rows:
        v = _locate({k: r[k] for k in FIELDS}, "user")
        if v["place_precision"]:
            updates.append((v["place_lat"], v["place_lon"], v["place_precision"], r["transaction_id"]))
    if updates:
        db.many("UPDATE transactions SET place_lat=?, place_lon=?, place_precision=? WHERE transaction_id=?", updates)


RULES_VERSION = 4  # raise this when the resolution rules change, so every row is placed again


def refresh_if_stale():
    """Place every row again when the rules or the Overture extract changed since the last run."""
    db.run("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    stamp = int(overture.DB_PATH.stat().st_mtime) if overture.DB_PATH.exists() else 0
    sig = f"{RULES_VERSION}:{stamp}"
    row = db.one("SELECT value FROM settings WHERE key='places_sig'")
    if row and row["value"] == sig:
        return None
    n = fill()
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('places_sig', ?)", (sig,))
    return n


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
    # No merchant key: write just this row, keeping any exact coordinates it already had.
    cur = db.one("SELECT place_lat, place_lon, place_precision FROM transactions WHERE transaction_id=?", (transaction_id,)) or {}
    v = _blank()
    v.update(place_address=vals["address"], place_city=vals["city"], place_region=vals["region"], place_postal=vals["postal"],
             place_country=vals["country"], place_lat=lat, place_lon=lon)
    if not _has_coords(v) and cur.get("place_precision") in (None, "exact"):
        v["place_lat"], v["place_lon"] = cur.get("place_lat"), cur.get("place_lon")
    v = _locate(v, "user")
    db.run(f"UPDATE transactions SET {', '.join(k + '=?' for k in FIELDS)}, place_source='user' WHERE transaction_id=?",
           tuple(v[k] for k in FIELDS) + (transaction_id,))
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
    text = ", ".join(x for x in (addr, city) if x)
    return f"likely {text}" if text and r.get("place_precision") == "likely" else text


def coverage():
    out = {"plaid": 0, "overture": 0, "history": 0, "hq": 0, "user": 0, "none": 0, "total": 0}
    for r in db.q("SELECT COALESCE(place_source,'none') AS s, COUNT(*) AS n FROM transactions GROUP BY 1"):
        s = r["s"]
        if s not in out:
            log.warning("unrecognized place_source %r", s)
            s = "none"
        out[s] += r["n"]
        out["total"] += r["n"]
    out["located"] = db.one("SELECT COUNT(*) AS n FROM transactions WHERE place_lat IS NOT NULL AND place_lon IS NOT NULL")["n"]
    out["lookup"] = overture.available()
    return out
