# Transfers and duplicates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Link money that moves between the owner's own accounts so neither side counts as spending or income, and stop a CSV import from adding rows the account already has.

**Architecture:** A new module, `backend/transfers.py`, finds pairs, links clear ones, and answers questions about a page of rows. Two tables hold pairs and turned-down pairs. The existing `is_transfer` flag keeps doing the work in totals. The categorizer, splits, and the Owed box learn to step around linked rows. The CSV import gets a near-match check. The row list shows a pill for a linked row and a question line for an unclear one.

**Tech Stack:** FastAPI, SQLite, pytest, React 19, Vite.

Spec: `docs/superpowers/specs/2026-11-16-transfers-duplicates-design.md`.

Commits: none until Scott says so. Before that commit, check the staged list. The repo is public: tests and docs use made-up account names and amounts only.

Test command, from the project root: `.venv\Scripts\python -m pytest backend/tests -q`. It passes 190 tests before this work.

---

## File map

- Create `backend/transfers.py`: matching, linking, unlinking, dismissing, page info, pruning.
- Create `backend/tests/test_transfers.py` and `backend/tests/test_import.py`.
- Modify `backend/db.py`: two tables.
- Modify `backend/tests/conftest.py`: empty the two tables in `fresh`.
- Modify `backend/rules.py`: skip linked rows.
- Modify `backend/splits.py`: refuse to split a linked row; never offer a linked deposit as a payback.
- Modify `backend/plaid_sync.py`: prune and detect after a sync; prune after an item is removed.
- Modify `backend/app.py`: startup hook, three routes, two row fields, CSV near-match check.
- Modify `frontend/src/api.js`, `frontend/src/components/TxList.jsx`.
- Modify `docs/ARCHITECTURE.md`, `README.md`.

---

### Task 1: Tables

**Files:**
- Modify: `backend/db.py`, the end of `SCHEMA`, after `payback_dismissed`
- Modify: `backend/tests/conftest.py`, the `fresh` fixture

- [ ] **Step 1: Add the tables to `SCHEMA`**

Insert after the `payback_dismissed` table, before the closing `"""`:

```sql
CREATE TABLE IF NOT EXISTS transfers (
  out_id TEXT PRIMARY KEY,
  in_id TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL DEFAULT 'auto',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS transfer_dismissed (
  out_id TEXT NOT NULL,
  in_id TEXT NOT NULL,
  PRIMARY KEY (out_id, in_id)
);
```

- [ ] **Step 2: Empty them in tests**

In `fresh`, the table tuple gains `"transfers", "transfer_dismissed"` after `"payback_dismissed"`.

- [ ] **Step 3: Run the suite**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: 190 passed.

---

### Task 2: Find and link clear pairs

**Files:**
- Create: `backend/transfers.py`
- Create: `backend/tests/test_transfers.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_transfers.py`:

```python
"""Transfers between the owner's own accounts: finding pairs, linking, unlinking, and what the bank does to them."""
import os
from datetime import date

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import rules  # noqa: E402
import splits  # noqa: E402
import transfers  # noqa: E402
from conftest import add_tx  # noqa: E402

HARDWARE = "HOME_IMPROVEMENT_HARDWARE"
CARD_PAY = "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"
FOOD = "FOOD_AND_DRINK_RESTAURANT"
INCOME = "INCOME_OTHER_INCOME"


@pytest.fixture
def own(fresh):
    """Three accounts of the owner's: checking, a credit card, savings."""
    for aid, name, typ in (("chk", "Checking", "depository"), ("card", "Travel Card", "credit"), ("sav", "Savings", "depository")):
        db.run("INSERT INTO accounts (account_id, name, type) VALUES (?,?,?)", (aid, name, typ))
    return db


def payment(out="p-out", inn="p-in", amount=50.0, out_date="2026-11-05", in_date="2026-11-06"):
    """Checking pays the card. The bank filed the checking side as a hardware purchase."""
    add_tx(out, amount=amount, account="chk", date=out_date, cat_id=HARDWARE, detail=HARDWARE, source="plaid")
    add_tx(inn, amount=-amount, account="card", date=in_date, cat_id=CARD_PAY, detail=CARD_PAY, source="plaid")


def row(tid):
    return db.one("SELECT cat_id, cat_source, is_transfer FROM transactions WHERE transaction_id=?", (tid,))


def test_clear_pair_links_and_fixes_a_picked_category(own):
    payment()
    assert transfers.detect() == 1
    assert row("p-out") == {"cat_id": CARD_PAY, "cat_source": "transfer", "is_transfer": 1}
    assert row("p-in") == {"cat_id": CARD_PAY, "cat_source": "plaid", "is_transfer": 1}
    assert db.one("SELECT out_id, in_id, source FROM transfers") == {"out_id": "p-out", "in_id": "p-in", "source": "auto"}
    assert transfers.detect() == 0


def test_between_bank_accounts_uses_account_transfer(own):
    add_tx("o", amount=200.0, account="chk", cat_id=FOOD)
    add_tx("i", amount=-200.0, account="sav", cat_id=INCOME)
    assert transfers.detect() == 1
    assert row("o")["cat_id"] == "TRANSFER_OUT_ACCOUNT_TRANSFER"
    assert row("i")["cat_id"] == "TRANSFER_IN_ACCOUNT_TRANSFER"


def test_category_set_by_hand_is_kept(own):
    payment()
    db.run("UPDATE transactions SET cat_source='user' WHERE transaction_id='p-out'")
    transfers.detect()
    assert row("p-out") == {"cat_id": HARDWARE, "cat_source": "user", "is_transfer": 1}


def test_three_days_apart_still_links(own):
    payment(out_date="2026-11-01", in_date="2026-11-04")
    assert transfers.detect() == 1


def test_no_link_when_too_far_one_account_or_a_cent_off(own):
    payment("a1", "a2", out_date="2026-11-01", in_date="2026-11-05")
    add_tx("b1", amount=30.0, account="chk")
    add_tx("b2", amount=-30.0, account="chk")
    add_tx("c1", amount=20.0, account="chk")
    add_tx("c2", amount=-20.01, account="card")
    assert transfers.detect() == 0
    assert transfers.candidates() == {}


def test_two_candidates_wait_for_the_owner(own):
    payment("o1", "i1")
    add_tx("i2", amount=-50.0, account="sav", date="2026-11-05")
    assert transfers.detect() == 0
    assert sorted(transfers.candidates()["o1"]) == ["i1", "i2"]


def test_pending_split_excluded_and_payback_rows_are_skipped(own):
    payment("s-out", "s-in", amount=40.0)
    splits.save("s-out", [{"cat_id": HARDWARE, "amount": 20}, {"cat_id": FOOD, "amount": 20}])
    payment("x-out", "x-in", amount=41.0)
    db.run("UPDATE transactions SET excluded=1 WHERE transaction_id='x-out'")
    payment("n-out", "n-in", amount=42.0)
    db.run("UPDATE transactions SET pending=1 WHERE transaction_id='n-in'")
    add_tx("d", amount=74.0, account="card", cat_id=FOOD)
    splits.save("d", [{"cat_id": FOOD, "amount": 37}, {"owed_by": "Sam", "amount": 37}])
    sid = next(l["id"] for l in splits.lines("d") if l["owed_by"])
    add_tx("v", amount=-37.0, account="chk", date="2026-11-06", cat_id=INCOME)
    splits.link(sid, payment_id="v")
    add_tx("v-out", amount=37.0, account="sav", date="2026-11-06")
    assert transfers.detect() == 0


def test_spending_total_leaves_out_both_sides(own):
    month = date.today().strftime("%Y-%m")
    payment(out_date=f"{month}-01", in_date=f"{month}-02")
    assert app.summary()["spent_month"] == 50.0
    transfers.detect()
    assert app.summary()["spent_month"] == 0.0
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_transfers.py -q`
Expected: errors with `ModuleNotFoundError: No module named 'transfers'`.

- [ ] **Step 3: Write the module**

`backend/transfers.py`:

```python
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
    """Rows that may be one side of a transfer: posted, not split, not excluded, not paired, not a payback deposit."""
    sql = f"""SELECT t.transaction_id, t.account_id, t.date, t.amount FROM transactions t
              WHERE COALESCE(t.pending,0)=0 AND COALESCE(t.excluded,0)=0 AND t.amount != 0
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest backend/tests/test_transfers.py -q`
Expected: 8 passed.

---

### Task 3: Link by hand, unlink, dismiss, and page info

**Files:**
- Modify: `backend/transfers.py`, append
- Modify: `backend/tests/test_transfers.py`, append

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_transfers.py`:

```python
def page():
    return {r["transaction_id"]: r for r in app.transactions()["rows"]}


def test_options_name_the_other_account(own):
    payment("o1", "i1")
    add_tx("i2", amount=-50.0, account="sav", date="2026-11-05")
    info = transfers.for_transactions(["o1", "i1"])
    assert [o["id"] for o in info["o1"]["options"]] == ["i2", "i1"]
    first = info["o1"]["options"][1]
    assert first == {"id": "i1", "account": "Travel Card", "date": "2026-11-06", "display_amount": 50.0}
    assert [o["id"] for o in info["i1"]["options"]] == ["o1"]
    assert "transfer" not in info["o1"]


def test_link_by_hand_unlink_and_dismiss(own):
    payment("o1", "i1")
    add_tx("i2", amount=-50.0, account="sav", date="2026-11-05")
    assert transfers.link("i1", "o1") == {"out_id": "o1", "in_id": "i1"}
    info = transfers.for_transactions(["o1", "i1", "i2"])
    assert info["o1"] == {"transfer": {"id": "i1", "account": "Travel Card", "dir": "to"}}
    assert info["i1"] == {"transfer": {"id": "o1", "account": "Checking", "dir": "from"}}
    assert "i2" not in info
    assert db.one("SELECT source FROM transfers")["source"] == "user"

    transfers.unlink("i1")
    assert db.q("SELECT out_id FROM transfers") == []
    assert transfers.detect() == 0  # o1 now has one candidate, i2, but the owner already weighed in on o1
    assert [o["id"] for o in transfers.for_transactions(["o1"])["o1"]["options"]] == ["i2"]

    assert transfers.dismiss("o1") == 1
    assert transfers.for_transactions(["o1", "i2"]) == {}


def test_link_by_hand_checks_the_pair(own):
    payment()
    add_tx("far", amount=-50.0, account="sav", date="2026-12-01")
    add_tx("same", amount=-50.0, account="chk", date="2026-11-05")
    with pytest.raises(LookupError):
        transfers.link("p-out", "nope")
    with pytest.raises(ValueError, match="days apart"):
        transfers.link("p-out", "far")
    with pytest.raises(ValueError, match="same account"):
        transfers.link("p-out", "same")
    with pytest.raises(ValueError, match="different"):
        transfers.link("p-out", "p-out")


def test_unlink_sends_rows_back_through_the_categorizer(own):
    payment()
    transfers.detect()
    transfers.unlink("p-out")
    assert row("p-out") == {"cat_id": HARDWARE, "cat_source": "plaid", "is_transfer": 0}
    assert row("p-in")["is_transfer"] == 0
    with pytest.raises(LookupError):
        transfers.unlink("p-out")


def test_rows_on_the_page_carry_transfer_fields(own):
    payment()
    transfers.detect()
    rows = page()
    assert rows["p-out"]["transfer"] == {"id": "p-in", "account": "Travel Card", "dir": "to"}
    assert rows["p-out"]["transfer_options"] == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_transfers.py -q`
Expected: the new tests fail with `AttributeError: module 'transfers' has no attribute 'for_transactions'`, and `test_rows_on_the_page_carry_transfer_fields` fails with `KeyError: 'transfer'`. That last one passes after Task 5.

- [ ] **Step 3: Append the functions**

Append to `backend/transfers.py`:

```python
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest backend/tests/test_transfers.py -q`
Expected: all pass except `test_rows_on_the_page_carry_transfer_fields`, which waits for Task 5.

---

### Task 4: The categorizer, splits, and the Owed box step around linked rows

**Files:**
- Modify: `backend/rules.py`, `_rows` and the UPDATE in `categorize`
- Modify: `backend/splits.py`, `save` and `_deposits`
- Modify: `backend/tests/test_transfers.py`, append

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_transfers.py`:

```python
def test_categorize_leaves_linked_rows_alone(own):
    payment()
    transfers.detect()
    rules.categorize()
    assert row("p-out") == {"cat_id": CARD_PAY, "cat_source": "transfer", "is_transfer": 1}


def test_split_refuses_a_linked_row(own):
    payment()
    transfers.detect()
    with pytest.raises(ValueError, match="Unlink it before splitting"):
        splits.save("p-out", [{"cat_id": HARDWARE, "amount": 25}, {"cat_id": FOOD, "amount": 25}])


def test_linked_deposit_is_not_offered_as_a_payback(own):
    add_tx("d", amount=100.0, account="card", cat_id=FOOD, date="2026-11-04")
    splits.save("d", [{"cat_id": FOOD, "amount": 50}, {"owed_by": "Sam", "amount": 50}])
    sid = next(l["id"] for l in splits.lines("d") if l["owed_by"])
    payment()
    assert any(p["transaction_id"] == "p-in" for p in splits.payments(sid))
    transfers.detect()
    assert all(p["transaction_id"] != "p-in" for p in splits.payments(sid))
    assert splits.owed()["suggestions"] == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_transfers.py -q -k "alone or refuses or payback"`
Expected: 3 failed.

- [ ] **Step 3: Skip linked rows in `rules.py`**

In `_rows`, the base WHERE becomes:

```python
            "WHERE COALESCE(cat_source,'') != 'user' AND transaction_id NOT IN (SELECT transaction_id FROM splits) "
            "AND transaction_id NOT IN (SELECT out_id FROM transfers UNION ALL SELECT in_id FROM transfers)")
```

The UPDATE in `categorize` gains the same clause on its last line:

```python
                   AND transaction_id NOT IN (SELECT transaction_id FROM splits)
                   AND transaction_id NOT IN (SELECT out_id FROM transfers UNION ALL SELECT in_id FROM transfers)""", updates)
```

Add one line to the module docstring: "A row linked as a transfer is skipped: the link set its category."

- [ ] **Step 4: Refuse in `splits.save`**

After the pending check in `save`:

```python
    if db.one("SELECT 1 FROM transfers WHERE out_id=? OR in_id=?", (transaction_id, transaction_id)):
        raise ValueError("This is a transfer. Unlink it before splitting.")
```

- [ ] **Step 5: Leave linked deposits out of `_deposits`**

The WHERE in `_deposits` becomes:

```python
                    FROM transactions t WHERE t.amount<0 AND COALESCE(t.pending,0)=0 AND t.date>=?
                      AND t.transaction_id NOT IN (SELECT out_id FROM transfers UNION ALL SELECT in_id FROM transfers)
```

- [ ] **Step 6: Run the suite**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass except `test_rows_on_the_page_carry_transfer_fields`.

---

### Task 5: Prune, routes, row fields, and hooks

**Files:**
- Modify: `backend/transfers.py`, append `prune`
- Modify: `backend/app.py`: import, `transactions`, routes after the owed routes, `_startup`
- Modify: `backend/plaid_sync.py`: import, `sync_item`, `remove_item`
- Modify: `backend/tests/test_transfers.py`, append

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_transfers.py`:

```python
def test_prune_drops_a_pair_when_a_row_changes_or_goes(own):
    payment()
    transfers.detect()
    db.run("UPDATE transactions SET amount=55.0 WHERE transaction_id='p-out'")
    assert transfers.prune() == 1
    assert row("p-in")["is_transfer"] == 0
    assert db.q("SELECT out_id FROM transfer_dismissed") == []
    payment("q-out", "q-in", amount=60.0)
    transfers.detect()
    db.run("DELETE FROM transactions WHERE transaction_id='q-in'")
    assert transfers.prune() == 1
    assert db.q("SELECT out_id FROM transfers") == []


def test_routes_map_errors(own):
    from fastapi import HTTPException
    payment()
    add_tx("far", amount=-50.0, account="sav", date="2026-12-01")
    with pytest.raises(HTTPException) as e:
        app.link_transfer(app.TransferReq(a="p-out", b="nope"))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        app.link_transfer(app.TransferReq(a="p-out", b="far"))
    assert e.value.status_code == 400
    assert app.link_transfer(app.TransferReq(a="p-in", b="p-out")) == {"out_id": "p-out", "in_id": "p-in"}
    assert app.unlink_transfer("p-in") == {"ok": True}
    with pytest.raises(HTTPException) as e:
        app.unlink_transfer("p-in")
    assert e.value.status_code == 404
    assert app.dismiss_transfer("far") == {"dismissed": 0}
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_transfers.py -q -k "prune or routes or page"`
Expected: 3 failed.

- [ ] **Step 3: Append `prune`**

Append to `backend/transfers.py`:

```python
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
```

- [ ] **Step 4: Wire `app.py`**

Add `import transfers  # noqa: E402` after `import splits  # noqa: E402`.

In `transactions`, after `split_lines, paid_by = ...`:

```python
    moved = transfers.for_transactions(ids)
```

and inside the row loop, after `r["payback_from"] = ...`:

```python
        r["transfer"] = moved.get(r["transaction_id"], {}).get("transfer")
        r["transfer_options"] = moved.get(r["transaction_id"], {}).get("options", [])
```

After the `owed_dismiss` route:

```python
class TransferReq(BaseModel):
    a: str
    b: str


@app.post("/api/transfers")
def link_transfer(req: TransferReq):
    return _split_call(transfers.link, req.a, req.b)


@app.delete("/api/transfers/{transaction_id}")
def unlink_transfer(transaction_id: str):
    _split_call(transfers.unlink, transaction_id)
    return {"ok": True}


@app.post("/api/transfers/{transaction_id}/dismiss")
def dismiss_transfer(transaction_id: str):
    return {"dismissed": _split_call(transfers.dismiss, transaction_id)}
```

`_split_call` maps `LookupError` to 404 and `ValueError` to 400. Its docstring becomes: "Run a splits or transfers function and turn its errors into the right status code."

In `_startup`, after the try block that ends with `splits.prune()`:

```python
    try:
        transfers.prune()
        transfers.detect()
    except Exception:
        log.exception("finding transfers at startup failed; continuing without it")
```

- [ ] **Step 5: Wire `plaid_sync.py`**

Add `import transfers` next to `import splits`. In `sync_item`, after the try block that runs `splits.check(...)`:

```python
        try:
            transfers.prune()
            transfers.detect()
        except Exception:
            log.exception("finding transfers after sync failed; transactions saved")
```

In `remove_item`, after `splits.prune()`: `transfers.prune()`.

- [ ] **Step 6: Run the suite**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass.

---

### Task 6: CSV import skips rows the account already has

**Files:**
- Create: `backend/tests/test_import.py`
- Modify: `backend/app.py`, `import_csv`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_import.py`:

```python
"""CSV import: a row the account already has, from any source, is skipped."""
import os

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
from conftest import add_tx  # noqa: E402

HEAD = "Date,Description,Amount\n"


@pytest.fixture
def card(fresh):
    db.run("INSERT INTO accounts (account_id, name, type) VALUES ('card','Store Card','credit')")
    return "card"


def imp(body):
    return app.import_csv("card", app.ImportReq(csv=HEAD + body))


def test_row_a_day_from_an_existing_row_is_skipped(card):
    add_tx("bank-1", amount=25.0, account="card", date="2026-11-05", name="STORE 123")
    assert imp("11/06/2026,Store #123 Anytown,25.00\n11/07/2026,Other Shop,9.99\n") == {"read": 2, "added": 1, "duplicates": 1}


def test_two_identical_rows_against_one_existing_row(card):
    add_tx("bank-1", amount=5.0, account="card", date="2026-11-05")
    assert imp("11/05/2026,Coffee,5.00\n11/05/2026,Coffee,5.00\n") == {"read": 2, "added": 1, "duplicates": 1}


def test_three_days_away_is_added(card):
    add_tx("bank-1", amount=25.0, account="card", date="2026-11-05")
    assert imp("11/08/2026,Store,25.00\n") == {"read": 1, "added": 1, "duplicates": 0}


def test_same_file_twice_adds_nothing_the_second_time(card):
    body = "11/05/2026,Coffee,5.00\n11/05/2026,Coffee,5.00\n11/09/2026,Hardware,30.00\n"
    assert imp(body)["added"] == 3
    assert imp(body) == {"read": 3, "added": 0, "duplicates": 3}


def test_same_date_match_wins_over_a_nearer_row_in_the_file(card):
    add_tx("bank-1", amount=5.0, account="card", date="2026-11-05")
    assert imp("11/06/2026,Coffee,5.00\n11/05/2026,Coffee,5.00\n")["added"] == 1
    assert db.one("SELECT date FROM transactions WHERE transaction_id LIKE 'imp-%'")["date"] == "2026-11-06"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_import.py -q`
Expected: `test_row_a_day...`, `test_two_identical...`, and `test_same_date_match...` fail. The other two pass already.

- [ ] **Step 3: Change `import_csv`**

Add a constant above the route: `DUP_DAYS = 2  # an imported row this close to one the account already has, same amount, is the same purchase`.

Replace the `before = ...` / `db.many(...)` / `after = ...` lines with:

```python
    have = db.q("SELECT transaction_id, date, amount FROM transactions WHERE account_id=?", (account_id,))
    have_ids = {h["transaction_id"] for h in have}
    pool = [h for h in have if h["transaction_id"] not in {r[0] for r in out}]
    todo = [r for r in out if r[0] not in have_ids]
    skipped = set()
    for gap in range(DUP_DAYS + 1):  # same-date matches first, then one day off, then two
        for r in todo:
            if r[0] in skipped:
                continue
            m = next((h for h in pool if transfers.cents(h["amount"]) == transfers.cents(r[5])
                      and (h["amount"] > 0) == (r[5] > 0) and transfers.days_apart(h["date"], r[3]) == gap), None)
            if m:
                pool.remove(m)
                skipped.add(r[0])
    keep = [r for r in todo if r[0] not in skipped]
    before = db.one("SELECT COUNT(*) AS n FROM transactions WHERE account_id=?", (account_id,))["n"]
    db.many("""INSERT OR IGNORE INTO transactions (transaction_id, account_id, item_id, date, authorized_date, amount, name, merchant_name,
               pending, category, category_detail, logo_url, website, payment_channel, raw) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", keep)
    after = db.one("SELECT COUNT(*) AS n FROM transactions WHERE account_id=?", (account_id,))["n"]
```

After the `places.fill` try block, before `return`:

```python
    try:
        transfers.prune()
        transfers.detect()
    except Exception:
        log.exception("finding transfers after import failed; rows imported")
```

The docstring gains: "A row the account already has, same amount within DUP_DAYS days, is skipped. Each existing row matches once."

- [ ] **Step 4: Run the suite**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass.

---

### Task 7: The page

**Files:**
- Modify: `frontend/src/api.js`, after `dismissPayback`
- Modify: `frontend/src/components/TxList.jsx`

- [ ] **Step 1: API helpers**

```js
  linkTransfer: (a, b) => req('POST', '/api/transfers', { a, b }),
  unlinkTransfer: (id) => req('DELETE', `/api/transfers/${encodeURIComponent(id)}`),
  dismissTransfer: (id) => req('POST', `/api/transfers/${encodeURIComponent(id)}/dismiss`),
```

- [ ] **Step 2: One handler for the three actions**

In `TxList`, next to the other handlers:

```js
  // Link, unlink, or turn down a transfer, then refresh every list and the Owed box.
  const transferAct = async (fn) => {
    setBusy(true)
    try { await fn(); txChanged({ reload: true }); onChanged && onChanged() } catch (e) { toast(e.message) } finally { setBusy(false) }
  }
```

- [ ] **Step 3: The pill**

Replace the line that renders the plain "Transfer" label with:

```jsx
                    {t.transfer
                      ? <span style={{ marginLeft: 8, display: 'inline-flex', alignItems: 'center', gap: 2, fontSize: 11, fontWeight: 400, padding: '0 2px 0 8px', borderRadius: 999, border: '1px solid var(--line)', color: 'var(--text2)', verticalAlign: 'middle' }}>
                          Transfer {t.transfer.dir} {t.transfer.account}
                          <button type="button" disabled={busy} onClick={(e) => { e.stopPropagation(); transferAct(() => api.unlinkTransfer(t.transaction_id)) }}
                            aria-label="Unlink transfer" title="Unlink"
                            style={{ border: 0, background: 'transparent', color: 'var(--muted)', fontSize: 13, lineHeight: 1, padding: '0 4px' }}>×</button>
                        </span>
                      : t.is_transfer ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>Transfer</span> : null}
```

- [ ] **Step 4: No Split on a linked row**

The picker's `onSplit` becomes `t.pending || t.transfer ? undefined : () => setSplitting(t.transaction_id)`.

- [ ] **Step 5: The question line**

After the `SplitEditor` line:

```jsx
              {!t.transfer && t.transfer_options?.length > 0 && (
                <div onClick={(e) => e.stopPropagation()} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '8px 16px 10px', fontSize: 13, color: 'var(--text2)', background: 'var(--hover)' }}>
                  {t.transfer_options.map((o) => (
                    <div key={o.id} style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10 }}>
                      <span style={{ flex: 1 }}>Possible transfer: {money(Math.abs(o.display_amount))} {o.display_amount > 0 ? 'into' : 'out of'} {o.account} on {fullDate(o.date)}</span>
                      <button type="button" className="press" disabled={busy} onClick={() => transferAct(() => api.linkTransfer(t.transaction_id, o.id))}
                        style={{ height: 30, padding: '0 12px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 12 }}>Link</button>
                    </div>
                  ))}
                  <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <button type="button" disabled={busy} onClick={() => transferAct(() => api.dismissTransfer(t.transaction_id))}
                      style={{ height: 30, padding: '0 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--text2)', fontSize: 12 }}>Not a transfer</button>
                  </div>
                </div>
              )}
```

- [ ] **Step 6: Build**

Run in `frontend\`: `npm run build`
Expected: builds clean. The chunk size warning is old and expected.

---

### Task 8: Docs

**Files:**
- Modify: `docs/ARCHITECTURE.md`, `README.md`

- [ ] **Step 1: `docs/ARCHITECTURE.md`**

- Module list, after `splits.py`: `    transfers.py         money between own accounts: pairs, questions, unlink`
- Tables, after `payback_dismissed`:
  - `| \`transfers\` | A row where money left one account and the row where it arrived on another |`
  - `| \`transfer_dismissed\` | Pairs the owner unlinked or turned down; never linked again |`
- Routes, after `/paybacks/{id}`:
  - `| POST | /transfers | link {a, b} by hand |`
  - `| DELETE | /transfers/{id} | unlink the pair holding this row |`
  - `| POST | /transfers/{id}/dismiss | Not a transfer: turn down every candidate for this row |`
- `/transactions` row: the added fields gain `transfer, transfer_options`.
- `/accounts/{id}/import` row: `CSV import, dedupe by sha1(account,date,amount,desc,occurrence), then skip rows the account has within 2 days, same amount`.
- New bullet after Splits: `- **Transfers:** \`transfers.detect\` links a row where money left one account to the row where the same amount arrived on another, at most 3 days apart, when neither has another candidate. It runs at startup, after a sync, and after an import. A link sets \`is_transfer\` and swaps a category the app picked for a transfer one. The categorizer skips linked rows. Unlink remembers the pair in \`transfer_dismissed\`. A row in a dismissed pair is never linked on its own again. Unclear rows show their candidates under the row with Link and "Not a transfer".`

- [ ] **Step 2: `README.md`**

Add to the feature list: `- Transfers between your own accounts link on their own, so a card payment never counts as spending. A CSV import skips rows the account already has.`

---

### Task 9: Check it in the browser

- [ ] **Step 1: Full suite**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass.

- [ ] **Step 2: Copy the database and serve it**

Copy `data\finance.db` to the scratchpad with SQLite's backup API, then run the app on port 8799 with `FINANCE_DB` pointing at the copy and empty Plaid keys. Startup runs `prune()` and `detect()`.

- [ ] **Step 3: Check on `http://127.0.0.1:8799`**

- Search for a card payment. Both sides show "Transfer to ..." and "Transfer from ...".
- The checking side of a store-card payment shows a transfer category, not the store's spending category.
- "Spent this month" did not go up.
- A row with two candidates shows the question line with "Link" per choice and "Not a transfer".
- The x on a pill unlinks. The row returns to its old category and does not relink after a reload.
- A linked row offers no "Split" in its category menu.
- Light and dark themes both read well.

- [ ] **Step 4: Clean up**

Close the tab, stop the server, and delete the copy.

- [ ] **Step 5: Report to Scott**

Report what was checked and what was not. Do not commit until he says so.
