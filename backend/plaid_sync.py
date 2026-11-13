"""Plaid client and sync logic (no API calls to Claude, ever)."""
import json
import logging
import os
from datetime import datetime

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.institutions_get_by_id_request_options import InstitutionsGetByIdRequestOptions
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.liabilities_get_request import LiabilitiesGetRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.transactions_sync_request_options import TransactionsSyncRequestOptions

import db
import logos
import places
import rules
from secure import decrypt, encrypt

log = logging.getLogger("plaid")

ENV = (os.getenv("PLAID_ENV") or "production").lower()
CLIENT_ID = os.getenv("PLAID_CLIENT_ID", "")
SECRET = os.getenv("PLAID_SECRET", "")


def configured():
    return bool(CLIENT_ID and SECRET)


def _client():
    host = plaid.Environment.Sandbox if ENV == "sandbox" else plaid.Environment.Production
    cfg = plaid.Configuration(host=host, api_key={"clientId": CLIENT_ID, "secret": SECRET})
    return plaid_api.PlaidApi(plaid.ApiClient(cfg))


client = _client() if configured() else None


def plaid_error(e):
    """Turn a Plaid ApiException into (code, message)."""
    try:
        body = json.loads(e.body)
        return body.get("error_code", "UNKNOWN"), body.get("display_message") or body.get("error_message", str(e))
    except Exception:
        return "UNKNOWN", str(e)


def _d(obj):
    return obj.to_dict() if hasattr(obj, "to_dict") else obj


# ---------- Link ----------

def create_link_token(item_id=None):
    args = dict(
        user=LinkTokenCreateRequestUser(client_user_id="scott-local"),
        client_name="Scott's Finance",
        country_codes=[CountryCode("US")],
        language="en",
    )
    if item_id:  # update mode: reconnect an item that needs login again
        item = db.one("SELECT access_token_enc FROM items WHERE item_id=?", (item_id,))
        args["access_token"] = decrypt(item["access_token_enc"])
    else:
        args["products"] = [Products("transactions")]
        args["optional_products"] = [Products("liabilities"), Products("investments")]
        args["transactions"] = LinkTokenTransactions(days_requested=730)
    redirect = os.getenv("PLAID_REDIRECT_URI")
    if redirect:
        args["redirect_uri"] = redirect
    return client.link_token_create(LinkTokenCreateRequest(**args)).link_token


def exchange(public_token, institution_id=None, institution_name=None):
    res = client.item_public_token_exchange(ItemPublicTokenExchangeRequest(public_token=public_token))
    item_id, token = res.item_id, res.access_token
    color = None
    if institution_id:
        try:
            inst = client.institutions_get_by_id(InstitutionsGetByIdRequest(
                institution_id=institution_id, country_codes=[CountryCode("US")],
                options=InstitutionsGetByIdRequestOptions(include_optional_metadata=True))).institution
            institution_name = inst.name
            d = _d(inst)
            color = d.get("primary_color")
            logos.save_institution_logo(institution_id, d.get("logo"))
        except plaid.ApiException as e:
            log.info("institution lookup failed: %s", plaid_error(e))
    db.run("""INSERT OR REPLACE INTO items (item_id, access_token_enc, institution_id, institution_name, institution_color, status)
              VALUES (?,?,?,?,?, 'ok')""", (item_id, encrypt(token), institution_id, institution_name, color))
    sync_item(item_id)
    return item_id


def remove_item(item_id):
    item = db.one("SELECT * FROM items WHERE item_id=?", (item_id,))
    if not item:
        return
    try:
        client.item_remove(ItemRemoveRequest(access_token=decrypt(item["access_token_enc"])))
    except plaid.ApiException as e:
        log.info("item_remove: %s", plaid_error(e))
    accts = [a["account_id"] for a in db.q("SELECT account_id FROM accounts WHERE item_id=?", (item_id,))]
    for a in accts:
        db.run("DELETE FROM liabilities WHERE account_id=?", (a,))
        db.run("DELETE FROM holdings WHERE account_id=?", (a,))
    db.run("DELETE FROM transactions WHERE item_id=?", (item_id,))
    db.run("DELETE FROM accounts WHERE item_id=?", (item_id,))
    db.run("DELETE FROM items WHERE item_id=?", (item_id,))


# ---------- Sync ----------

def _save_accounts(item_id, accounts):
    for a in accounts:
        a = _d(a)
        b = a.get("balances") or {}
        db.run("""INSERT INTO accounts (account_id, item_id, name, official_name, mask, type, subtype, current, available, limit_amt, currency, updated_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?,?, datetime('now'))
                  ON CONFLICT(account_id) DO UPDATE SET name=excluded.name, official_name=excluded.official_name, mask=excluded.mask,
                  type=excluded.type, subtype=excluded.subtype, current=excluded.current, available=excluded.available,
                  limit_amt=excluded.limit_amt, currency=excluded.currency, updated_at=excluded.updated_at""",
               (a["account_id"], item_id, a.get("name"), a.get("official_name"), a.get("mask"), str(a.get("type")),
                str(a.get("subtype")), b.get("current"), b.get("available"), b.get("limit"), b.get("iso_currency_code")))


def _tx_row(t, item_id):
    t = _d(t)
    pfc = t.get("personal_finance_category") or {}
    return (t["transaction_id"], t["account_id"], item_id, str(t.get("date")), str(t.get("authorized_date") or ""),
            t.get("amount"), t.get("name"), t.get("merchant_name"), 1 if t.get("pending") else 0,
            pfc.get("primary"), pfc.get("detailed"), t.get("logo_url"), t.get("website"),
            str(t.get("payment_channel") or ""), db.dumps(t))


TX_UPSERT = """INSERT INTO transactions (transaction_id, account_id, item_id, date, authorized_date, amount, name, merchant_name, pending,
               category, category_detail, logo_url, website, payment_channel, raw)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(transaction_id) DO UPDATE SET account_id=excluded.account_id, date=excluded.date,
               authorized_date=excluded.authorized_date, amount=excluded.amount, name=excluded.name,
               merchant_name=excluded.merchant_name, pending=excluded.pending, category=excluded.category,
               category_detail=excluded.category_detail, logo_url=excluded.logo_url, website=excluded.website,
               payment_channel=excluded.payment_channel, raw=excluded.raw"""


def sync_item(item_id):
    item = db.one("SELECT * FROM items WHERE item_id=?", (item_id,))
    token = decrypt(item["access_token_enc"])
    start_cursor = item["cursor"]
    added = modified = removed = 0
    try:
        # Transactions: page through /transactions/sync, only save the cursor when complete
        for attempt in range(3):
            cursor, pages_added, pages_modified, pages_removed = start_cursor, [], [], []
            try:
                while True:
                    kw = dict(access_token=token, count=500,
                              options=TransactionsSyncRequestOptions(include_original_description=True))
                    if cursor:
                        kw["cursor"] = cursor
                    r = client.transactions_sync(TransactionsSyncRequest(**kw))
                    pages_added += r.added
                    pages_modified += r.modified
                    pages_removed += r.removed
                    _save_accounts(item_id, r.accounts)
                    cursor = r.next_cursor
                    if not r.has_more:
                        break
                break
            except plaid.ApiException as e:
                code, _ = plaid_error(e)
                if code == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION" and attempt < 2:
                    continue
                raise
        db.many(TX_UPSERT, [_tx_row(t, item_id) for t in pages_added + pages_modified])
        try:
            rules.categorize([_d(t)["transaction_id"] for t in pages_added + pages_modified])
        except Exception:
            log.exception("categorization after sync failed; transactions saved but left uncategorized")
        try:
            places.fill([_d(t)["transaction_id"] for t in pages_added + pages_modified])
        except Exception:
            log.exception("placing after sync failed; transactions saved but left unplaced")
        for t in pages_removed:
            db.run("DELETE FROM transactions WHERE transaction_id=?", (_d(t)["transaction_id"],))
        added, modified, removed = len(pages_added), len(pages_modified), len(pages_removed)
        db.run("UPDATE items SET cursor=?, status='ok', error=NULL, last_sync=datetime('now') WHERE item_id=?", (cursor, item_id))

        # Balances (cached balances, no per-call Balance fee)
        _save_accounts(item_id, client.accounts_get(AccountsGetRequest(access_token=token)).accounts)

        # Liabilities (credit cards, mortgages, student loans) if the bank supports it
        try:
            lr = _d(client.liabilities_get(LiabilitiesGetRequest(access_token=token)).liabilities)
            for kind in ("credit", "mortgage", "student"):
                for l in lr.get(kind) or []:
                    db.run("INSERT OR REPLACE INTO liabilities (account_id, kind, data, updated_at) VALUES (?,?,?, datetime('now'))",
                           (l["account_id"], kind, db.dumps(l)))
        except plaid.ApiException as e:
            log.info("liabilities skipped: %s", plaid_error(e)[0])

        # Investment holdings if supported
        try:
            hr = _d(client.investments_holdings_get(InvestmentsHoldingsGetRequest(access_token=token)))
            secs = {s["security_id"]: s for s in hr.get("securities") or []}
            for h in hr.get("holdings") or []:
                s = secs.get(h["security_id"], {})
                db.run("""INSERT OR REPLACE INTO holdings (account_id, security_id, name, ticker, type, quantity, value, cost_basis)
                          VALUES (?,?,?,?,?,?,?,?)""",
                       (h["account_id"], h["security_id"], s.get("name"), s.get("ticker_symbol"), str(s.get("type")),
                        h.get("quantity"), h.get("institution_value"), h.get("cost_basis")))
        except plaid.ApiException as e:
            log.info("investments skipped: %s", plaid_error(e)[0])

        db.run("INSERT INTO sync_log (item_id, added, modified, removed) VALUES (?,?,?,?)", (item_id, added, modified, removed))
        return {"item_id": item_id, "added": added, "modified": modified, "removed": removed}
    except plaid.ApiException as e:
        code, msg = plaid_error(e)
        status = "needs_reconnect" if code in ("ITEM_LOGIN_REQUIRED", "PENDING_EXPIRATION", "ACCESS_NOT_GRANTED") else "error"
        db.run("UPDATE items SET status=?, error=? WHERE item_id=?", (status, f"{code}: {msg}", item_id))
        db.run("INSERT INTO sync_log (item_id, error) VALUES (?,?)", (item_id, f"{code}: {msg}"))
        return {"item_id": item_id, "error": code, "message": msg}


def sync_all():
    return [sync_item(i["item_id"]) for i in db.q("SELECT item_id FROM items")]
