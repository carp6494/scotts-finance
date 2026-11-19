"""Money moving between the owner's own accounts.

A pair is a row where money left one account and a row where the same amount arrived on another,
at most WINDOW days apart. detect() links a pair only when neither row has any other candidate.
A row with other candidates is a question shown on the page. A pair the owner unlinked or turned
down is never linked again, and a row in such a pair is never linked on its own again.
"""
import logging
from datetime import date

import categories
import db
import rules

log = logging.getLogger("finance.transfers")

WINDOW = 3
CARD = "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"
OUT_CAT = "TRANSFER_OUT_ACCOUNT_TRANSFER"
IN_CAT = "TRANSFER_IN_ACCOUNT_TRANSFER"
PAIRED = "SELECT out_id FROM transfers UNION ALL SELECT in_id FROM transfers"


def _in(ids):
    return ",".join("?" * len(ids))


def cents(v) -> int:
    return round(abs(v or 0) * 100)


def days_apart(a, b) -> int:
    """Whole days between two YYYY-MM-DD dates. A missing date counts as far apart."""
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except (TypeError, ValueError):
        return 10 ** 6


def _eligible(ids=None) -> list:
    """Rows that may be one side of a transfer: posted, not split, not excluded, not paired, not a payback deposit,
    and not filed under Cash and ATM. Cash in or out at a machine is never a move between your own accounts."""
    sql = f"""SELECT t.transaction_id, t.account_id, t.date, t.amount FROM transactions t
              WHERE COALESCE(t.pending,0)=0 AND COALESCE(t.excluded,0)=0 AND t.amount != 0
                AND COALESCE((SELECT c.group_name FROM categories c WHERE c.id=t.cat_id),'') != '{categories.CASH_GROUP}'
                AND t.transaction_id NOT IN (SELECT transaction_id FROM splits)
                AND t.transaction_id NOT IN ({PAIRED})
                AND t.transaction_id NOT IN (SELECT payment_id FROM paybacks WHERE payment_id IS NOT NULL)"""
    if ids is None:
        return db.q(sql)
    ids = list(ids)
    return db.q(f"{sql} AND t.transaction_id IN ({_in(ids)})", ids) if ids else []


def _dismissed() -> set:
    return {(r["out_id"], r["in_id"]) for r in db.q("SELECT out_id, in_id FROM transfer_dismissed")}


def candidates(rows=None) -> dict:
    """{transaction_id: [partner ids]} for every eligible row that has at least one candidate."""
    rows = _eligible() if rows is None else rows
    dismissed = _dismissed()
    outs, ins = {}, {}
    for r in rows:
        (outs if r["amount"] > 0 else ins).setdefault(cents(r["amount"]), []).append(r)
    found = {}
    for key, out_rows in outs.items():
        for o in out_rows:
            for i in ins.get(key, []):
                if (i["account_id"] != o["account_id"] and days_apart(o["date"], i["date"]) <= WINDOW
                        and (o["transaction_id"], i["transaction_id"]) not in dismissed):
                    found.setdefault(o["transaction_id"], []).append(i["transaction_id"])
                    found.setdefault(i["transaction_id"], []).append(o["transaction_id"])
    return found


def _link(out_id, in_id, source):
    """Store a pair, flag both rows, and swap a category the app picked for a transfer one."""
    db.run("INSERT INTO transfers (out_id, in_id, source) VALUES (?,?,?)", (out_id, in_id, source))
    db.run("UPDATE transactions SET is_transfer=1 WHERE transaction_id IN (?,?)", (out_id, in_id))
    acct = db.one("SELECT a.type FROM transactions t JOIN accounts a ON a.account_id=t.account_id WHERE t.transaction_id=?", (in_id,))
    to_card = bool(acct) and acct["type"] == "credit"
    for tid, code in ((out_id, CARD if to_card else OUT_CAT), (in_id, CARD if to_card else IN_CAT)):
        db.run("""UPDATE transactions SET cat_id=?, cat_source='transfer'
                  WHERE transaction_id=? AND COALESCE(cat_source,'') != 'user'
                    AND COALESCE((SELECT c.type FROM categories c WHERE c.id=transactions.cat_id),'expense') != 'transfer'""",
               (categories.ensure(code), tid))


def detect() -> int:
    """Link every clear pair. Returns how many were linked."""
    rows = _eligible()
    out_side = {r["transaction_id"] for r in rows if r["amount"] > 0}
    found = candidates(rows)
    touched = {x for pair in _dismissed() for x in pair}
    n = 0
    for tid, partners in found.items():
        if tid not in out_side or len(partners) != 1:
            continue
        other = partners[0]
        if found.get(other) == [tid] and tid not in touched and other not in touched:
            _link(tid, other, "auto")
            n += 1
    if n:
        log.info("linked %s transfers", n)
    return n


def link(a, b) -> dict:
    """Link two rows by hand, in either order. They must qualify as a pair, but other candidates are fine."""
    if a == b:
        raise ValueError("Pick two different transactions.")
    for tid in (a, b):
        if not db.one("SELECT 1 FROM transactions WHERE transaction_id=?", (tid,)):
            raise LookupError("Transaction not found")
    rows = {r["transaction_id"]: r for r in _eligible([a, b])}
    if len(rows) < 2:
        raise ValueError("That can't be a transfer. One of them is pending, split, excluded, already linked, or a payback.")
    o, i = (rows[a], rows[b]) if rows[a]["amount"] > 0 else (rows[b], rows[a])
    if not (o["amount"] > 0 > i["amount"]) or cents(o["amount"]) != cents(i["amount"]):
        raise ValueError("A transfer is money out of one account and the same amount into another.")
    if o["account_id"] == i["account_id"]:
        raise ValueError("Both are on the same account.")
    if days_apart(o["date"], i["date"]) > WINDOW:
        raise ValueError(f"They are more than {WINDOW} days apart.")
    db.run("DELETE FROM transfer_dismissed WHERE out_id=? AND in_id=?", (o["transaction_id"], i["transaction_id"]))
    _link(o["transaction_id"], i["transaction_id"], "user")
    return {"out_id": o["transaction_id"], "in_id": i["transaction_id"]}


def _release(pairs):
    """Drop pairs and send their rows back to the categorizer, as if they had never been linked."""
    if not pairs:
        return
    ids = [x for p in pairs for x in (p["out_id"], p["in_id"])]
    db.many("DELETE FROM transfers WHERE out_id=?", [(p["out_id"],) for p in pairs])
    db.run(f"UPDATE transactions SET is_transfer=0 WHERE transaction_id IN ({_in(ids)})", ids)
    db.run(f"UPDATE transactions SET cat_source=NULL WHERE cat_source='transfer' AND transaction_id IN ({_in(ids)})", ids)
    rules.categorize(ids)


def unlink(transaction_id) -> dict:
    """Undo the pair holding this row and remember it, so it is never linked again."""
    p = db.one("SELECT out_id, in_id FROM transfers WHERE out_id=? OR in_id=?", (transaction_id, transaction_id))
    if not p:
        raise LookupError("This transaction is not linked as a transfer")
    db.run("INSERT OR IGNORE INTO transfer_dismissed (out_id, in_id) VALUES (?,?)", (p["out_id"], p["in_id"]))
    _release([p])
    return p


def dismiss(transaction_id) -> int:
    """Not a transfer: turn down every current candidate for this row. Returns how many."""
    if not db.one("SELECT 1 FROM transactions WHERE transaction_id=?", (transaction_id,)):
        raise LookupError("Transaction not found")
    rows = _eligible()
    me = next((r for r in rows if r["transaction_id"] == transaction_id), None)
    if not me:
        return 0
    partners = candidates(rows).get(transaction_id, [])
    pairs = [(transaction_id, p) if me["amount"] > 0 else (p, transaction_id) for p in partners]
    db.many("INSERT OR IGNORE INTO transfer_dismissed (out_id, in_id) VALUES (?,?)", pairs)
    return len(pairs)


def for_transactions(ids) -> dict:
    """{id: {"transfer": {id, account, dir}}} for linked rows, {id: {"options": [...]}} for rows with candidates."""
    want = set(ids)
    if not want:
        return {}
    linked = [p for p in db.q("SELECT out_id, in_id FROM transfers") if p["out_id"] in want or p["in_id"] in want]
    found = candidates()
    others = {x for p in linked for x in (p["out_id"], p["in_id"])} | {x for tid in want for x in found.get(tid, [])}
    info = {}
    if others:
        o = list(others)
        info = {r["transaction_id"]: r for r in db.q(f"""SELECT t.transaction_id, t.date, t.amount, a.name AS account
                    FROM transactions t LEFT JOIN accounts a ON a.account_id=t.account_id
                    WHERE t.transaction_id IN ({_in(o)})""", o)}

    def name(tid):
        return (info.get(tid) or {}).get("account") or "another account"

    out = {}
    for p in linked:
        for me, other, way in ((p["out_id"], p["in_id"], "to"), (p["in_id"], p["out_id"], "from")):
            if me in want:
                out[me] = {"transfer": {"id": other, "account": name(other), "dir": way}}
    for tid in want:
        opts = [{"id": x, "account": name(x), "date": info[x]["date"], "display_amount": -info[x]["amount"]}
                for x in found.get(tid, []) if x in info]
        if opts:
            out.setdefault(tid, {})["options"] = sorted(opts, key=lambda v: (v["date"], v["id"]))
    return out


def prune() -> int:
    """Drop pairs whose rows are gone or no longer match. A dropped pair is not dismissed, so detect() may link it again."""
    rows = db.q("""SELECT p.out_id, p.in_id, o.amount AS oa, o.date AS od, o.account_id AS oacc,
                          i.amount AS ia, i.date AS idt, i.account_id AS iacc
                   FROM transfers p LEFT JOIN transactions o ON o.transaction_id=p.out_id
                   LEFT JOIN transactions i ON i.transaction_id=p.in_id""")
    bad = [r for r in rows if r["oa"] is None or r["ia"] is None or not (r["oa"] > 0 > r["ia"])
           or cents(r["oa"]) != cents(r["ia"]) or r["oacc"] == r["iacc"] or days_apart(r["od"], r["idt"]) > WINDOW]
    _release(bad)
    db.run("""DELETE FROM transfer_dismissed WHERE out_id NOT IN (SELECT transaction_id FROM transactions)
              OR in_id NOT IN (SELECT transaction_id FROM transactions)""")
    return len(bad)
