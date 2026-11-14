"""Scott's Finance: local API + web app. Runs only on 127.0.0.1."""
import json
import logging
import math
import mimetypes
import os
import threading
import uuid
import webbrowser
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import db  # noqa: E402
import logos  # noqa: E402
import plaid_sync as ps  # noqa: E402
import auth  # noqa: E402
import maintenance  # noqa: E402
import categories  # noqa: E402
import rules  # noqa: E402
import places  # noqa: E402
import site_icons  # noqa: E402
import review  # noqa: E402
import tags  # noqa: E402
import tiles  # noqa: E402
from fastapi import Request, Response  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("app")
from contextlib import asynccontextmanager  # noqa: E402


@asynccontextmanager
async def lifespan(_app):
    _startup()
    yield


app = FastAPI(title="Scott's Finance", lifespan=lifespan)


@app.middleware("http")
async def require_sign_in(request: Request, call_next):
    p = request.url.path
    if p.startswith("/api/") and not p.startswith("/api/auth/"):
        if not auth.valid(request.cookies.get(auth.COOKIE)):
            return JSONResponse({"detail": "Sign in required"}, status_code=401)
    return await call_next(request)


@app.get("/api/auth/state")
def auth_state(request: Request):
    return {"enrolled": auth.is_enrolled(), "signed_in": auth.valid(request.cookies.get(auth.COOKIE))}


@app.post("/api/auth/setup")
def auth_setup():
    r = auth.setup()
    if r is None:
        raise HTTPException(400, "Authenticator is already set up")
    return r


class CodeReq(BaseModel):
    code: str


@app.post("/api/auth/verify")
def auth_verify(req: CodeReq, response: Response):
    token = auth.verify(req.code)
    if not token:
        raise HTTPException(401, "That code didn't match. Try the newest code in your authenticator app.")
    _set_session_cookie(response, token)
    return {"ok": True}


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="strict", max_age=auth.session_hours() * 3600)


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.logout(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


class SessionReq(BaseModel):
    hours: int


# Not under /api/auth/, so the sign-in check above covers both routes.
@app.get("/api/settings/session")
def get_session_setting():
    return {"hours": auth.session_hours(), "choices": list(auth.SESSION_CHOICES)}


@app.put("/api/settings/session")
def put_session_setting(req: SessionReq, request: Request, response: Response):
    token = request.cookies.get(auth.COOKIE)
    try:
        auth.set_session_hours(req.hours, token)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _set_session_cookie(response, token)
    return get_session_setting()


class ToggleReq(BaseModel):
    enabled: bool


class MapSettingsReq(BaseModel):
    usgs: bool | None = None
    terrain: bool | None = None
    buildings: bool | None = None


@app.get("/api/settings/map")
def get_map_settings():
    return {**tiles.settings(), "saved": tiles.saved()}


@app.put("/api/settings/map")
def put_map_settings(req: MapSettingsReq):
    for group, on in req.model_dump(exclude_none=True).items():
        tiles.set_setting(group, on)
    return get_map_settings()


@app.delete("/api/settings/map/saved")
def clear_saved_map():
    return {"removed": tiles.clear(), **get_map_settings()}


@app.get("/api/tiles/{source}/{z}/{x}/{y}")
def map_tile(source: str, z: int, x: int, y: int):
    """One map square, from disk or from its public service. Under /api/, so it needs sign-in."""
    try:
        got = tiles.get(source, z, x, y)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except tiles.Refused:
        raise HTTPException(403, "This map data is switched off in Settings.")
    if got is None:
        return Response(status_code=204)
    body, media = got
    return Response(content=body, media_type=media, headers={"Cache-Control": "private, max-age=604800"})


@app.get("/api/settings/site-icons")
def get_site_icons_setting():
    return {"enabled": site_icons.enabled()}


@app.put("/api/settings/site-icons")
def put_site_icons_setting(req: ToggleReq):
    site_icons.set_enabled(req.enabled)
    return get_site_icons_setting()

CASH_TYPES = ("depository",)
DEBT_TYPES = ("credit", "loan")


def _need_plaid():
    if not ps.configured():
        raise HTTPException(400, "Plaid keys missing. Add PLAID_CLIENT_ID and PLAID_SECRET to the .env file, then restart.")


# ---------- status / link ----------

@app.get("/api/status")
def status():
    items = db.q("SELECT item_id, institution_name, status, error, last_sync FROM items ORDER BY institution_name")
    return {"configured": ps.configured(), "env": ps.ENV, "items": items}


class LinkReq(BaseModel):
    item_id: str | None = None


@app.post("/api/link/token")
def link_token(req: LinkReq):
    _need_plaid()
    try:
        return {"link_token": ps.create_link_token(req.item_id)}
    except ps.plaid.ApiException as e:
        raise HTTPException(400, ps.plaid_error(e)[1])


class ExchangeReq(BaseModel):
    public_token: str
    institution_id: str | None = None
    institution_name: str | None = None


@app.post("/api/link/exchange")
def link_exchange(req: ExchangeReq):
    _need_plaid()
    try:
        item_id = ps.exchange(req.public_token, req.institution_id, req.institution_name)
        return {"item_id": item_id}
    except ps.plaid.ApiException as e:
        raise HTTPException(400, ps.plaid_error(e)[1])


@app.post("/api/sync")
def sync():
    _need_plaid()
    return {"results": ps.sync_all()}


@app.post("/api/items/{item_id}/sync")
def sync_one(item_id: str):
    _need_plaid()
    return ps.sync_item(item_id)


@app.delete("/api/items/{item_id}")
def remove(item_id: str):
    _need_plaid()
    ps.remove_item(item_id)
    return {"ok": True}


# ---------- accounts ----------

def _account_out(a, items, liab=None):
    it = items.get(a["item_id"]) or {}
    is_debt = a["type"] in DEBT_TYPES
    bal = a["current"] or 0
    signed = -bal if is_debt else bal
    out = dict(a)
    lia = liab.get(a["account_id"]) if liab is not None else None
    plaid_apr = None
    if lia:
        aprs = lia.get("aprs") or []
        pa = next((x for x in aprs if x.get("apr_type") == "purchase_apr"), aprs[0] if aprs else None)
        plaid_apr = pa.get("apr_percentage") if pa else None
        if plaid_apr is None and lia.get("interest_rate"):
            plaid_apr = (lia.get("interest_rate") or {}).get("percentage") or lia.get("interest_rate_percentage")
        elif plaid_apr is None:
            plaid_apr = lia.get("interest_rate_percentage")
    out["apr"] = a.get("apr_override") if a.get("apr_override") is not None else plaid_apr
    out["apr_source"] = "you" if a.get("apr_override") is not None else ("bank" if plaid_apr is not None else None)
    plaid_min = (lia or {}).get("minimum_payment_amount")
    if plaid_min is None and lia:
        plaid_min = lia.get("next_monthly_payment")
    out["min_payment"] = a.get("min_payment_override") if a.get("min_payment_override") is not None else plaid_min
    if not a.get("limit_amt") and a.get("limit_override"):
        out["limit_amt"] = a["limit_override"]
        if a["type"] == "credit":
            out["available"] = a["limit_override"] - (a["current"] or 0)
    out.update({
        "institution": it.get("institution_name") or a.get("institution") or ("Manual" if a["manual"] else ""),
        "item_status": it.get("status"),
        "item_error": it.get("error"),
        "last_sync": it.get("last_sync"),
        "signed_balance": signed,
        "logo": None if a["type"] == "property" else logos.account_logo(a, it.get("institution_name") or a.get("institution"), it.get("institution_id")),
    })
    return out


@app.get("/api/accounts")
def accounts():
    items = {i["item_id"]: i for i in db.q("SELECT * FROM items")}
    rows = db.q("SELECT * FROM accounts WHERE hidden=0 ORDER BY manual, type, name")
    return [_account_out(a, items, _liabs()) for a in rows]


def _liabs():
    return {r["account_id"]: json.loads(r["data"]) for r in db.q("SELECT account_id, data FROM liabilities")}


@app.get("/api/accounts/{account_id}")
def account_detail(account_id: str):
    a = db.one("SELECT * FROM accounts WHERE account_id=?", (account_id,))
    if not a:
        raise HTTPException(404, "Account not found")
    items = {i["item_id"]: i for i in db.q("SELECT * FROM items")}
    out = _account_out(a, items, _liabs())
    lia = db.one("SELECT kind, data, updated_at FROM liabilities WHERE account_id=?", (account_id,))
    out["liability"] = {"kind": lia["kind"], **json.loads(lia["data"])} if lia else None
    if a["manual"] and a["linked_account_id"]:
        m = db.one("SELECT kind, data FROM liabilities WHERE account_id=?", (a["linked_account_id"],))
        ma = db.one("SELECT current, name FROM accounts WHERE account_id=?", (a["linked_account_id"],))
        out["mortgage"] = {"balance": ma["current"] if ma else None, "name": ma["name"] if ma else None,
                           **(json.loads(m["data"]) if m else {})}
    out["holdings"] = db.q("SELECT * FROM holdings WHERE account_id=? ORDER BY value DESC", (account_id,))
    # Activity since the last statement when the bank sends a statement date, else the calendar month so far.
    stmt = out["liability"].get("last_statement_issue_date") if out["liability"] and lia["kind"] == "credit" else None
    if stmt:
        start = (date.fromisoformat(stmt) + timedelta(days=1)).isoformat()
        basis = {"basis": "statement", "statement_date": stmt}
    else:
        start = date.today().replace(day=1).isoformat()
        basis = {"basis": "month"}
    agg = db.one("""SELECT COALESCE(SUM(CASE WHEN amount>0 THEN amount END),0) AS out_amt,
                           COALESCE(SUM(CASE WHEN amount<0 THEN -amount END),0) AS in_amt, COUNT(*) AS n
                    FROM transactions WHERE account_id=? AND date>=?""", (account_id, start))
    out["activity"] = {**basis, "since": start, **agg}
    return out


class ManualReq(BaseModel):
    name: str = "Home"
    value: float
    linked_account_id: str | None = None  # the mortgage account from Plaid, if connected


@app.post("/api/manual")
def add_manual(req: ManualReq):
    aid = "manual-" + uuid.uuid4().hex[:10]
    db.run("""INSERT INTO accounts (account_id, item_id, name, type, subtype, current, manual, linked_account_id)
              VALUES (?, NULL, ?, 'property', 'home', ?, 1, ?)""", (aid, req.name, req.value, req.linked_account_id))
    return {"account_id": aid}


@app.put("/api/manual/{account_id}")
def update_manual(account_id: str, req: ManualReq):
    db.run("UPDATE accounts SET name=?, current=?, linked_account_id=?, updated_at=datetime('now') WHERE account_id=? AND manual=1",
           (req.name, req.value, req.linked_account_id, account_id))
    return {"ok": True}


@app.delete("/api/manual/{account_id}")
def delete_manual(account_id: str):
    db.run("DELETE FROM accounts WHERE account_id=? AND manual=1", (account_id,))
    return {"ok": True}


class ManualAccountReq(BaseModel):
    name: str
    institution: str | None = None
    type: str = "credit"  # credit, depository, loan, investment
    subtype: str | None = None
    mask: str | None = None
    current: float = 0
    limit_amt: float | None = None


@app.post("/api/manual/account")
def add_manual_account(req: ManualAccountReq):
    aid = "manual-" + uuid.uuid4().hex[:10]
    db.run("""INSERT INTO accounts (account_id, item_id, name, official_name, institution, mask, type, subtype, current, available, limit_amt, manual)
              VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
           (aid, req.name, req.name, req.institution, req.mask, req.type, req.subtype or req.type, req.current,
            (req.limit_amt - req.current) if req.limit_amt else req.current, req.limit_amt))
    return {"account_id": aid}


class BalanceReq(BaseModel):
    current: float
    limit_amt: float | None = None


@app.patch("/api/manual/{account_id}/balance")
def set_balance(account_id: str, req: BalanceReq):
    a = db.one("SELECT type FROM accounts WHERE account_id=? AND manual=1", (account_id,))
    if not a:
        raise HTTPException(404, "Manual account not found")
    avail = (req.limit_amt - req.current) if (a["type"] == "credit" and req.limit_amt) else req.current
    db.run("UPDATE accounts SET current=?, limit_amt=?, available=?, updated_at=datetime('now') WHERE account_id=?",
           (req.current, req.limit_amt, avail, account_id))
    return {"ok": True}


class ImportReq(BaseModel):
    csv: str
    flip: bool = False  # flip signs if the file shows purchases as negative


def _parse_date(s):
    from datetime import datetime as _dt
    s = (s or "").strip()
    for f in ("%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y", "%m/%d/%y", "%B %d, %Y", "%d-%b-%Y"):
        try:
            return _dt.strptime(s, f).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _num(s):
    s = (s or "").replace("$", "").replace(",", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


@app.post("/api/accounts/{account_id}/import")
def import_csv(account_id: str, req: ImportReq):
    """Import a CSV of transactions. Sign convention matches Plaid: positive = money out (purchase)."""
    import csv
    import hashlib
    import io
    a = db.one("SELECT * FROM accounts WHERE account_id=?", (account_id,))
    if not a:
        raise HTTPException(404, "Account not found")
    rows = list(csv.DictReader(io.StringIO(req.csv.lstrip("\ufeff"))))
    if not rows:
        raise HTTPException(400, "No rows found in that file")
    keys = {k.lower().strip(): k for k in rows[0].keys() if k}
    pick = lambda *names: next((keys[n] for n in names if n in keys), None)  # noqa: E731
    dk = pick("date", "transaction date", "trans. date", "posted date", "post date", "posting date")
    nk = pick("description", "merchant", "payee", "name", "details")
    ak = pick("amount", "transaction amount")
    debit, credit = pick("debit", "charges"), pick("credit", "payments")
    if not dk or not nk or not (ak or debit or credit):
        raise HTTPException(400, f"Could not find date, description and amount columns. Columns seen: {', '.join(keys)}")
    seen, out = {}, []
    for r in rows:
        d = _parse_date(r.get(dk))
        if not d:
            continue
        if ak:
            amt = _num(r.get(ak))
        else:
            amt = (_num(r.get(debit)) or 0) - (_num(r.get(credit)) or 0)
        if amt is None:
            continue
        if req.flip:
            amt = -amt
        desc = (r.get(nk) or "").strip()
        base = f"{account_id}|{d}|{amt:.2f}|{desc}"
        seen[base] = seen.get(base, 0) + 1
        tid = "imp-" + hashlib.sha1(f"{base}|{seen[base]}".encode()).hexdigest()[:20]
        cat = "LOAN_PAYMENTS" if amt < 0 and "payment" in desc.lower() else None
        out.append((tid, account_id, None, d, "", amt, desc, desc.title()[:60], 0, cat, None, None, None, "import", "{}"))
    before = db.one("SELECT COUNT(*) AS n FROM transactions WHERE account_id=?", (account_id,))["n"]
    db.many("""INSERT OR IGNORE INTO transactions (transaction_id, account_id, item_id, date, authorized_date, amount, name, merchant_name,
               pending, category, category_detail, logo_url, website, payment_channel, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", out)
    after = db.one("SELECT COUNT(*) AS n FROM transactions WHERE account_id=?", (account_id,))["n"]
    try:
        rules.categorize([r[0] for r in out])
    except Exception:
        log.exception("categorization after import failed; rows imported but left uncategorized")
    try:
        places.fill([r[0] for r in out])
    except Exception:
        log.exception("placing after import failed; rows imported but left unplaced")
    return {"read": len(out), "added": after - before, "duplicates": len(out) - (after - before)}


class TermsReq(BaseModel):
    apr: float | None = None
    limit_amt: float | None = None
    min_payment: float | None = None


@app.patch("/api/accounts/{account_id}/terms")
def set_terms(account_id: str, req: TermsReq):
    """Fill in what the bank doesn't send (APR, credit limit, minimum payment). Blank = use the bank's value."""
    db.run("UPDATE accounts SET apr_override=?, limit_override=?, min_payment_override=? WHERE account_id=?",
           (req.apr, req.limit_amt, req.min_payment, account_id))
    return {"ok": True}


@app.get("/api/debts")
def debts():
    items = {i["item_id"]: i for i in db.q("SELECT * FROM items")}
    rows = db.q("SELECT * FROM accounts WHERE hidden=0 AND type IN ('credit','loan')")
    out = []
    liab = _liabs()
    for a in rows:
        o = _account_out(a, items, liab)
        out.append({k: o.get(k) for k in ("account_id", "name", "official_name", "institution", "mask", "type", "subtype",
                                          "current", "limit_amt", "apr", "apr_source", "min_payment", "logo",
                                          "apr_override", "limit_override", "min_payment_override")})
    return out


# ---------- categories ----------

CAT_TYPES = ("income", "expense", "transfer")


class CategoryReq(BaseModel):
    name: str
    group_name: str
    type: str = "expense"
    icon: str | None = None


class CategoryPatch(BaseModel):
    name: str | None = None
    group_name: str | None = None
    hidden: bool | None = None
    icon: str | None = None


def _clean_icon(raw: str | None) -> str | None:
    if raw is None:
        return None
    icon = raw.strip()
    if len(icon) > 16:
        raise HTTPException(400, "Icon is too long")
    return icon


@app.get("/api/categories")
def list_categories():
    return categories.grouped()


@app.post("/api/categories")
def add_category(req: CategoryReq):
    if not req.name.strip() or not req.group_name.strip():
        raise HTTPException(400, "Name and group are required")
    if req.type not in CAT_TYPES:
        raise HTTPException(400, "Type must be income, expense, or transfer")
    return categories.add_custom(req.name, req.group_name, req.type, _clean_icon(req.icon))


@app.patch("/api/categories/{cat_id}")
def patch_category(cat_id: str, req: CategoryPatch):
    if cat_id == categories.UNCAT:
        raise HTTPException(400, "Uncategorized cannot be changed")
    if not categories.get(cat_id):
        raise HTTPException(404, "Category not found")
    sets, args = [], []
    if req.name is not None:
        if not req.name.strip():
            raise HTTPException(400, "Name cannot be empty")
        sets.append("name=?"); args.append(req.name.strip())
    if req.group_name is not None:
        if not req.group_name.strip():
            raise HTTPException(400, "Group cannot be empty")
        sets.append("group_name=?"); args.append(req.group_name.strip())
    if req.hidden is not None:
        sets.append("hidden=?"); args.append(1 if req.hidden else 0)
    if req.icon is not None:
        icon = _clean_icon(req.icon)
        if not icon:
            row = categories.get(cat_id)
            icon = categories.default_icon(cat_id, (req.group_name or row["group_name"]).strip())
        sets.append("icon=?"); args.append(icon)
    if sets:
        db.run(f"UPDATE categories SET {', '.join(sets)} WHERE id=?", args + [cat_id])
    return categories.get(cat_id)


# ---------- transactions ----------

@app.get("/api/transactions")
def transactions(account_id: str | None = None, q: str | None = None, cat_id: str | None = None,
                 spending_only: int = 0, limit: int = 100, offset: int = 0,
                 spot: str | None = None, start: str | None = None, end: str | None = None, merchant: str | None = None,
                 tag_id: int | None = None, unreviewed: int = 0):
    where, args = ["1=1"], []
    if tag_id:
        where.append("EXISTS (SELECT 1 FROM transaction_tags x WHERE x.transaction_id=t.transaction_id AND x.tag_id=?)")
        args.append(tag_id)
    if unreviewed:
        where.append("COALESCE(t.reviewed,0)=0 AND COALESCE(t.pending,0)=0")
    if merchant:
        where.append("COALESCE(NULLIF(t.display_name,''), NULLIF(t.merchant_name,''), t.name)=?")
        args.append(merchant)
    if spot:
        try:
            lat, lon = (float(x) for x in spot.split(","))
        except ValueError:
            raise HTTPException(400, "spot must be latitude,longitude")
        where.append("ROUND(t.place_lat,4)=ROUND(?,4) AND ROUND(t.place_lon,4)=ROUND(?,4)")
        args += [lat, lon]
    if start:
        where.append("t.date>=?")
        args.append(start)
    if end:
        where.append("t.date<=?")
        args.append(end)
    if account_id:
        where.append("t.account_id=?")
        args.append(account_id)
    if cat_id:
        where.append("t.cat_id=?")
        args.append(cat_id)
    if spending_only:
        where.append("COALESCE(t.excluded,0)=0 AND COALESCE(t.is_transfer,0)=0 AND COALESCE(c.type,'expense') != 'transfer'")
    if q:
        where.append("(LOWER(COALESCE(t.display_name,'')||' '||COALESCE(t.merchant_name,'')||' '||COALESCE(t.name,'')||' '||COALESCE(c.name,'')||' '||COALESCE(c.group_name,'')) LIKE ?"
                     " OR EXISTS (SELECT 1 FROM transaction_tags x JOIN tags g ON g.id=x.tag_id"
                     " WHERE x.transaction_id=t.transaction_id AND LOWER(g.name) LIKE ?))")
        args += [f"%{q.lower()}%"] * 2
    w = " AND ".join(where)
    frm = "FROM transactions t LEFT JOIN accounts a ON a.account_id=t.account_id LEFT JOIN categories c ON c.id=t.cat_id"
    total = db.one(f"SELECT COUNT(*) AS n {frm} WHERE {w}", args)["n"]
    rows = db.q(f"""SELECT t.transaction_id, t.account_id, t.date, t.amount, t.name, t.merchant_name, t.display_name,
                    t.place_address, t.place_city, t.place_region, t.place_postal, t.place_country, t.place_lat, t.place_lon, t.place_source, t.place_precision, t.pending,
                    t.category, t.category_detail, t.logo_url, t.website, t.place_website, t.notes, t.reviewed,
                    t.cat_id, t.cat_source, COALESCE(t.excluded,0) AS excluded, COALESCE(t.is_transfer,0) AS is_transfer,
                    c.name AS cat_name, c.group_name AS cat_group, c.type AS cat_type,
                    a.name AS account_name, a.mask
                    {frm} WHERE {w} ORDER BY t.date DESC, t.transaction_id LIMIT ? OFFSET ?""", args + [min(limit, 500), offset])
    tagged = tags.for_transactions([r["transaction_id"] for r in rows])
    for r in rows:
        r["tags"] = tagged.get(r["transaction_id"], [])
        r["logo"] = logos.merchant_logo(r["merchant_name"] or r["name"], r.pop("logo_url"), r.pop("website") or r.pop("place_website"))
        r.pop("place_website", None)
        r["display_amount"] = -(r["amount"] or 0)  # Plaid: positive = money out
        r["place_line"] = places.line(r)
    return {"total": total, "rows": rows}


class TxPatch(BaseModel):
    cat_id: str | None = None
    notes: str | None = None
    excluded: bool | None = None
    is_transfer: bool | None = None
    display_name: str | None = None
    place: dict | None = None
    clear_place: bool = False
    reviewed: bool | None = None


@app.patch("/api/transactions/{transaction_id}")
def patch_transaction(transaction_id: str, req: TxPatch):
    if not db.one("SELECT 1 FROM transactions WHERE transaction_id=?", (transaction_id,)):
        raise HTTPException(404, "Transaction not found")
    sets, args, similar = [], [], 0
    if req.cat_id is not None:
        if not categories.get(req.cat_id):
            raise HTTPException(400, "Unknown category")
        similar = rules.similar_count(transaction_id, req.cat_id)
        sets += ["cat_id=?", "cat_source='user'"]; args.append(req.cat_id)
        rules.remember(transaction_id, req.cat_id)
    if req.notes is not None:
        sets.append("notes=?"); args.append(req.notes)
    if req.excluded is not None:
        sets.append("excluded=?"); args.append(1 if req.excluded else 0)
    if req.is_transfer is not None:
        sets.append("is_transfer=?"); args.append(1 if req.is_transfer else 0)
    if req.display_name is not None:
        sets.append("display_name=?"); args.append(req.display_name.strip() or None)
    if req.reviewed is not None:
        sets.append("reviewed=?"); args.append(1 if req.reviewed else 0)
    if sets:
        db.run(f"UPDATE transactions SET {', '.join(sets)} WHERE transaction_id=?", args + [transaction_id])
    if req.clear_place:
        places.clear_user_place(transaction_id)
    elif req.place is not None:
        if not isinstance(req.place, dict) or not any(str(req.place.get(k) or "").strip() for k in ("address", "city", "region", "postal", "country")):
            raise HTTPException(400, "Enter at least a city or an address")
        places.set_user_place(transaction_id, req.place)
    row = db.one("""SELECT t.transaction_id, t.cat_id, t.cat_source, COALESCE(t.excluded,0) AS excluded, COALESCE(t.is_transfer,0) AS is_transfer,
                           t.display_name, t.notes, t.reviewed, c.name AS cat_name, c.group_name AS cat_group, c.type AS cat_type,
                           t.place_address, t.place_city, t.place_region, t.place_postal, t.place_country, t.place_lat, t.place_lon, t.place_source, t.place_precision
                    FROM transactions t LEFT JOIN categories c ON c.id=t.cat_id WHERE t.transaction_id=?""", (transaction_id,))
    row["similar"] = similar
    row["place_line"] = places.line(row)
    return row


# ---------- tags ----------

class TagReq(BaseModel):
    name: str


class TagPatch(BaseModel):
    name: str | None = None
    color: str | None = None


def _tag_or_404(tag_id: int):
    if not tags.get(tag_id):
        raise HTTPException(404, "Tag not found")


def _tx_or_404(transaction_id: str):
    if not db.one("SELECT 1 FROM transactions WHERE transaction_id=?", (transaction_id,)):
        raise HTTPException(404, "Transaction not found")


@app.get("/api/tags")
def list_tags():
    return {"tags": tags.all_tags(), "colors": list(tags.PALETTE)}


@app.post("/api/tags")
def add_tag(req: TagReq):
    try:
        return tags.ensure(req.name)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/tags/{tag_id}")
def patch_tag(tag_id: int, req: TagPatch):
    _tag_or_404(tag_id)
    try:
        if req.name is not None:
            tags.rename(tag_id, req.name)
        if req.color is not None:
            tags.recolor(tag_id, req.color)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return tags.get(tag_id)


@app.delete("/api/tags/{tag_id}")
def delete_tag(tag_id: int):
    _tag_or_404(tag_id)
    tags.delete(tag_id)
    return {"ok": True}


@app.post("/api/transactions/{transaction_id}/tags")
def tag_transaction(transaction_id: str, req: TagReq):
    _tx_or_404(transaction_id)
    try:
        tags.add(transaction_id, req.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"tags": tags.for_transactions([transaction_id]).get(transaction_id, [])}


@app.delete("/api/transactions/{transaction_id}/tags/{tag_id}")
def untag_transaction(transaction_id: str, tag_id: int):
    _tx_or_404(transaction_id)
    tags.remove(transaction_id, tag_id)
    return {"tags": tags.for_transactions([transaction_id]).get(transaction_id, [])}


# ---------- review queue ----------

@app.post("/api/review/all")
def review_all():
    return {"marked": review.mark_all()}


# ---------- rules ----------

class RuleReq(BaseModel):
    name: str
    priority: int = 100
    enabled: bool = True
    conditions: dict = {}
    actions: dict = {}
    created_from: str | None = None
    apply_past: bool = False


class PreviewReq(BaseModel):
    conditions: dict = {}
    actions: dict = {}


COND_KEYS = {"merchant", "text", "amount_min", "amount_max", "account_id", "day_min", "day_max"}
ACT_KEYS = {"cat_id", "display_name", "exclude", "transfer", "tags"}


def _clean_rule(conditions: dict, actions: dict, need_actions: bool = True):
    """Drop empty values, check bounds, return (conditions, actions) ready to store."""
    def _keep(v):
        return v is not None and v is not False and v != ""

    c = {k: v for k, v in (conditions or {}).items() if k in COND_KEYS and _keep(v)}
    a = {k: v for k, v in (actions or {}).items() if k in ACT_KEYS and _keep(v)}
    # The form sends tag names. The rule stores ids, so renaming a tag keeps its rules working.
    names = a.pop("tags", None)
    if names:
        if not isinstance(names, list):
            raise HTTPException(400, "Tags must be a list of names")
        try:
            ids = [tags.ensure(n)["id"] for n in names if str(n or "").strip()]
        except ValueError as e:
            raise HTTPException(400, str(e))
        if ids:
            a["tag_ids"] = list(dict.fromkeys(ids))
    for k in ("merchant", "text", "account_id"):
        if k in c:
            c[k] = str(c[k]).strip()
            if not c[k]:
                del c[k]
    if "display_name" in a:
        a["display_name"] = str(a["display_name"]).strip()
        if not a["display_name"]:
            del a["display_name"]
    for k in ("exclude", "transfer"):
        if k in a:
            v = a[k]
            a[k] = v if isinstance(v, bool) else str(v).strip().lower() in ("true", "1", "yes", "on")
            if not a[k]:
                del a[k]
    for k in ("amount_min", "amount_max"):
        if k in c:
            try:
                c[k] = float(c[k])
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k} must be a number")
    for k in ("day_min", "day_max"):
        if k in c:
            try:
                c[k] = int(c[k])
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k} must be a whole number")
            if not 1 <= c[k] <= 31:
                raise HTTPException(400, "Day of month must be between 1 and 31")
    if "amount_min" in c and "amount_max" in c and c["amount_min"] > c["amount_max"]:
        raise HTTPException(400, "Minimum amount is above the maximum")
    if "day_min" in c and "day_max" in c and c["day_min"] > c["day_max"]:
        raise HTTPException(400, "First day is after the last day")
    if "cat_id" in a and not categories.get(a["cat_id"]):
        raise HTTPException(400, "Unknown category")
    if not c:
        raise HTTPException(400, "Add at least one condition")
    if need_actions and not a:
        raise HTTPException(400, "Add at least one action")
    return c, a


def _rule_out(r):
    r = dict(r)
    r["conditions"] = json.loads(r["conditions"] or "{}")
    r["actions"] = json.loads(r["actions"] or "{}")
    if isinstance(r["actions"], dict) and r["actions"].get("tag_ids"):
        found = [tags.get(i) for i in r["actions"]["tag_ids"]]
        r["actions"]["tags"] = [g["name"] for g in found if g]
    r["enabled"] = bool(r["enabled"])
    return r


@app.get("/api/rules")
def list_rules():
    return [_rule_out(r) for r in db.q("SELECT * FROM rules ORDER BY priority, id")]


@app.post("/api/rules/preview")
def preview_rule(req: PreviewReq):
    c, _ = _clean_rule(req.conditions, req.actions, need_actions=False)
    return rules.preview(c)


@app.post("/api/rules/apply")
def apply_rules():
    return {"changed": rules.categorize()}


def _rule_input(req: RuleReq):
    if not req.name.strip():
        raise HTTPException(400, "Name is required")
    c, a = _clean_rule(req.conditions, req.actions)
    return req.name.strip(), c, a


@app.post("/api/rules")
def add_rule(req: RuleReq):
    name, c, a = _rule_input(req)
    cur = db.run("INSERT INTO rules (name, priority, enabled, conditions, actions, created_from) VALUES (?,?,?,?,?,?)",
                 (name, req.priority, 1 if req.enabled else 0, json.dumps(c), json.dumps(a), req.created_from))
    rid = cur.lastrowid
    changed = rules.categorize() if req.apply_past else 0
    return {**_rule_out(db.one("SELECT * FROM rules WHERE id=?", (rid,))), "changed": changed}


@app.put("/api/rules/{rule_id}")
def update_rule(rule_id: int, req: RuleReq):
    if not db.one("SELECT 1 FROM rules WHERE id=?", (rule_id,)):
        raise HTTPException(404, "Rule not found")
    name, c, a = _rule_input(req)
    db.run("UPDATE rules SET name=?, priority=?, enabled=?, conditions=?, actions=? WHERE id=?",
           (name, req.priority, 1 if req.enabled else 0, json.dumps(c), json.dumps(a), rule_id))
    changed = rules.categorize() if req.apply_past else 0
    return {**_rule_out(db.one("SELECT * FROM rules WHERE id=?", (rule_id,))), "changed": changed}


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    if db.run("DELETE FROM rules WHERE id=?", (rule_id,)).rowcount == 0:
        raise HTTPException(404, "Rule not found")
    return {"ok": True}


@app.get("/api/places/coverage")
def places_coverage():
    return places.coverage()


_PRECISION_RANK = {"exact": 0, "likely": 1, "zip": 2, "city": 3, "hq": 4}


# How far apart to stand businesses that share one point, in degrees. A city center holds many
# businesses, so they spread wide. An exact address holds few, so they stay close.
_SPREAD = {"exact": 0.0006, "likely": 0.0006, "zip": 0.004, "city": 0.004, "hq": 0.02}
_MERCHANT = "COALESCE(NULLIF(t.display_name,''), NULLIF(t.merchant_name,''), t.name)"


@app.get("/api/map")
def map_points(account_id: str | None = None, cat_id: str | None = None, q: str | None = None,
               start: str | None = None, end: str | None = None, hq: int = 0):
    """One point per business per spot. The spot says where the bar stands; the total is the money spent at that business."""
    where = ["t.amount>0", "t.pending=0", "COALESCE(t.excluded,0)=0", "COALESCE(t.is_transfer,0)=0",
             "COALESCE(c.type,'expense')='expense'"]
    args = []
    for clause, value in (("t.account_id=?", account_id), ("t.cat_id=?", cat_id), ("t.date>=?", start), ("t.date<=?", end)):
        if value:
            where.append(clause)
            args.append(value)
    if q:
        where.append("LOWER(COALESCE(t.display_name,'')||' '||COALESCE(t.merchant_name,'')||' '||COALESCE(t.name,'')) LIKE ?")
        args.append(f"%{q.lower()}%")
    rows = db.q(f"""SELECT ROUND(t.place_lat,4) AS lat, ROUND(t.place_lon,4) AS lon, t.place_address, t.place_city, t.place_region,
                           t.place_country, t.place_precision, t.place_source, t.amount, {_MERCHANT} AS merchant
                    FROM transactions t LEFT JOIN categories c ON c.id=t.cat_id WHERE {' AND '.join(where)}""", args)
    found = {}
    unplaced = {"count": 0, "total": 0.0}
    at_hq = {"count": 0, "total": 0.0}
    for r in rows:
        if r["lat"] is None or r["lon"] is None:
            unplaced["count"] += 1
            unplaced["total"] += r["amount"]
            continue
        if r["place_source"] == "hq":
            at_hq["count"] += 1
            at_hq["total"] += r["amount"]
            if not hq:
                continue
        precision = r["place_precision"] or "city"
        name = r["merchant"] or "Unknown"
        s = found.setdefault((name, r["lat"], r["lon"]), {
            "id": f"{name}|{r['lat']}|{r['lon']}", "name": name, "lat": r["lat"], "lon": r["lon"],
            "address": r["place_address"], "city": r["place_city"], "region": r["place_region"], "country": r["place_country"],
            "precision": precision, "total": 0.0, "count": 0})
        if _PRECISION_RANK.get(precision, 9) < _PRECISION_RANK.get(s["precision"], 9):
            s["precision"] = precision
        s["address"] = s["address"] or r["place_address"]
        s["total"] += r["amount"]
        s["count"] += 1
    points = sorted(found.values(), key=lambda p: (-p["total"], p["name"]))
    # Businesses that share a point stand in a spiral around it, biggest in the middle, so every bar can be seen.
    taken = {}
    for p in points:
        k = taken.get((p["lat"], p["lon"]), 0)
        taken[(p["lat"], p["lon"])] = k + 1
        step = _SPREAD.get(p["precision"], 0.004)
        r, turn = step * math.sqrt(k), math.radians(137.508) * k
        p["show_lat"] = round(p["lat"] + r * math.sin(turn), 5)
        p["show_lon"] = round(p["lon"] + r * math.cos(turn) / max(math.cos(math.radians(p["lat"])), 0.2), 5)
        p["total"] = round(p["total"], 2)
    for d in (unplaced, at_hq):
        d["total"] = round(d["total"], 2)
    return {"points": points, "unplaced": unplaced, "hq": at_hq, "total": round(sum(p["total"] for p in points), 2)}


# ---------- summary ----------

@app.get("/api/summary")
def summary(account_id: str | None = None, cat_id: str | None = None, tag_id: int | None = None):
    rows = db.q("SELECT * FROM accounts WHERE hidden=0")
    cash = sum(a["current"] or 0 for a in rows if a["type"] in CASH_TYPES)
    debt = sum(a["current"] or 0 for a in rows if a["type"] in DEBT_TYPES)
    invest = sum(a["current"] or 0 for a in rows if a["type"] == "investment")
    prop = sum(a["current"] or 0 for a in rows if a["type"] == "property")
    month = date.today().strftime("%Y-%m")
    where, args = ["substr(t.date,1,7)=?", "t.pending=0", "COALESCE(t.excluded,0)=0", "COALESCE(t.is_transfer,0)=0"], [month]
    if account_id:
        where.append("t.account_id=?"); args.append(account_id)
    if cat_id:
        where.append("t.cat_id=?"); args.append(cat_id)
    if tag_id:
        where.append("EXISTS (SELECT 1 FROM transaction_tags x WHERE x.transaction_id=t.transaction_id AND x.tag_id=?)")
        args.append(tag_id)
    m = db.one(f"""SELECT COALESCE(SUM(CASE WHEN t.amount>0 AND COALESCE(c.type,'expense')='expense' THEN t.amount END),0) AS spent,
                          COALESCE(SUM(CASE WHEN t.amount<0 AND c.type='income' THEN -t.amount END),0) AS income
                   FROM transactions t LEFT JOIN categories c ON c.id=t.cat_id WHERE {' AND '.join(where)}""", args)
    return {"net_worth": cash + invest + prop - debt, "cash": cash, "debt": debt, "investments": invest,
            "property": prop, "spent_month": m["spent"], "income_month": m["income"],
            "tx_count": db.one("SELECT COUNT(*) AS n FROM transactions")["n"], "unreviewed": review.count()}


# ---------- static ----------

# Windows can report script files as plain text, and browsers refuse to run a module worker served that way.
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("text/javascript", ".js")

app.mount("/logos", StaticFiles(directory=str(logos.LOGOS)), name="logos")
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")


# ---------- background sync every 6 hours ----------

def _auto_sync():
    if ps.configured() and db.q("SELECT 1 FROM items LIMIT 1"):
        try:
            ps.sync_all()
        except Exception as e:
            log.warning("auto sync failed: %s", e)
    t = threading.Timer(6 * 3600, _auto_sync)
    t.daemon = True
    t.start()


def _daily():
    maintenance.daily()
    t = threading.Timer(24 * 3600, _daily)
    t.daemon = True
    t.start()


def _startup():
    try:
        categories.seed()
        missing = rules.missing_ids()
        if missing:
            n = rules.categorize(missing)
            log.info("categorized %s transactions that had no category", n)
    except Exception:
        log.exception("startup categorization failed; continuing without it")
    try:
        if review.start():
            log.info("review queue started; %s transactions wait in it", review.count())
        tags.prune()
    except Exception:
        log.exception("starting the review queue failed; continuing without it")
    try:
        refreshed = places.refresh_if_stale()
        if refreshed is not None:
            log.info("placed every transaction again, %s changed", refreshed)
        missing_places = places.missing_ids()
        if missing_places:
            log.info("placed %s transactions", places.fill(missing_places))
    except Exception:
        log.exception("startup placing failed; continuing without it")
    threading.Timer(5, _auto_sync).start()
    threading.Timer(10, _daily).start()
    if os.getenv("OPEN_BROWSER", "1") == "1":
        threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8765")).start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
