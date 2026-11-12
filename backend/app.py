"""Scott's Finance: local API + web app. Runs only on 127.0.0.1."""
import json
import logging
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
    response.set_cookie(auth.COOKIE, token, httponly=True, samesite="strict", max_age=auth.SESSION_HOURS * 3600)
    return {"ok": True}


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response):
    auth.logout(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}

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
    rules.categorize([r[0] for r in out])
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


class CategoryPatch(BaseModel):
    name: str | None = None
    group_name: str | None = None
    hidden: bool | None = None


@app.get("/api/categories")
def list_categories():
    return categories.grouped()


@app.post("/api/categories")
def add_category(req: CategoryReq):
    if not req.name.strip() or not req.group_name.strip():
        raise HTTPException(400, "Name and group are required")
    if req.type not in CAT_TYPES:
        raise HTTPException(400, "Type must be income, expense, or transfer")
    return categories.add_custom(req.name, req.group_name, req.type)


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
    if sets:
        db.run(f"UPDATE categories SET {', '.join(sets)} WHERE id=?", args + [cat_id])
    return categories.get(cat_id)


# ---------- transactions ----------

@app.get("/api/transactions")
def transactions(account_id: str | None = None, q: str | None = None, limit: int = 100, offset: int = 0):
    where, args = ["1=1"], []
    if account_id:
        where.append("t.account_id=?")
        args.append(account_id)
    if q:
        where.append("(LOWER(COALESCE(t.merchant_name,'')||' '||COALESCE(t.name,'')||' '||COALESCE(t.category,'')) LIKE ?)")
        args.append(f"%{q.lower()}%")
    w = " AND ".join(where)
    total = db.one(f"SELECT COUNT(*) AS n FROM transactions t WHERE {w}", args)["n"]
    rows = db.q(f"""SELECT t.transaction_id, t.account_id, t.date, t.amount, t.name, t.merchant_name, t.pending, t.category,
                    t.category_detail, t.logo_url, t.user_category, t.reviewed, a.name AS account_name, a.mask
                    FROM transactions t LEFT JOIN accounts a ON a.account_id=t.account_id
                    WHERE {w} ORDER BY t.date DESC, t.transaction_id LIMIT ? OFFSET ?""", args + [min(limit, 500), offset])
    for r in rows:
        r["logo"] = logos.merchant_logo(r["merchant_name"] or r["name"], r.pop("logo_url"))
        r["display_amount"] = -(r["amount"] or 0)  # Plaid: positive = money out
    return {"total": total, "rows": rows}


# ---------- summary ----------

@app.get("/api/summary")
def summary():
    rows = db.q("SELECT * FROM accounts WHERE hidden=0")
    cash = sum(a["current"] or 0 for a in rows if a["type"] in CASH_TYPES)
    debt = sum(a["current"] or 0 for a in rows if a["type"] in DEBT_TYPES)
    invest = sum(a["current"] or 0 for a in rows if a["type"] == "investment")
    prop = sum(a["current"] or 0 for a in rows if a["type"] == "property")
    month = date.today().strftime("%Y-%m")
    m = db.one("""SELECT COALESCE(SUM(CASE WHEN amount>0 AND COALESCE(category,'') NOT IN ('TRANSFER_OUT','LOAN_PAYMENTS') THEN amount END),0) AS spent,
                         COALESCE(SUM(CASE WHEN amount<0 AND COALESCE(category,'') NOT IN ('TRANSFER_IN') THEN -amount END),0) AS income
                  FROM transactions WHERE substr(date,1,7)=? AND pending=0""", (month,))
    return {"net_worth": cash + invest + prop - debt, "cash": cash, "debt": debt, "investments": invest,
            "property": prop, "spent_month": m["spent"], "income_month": m["income"],
            "tx_count": db.one("SELECT COUNT(*) AS n FROM transactions")["n"]}


# ---------- static ----------

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
    categories.seed()
    missing = rules.missing_ids()
    if missing:
        n = rules.categorize(missing)
        log.info("categorized %s transactions that had no category", n)
    threading.Timer(5, _auto_sync).start()
    threading.Timer(10, _daily).start()
    if os.getenv("OPEN_BROWSER", "1") == "1":
        threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8765")).start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
