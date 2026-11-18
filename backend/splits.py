"""Splits: one bank charge divided into lines, and parts of a charge owed back by a person.

A split transaction keeps its bank row untouched. Its lines carry the categories. A line can
instead name a person who owes that part. Paybacks record what they paid back, from a deposit
or in cash. Totals read the tx_lines view: one line per unsplit transaction, one per split line.
"""
import re
from datetime import datetime, timedelta, timezone

import categories
import db
import rules

CENT = 0.005
MAX_NAME = 40
RECENT_DAYS = 30
SHOWN = "COALESCE(NULLIF(t.display_name,''), NULLIF(t.merchant_name,''), t.name)"


class PaybackLinked(ValueError):
    """A change would drop an owed line that already has a payback."""


def _in(ids):
    return ",".join("?" * len(ids))


def _money(v) -> float:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        raise ValueError("Each line needs an amount")


def clean_person(raw) -> str:
    name = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not name:
        raise ValueError("Enter who owes this part")
    if len(name) > MAX_NAME:
        raise ValueError(f"A name is longer than {MAX_NAME} characters")
    return name


def lines(transaction_id) -> list:
    return db.q("SELECT id, seq, amount, cat_id, owed_by, note FROM splits WHERE transaction_id=? ORDER BY seq, id",
                (transaction_id,))


def _paid(split_id) -> float:
    return round(db.one("SELECT COALESCE(SUM(amount),0) AS n FROM paybacks WHERE split_id=?", (split_id,))["n"], 2)


def _clean_lines(t, raw_lines) -> list:
    if not isinstance(raw_lines, list) or len(raw_lines) < 2:
        raise ValueError("A split needs at least two lines")
    out = []
    for raw in raw_lines:
        amount = _money(raw.get("amount"))
        cat = raw.get("cat_id") or None
        who = clean_person(raw["owed_by"]) if str(raw.get("owed_by") or "").strip() else None
        if bool(cat) == bool(who):
            raise ValueError("Each line needs a category or a person, not both")
        if cat and not categories.get(cat):
            raise ValueError("Unknown category")
        if abs(amount) < CENT:
            raise ValueError("A line can't be $0.00")
        if who and ((t["amount"] or 0) <= 0 or amount <= 0):
            raise ValueError("Only money you spent can be owed back")
        out.append({"amount": amount, "cat_id": cat, "owed_by": who, "note": str(raw.get("note") or "").strip() or None})
    total, want = round(sum(l["amount"] for l in out), 2), round(t["amount"] or 0, 2)
    if abs(total - want) > CENT:
        raise ValueError(f"The lines add up to ${abs(total):,.2f}, not ${abs(want):,.2f}")
    return out


def save(transaction_id, raw_lines) -> list:
    """Replace every line of a transaction. An owed line that has paybacks must stay, same person and amount."""
    t = db.one("SELECT amount, pending FROM transactions WHERE transaction_id=?", (transaction_id,))
    if not t:
        raise LookupError("Transaction not found")
    if t["pending"]:
        raise ValueError("A pending charge can't be split. Wait until it posts.")
    if db.one("SELECT 1 FROM transfers WHERE out_id=? OR in_id=?", (transaction_id, transaction_id)):
        raise ValueError("This is a transfer. Unlink it before splitting.")
    new = _clean_lines(t, raw_lines)
    for old in lines(transaction_id):
        if not old["owed_by"] or _paid(old["id"]) < CENT:
            continue
        keep = next((n for n in new if "id" not in n and n["owed_by"] and n["owed_by"].lower() == old["owed_by"].lower()
                     and abs(n["amount"] - old["amount"]) < CENT), None)
        if not keep:
            raise PaybackLinked(f"{old['owed_by']}'s part has a payback linked. Keep that line, or unlink the payback first.")
        keep["id"] = old["id"]
    kept = [n["id"] for n in new if "id" in n]
    if kept:
        db.run(f"DELETE FROM splits WHERE transaction_id=? AND id NOT IN ({_in(kept)})", [transaction_id, *kept])
    else:
        db.run("DELETE FROM splits WHERE transaction_id=?", (transaction_id,))
    for seq, n in enumerate(new, 1):
        if "id" in n:
            db.run("UPDATE splits SET seq=?, owed_by=?, note=? WHERE id=?", (seq, n["owed_by"], n["note"], n["id"]))
        else:
            db.run("INSERT INTO splits (transaction_id, seq, amount, cat_id, owed_by, note) VALUES (?,?,?,?,?,?)",
                   (transaction_id, seq, n["amount"], n["cat_id"], n["owed_by"], n["note"]))
    prune()
    return lines(transaction_id)


def unsplit(transaction_id, force=False):
    """Remove every line. Refuses when a payback is linked, unless forced, which removes the paybacks too."""
    ids = [l["id"] for l in lines(transaction_id)]
    if not ids:
        return
    if not force and db.one(f"SELECT COUNT(*) AS n FROM paybacks WHERE split_id IN ({_in(ids)})", ids)["n"]:
        raise PaybackLinked("A payback is linked to this split. Unsplitting removes it.")
    db.run("DELETE FROM splits WHERE transaction_id=?", (transaction_id,))
    prune()
    rules.categorize([transaction_id])


def prune():
    """Drop lines of transactions that are gone, and paybacks or dismissals that point at something gone."""
    db.run("DELETE FROM splits WHERE transaction_id NOT IN (SELECT transaction_id FROM transactions)")
    db.run("DELETE FROM paybacks WHERE split_id NOT IN (SELECT id FROM splits)")
    db.run("DELETE FROM paybacks WHERE payment_id IS NOT NULL AND payment_id NOT IN (SELECT transaction_id FROM transactions)")
    db.run("""DELETE FROM payback_dismissed WHERE split_id NOT IN (SELECT id FROM splits)
              OR payment_id NOT IN (SELECT transaction_id FROM transactions)""")


def check(transaction_ids) -> list:
    """Send split transactions whose lines no longer add up back to the review box. Returns their ids."""
    off = []
    for tid in dict.fromkeys(transaction_ids or []):
        t = db.one("SELECT amount FROM transactions WHERE transaction_id=?", (tid,))
        ls = lines(tid)
        if t and ls and abs(round(sum(l["amount"] for l in ls), 2) - round(t["amount"] or 0, 2)) > CENT:
            off.append(tid)
    if off:
        db.many("UPDATE transactions SET reviewed=0 WHERE transaction_id=?", [(i,) for i in off])
    return off


def for_transactions(transaction_ids) -> dict:
    """{transaction_id: [line]} for the given ids. Each line has its paid-back sum and a display amount."""
    ids, out = list(dict.fromkeys(transaction_ids)), {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows = db.q(f"""SELECT s.id, s.transaction_id, s.amount, s.cat_id, s.owed_by,
                               COALESCE((SELECT SUM(p.amount) FROM paybacks p WHERE p.split_id=s.id),0) AS paid
                        FROM splits s WHERE s.transaction_id IN ({_in(chunk)}) ORDER BY s.seq, s.id""", chunk)
        for r in rows:
            r["paid"] = round(r["paid"], 2)
            r["display_amount"] = -r["amount"]
            out.setdefault(r.pop("transaction_id"), []).append(r)
    return out


def off_by(amount, line_list):
    """How far the lines are from the bank amount, or None when they add up."""
    if not line_list:
        return None
    diff = round(abs((amount or 0) - sum(l["amount"] for l in line_list)), 2)
    return diff if diff > CENT else None


def payback_names(transaction_ids) -> dict:
    """{deposit id: "Sam and Alex"} for deposits linked as paybacks."""
    ids, names = list(dict.fromkeys(transaction_ids)), {}
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        for r in db.q(f"""SELECT p.payment_id, s.owed_by FROM paybacks p JOIN splits s ON s.id=p.split_id
                          WHERE p.payment_id IN ({_in(chunk)}) ORDER BY p.id""", chunk):
            got = names.setdefault(r["payment_id"], [])
            if r["owed_by"].lower() not in (n.lower() for n in got):
                got.append(r["owed_by"])
    return {k: (v[0] if len(v) == 1 else ", ".join(v[:-1]) + " and " + v[-1]) for k, v in names.items()}


# ---------- money owed back ----------

def _owed_line(split_id) -> dict:
    r = db.one("""SELECT s.id, s.amount, s.owed_by, t.date FROM splits s JOIN transactions t ON t.transaction_id=s.transaction_id
                  WHERE s.id=? AND s.owed_by IS NOT NULL""", (split_id,))
    if not r:
        raise LookupError("Owed item not found")
    r["open"] = round(r["amount"] - _paid(split_id), 2)
    return r


def _deposits(since) -> list:
    """Posted deposits on or after a date that still have money left to link, newest first."""
    rows = db.q(f"""SELECT t.transaction_id, t.date, -t.amount AS amount, {SHOWN} AS name,
                           COALESCE((SELECT SUM(p.amount) FROM paybacks p WHERE p.payment_id=t.transaction_id),0) AS used
                    FROM transactions t WHERE t.amount<0 AND COALESCE(t.pending,0)=0 AND t.date>=?
                      AND t.transaction_id NOT IN (SELECT out_id FROM transfers UNION ALL SELECT in_id FROM transfers)
                    ORDER BY t.date DESC, t.transaction_id""", (since,))
    for r in rows:
        r["amount"] = round(r["amount"], 2)
        r["left"] = round(r["amount"] - r.pop("used"), 2)
    return [r for r in rows if r["left"] > CENT]


def _paybacks(split_ids) -> dict:
    out = {}
    for i in range(0, len(split_ids), 500):
        chunk = split_ids[i:i + 500]
        for r in db.q(f"""SELECT p.id, p.split_id, p.amount, p.cash, p.payment_id, t.date, {SHOWN} AS name
                          FROM paybacks p LEFT JOIN transactions t ON t.transaction_id=p.payment_id
                          WHERE p.split_id IN ({_in(chunk)}) ORDER BY p.id""", chunk):
            out.setdefault(r.pop("split_id"), []).append(r)
    return out


def owed() -> dict:
    """Open owed items by person, the total, suggestions, items paid back lately, and every name used."""
    rows = db.q(f"""SELECT s.id AS split_id, s.transaction_id, s.amount, s.owed_by, t.date, {SHOWN} AS merchant,
                           COALESCE((SELECT SUM(p.amount) FROM paybacks p WHERE p.split_id=s.id),0) AS paid,
                           (SELECT MAX(p.created_at) FROM paybacks p WHERE p.split_id=s.id) AS last_paid
                    FROM splits s JOIN transactions t ON t.transaction_id=s.transaction_id
                    WHERE s.owed_by IS NOT NULL ORDER BY t.date, s.id""")
    names = {}
    for r in rows:
        names.setdefault(r["owed_by"].lower(), r["owed_by"])  # a person shows as first written
        r["owed_by"] = names[r["owed_by"].lower()]
        r["paid"] = round(r["paid"], 2)
        r["open"] = round(r["amount"] - r["paid"], 2)
    open_rows = [r for r in rows if r["open"] > CENT]
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    recent = [r for r in rows if r["open"] <= CENT and (r["last_paid"] or "") >= cutoff]
    pays = _paybacks([r["split_id"] for r in open_rows + recent])
    keys = ("split_id", "transaction_id", "date", "merchant", "owed_by", "amount", "paid", "open")

    def item(r):
        return {**{k: r[k] for k in keys}, "paybacks": pays.get(r["split_id"], [])}

    people = {}
    for r in open_rows:
        p = people.setdefault(r["owed_by"], {"name": r["owed_by"], "total": 0.0, "items": []})
        p["total"] = round(p["total"] + r["open"], 2)
        p["items"].append(item(r))
    return {"total": round(sum(r["open"] for r in open_rows), 2),
            "people": sorted(people.values(), key=lambda p: (-p["total"], p["name"].lower())),
            "recent": [item(r) for r in sorted(recent, key=lambda r: r["last_paid"] or "", reverse=True)],
            "suggestions": suggestions(open_rows),
            "names": sorted(names.values(), key=str.lower)}


def suggestions(open_rows) -> list:
    """Deposits whose amount left equals an open item's amount, dated on or after it. Each deposit and item used once."""
    if not open_rows:
        return []
    dismissed = {(d["split_id"], d["payment_id"]) for d in db.q("SELECT split_id, payment_id FROM payback_dismissed")}
    deposits = sorted(_deposits(min(r["date"] for r in open_rows)), key=lambda d: (d["date"], d["transaction_id"]))
    used, out = set(), []
    for r in open_rows:
        for d in deposits:
            if d["transaction_id"] in used or d["date"] < r["date"] or (r["split_id"], d["transaction_id"]) in dismissed:
                continue
            if abs(d["left"] - r["open"]) <= CENT:
                used.add(d["transaction_id"])
                out.append({"split_id": r["split_id"], "payment_id": d["transaction_id"], "payment_name": d["name"],
                            "payment_date": d["date"], "amount": r["open"], "owed_by": r["owed_by"], "merchant": r["merchant"]})
                break
    return out


def payments(split_id) -> list:
    """Deposits that can pay this item, newest first."""
    return _deposits(_owed_line(split_id)["date"])[:50]


def link(split_id, payment_id=None, cash=False) -> dict:
    """Record a payback. A deposit pays up to what is open on the item; the rest of it stays free for other items."""
    item = _owed_line(split_id)
    if item["open"] <= CENT:
        raise ValueError("This is already paid back")
    if cash:
        amount, payment_id = item["open"], None
    else:
        d = next((x for x in _deposits(item["date"]) if x["transaction_id"] == payment_id), None)
        if not d:
            raise ValueError("That payment can't be linked. It may be used up, pending, or dated before the charge.")
        amount = min(item["open"], d["left"])
    pid = db.run("INSERT INTO paybacks (split_id, payment_id, amount, cash) VALUES (?,?,?,?)",
                 (split_id, payment_id, round(amount, 2), 1 if cash else 0)).lastrowid
    return db.one("SELECT * FROM paybacks WHERE id=?", (pid,))


def unlink(payback_id):
    if not db.one("SELECT 1 FROM paybacks WHERE id=?", (payback_id,)):
        raise LookupError("Payback not found")
    db.run("DELETE FROM paybacks WHERE id=?", (payback_id,))


def dismiss(split_id, payment_id):
    """Hide one suggested pairing for good."""
    _owed_line(split_id)
    db.run("INSERT OR IGNORE INTO payback_dismissed (split_id, payment_id) VALUES (?,?)", (split_id, payment_id))
