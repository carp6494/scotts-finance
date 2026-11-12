"""Rules engine and categorization order.

Order for every transaction the user has not set by hand:
  1. enabled rules by priority (first that sets a category wins; flag-only rules keep going)
  2. merchant memory (the category the user last chose for this merchant)
  3. the Plaid category, inserting a category row if it is new
  4. UNCATEGORIZED
"""
import json
import logging

import categories
import db

log = logging.getLogger("rules")


def merchant_key(t) -> str:
    return (t.get("merchant_name") or t.get("name") or "").strip().lower()


def _contains(hay, needle) -> bool:
    return str(needle).lower() in (hay or "").lower()


def match(conditions, t) -> bool:
    """True when every condition present in the dict holds for transaction dict t. Bad values never raise."""
    try:
        return _match(conditions or {}, t)
    except (ValueError, TypeError, AttributeError):
        return False


def _match(c, t) -> bool:
    if c.get("merchant"):
        if not any(_contains(t.get(k), c["merchant"]) for k in ("display_name", "merchant_name", "name")):
            return False
    if c.get("text") and not _contains(t.get("name"), c["text"]):
        return False
    amt = t.get("amount")
    if c.get("amount_min") is not None and (amt is None or amt < float(c["amount_min"])):
        return False
    if c.get("amount_max") is not None and (amt is None or amt > float(c["amount_max"])):
        return False
    if c.get("account_id") and t.get("account_id") != c["account_id"]:
        return False
    if c.get("day_min") is not None or c.get("day_max") is not None:
        try:
            day = int(str(t.get("date") or "")[8:10])
        except ValueError:
            return False
        if c.get("day_min") is not None and day < int(c["day_min"]):
            return False
        if c.get("day_max") is not None and day > int(c["day_max"]):
            return False
    return True


def _load_rules():
    out = []
    for r in db.q("SELECT * FROM rules WHERE enabled=1 ORDER BY priority, id"):
        try:
            cond = json.loads(r["conditions"] or "{}")
            act = json.loads(r["actions"] or "{}")
            if isinstance(cond, dict):
                for k in ("amount_min", "amount_max"):
                    if cond.get(k) is not None:
                        cond[k] = float(cond[k])
                for k in ("day_min", "day_max"):
                    if cond.get(k) is not None:
                        cond[k] = int(cond[k])
        except (json.JSONDecodeError, TypeError, ValueError):
            log.warning("rule %s (%s) has bad JSON or bad values and was skipped", r["id"], r["name"])
            continue
        if not isinstance(cond, dict) or not isinstance(act, dict):
            log.warning("rule %s (%s) conditions or actions are not objects and was skipped", r["id"], r["name"])
            continue
        out.append((r, cond, act))
    return out


def _rows(transaction_ids):
    base = ("SELECT transaction_id, account_id, date, amount, name, merchant_name, display_name, category, "
            "category_detail, cat_id, cat_source, excluded, is_transfer FROM transactions "
            "WHERE COALESCE(cat_source,'') != 'user'")
    if transaction_ids is None:
        return db.q(base)
    ids = list(dict.fromkeys(transaction_ids))
    rows = []
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows += db.q(f"{base} AND transaction_id IN ({','.join('?' * len(chunk))})", chunk)
    return rows


def categorize(transaction_ids=None) -> int:
    """Run the categorization order over every non-user transaction (or just the given ids).

    Returns how many rows changed. Flags and display names set by rules are only ever set,
    never cleared, so a manual exclude survives the next sync. A rule's display_name only
    fills an empty one, so a name the user typed is kept.
    """
    loaded = _load_rules()
    memory = {m["merchant_key"]: m["cat_id"] for m in db.q("SELECT merchant_key, cat_id FROM merchant_memory")}
    known = {r["id"] for r in db.q("SELECT id FROM categories")}
    updates, matched_rules = [], set()
    for t in _rows(transaction_ids):
        cat = source = None
        excluded, transfer, display = int(t.get("excluded") or 0), int(t.get("is_transfer") or 0), t.get("display_name")
        for r, cond, act in loaded:
            if not match(cond, t):
                continue
            matched_rules.add(r["id"])
            if act.get("exclude"):
                excluded = 1
            if act.get("transfer"):
                transfer = 1
            if act.get("display_name") and not display:
                display = act["display_name"]
            if act.get("cat_id"):
                if act["cat_id"] in known:
                    cat, source = act["cat_id"], f"rule:{r['id']}"
                    break
                log.warning("rule %s points at unknown category %s and was ignored for the category", r["id"], act["cat_id"])
        if not cat:
            mk = merchant_key(t)
            if mk and memory.get(mk) in known:
                cat, source = memory[mk], "merchant"
        if not cat:
            code = t.get("category_detail") or t.get("category")
            if code:
                if code not in known:
                    categories.ensure(code)
                    known.add(code)
                cat, source = code, "plaid"
        if not cat:
            cat, source = categories.UNCAT, "none"
        before = (t.get("cat_id"), t.get("cat_source"), int(t.get("excluded") or 0), int(t.get("is_transfer") or 0), t.get("display_name"))
        if before != (cat, source, excluded, transfer, display):
            updates.append((cat, source, excluded, transfer, display, t["transaction_id"]))
    if updates:
        db.many("""UPDATE transactions SET cat_id=?, cat_source=?, excluded=?, is_transfer=?, display_name=?
                   WHERE transaction_id=? AND COALESCE(cat_source,'') != 'user'""", updates)
    db.run("""UPDATE rules SET hits = COALESCE(
                (SELECT c FROM (SELECT cat_source AS s, COUNT(*) AS c FROM transactions GROUP BY cat_source) WHERE s = 'rule:' || rules.id), 0)""")
    if matched_rules:
        db.many("UPDATE rules SET last_applied=datetime('now') WHERE id=?", [(rid,) for rid in matched_rules])
    log.info("categorized %s rows, %s rules matched", len(updates), len(matched_rules))
    return len(updates)


def missing_ids():
    return [r["transaction_id"] for r in db.q("SELECT transaction_id FROM transactions WHERE cat_id IS NULL")]


def similar_count(transaction_id, cat_id) -> int:
    """Other non-user transactions with the same merchant key whose category differs from cat_id."""
    t = db.one("SELECT merchant_name, name FROM transactions WHERE transaction_id=?", (transaction_id,))
    if not t:
        return 0
    key = merchant_key(t)
    if not key:
        return 0
    rows = db.q("""SELECT merchant_name, name, cat_id FROM transactions
                   WHERE transaction_id != ? AND COALESCE(cat_source,'') != 'user'""", (transaction_id,))
    return sum(1 for r in rows if merchant_key(r) == key and (r["cat_id"] or "") != cat_id)


def preview(conditions, limit=10):
    """Count non-user transactions matching the conditions, plus the newest few as a sample."""
    limit = max(1, min(int(limit), 50))
    rows = [t for t in _rows(None) if match(conditions, t)]
    rows.sort(key=lambda t: (t.get("date") or "", t["transaction_id"]), reverse=True)
    keys = ("transaction_id", "date", "amount", "name", "merchant_name", "display_name", "cat_id")
    return {"count": len(rows), "sample": [{k: t.get(k) for k in keys} for t in rows[:limit]]}


def remember(transaction_id, cat_id):
    """Record the user's choice for this merchant so future transactions follow it."""
    t = db.one("SELECT merchant_name, name FROM transactions WHERE transaction_id=?", (transaction_id,))
    key = merchant_key(t) if t else ""
    if key:
        db.run("INSERT INTO merchant_memory (merchant_key, cat_id, updated_at) VALUES (?,?, datetime('now')) "
               "ON CONFLICT(merchant_key) DO UPDATE SET cat_id=excluded.cat_id, updated_at=datetime('now')", (key, cat_id))
