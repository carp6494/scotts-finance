# Categories and Rules Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every transaction gets a category from a seeded taxonomy, a Python rules engine keeps them current without touching manual choices, and the UI lets the user edit categories, make rules from edits, filter by category, and manage rules and categories.

**Architecture:** Three new backend modules. `categories.py` owns the seeded taxonomy and name derivation. `rules.py` owns matching and the categorization order and writes the effective category onto each transaction row. `app.py` gains REST endpoints for categories, rules, and transaction edits, and calls the engine after sync and import. The React frontend gains a `CategoryPicker`, a Rules page, and filters, all against those endpoints.

**Tech Stack:** Python 3.10+, FastAPI, sqlite3 (raw SQL, existing `db.py` helpers), pytest (new). React 19, Vite 7, existing inline-style conventions. No new npm packages.

**Spec:** `docs/superpowers/specs/2026-11-12-categories-rules-design.md`

**Conventions the engineer must know:**
- Run backend tests from the project root: `.venv\Scripts\python -m pytest backend/tests -q`
- Build the frontend from `frontend\`: `npm run build`. The running server serves `frontend/dist` straight from disk, so a rebuild shows up on refresh. Backend changes need the server restarted by closing the `start.bat` window and running it again. The engineer cannot restart it; note it in the handoff.
- `db.py` helpers: `db.q(sql, args)` returns a list of dicts, `db.one` returns the first dict or None, `db.run` executes and commits, `db.many(sql, rows)` is executemany and commit.
- Transaction amounts follow Plaid: positive is money out, negative is money in.
- Commit messages end with the line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Before every commit run `git diff --cached --name-only` and confirm no file under `data/`, `backups/`, `imports/`, nor `.env` nor `HANDOFF.md` is staged. The repo is public.
- Never put account names, card numbers, balances, or rates in any committed file, test, or fixture. Tests use made-up merchants and amounts.

---

## File structure

| File | Responsibility |
|---|---|
| `requirements-dev.txt` | Create. pytest only. |
| `backend/db.py` | Modify. `FINANCE_DB` override, new tables, new transaction columns. |
| `backend/categories.py` | Create. Plaid taxonomy seed, readable names, `ensure`, `seed`, `grouped`. |
| `backend/rules.py` | Create. `match`, `categorize`, `merchant_key`, `similar_count`, `preview`. |
| `backend/tests/conftest.py` | Create. Temp database, path setup, `fresh` fixture. |
| `backend/tests/test_categories.py` | Create. |
| `backend/tests/test_rules.py` | Create. |
| `backend/plaid_sync.py` | Modify. Call the engine after upsert. |
| `backend/app.py` | Modify. Startup seed and backfill, import hook, categories API, transactions list fields and PATCH, rules API, summary. |
| `frontend/src/api.js` | Modify. New request wrappers. |
| `frontend/src/categories.js` | Create. Cached category list hook. |
| `frontend/src/components/CategoryPicker.jsx` | Create. |
| `frontend/src/components/TxList.jsx` | Modify. Picker, display name, muted rows, make-rule bar, new props. |
| `frontend/src/pages/Transactions.jsx` | Modify. Category filter and spending-only toggle. |
| `frontend/src/pages/Rules.jsx` | Create. Rules tab and Categories tab. |
| `frontend/src/App.jsx` | Modify. Nav item, page switch, toast event listener. |

---

### Task 1: Test harness and database path override

**Files:**
- Create: `requirements-dev.txt`
- Modify: `backend/db.py:1-14`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_harness.py`

- [ ] **Step 1: Create `requirements-dev.txt`**

```
-r requirements.txt
pytest>=8
```

- [ ] **Step 2: Install it**

Run: `.venv\Scripts\python -m pip install -q -r requirements-dev.txt`
Expected: no errors. `.venv\Scripts\python -m pytest --version` prints a version.

- [ ] **Step 3: Write the conftest**

`backend/tests/conftest.py`:

```python
"""Point db.py at a temporary database before anything imports it."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="finance-test-"))
os.environ["FINANCE_DB"] = str(_TMP / "test.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

import db  # noqa: E402


@pytest.fixture
def fresh():
    """Empty every table the engine touches, then reseed categories."""
    for t in ("transactions", "rules", "merchant_memory", "categories", "accounts"):
        db.run(f"DELETE FROM {t}")
    import categories
    categories.seed()
    return db


def add_tx(tid, *, amount=10.0, name="Test", merchant=None, account="acc-1", date="2026-11-05",
           category=None, detail=None, source=None, cat_id=None):
    """Insert one transaction row with only the fields the engine reads."""
    db.run("""INSERT INTO transactions (transaction_id, account_id, item_id, date, authorized_date, amount, name, merchant_name,
              pending, category, category_detail, payment_channel, raw, cat_id, cat_source)
              VALUES (?,?,?,?,?,?,?,?,0,?,?,'in store','{}',?,?)""",
           (tid, account, "item-1", date, "", amount, name, merchant, category, detail, cat_id, source))
    return tid
```

- [ ] **Step 4: Write the failing harness test**

`backend/tests/test_harness.py`:

```python
import os


def test_uses_temp_database():
    import db
    assert str(db.DB_PATH) == os.environ["FINANCE_DB"]
    assert db.DB_PATH.name == "test.db"
```

- [ ] **Step 5: Run it to see it fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_harness.py -q`
Expected: FAIL, `db.DB_PATH` ends in `finance.db`.

- [ ] **Step 6: Add the override to `db.py`**

Replace the top of `backend/db.py` (the lines from the docstring through `DB_PATH = ...`) with:

```python
"""SQLite storage. One local file: data/finance.db.

Set FINANCE_DB to a file path to use a different database (tests do this).
"""
import json
import os
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
DB_PATH = Path(os.environ["FINANCE_DB"]) if os.environ.get("FINANCE_DB") else DATA / "finance.db"
```

- [ ] **Step 7: Run it to see it pass**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: `1 passed`.

- [ ] **Step 8: Commit**

```bash
git add requirements-dev.txt backend/db.py backend/tests/conftest.py backend/tests/test_harness.py
git diff --cached --name-only
git commit -m "Add pytest harness with a temporary database

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Schema for categories, rules, merchant memory, and transaction columns

**Files:**
- Modify: `backend/db.py` (SCHEMA string and the ALTER loop)
- Create: `backend/tests/test_schema.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_schema.py`:

```python
import db


def cols(table):
    return [r["name"] for r in db.q(f"PRAGMA table_info({table})")]


def test_new_tables_exist():
    for t in ("categories", "rules", "merchant_memory"):
        assert db.one("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)), t


def test_transactions_has_new_columns():
    c = cols("transactions")
    for col in ("cat_id", "cat_source", "excluded", "is_transfer", "display_name"):
        assert col in c, col


def test_rules_columns():
    c = cols("rules")
    for col in ("name", "priority", "enabled", "conditions", "actions", "created_from", "hits", "last_applied", "created_at"):
        assert col in c, col
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_schema.py -q`
Expected: 3 failures, tables missing.

- [ ] **Step 3: Add the tables to SCHEMA**

In `backend/db.py`, inside the `SCHEMA` string, after the `sync_log` table definition and before the closing `"""`, add:

```sql
CREATE TABLE IF NOT EXISTS categories (
  id TEXT PRIMARY KEY,
  group_name TEXT NOT NULL,
  name TEXT NOT NULL,
  type TEXT NOT NULL,
  hidden INTEGER DEFAULT 0,
  custom INTEGER DEFAULT 0,
  sort INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  priority INTEGER DEFAULT 100,
  enabled INTEGER DEFAULT 1,
  conditions TEXT NOT NULL DEFAULT '{}',
  actions TEXT NOT NULL DEFAULT '{}',
  created_from TEXT,
  hits INTEGER DEFAULT 0,
  last_applied TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS merchant_memory (
  merchant_key TEXT PRIMARY KEY,
  cat_id TEXT NOT NULL,
  updated_at TEXT DEFAULT (datetime('now'))
);
```

- [ ] **Step 4: Generalize the ALTER loop**

Replace this block in `backend/db.py`:

```python
for _col in ("institution TEXT", "apr_override REAL", "limit_override REAL", "min_payment_override REAL"):
    try:
        _con.execute(f"ALTER TABLE accounts ADD COLUMN {_col}")
    except sqlite3.OperationalError:
        pass  # already there
_con.commit()
```

with:

```python
_ADDED_COLUMNS = (
    ("accounts", "institution TEXT"),
    ("accounts", "apr_override REAL"),
    ("accounts", "limit_override REAL"),
    ("accounts", "min_payment_override REAL"),
    ("transactions", "cat_id TEXT"),
    ("transactions", "cat_source TEXT"),
    ("transactions", "excluded INTEGER DEFAULT 0"),
    ("transactions", "is_transfer INTEGER DEFAULT 0"),
    ("transactions", "display_name TEXT"),
)
for _table, _col in _ADDED_COLUMNS:
    try:
        _con.execute(f"ALTER TABLE {_table} ADD COLUMN {_col}")
    except sqlite3.OperationalError:
        pass  # already there
_con.execute("CREATE INDEX IF NOT EXISTS ix_tx_cat ON transactions(cat_id)")
_con.commit()
```

- [ ] **Step 5: Run the tests**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/db.py backend/tests/test_schema.py
git diff --cached --name-only
git commit -m "Schema: categories, rules, merchant memory, transaction category columns

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Category taxonomy module

**Files:**
- Create: `backend/categories.py`
- Create: `backend/tests/test_categories.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_categories.py`:

```python
import categories
import db


def test_seed_inserts_full_taxonomy(fresh):
    n = db.one("SELECT COUNT(*) AS n FROM categories")["n"]
    assert n >= 100
    row = db.one("SELECT * FROM categories WHERE id='FOOD_AND_DRINK_FAST_FOOD'")
    assert row["group_name"] == "Food & drink"
    assert row["name"] == "Fast food"
    assert row["type"] == "expense"
    assert db.one("SELECT type FROM categories WHERE id='LOAN_PAYMENTS_CREDIT_CARD_PAYMENT'")["type"] == "transfer"
    assert db.one("SELECT type FROM categories WHERE id='INCOME_WAGES'")["type"] == "income"
    assert db.one("SELECT * FROM categories WHERE id='UNCATEGORIZED'")


def test_seed_is_idempotent(fresh):
    before = db.one("SELECT COUNT(*) AS n FROM categories")["n"]
    categories.seed()
    assert db.one("SELECT COUNT(*) AS n FROM categories")["n"] == before


def test_readable_names():
    assert categories.readable("TRANSPORTATION_TAXIS_AND_RIDE_SHARES") == "Taxis and ride shares"
    assert categories.readable("GENERAL_MERCHANDISE_ONLINE_MARKETPLACES") == "Online marketplaces"
    assert categories.readable("LOAN_PAYMENTS") == "Loan payments"


def test_ensure_adds_unknown_code(fresh):
    assert categories.ensure("FOOD_AND_DRINK_SOMETHING_NEW") == "FOOD_AND_DRINK_SOMETHING_NEW"
    row = db.one("SELECT * FROM categories WHERE id='FOOD_AND_DRINK_SOMETHING_NEW'")
    assert row["group_name"] == "Food & drink"
    assert row["name"] == "Something new"
    assert row["type"] == "expense"


def test_ensure_handles_bare_primary(fresh):
    assert categories.ensure("LOAN_PAYMENTS") == "LOAN_PAYMENTS"
    row = db.one("SELECT * FROM categories WHERE id='LOAN_PAYMENTS'")
    assert row["name"] == "Loan payments"
    assert row["type"] == "transfer"


def test_ensure_returns_none_for_empty(fresh):
    assert categories.ensure(None) is None
    assert categories.ensure("") is None


def test_grouped_structure(fresh):
    g = categories.grouped()
    names = [x["group_name"] for x in g]
    assert "Income" in names and "Food & drink" in names
    food = next(x for x in g if x["group_name"] == "Food & drink")
    assert any(c["id"] == "FOOD_AND_DRINK_GROCERIES" for c in food["categories"])
    assert set(food["categories"][0].keys()) == {"id", "name", "type", "hidden", "custom"}


def test_add_custom(fresh):
    c = categories.add_custom("Dog stuff", "Pets", "expense")
    assert c["id"].startswith("custom-")
    assert c["custom"] == 1
    assert db.one("SELECT * FROM categories WHERE id=?", (c["id"],))["group_name"] == "Pets"
    again = categories.add_custom("Dog stuff", "Pets", "expense")
    assert again["id"] != c["id"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_categories.py -q`
Expected: errors, `No module named 'categories'`.

- [ ] **Step 3: Write `backend/categories.py`**

```python
"""Category taxonomy. Seeded from Plaid's personal finance categories, extended by the user.

Category ids are Plaid's detailed codes (FOOD_AND_DRINK_FAST_FOOD) so Plaid transactions map with no
lookup table. Custom categories get ids like custom-dog-stuff-3f2a.
"""
import re
import uuid

import db

UNCAT = "UNCATEGORIZED"

# Plaid primary code -> (readable group, type)
GROUPS = {
    "INCOME": ("Income", "income"),
    "TRANSFER_IN": ("Transfers in", "transfer"),
    "TRANSFER_OUT": ("Transfers out", "transfer"),
    "LOAN_PAYMENTS": ("Loan payments", "transfer"),
    "BANK_FEES": ("Bank fees", "expense"),
    "ENTERTAINMENT": ("Entertainment", "expense"),
    "FOOD_AND_DRINK": ("Food & drink", "expense"),
    "GENERAL_MERCHANDISE": ("Shopping", "expense"),
    "HOME_IMPROVEMENT": ("Home improvement", "expense"),
    "MEDICAL": ("Medical", "expense"),
    "PERSONAL_CARE": ("Personal care", "expense"),
    "GENERAL_SERVICES": ("Services", "expense"),
    "GOVERNMENT_AND_NON_PROFIT": ("Government & non-profit", "expense"),
    "TRANSPORTATION": ("Transportation", "expense"),
    "TRAVEL": ("Travel", "expense"),
    "RENT_AND_UTILITIES": ("Rent & utilities", "expense"),
    "OTHER": ("Other", "expense"),
}

# Plaid detailed suffixes per primary code
DETAILED = {
    "INCOME": ["DIVIDENDS", "INTEREST_EARNED", "RETIREMENT_PENSION", "TAX_REFUND", "UNEMPLOYMENT", "WAGES", "OTHER_INCOME"],
    "TRANSFER_IN": ["CASH_ADVANCES_AND_LOANS", "DEPOSIT", "INVESTMENT_AND_RETIREMENT_FUNDS", "SAVINGS", "ACCOUNT_TRANSFER", "OTHER_TRANSFER_IN"],
    "TRANSFER_OUT": ["INVESTMENT_AND_RETIREMENT_FUNDS", "SAVINGS", "WITHDRAWAL", "ACCOUNT_TRANSFER", "OTHER_TRANSFER_OUT"],
    "LOAN_PAYMENTS": ["CAR_PAYMENT", "CREDIT_CARD_PAYMENT", "PERSONAL_LOAN_PAYMENT", "MORTGAGE_PAYMENT", "STUDENT_LOAN_PAYMENT", "OTHER_PAYMENT"],
    "BANK_FEES": ["ATM_FEES", "FOREIGN_TRANSACTION_FEES", "INSUFFICIENT_FUNDS", "INTEREST_CHARGE", "OVERDRAFT_FEES", "OTHER_BANK_FEES"],
    "ENTERTAINMENT": ["CASINOS_AND_GAMBLING", "MUSIC_AND_AUDIO", "SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS", "TV_AND_MOVIES", "VIDEO_GAMES", "OTHER_ENTERTAINMENT"],
    "FOOD_AND_DRINK": ["BEER_WINE_AND_LIQUOR", "COFFEE", "FAST_FOOD", "GROCERIES", "RESTAURANT", "VENDING_MACHINES", "OTHER_FOOD_AND_DRINK"],
    "GENERAL_MERCHANDISE": ["BOOKSTORES_AND_NEWSSTANDS", "CLOTHING_AND_ACCESSORIES", "CONVENIENCE_STORES", "DEPARTMENT_STORES", "DISCOUNT_STORES",
                            "ELECTRONICS", "GIFTS_AND_NOVELTIES", "OFFICE_SUPPLIES", "ONLINE_MARKETPLACES", "PET_SUPPLIES", "SPORTING_GOODS",
                            "SUPERSTORES", "TOBACCO_AND_VAPE", "OTHER_GENERAL_MERCHANDISE"],
    "HOME_IMPROVEMENT": ["FURNITURE", "HARDWARE", "REPAIR_AND_MAINTENANCE", "SECURITY", "OTHER_HOME_IMPROVEMENT"],
    "MEDICAL": ["DENTAL_CARE", "EYE_CARE", "NURSING_CARE", "PHARMACIES_AND_SUPPLEMENTS", "PRIMARY_CARE", "VETERINARY_SERVICES", "OTHER_MEDICAL"],
    "PERSONAL_CARE": ["GYMS_AND_FITNESS_CENTERS", "HAIR_AND_BEAUTY", "LAUNDRY_AND_DRY_CLEANING", "OTHER_PERSONAL_CARE"],
    "GENERAL_SERVICES": ["ACCOUNTING_AND_FINANCIAL_PLANNING", "AUTOMOTIVE", "CHILDCARE", "CONSULTING_AND_LEGAL", "EDUCATION", "INSURANCE",
                         "POSTAGE_AND_SHIPPING", "STORAGE", "OTHER_GENERAL_SERVICES"],
    "GOVERNMENT_AND_NON_PROFIT": ["DONATIONS", "GOVERNMENT_DEPARTMENTS_AND_AGENCIES", "TAX_PAYMENT", "OTHER_GOVERNMENT_AND_NON_PROFIT"],
    "TRANSPORTATION": ["BIKES_AND_SCOOTERS", "GAS", "PARKING", "PUBLIC_TRANSIT", "TAXIS_AND_RIDE_SHARES", "TOLLS", "OTHER_TRANSPORTATION"],
    "TRAVEL": ["FLIGHTS", "LODGING", "RENTAL_CARS", "OTHER_TRAVEL"],
    "RENT_AND_UTILITIES": ["GAS_AND_ELECTRICITY", "INTERNET_AND_CABLE", "RENT", "SEWAGE_AND_WASTE_MANAGEMENT", "TELEPHONE", "WATER", "OTHER_UTILITIES"],
    "OTHER": ["OTHER"],
}

NAME_OVERRIDES = {
    "ENTERTAINMENT_SPORTING_EVENTS_AMUSEMENT_PARKS_AND_MUSEUMS": "Events, parks and museums",
    "TRANSPORTATION_GAS": "Gas station",
    "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY": "Gas and electric",
    "GENERAL_MERCHANDISE_TOBACCO_AND_VAPE": "Tobacco and vape",
    "OTHER_OTHER": "Other",
}

_PRIMARIES = sorted(GROUPS, key=len, reverse=True)  # longest first so FOOD_AND_DRINK beats OTHER


def primary_of(code: str) -> str:
    for p in _PRIMARIES:
        if code == p or code.startswith(p + "_"):
            return p
    return "OTHER"


def readable(code: str) -> str:
    """FOOD_AND_DRINK_FAST_FOOD -> 'Fast food'. A bare primary code gives the group name."""
    if code in NAME_OVERRIDES:
        return NAME_OVERRIDES[code]
    p = primary_of(code)
    suffix = code[len(p) + 1:] if code.startswith(p + "_") else ""
    if not suffix:
        return GROUPS.get(p, ("Other", "expense"))[0]
    words = suffix.lower().split("_")
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def seed():
    rows = []
    for p, suffixes in DETAILED.items():
        group, typ = GROUPS[p]
        for i, s in enumerate(suffixes):
            code = f"{p}_{s}"
            rows.append((code, group, readable(code), typ, i))
    rows.append((UNCAT, "Uncategorized", "Uncategorized", "expense", 0))
    db.many("INSERT OR IGNORE INTO categories (id, group_name, name, type, sort) VALUES (?,?,?,?,?)", rows)


def ensure(code):
    """Return the category id for a Plaid or import code, inserting a row the first time it is seen."""
    if not code:
        return None
    if db.one("SELECT 1 FROM categories WHERE id=?", (code,)):
        return code
    group, typ = GROUPS.get(primary_of(code), ("Other", "expense"))
    db.run("INSERT OR IGNORE INTO categories (id, group_name, name, type, sort) VALUES (?,?,?,?,999)", (code, group, readable(code), typ))
    return code


def get(cat_id):
    return db.one("SELECT * FROM categories WHERE id=?", (cat_id,))


def grouped():
    """[{group_name, categories: [{id, name, type, hidden, custom}]}] in display order."""
    order = {g: i for i, g in enumerate(v[0] for v in GROUPS.values())}
    rows = db.q("SELECT id, group_name, name, type, hidden, custom FROM categories ORDER BY sort, name")
    groups = {}
    for r in rows:
        groups.setdefault(r["group_name"], []).append({k: r[k] for k in ("id", "name", "type", "hidden", "custom")})
    keys = sorted(groups, key=lambda g: (g == "Uncategorized", order.get(g, 500), g))
    return [{"group_name": g, "categories": groups[g]} for g in keys]


def add_custom(name: str, group_name: str, typ: str):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "category"
    cat_id = f"custom-{slug}-{uuid.uuid4().hex[:4]}"
    db.run("INSERT INTO categories (id, group_name, name, type, custom, sort) VALUES (?,?,?,?,1,500)", (cat_id, group_name.strip(), name.strip(), typ))
    return get(cat_id)
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass, 12 tests.

- [ ] **Step 5: Commit**

```bash
git add backend/categories.py backend/tests/test_categories.py
git diff --cached --name-only
git commit -m "Categories module seeded from Plaid's taxonomy

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Rule matching

**Files:**
- Create: `backend/rules.py`
- Create: `backend/tests/test_rules.py`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_rules.py`:

```python
import rules

TX = {"transaction_id": "t1", "account_id": "acc-1", "date": "2026-11-15", "amount": 42.5,
      "name": "SQ *JOES BBQ 1234 SPRINGFIELD", "merchant_name": "Joes BBQ", "display_name": None}


def test_empty_conditions_match_everything():
    assert rules.match({}, TX)
    assert rules.match(None, TX)


def test_merchant_substring_case_insensitive():
    assert rules.match({"merchant": "joes"}, TX)
    assert rules.match({"merchant": "BBQ"}, TX)
    assert not rules.match({"merchant": "walmart"}, TX)


def test_merchant_checks_display_name_and_raw_name():
    assert rules.match({"merchant": "springfield"}, TX)  # from name
    assert rules.match({"merchant": "renamed"}, {**TX, "display_name": "Renamed Place"})


def test_text_matches_raw_name_only():
    assert rules.match({"text": "SQ *"}, TX)
    assert not rules.match({"text": "Joes BBQ"}, {**TX, "name": "SOMETHING ELSE"})


def test_amount_bounds_inclusive():
    assert rules.match({"amount_min": 42.5}, TX)
    assert rules.match({"amount_max": 42.5}, TX)
    assert rules.match({"amount_min": 40, "amount_max": 45}, TX)
    assert not rules.match({"amount_min": 50}, TX)
    assert not rules.match({"amount_max": 10}, TX)
    assert not rules.match({"amount_min": 1}, {**TX, "amount": None})


def test_account_exact():
    assert rules.match({"account_id": "acc-1"}, TX)
    assert not rules.match({"account_id": "acc-2"}, TX)


def test_day_of_month_bounds():
    assert rules.match({"day_min": 15, "day_max": 15}, TX)
    assert rules.match({"day_min": 10}, TX)
    assert not rules.match({"day_max": 14}, TX)
    assert not rules.match({"day_min": 1}, {**TX, "date": "bad"})


def test_all_conditions_must_hold():
    assert rules.match({"merchant": "joes", "amount_min": 40, "account_id": "acc-1"}, TX)
    assert not rules.match({"merchant": "joes", "amount_min": 40, "account_id": "acc-2"}, TX)


def test_merchant_key():
    assert rules.merchant_key(TX) == "joes bbq"
    assert rules.merchant_key({"merchant_name": None, "name": "  RAW NAME "}) == "raw name"
    assert rules.merchant_key({"merchant_name": None, "name": None}) == ""
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_rules.py -q`
Expected: `No module named 'rules'`.

- [ ] **Step 3: Write `backend/rules.py` with matching only**

```python
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
    """True when every condition present in the dict holds for transaction dict t."""
    c = conditions or {}
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python -m pytest backend/tests/test_rules.py -q`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/rules.py backend/tests/test_rules.py
git diff --cached --name-only
git commit -m "Rules: condition matching

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Categorization engine

**Files:**
- Modify: `backend/rules.py`
- Modify: `backend/tests/test_rules.py`

- [ ] **Step 1: Add the failing engine tests**

Append to `backend/tests/test_rules.py`:

```python
import json

import db
from conftest import add_tx


def add_rule(name, conditions, actions, priority=100, enabled=1):
    db.run("INSERT INTO rules (name, priority, enabled, conditions, actions) VALUES (?,?,?,?,?)",
           (name, priority, enabled, json.dumps(conditions), json.dumps(actions)))
    return db.one("SELECT id FROM rules WHERE name=?", (name,))["id"]


def tx(tid):
    return db.one("SELECT * FROM transactions WHERE transaction_id=?", (tid,))


def test_plaid_fallback_and_uncategorized(fresh):
    add_tx("a", detail="FOOD_AND_DRINK_GROCERIES")
    add_tx("b")
    assert rules.categorize() == 2
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_GROCERIES" and tx("a")["cat_source"] == "plaid"
    assert tx("b")["cat_id"] == "UNCATEGORIZED" and tx("b")["cat_source"] == "none"


def test_plaid_fallback_inserts_unseen_code(fresh):
    add_tx("a", detail="FOOD_AND_DRINK_BRAND_NEW")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_BRAND_NEW"
    assert db.one("SELECT name FROM categories WHERE id='FOOD_AND_DRINK_BRAND_NEW'")["name"] == "Brand new"


def test_import_rows_use_primary_category(fresh):
    add_tx("a", category="LOAN_PAYMENTS", detail=None)
    rules.categorize()
    assert tx("a")["cat_id"] == "LOAN_PAYMENTS"


def test_rule_beats_plaid_and_counts_hits(fresh):
    rid = add_rule("Joes", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"})
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    add_tx("b", merchant="Walmart", detail="GENERAL_MERCHANDISE_SUPERSTORES")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_RESTAURANT" and tx("a")["cat_source"] == f"rule:{rid}"
    assert tx("b")["cat_id"] == "GENERAL_MERCHANDISE_SUPERSTORES"
    r = db.one("SELECT hits, last_applied FROM rules WHERE id=?", (rid,))
    assert r["hits"] == 1 and r["last_applied"]


def test_priority_order_and_tie_break(fresh):
    low = add_rule("second", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_FAST_FOOD"}, priority=200)
    high = add_rule("first", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"}, priority=10)
    add_tx("a", merchant="Joes BBQ")
    rules.categorize()
    assert tx("a")["cat_source"] == f"rule:{high}"
    db.run("UPDATE rules SET priority=10 WHERE id=?", (low,))
    rules.categorize()
    assert tx("a")["cat_source"] == f"rule:{high}"  # lower id wins the tie


def test_user_set_transaction_is_never_touched(fresh):
    add_rule("Joes", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT", "exclude": True})
    add_tx("a", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_COFFEE", source="user")
    assert rules.categorize() == 0
    row = tx("a")
    assert row["cat_id"] == "FOOD_AND_DRINK_COFFEE" and row["cat_source"] == "user" and row["excluded"] == 0


def test_merchant_memory_applies_when_no_rule(fresh):
    db.run("INSERT INTO merchant_memory (merchant_key, cat_id) VALUES ('joes bbq', 'FOOD_AND_DRINK_RESTAURANT')")
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_RESTAURANT" and tx("a")["cat_source"] == "merchant"


def test_disabled_rule_is_skipped(fresh):
    add_rule("Joes", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"}, enabled=0)
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    assert tx("a")["cat_source"] == "plaid"


def test_rerun_falls_back_when_rule_stops_matching(fresh):
    rid = add_rule("Joes", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"})
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    assert tx("a")["cat_source"] == f"rule:{rid}"
    db.run("UPDATE rules SET conditions=? WHERE id=?", (json.dumps({"merchant": "nobody"}), rid))
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_FAST_FOOD" and tx("a")["cat_source"] == "plaid"
    assert db.one("SELECT hits FROM rules WHERE id=?", (rid,))["hits"] == 0


def test_flag_only_rule_keeps_walking_for_category(fresh):
    add_rule("Rename", {"merchant": "sq *joes"}, {"display_name": "Joe's BBQ", "exclude": True}, priority=1)
    add_rule("Cat", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"}, priority=2)
    add_tx("a", merchant="SQ *JOES BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    row = tx("a")
    assert row["display_name"] == "Joe's BBQ" and row["excluded"] == 1
    assert row["cat_id"] == "FOOD_AND_DRINK_RESTAURANT"


def test_flags_are_never_cleared_by_rerun(fresh):
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    db.run("UPDATE transactions SET excluded=1, is_transfer=1, display_name='Mine' WHERE transaction_id='a'")
    rules.categorize()
    row = tx("a")
    assert row["excluded"] == 1 and row["is_transfer"] == 1 and row["display_name"] == "Mine"


def test_categorize_subset_only_touches_given_ids(fresh):
    add_tx("a", detail="FOOD_AND_DRINK_GROCERIES")
    add_tx("b", detail="FOOD_AND_DRINK_COFFEE")
    assert rules.categorize(["a"]) == 1
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_GROCERIES"
    assert tx("b")["cat_id"] is None


def test_bad_rule_json_is_skipped(fresh):
    db.run("INSERT INTO rules (name, conditions, actions) VALUES ('broken', 'not json', '{}')")
    add_tx("a", detail="FOOD_AND_DRINK_GROCERIES")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_GROCERIES"


def test_similar_count(fresh):
    add_tx("a", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")
    add_tx("b", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")
    add_tx("c", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_RESTAURANT", source="plaid")
    add_tx("d", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="user")
    add_tx("e", merchant="Other", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")
    assert rules.similar_count("a", "FOOD_AND_DRINK_RESTAURANT") == 1  # only b


def test_preview_counts_non_user_matches(fresh):
    add_tx("a", merchant="Joes BBQ", source="plaid", cat_id="UNCATEGORIZED", date="2026-11-01")
    add_tx("b", merchant="Joes BBQ", source="user", cat_id="UNCATEGORIZED", date="2026-11-02")
    add_tx("c", merchant="Walmart", source="plaid", cat_id="UNCATEGORIZED", date="2026-11-03")
    p = rules.preview({"merchant": "joes"})
    assert p["count"] == 1
    assert [r["transaction_id"] for r in p["sample"]] == ["a"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python -m pytest backend/tests/test_rules.py -q`
Expected: failures, `rules has no attribute 'categorize'`.

- [ ] **Step 3: Add the engine to `backend/rules.py`**

Append to `backend/rules.py`:

```python
def _load_rules():
    out = []
    for r in db.q("SELECT * FROM rules WHERE enabled=1 ORDER BY priority, id"):
        try:
            out.append((r, json.loads(r["conditions"] or "{}"), json.loads(r["actions"] or "{}")))
        except (json.JSONDecodeError, TypeError):
            log.warning("rule %s (%s) has bad JSON and was skipped", r["id"], r["name"])
    return out


def _rows(transaction_ids):
    base = "SELECT * FROM transactions WHERE COALESCE(cat_source,'') != 'user'"
    if transaction_ids is None:
        return db.q(base)
    ids = list(transaction_ids)
    rows = []
    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        rows += db.q(f"{base} AND transaction_id IN ({','.join('?' * len(chunk))})", chunk)
    return rows


def categorize(transaction_ids=None) -> int:
    """Run the categorization order over every non-user transaction (or just the given ids).

    Returns how many rows changed. Flags and display names set by rules are only ever set,
    never cleared, so a manual exclude survives the next sync.
    """
    loaded = _load_rules()
    memory = {m["merchant_key"]: m["cat_id"] for m in db.q("SELECT merchant_key, cat_id FROM merchant_memory")}
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
            if act.get("display_name"):
                display = act["display_name"]
            if act.get("cat_id"):
                cat, source = act["cat_id"], f"rule:{r['id']}"
                break
        if not cat:
            mk = merchant_key(t)
            if mk and mk in memory:
                cat, source = memory[mk], "merchant"
        if not cat:
            code = categories.ensure(t.get("category_detail") or t.get("category"))
            if code:
                cat, source = code, "plaid"
        if not cat:
            cat, source = categories.UNCAT, "none"
        before = (t.get("cat_id"), t.get("cat_source"), int(t.get("excluded") or 0), int(t.get("is_transfer") or 0), t.get("display_name"))
        if before != (cat, source, excluded, transfer, display):
            updates.append((cat, source, excluded, transfer, display, t["transaction_id"]))
    if updates:
        db.many("UPDATE transactions SET cat_id=?, cat_source=?, excluded=?, is_transfer=?, display_name=? WHERE transaction_id=?", updates)
    db.run("UPDATE rules SET hits=(SELECT COUNT(*) FROM transactions WHERE cat_source='rule:' || rules.id)")
    for rid in matched_rules:
        db.run("UPDATE rules SET last_applied=datetime('now') WHERE id=?", (rid,))
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
    return db.one("""SELECT COUNT(*) AS n FROM transactions
                     WHERE transaction_id != ? AND LOWER(TRIM(COALESCE(merchant_name, name, ''))) = ?
                       AND COALESCE(cat_source,'') != 'user' AND COALESCE(cat_id,'') != ?""",
                  (transaction_id, key, cat_id))["n"]


def preview(conditions, limit=10):
    """Count non-user transactions matching the conditions, plus the newest few as a sample."""
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
```

- [ ] **Step 4: Run all tests**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass. If `test_import_rows_use_primary_category` fails because `add_tx` passes `category` as the Plaid primary, confirm `conftest.add_tx` writes the `category` column (it does, parameter `category`).

- [ ] **Step 5: Commit**

```bash
git add backend/rules.py backend/tests/test_rules.py
git diff --cached --name-only
git commit -m "Rules: categorization engine, merchant memory, preview, similar count

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Run the engine at startup, after sync, and after import

**Files:**
- Modify: `backend/app.py` (imports, `_startup`, `import_csv`)
- Modify: `backend/plaid_sync.py` (imports, `sync_item`)

- [ ] **Step 1: Import the modules in `app.py`**

In `backend/app.py`, after the line `import maintenance  # noqa: E402`, add:

```python
import categories  # noqa: E402
import rules  # noqa: E402
```

- [ ] **Step 2: Seed and backfill at startup**

In `backend/app.py`, replace:

```python
def _startup():
    threading.Timer(5, _auto_sync).start()
```

with:

```python
def _startup():
    categories.seed()
    missing = rules.missing_ids()
    if missing:
        n = rules.categorize(missing)
        log.info("categorized %s transactions that had no category", n)
    threading.Timer(5, _auto_sync).start()
```

- [ ] **Step 3: Categorize imported rows**

In `backend/app.py` inside `import_csv`, replace:

```python
    after = db.one("SELECT COUNT(*) AS n FROM transactions WHERE account_id=?", (account_id,))["n"]
    return {"read": len(out), "added": after - before, "duplicates": len(out) - (after - before)}
```

with:

```python
    after = db.one("SELECT COUNT(*) AS n FROM transactions WHERE account_id=?", (account_id,))["n"]
    rules.categorize([r[0] for r in out])
    return {"read": len(out), "added": after - before, "duplicates": len(out) - (after - before)}
```

- [ ] **Step 4: Categorize synced rows**

In `backend/plaid_sync.py`, after `import logos` add:

```python
import rules
```

Then replace:

```python
        db.many(TX_UPSERT, [_tx_row(t, item_id) for t in pages_added + pages_modified])
        for t in pages_removed:
```

with:

```python
        db.many(TX_UPSERT, [_tx_row(t, item_id) for t in pages_added + pages_modified])
        rules.categorize([_d(t)["transaction_id"] for t in pages_added + pages_modified])
        for t in pages_removed:
```

- [ ] **Step 5: Check the backend still imports**

Run from the project root:
```
.venv\Scripts\python -c "import os, sys; os.environ['OPEN_BROWSER']='0'; sys.path.insert(0,'backend'); import app; print('ok')"
```
Expected: `ok`. This imports against the real `data/finance.db` and only adds columns and tables, which is safe.

- [ ] **Step 6: Run the tests**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/plaid_sync.py
git diff --cached --name-only
git commit -m "Run the categorization engine at startup, after sync, and after import

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Categories API

**Files:**
- Modify: `backend/app.py` (add a section before `# ---------- transactions ----------`)

- [ ] **Step 1: Add the endpoints**

In `backend/app.py`, directly above the line `# ---------- transactions ----------`, add:

```python
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
```

- [ ] **Step 2: Check the backend imports**

Run: `.venv\Scripts\python -c "import os, sys; os.environ['OPEN_BROWSER']='0'; sys.path.insert(0,'backend'); import app; print(len(app.app.routes))"`
Expected: a number, no traceback.

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git diff --cached --name-only
git commit -m "API: list, add, and edit categories

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Transactions list fields, filters, and PATCH

**Files:**
- Modify: `backend/app.py` (`transactions` route and a new PATCH route)

- [ ] **Step 1: Replace the list route**

In `backend/app.py`, replace the whole `transactions` function (from `@app.get("/api/transactions")` through `return {"total": total, "rows": rows}`) with:

```python
@app.get("/api/transactions")
def transactions(account_id: str | None = None, q: str | None = None, cat_id: str | None = None,
                 spending_only: int = 0, limit: int = 100, offset: int = 0):
    where, args = ["1=1"], []
    if account_id:
        where.append("t.account_id=?")
        args.append(account_id)
    if cat_id:
        where.append("t.cat_id=?")
        args.append(cat_id)
    if spending_only:
        where.append("COALESCE(t.excluded,0)=0 AND COALESCE(t.is_transfer,0)=0 AND COALESCE(c.type,'expense') != 'transfer'")
    if q:
        where.append("(LOWER(COALESCE(t.display_name,'')||' '||COALESCE(t.merchant_name,'')||' '||COALESCE(t.name,'')||' '||COALESCE(c.name,'')||' '||COALESCE(c.group_name,'')) LIKE ?)")
        args.append(f"%{q.lower()}%")
    w = " AND ".join(where)
    frm = "FROM transactions t LEFT JOIN accounts a ON a.account_id=t.account_id LEFT JOIN categories c ON c.id=t.cat_id"
    total = db.one(f"SELECT COUNT(*) AS n {frm} WHERE {w}", args)["n"]
    rows = db.q(f"""SELECT t.transaction_id, t.account_id, t.date, t.amount, t.name, t.merchant_name, t.display_name, t.pending,
                    t.category, t.category_detail, t.logo_url, t.notes, t.reviewed,
                    t.cat_id, t.cat_source, COALESCE(t.excluded,0) AS excluded, COALESCE(t.is_transfer,0) AS is_transfer,
                    c.name AS cat_name, c.group_name AS cat_group, c.type AS cat_type,
                    a.name AS account_name, a.mask
                    {frm} WHERE {w} ORDER BY t.date DESC, t.transaction_id LIMIT ? OFFSET ?""", args + [min(limit, 500), offset])
    for r in rows:
        r["logo"] = logos.merchant_logo(r["merchant_name"] or r["name"], r.pop("logo_url"))
        r["display_amount"] = -(r["amount"] or 0)  # Plaid: positive = money out
    return {"total": total, "rows": rows}


class TxPatch(BaseModel):
    cat_id: str | None = None
    notes: str | None = None
    excluded: bool | None = None
    is_transfer: bool | None = None
    display_name: str | None = None


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
    if sets:
        db.run(f"UPDATE transactions SET {', '.join(sets)} WHERE transaction_id=?", args + [transaction_id])
    row = db.one("""SELECT t.transaction_id, t.cat_id, t.cat_source, COALESCE(t.excluded,0) AS excluded, COALESCE(t.is_transfer,0) AS is_transfer,
                           t.display_name, t.notes, c.name AS cat_name, c.group_name AS cat_group, c.type AS cat_type
                    FROM transactions t LEFT JOIN categories c ON c.id=t.cat_id WHERE t.transaction_id=?""", (transaction_id,))
    row["similar"] = similar
    return row
```

- [ ] **Step 2: Check the backend imports**

Run: `.venv\Scripts\python -c "import os, sys; os.environ['OPEN_BROWSER']='0'; sys.path.insert(0,'backend'); import app; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Smoke test the list query against the real database read-only**

Run:
```
.venv\Scripts\python -c "import os, sys; os.environ['OPEN_BROWSER']='0'; sys.path.insert(0,'backend'); import app; r=app.transactions(limit=2); print(r['total'], [ (x['cat_id'], x['cat_name'], x['cat_source']) for x in r['rows']])"
```
Expected: a total above 2,000 and two tuples. Category fields may be `None` until the server restarts and the startup backfill runs. That is fine here.

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git diff --cached --name-only
git commit -m "API: transaction list carries category fields and filters; PATCH a transaction

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Rules API

**Files:**
- Modify: `backend/app.py` (new section after the transactions section, before `# ---------- summary ----------`)

- [ ] **Step 1: Add the endpoints**

In `backend/app.py`, directly above the line `# ---------- summary ----------`, add:

```python
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
ACT_KEYS = {"cat_id", "display_name", "exclude", "transfer"}


def _clean_rule(conditions: dict, actions: dict, need_actions: bool = True):
    """Drop empty values, check bounds, return (conditions, actions) ready to store."""
    c = {k: v for k, v in (conditions or {}).items() if k in COND_KEYS and v not in (None, "", False)}
    a = {k: v for k, v in (actions or {}).items() if k in ACT_KEYS and v not in (None, "", False)}
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


@app.post("/api/rules")
def add_rule(req: RuleReq):
    if not req.name.strip():
        raise HTTPException(400, "Name is required")
    c, a = _clean_rule(req.conditions, req.actions)
    cur = db.run("INSERT INTO rules (name, priority, enabled, conditions, actions, created_from) VALUES (?,?,?,?,?,?)",
                 (req.name.strip(), req.priority, 1 if req.enabled else 0, json.dumps(c), json.dumps(a), req.created_from))
    rid = cur.lastrowid
    changed = rules.categorize() if req.apply_past else 0
    return {**_rule_out(db.one("SELECT * FROM rules WHERE id=?", (rid,))), "changed": changed}


@app.put("/api/rules/{rule_id}")
def update_rule(rule_id: int, req: RuleReq):
    if not db.one("SELECT 1 FROM rules WHERE id=?", (rule_id,)):
        raise HTTPException(404, "Rule not found")
    if not req.name.strip():
        raise HTTPException(400, "Name is required")
    c, a = _clean_rule(req.conditions, req.actions)
    db.run("UPDATE rules SET name=?, priority=?, enabled=?, conditions=?, actions=? WHERE id=?",
           (req.name.strip(), req.priority, 1 if req.enabled else 0, json.dumps(c), json.dumps(a), rule_id))
    changed = rules.categorize() if req.apply_past else 0
    return {**_rule_out(db.one("SELECT * FROM rules WHERE id=?", (rule_id,))), "changed": changed}


@app.delete("/api/rules/{rule_id}")
def delete_rule(rule_id: int):
    db.run("DELETE FROM rules WHERE id=?", (rule_id,))
    return {"ok": True}
```

Note on route order: `/api/rules/preview` and `/api/rules/apply` are POST routes and `/api/rules/{rule_id}` only has PUT and DELETE, so there is no clash.

- [ ] **Step 2: Check the backend imports**

Run: `.venv\Scripts\python -c "import os, sys; os.environ['OPEN_BROWSER']='0'; sys.path.insert(0,'backend'); import app; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git diff --cached --name-only
git commit -m "API: rules CRUD, preview, and apply

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Summary ignores transfers and excluded items

**Files:**
- Modify: `backend/app.py` (`summary` route)

- [ ] **Step 1: Replace the monthly query**

In `backend/app.py` inside `summary`, replace:

```python
    m = db.one("""SELECT COALESCE(SUM(CASE WHEN amount>0 AND COALESCE(category,'') NOT IN ('TRANSFER_OUT','LOAN_PAYMENTS') THEN amount END),0) AS spent,
                         COALESCE(SUM(CASE WHEN amount<0 AND COALESCE(category,'') NOT IN ('TRANSFER_IN') THEN -amount END),0) AS income
                  FROM transactions WHERE substr(date,1,7)=? AND pending=0""", (month,))
```

with:

```python
    m = db.one("""SELECT COALESCE(SUM(CASE WHEN t.amount>0 AND COALESCE(c.type,'expense')='expense' THEN t.amount END),0) AS spent,
                         COALESCE(SUM(CASE WHEN t.amount<0 AND c.type='income' THEN -t.amount END),0) AS income
                  FROM transactions t LEFT JOIN categories c ON c.id=t.cat_id
                  WHERE substr(t.date,1,7)=? AND t.pending=0 AND COALESCE(t.excluded,0)=0 AND COALESCE(t.is_transfer,0)=0""", (month,))
```

- [ ] **Step 2: Check it runs**

Run: `.venv\Scripts\python -c "import os, sys; os.environ['OPEN_BROWSER']='0'; sys.path.insert(0,'backend'); import app; s=app.summary(); print(sorted(s.keys()))"`
Expected: the key list including `spent_month` and `income_month`.

- [ ] **Step 3: Run the full test suite**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git diff --cached --name-only
git commit -m "Summary: spending and income follow category type and flags

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Frontend API wrappers, category cache, toast event

**Files:**
- Modify: `frontend/src/api.js`
- Create: `frontend/src/categories.js`
- Modify: `frontend/src/App.jsx:59`

- [ ] **Step 1: Add the wrappers**

In `frontend/src/api.js`, after the line `  importCsv: (id, body) => req('POST', ...),` and before the closing `}` of the `api` object, add:

```js
  categories: () => req('GET', '/api/categories'),
  addCategory: (body) => req('POST', '/api/categories', body),
  patchCategory: (id, body) => req('PATCH', `/api/categories/${encodeURIComponent(id)}`, body),
  patchTransaction: (id, body) => req('PATCH', `/api/transactions/${encodeURIComponent(id)}`, body),
  rules: () => req('GET', '/api/rules'),
  addRule: (body) => req('POST', '/api/rules', body),
  updateRule: (id, body) => req('PUT', `/api/rules/${id}`, body),
  deleteRule: (id) => req('DELETE', `/api/rules/${id}`),
  previewRule: (body) => req('POST', '/api/rules/preview', body),
  applyRules: () => req('POST', '/api/rules/apply'),
```

Also add, after the `titleCase` export at the bottom of `api.js`:

```js
export const toast = (msg) => window.dispatchEvent(new CustomEvent('toast', { detail: msg }))
```

- [ ] **Step 2: Create the category cache**

`frontend/src/categories.js`:

```js
import { useEffect, useState } from 'react'
import { api } from './api'

// One shared copy of the grouped category list. Components subscribe; adding a category refreshes everyone.
let cache = null
let inflight = null
const listeners = new Set()

export function loadCategories(force = false) {
  if (cache && !force) return Promise.resolve(cache)
  if (!inflight || force) {
    inflight = api.categories().then((g) => { cache = g; inflight = null; listeners.forEach((l) => l(g)); return g })
  }
  return inflight
}

export function useCategories() {
  const [groups, setGroups] = useState(cache || [])
  useEffect(() => {
    listeners.add(setGroups)
    loadCategories().then(setGroups).catch(() => {})
    return () => listeners.delete(setGroups)
  }, [])
  return groups
}

export const flatCategories = (groups) => groups.flatMap((g) => g.categories.map((c) => ({ ...c, group_name: g.group_name })))

export const categoryLabel = (groups, id) => {
  const c = flatCategories(groups).find((x) => x.id === id)
  return c ? `${c.group_name} · ${c.name}` : 'Uncategorized'
}
```

- [ ] **Step 3: Let any component raise a toast**

In `frontend/src/App.jsx`, after the line:

```js
  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(''), 5000); return () => clearTimeout(t) } }, [toast])
```

add:

```js
  useEffect(() => {
    const onToast = (e) => setToast(e.detail)
    window.addEventListener('toast', onToast)
    return () => window.removeEventListener('toast', onToast)
  }, [])
```

- [ ] **Step 4: Build**

Run from `frontend\`: `npm run build`
Expected: `✓ built`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api.js frontend/src/categories.js frontend/src/App.jsx
git diff --cached --name-only
git commit -m "Frontend: API wrappers for categories and rules, shared category cache, toast event

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: CategoryPicker component

**Files:**
- Create: `frontend/src/components/CategoryPicker.jsx`

- [ ] **Step 1: Write the component**

```jsx
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useCategories, flatCategories, loadCategories } from '../categories'

const inp = { height: 32, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', padding: '0 8px', fontSize: 13 }

// A category badge. Click to search and pick another category, or add a new one.
export default function CategoryPicker({ value, onChange, compact = false }) {
  const groups = useCategories()
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [adding, setAdding] = useState(false)
  const [draft, setDraft] = useState({ name: '', group_name: '', type: 'expense' })
  const [err, setErr] = useState('')
  const box = useRef(null)

  const all = flatCategories(groups)
  const current = all.find((c) => c.id === value)

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const needle = q.trim().toLowerCase()
  const visible = all
    .filter((c) => !c.hidden || c.id === value)
    .filter((c) => !needle || `${c.group_name} ${c.name}`.toLowerCase().includes(needle))
  const byGroup = []
  for (const c of visible) {
    const g = byGroup.find((x) => x.name === c.group_name)
    if (g) g.items.push(c); else byGroup.push({ name: c.group_name, items: [c] })
  }

  const close = () => { setOpen(false); setQ(''); setAdding(false); setErr('') }
  const pick = (id) => { close(); if (id !== value) onChange(id) }
  const onKey = (e) => {
    if (e.key === 'Escape') close()
    if (e.key === 'Enter' && visible.length) { e.preventDefault(); pick(visible[0].id) }
  }
  const add = async (e) => {
    e.preventDefault()
    try {
      const c = await api.addCategory(draft)
      await loadCategories(true)
      pick(c.id)
    } catch (x) { setErr(x.message) }
  }

  return (
    <span ref={box} style={{ position: 'relative', display: 'inline-block' }}>
      <button type="button" onClick={(e) => { e.stopPropagation(); setOpen(!open) }} className="press" title="Change category"
        style={{ font: 'inherit', fontSize: compact ? 11 : 12, lineHeight: 1.4, color: 'var(--text2)', background: 'var(--hover)', border: '1px solid var(--line)', borderRadius: 999, padding: '1px 9px', whiteSpace: 'nowrap' }}>
        {current ? `${current.group_name} · ${current.name}` : 'Uncategorized'}
      </button>
      {open && (
        <div style={{ position: 'absolute', zIndex: 60, top: 'calc(100% + 4px)', left: 0, width: 300, maxHeight: 380, overflowY: 'auto', background: 'var(--card)', border: '1px solid var(--line3)', borderRadius: 10, boxShadow: '0 12px 40px rgba(0,0,0,.35)', padding: 8 }}>
          <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} placeholder="Search categories"
            style={{ ...inp, width: '100%', height: 34, marginBottom: 6 }} />
          {byGroup.map((g) => (
            <div key={g.name}>
              <div style={{ fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)', padding: '6px 6px 2px' }}>{g.name}</div>
              {g.items.map((c) => (
                <button key={c.id} type="button" onClick={() => pick(c.id)}
                  style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 8px', borderRadius: 6, border: 0, background: c.id === value ? 'var(--active)' : 'transparent', color: 'var(--text)', fontSize: 13 }}>
                  {c.name}{c.custom ? <span style={{ marginLeft: 6, fontSize: 10, color: 'var(--muted)' }}>custom</span> : null}
                </button>
              ))}
            </div>
          ))}
          {!visible.length && <div style={{ padding: 8, fontSize: 13, color: 'var(--muted)' }}>No match.</div>}
          <div style={{ borderTop: '1px solid var(--line2)', marginTop: 6, paddingTop: 6 }}>
            {!adding ? (
              <button type="button" onClick={() => { setAdding(true); setDraft({ name: q.trim(), group_name: '', type: 'expense' }) }}
                style={{ border: 0, background: 'transparent', color: 'var(--info)', fontSize: 13, padding: '4px 8px' }}>New category</button>
            ) : (
              <form onSubmit={add} style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 4 }}>
                <input required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Name" style={inp} />
                <input required list="cat-groups" value={draft.group_name} onChange={(e) => setDraft({ ...draft, group_name: e.target.value })} placeholder="Group" style={inp} />
                <datalist id="cat-groups">{groups.map((g) => <option key={g.group_name} value={g.group_name} />)}</datalist>
                <select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })} style={inp}>
                  <option value="expense">Expense</option>
                  <option value="income">Income</option>
                  <option value="transfer">Transfer</option>
                </select>
                {err && <div style={{ fontSize: 12, color: 'var(--neg)' }}>{err}</div>}
                <button type="submit" className="press" style={{ height: 32, borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }}>Add</button>
              </form>
            )}
          </div>
        </div>
      )}
    </span>
  )
}
```

- [ ] **Step 2: Build**

Run from `frontend\`: `npm run build`
Expected: `✓ built`. The component is not used yet, so the bundle is unchanged apart from tree shaking.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CategoryPicker.jsx
git diff --cached --name-only
git commit -m "Frontend: CategoryPicker component

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: TxList with picker, display name, muted rows, make-rule bar

**Files:**
- Modify: `frontend/src/components/TxList.jsx` (whole file)

- [ ] **Step 1: Replace the file**

`frontend/src/components/TxList.jsx`:

```jsx
import { useEffect, useRef, useState } from 'react'
import { api, money, shortDate, toast } from '../api'
import { useCategories, categoryLabel } from '../categories'
import CategoryPicker from './CategoryPicker'
import Logo from './Logo'

const PAGE = 100

export default function TxList({ accountId, catId, spendingOnly = false, showAccount = true, compact = false, refreshKey = 0, onChanged }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [prompt, setPrompt] = useState(null) // { id, merchant, catId, similar }
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)
  const groups = useCategories()

  const load = async (offset = 0, query = q) => {
    setLoading(true)
    try {
      const r = await api.transactions({ account_id: accountId, cat_id: catId, spending_only: spendingOnly ? 1 : undefined, q: query, limit: PAGE, offset })
      setTotal(r.total)
      setRows((prev) => (offset ? [...prev, ...r.rows] : r.rows))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0, q) }, [accountId, catId, spendingOnly, refreshKey]) // eslint-disable-line

  const onSearch = (v) => {
    setQ(v)
    clearTimeout(timer.current)
    timer.current = setTimeout(() => load(0, v), 250)
  }

  const setCategory = async (t, newCatId) => {
    try {
      const r = await api.patchTransaction(t.transaction_id, { cat_id: newCatId })
      setRows((prev) => prev.map((x) => (x.transaction_id === t.transaction_id ? { ...x, ...r } : x)))
      const merchant = t.display_name || t.merchant_name || t.name
      setPrompt(r.similar > 0 ? { id: t.transaction_id, merchant, catId: newCatId, similar: r.similar } : null)
      onChanged && onChanged()
    } catch (e) { toast(e.message) }
  }

  const makeRule = async () => {
    if (!prompt) return
    setBusy(true)
    try {
      const r = await api.addRule({
        name: `${prompt.merchant} → ${categoryLabel(groups, prompt.catId)}`,
        conditions: { merchant: prompt.merchant },
        actions: { cat_id: prompt.catId },
        created_from: prompt.id,
        apply_past: true,
      })
      toast(`Rule saved. ${r.changed} past transaction${r.changed === 1 ? '' : 's'} updated.`)
      setPrompt(null)
      load(0, q)
      onChanged && onChanged()
    } catch (e) { toast(e.message) } finally { setBusy(false) }
  }

  return (
    <div>
      <label style={{ display: 'flex', alignItems: 'center', gap: 8, background: 'var(--bg)', border: '1px solid var(--line)', borderRadius: 8, padding: '0 12px', height: 40, marginBottom: 10 }}>
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ color: 'var(--muted)' }}><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        <span className="sr-only">Search transactions</span>
        <input value={q} onChange={(e) => onSearch(e.target.value)} placeholder="Search merchant, category"
          style={{ flex: 1, background: 'transparent', border: 0, outline: 'none', color: 'var(--text)', fontSize: 14 }} />
        <span style={{ fontSize: 12, color: 'var(--muted)' }}>{total.toLocaleString()} total</span>
      </label>
      <div style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
        {rows.map((t, i) => {
          const quiet = t.excluded || t.is_transfer || t.cat_type === 'transfer'
          return (
            <div key={t.transaction_id}>
              <div className="rise" style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: compact ? '9px 14px' : '11px 16px',
                borderTop: i ? '1px solid var(--line2)' : 0, animationDelay: `${Math.min(i, 20) * 0.025}s`, opacity: quiet ? 0.6 : 1,
              }}>
                <span style={{ width: 50, fontSize: 12, color: 'var(--muted)', flexShrink: 0 }}>{shortDate(t.date)}</span>
                <Logo src={t.logo} name={t.merchant_name || t.name} size={compact ? 28 : 32} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 14, fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {t.display_name || t.merchant_name || t.name}
                    {t.pending ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--warn)' }}>Pending</span> : null}
                    {t.excluded ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>Excluded</span> : null}
                    {t.is_transfer ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>Transfer</span> : null}
                  </span>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2, fontSize: 12, color: 'var(--muted)', flexWrap: 'wrap' }}>
                    <CategoryPicker value={t.cat_id} compact={compact} onChange={(id) => setCategory(t, id)} />
                    {showAccount && t.account_name ? <span>{t.account_name}{t.mask ? ' ' + t.mask : ''}</span> : null}
                  </span>
                </span>
                <span className="num" style={{ fontSize: 14, fontWeight: 600, color: t.display_amount > 0 ? 'var(--pos)' : 'var(--text)' }}>
                  {t.display_amount > 0 ? '+' : ''}{money(t.display_amount)}
                </span>
              </div>
              {prompt && prompt.id === t.transaction_id && (
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 10, padding: '8px 16px 10px', fontSize: 13, color: 'var(--text2)', background: 'var(--hover)' }}>
                  <span style={{ flex: 1 }}>
                    Always file <b>{prompt.merchant}</b> as <b>{categoryLabel(groups, prompt.catId)}</b>? {prompt.similar} past transaction{prompt.similar === 1 ? '' : 's'} would change.
                  </span>
                  <button type="button" onClick={makeRule} disabled={busy} className="press"
                    style={{ height: 30, padding: '0 12px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 12 }}>
                    {busy ? 'Saving...' : 'Make rule'}
                  </button>
                  <button type="button" onClick={() => setPrompt(null)} style={{ height: 30, padding: '0 10px', borderRadius: 8, border: '1px solid var(--line)', background: 'transparent', color: 'var(--text2)', fontSize: 12 }}>Not now</button>
                </div>
              )}
            </div>
          )
        })}
        {!rows.length && !loading && <div style={{ padding: 16, fontSize: 14, color: 'var(--muted)' }}>No transactions yet.</div>}
      </div>
      {rows.length < total && (
        <button type="button" onClick={() => load(rows.length)} disabled={loading} className="press"
          style={{ marginTop: 10, width: '100%', height: 40, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', fontSize: 13 }}>
          {loading ? 'Loading...' : `Load more (${(total - rows.length).toLocaleString()} left)`}
        </button>
      )}
    </div>
  )
}
```

Note the list container lost `overflow: hidden` so the picker popover can extend past a row. Rows have no background, so the rounded border still reads correctly.

- [ ] **Step 2: Build**

Run from `frontend\`: `npm run build`
Expected: `✓ built`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/TxList.jsx
git diff --cached --name-only
git commit -m "Frontend: category picker, display names, muted rows, and the make-rule prompt in the transaction list

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 14: Transactions page filters

**Files:**
- Modify: `frontend/src/pages/Transactions.jsx` (whole file)

- [ ] **Step 1: Replace the file**

```jsx
import { useState } from 'react'
import { money } from '../api'
import { useCategories } from '../categories'
import Odometer from '../components/Odometer'
import TxList from '../components/TxList'

const sel = { height: 36, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--card)', color: 'var(--text)', padding: '0 8px' }

export default function Transactions({ summary, accounts, refreshKey, onChanged }) {
  const [acct, setAcct] = useState('')
  const [cat, setCat] = useState('')
  const [spendingOnly, setSpendingOnly] = useState(false)
  const groups = useCategories()
  const s = summary || {}
  const linked = accounts.filter((a) => !a.manual)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14 }}>
        {[['Spent this month', s.spent_month], ['Income this month', s.income_month]].map(([l, v], i) => (
          <div key={l} className="card rise" style={{ padding: '14px 18px', animationDelay: `${i * 0.06}s` }}>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>{l}</div>
            <div style={{ marginTop: 4, fontSize: 22, fontWeight: 700, color: i ? 'var(--pos)' : 'var(--text)' }}><Odometer value={money(v || 0)} delay={i * 0.15} /></div>
          </div>
        ))}
        <div className="card rise" style={{ padding: '14px 18px', animationDelay: '.12s' }}>
          <div style={{ fontSize: 12, color: 'var(--muted)' }}>Transactions stored</div>
          <div className="num" style={{ marginTop: 4, fontSize: 22, fontWeight: 700 }}>{(s.tx_count || 0).toLocaleString()}</div>
        </div>
      </div>
      <div className="card rise" style={{ padding: 18, animationDelay: '.18s' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h2 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>All transactions</h2>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', fontSize: 13, color: 'var(--muted)' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>Account
              <select value={acct} onChange={(e) => setAcct(e.target.value)} style={sel}>
                <option value="">All accounts</option>
                {linked.map((a) => <option key={a.account_id} value={a.account_id}>{a.official_name || a.name}{a.mask ? ` ${a.mask}` : ''}</option>)}
              </select>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>Category
              <select value={cat} onChange={(e) => setCat(e.target.value)} style={sel}>
                <option value="">All categories</option>
                {groups.map((g) => (
                  <optgroup key={g.group_name} label={g.group_name}>
                    {g.categories.filter((c) => !c.hidden).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
            <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={spendingOnly} onChange={(e) => setSpendingOnly(e.target.checked)} /> Hide transfers and excluded
            </label>
          </div>
        </div>
        <TxList accountId={acct || undefined} catId={cat || undefined} spendingOnly={spendingOnly} refreshKey={refreshKey} onChanged={onChanged} />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Pass `onChanged` from App**

In `frontend/src/App.jsx`, replace:

```jsx
            {page === 'transactions' && <Transactions summary={summary} accounts={accounts} refreshKey={refreshKey} />}
```

with:

```jsx
            {page === 'transactions' && <Transactions summary={summary} accounts={accounts} refreshKey={refreshKey} onChanged={refresh} />}
```

- [ ] **Step 3: Build**

Run from `frontend\`: `npm run build`
Expected: `✓ built`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Transactions.jsx frontend/src/App.jsx
git diff --cached --name-only
git commit -m "Frontend: category filter and spending-only toggle on the Transactions page

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 15: Rules page, rules tab

**Files:**
- Create: `frontend/src/pages/Rules.jsx`
- Modify: `frontend/src/App.jsx:27` and `:130`

- [ ] **Step 1: Write the page with the Rules tab**

`frontend/src/pages/Rules.jsx`:

```jsx
import { useEffect, useRef, useState } from 'react'
import { api, money, toast } from '../api'
import { useCategories, categoryLabel, loadCategories } from '../categories'

const inp = { height: 36, borderRadius: 8, border: '1px solid var(--line)', background: 'var(--bg)', color: 'var(--text)', padding: '0 10px', fontSize: 13 }
const btn = { height: 36, padding: '0 14px', borderRadius: 8, border: 0, background: 'var(--accent)', color: '#fff', fontWeight: 600, fontSize: 13 }
const ghost = { ...btn, background: 'transparent', border: '1px solid var(--line)', color: 'var(--text2)', fontWeight: 500 }
const EMPTY = { name: '', priority: 100, enabled: true, conditions: {}, actions: {} }

function describe(rule, groups) {
  const c = rule.conditions, a = rule.actions, parts = []
  if (c.merchant) parts.push(`merchant has "${c.merchant}"`)
  if (c.text) parts.push(`text has "${c.text}"`)
  if (c.amount_min != null && c.amount_max != null) parts.push(`amount ${money(c.amount_min)} to ${money(c.amount_max)}`)
  else if (c.amount_min != null) parts.push(`amount at least ${money(c.amount_min)}`)
  else if (c.amount_max != null) parts.push(`amount at most ${money(c.amount_max)}`)
  if (c.account_id) parts.push('one account')
  if (c.day_min != null || c.day_max != null) parts.push(`day ${c.day_min ?? 1} to ${c.day_max ?? 31}`)
  const acts = []
  if (a.cat_id) acts.push(`file as ${categoryLabel(groups, a.cat_id)}`)
  if (a.display_name) acts.push(`show as "${a.display_name}"`)
  if (a.exclude) acts.push('exclude from totals')
  if (a.transfer) acts.push('mark as transfer')
  return `When ${parts.join(' and ') || 'anything'}: ${acts.join(', ') || 'nothing'}`
}

function RuleEditor({ initial, accounts, groups, onSaved, onCancel }) {
  const [r, setR] = useState(initial)
  const [preview, setPreview] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const timer = useRef(null)
  const setC = (k, v) => setR((x) => ({ ...x, conditions: { ...x.conditions, [k]: v } }))
  const setA = (k, v) => setR((x) => ({ ...x, actions: { ...x.actions, [k]: v } }))

  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      api.previewRule({ conditions: r.conditions, actions: r.actions }).then(setPreview).catch(() => setPreview(null))
    }, 300)
    return () => clearTimeout(timer.current)
  }, [r.conditions, r.actions])

  const save = async (applyPast) => {
    setBusy(true); setErr('')
    try {
      const body = { ...r, apply_past: applyPast }
      const out = r.id ? await api.updateRule(r.id, body) : await api.addRule(body)
      if (applyPast) toast(`${out.changed} transaction${out.changed === 1 ? '' : 's'} updated.`)
      onSaved()
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const c = r.conditions, a = r.actions
  return (
    <div className="card" style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <input value={r.name} onChange={(e) => setR({ ...r, name: e.target.value })} placeholder="Rule name" style={{ ...inp, flex: '2 1 220px' }} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)' }}>Priority
          <input type="number" value={r.priority} onChange={(e) => setR({ ...r, priority: Number(e.target.value) || 0 })} style={{ ...inp, width: 80 }} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)' }}>
          <input type="checkbox" checked={r.enabled} onChange={(e) => setR({ ...r, enabled: e.target.checked })} /> Enabled
        </label>
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>When all of these match</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10 }}>
        <input value={c.merchant || ''} onChange={(e) => setC('merchant', e.target.value)} placeholder="Merchant contains" style={inp} />
        <input value={c.text || ''} onChange={(e) => setC('text', e.target.value)} placeholder="Raw text contains" style={inp} />
        <input type="number" step="0.01" value={c.amount_min ?? ''} onChange={(e) => setC('amount_min', e.target.value === '' ? null : e.target.value)} placeholder="Amount at least" style={inp} />
        <input type="number" step="0.01" value={c.amount_max ?? ''} onChange={(e) => setC('amount_max', e.target.value === '' ? null : e.target.value)} placeholder="Amount at most" style={inp} />
        <select value={c.account_id || ''} onChange={(e) => setC('account_id', e.target.value || null)} style={inp}>
          <option value="">Any account</option>
          {accounts.map((x) => <option key={x.account_id} value={x.account_id}>{x.official_name || x.name}{x.mask ? ` ${x.mask}` : ''}</option>)}
        </select>
        <div style={{ display: 'flex', gap: 6 }}>
          <input type="number" min="1" max="31" value={c.day_min ?? ''} onChange={(e) => setC('day_min', e.target.value === '' ? null : e.target.value)} placeholder="Day from" style={{ ...inp, width: '50%' }} />
          <input type="number" min="1" max="31" value={c.day_max ?? ''} onChange={(e) => setC('day_max', e.target.value === '' ? null : e.target.value)} placeholder="Day to" style={{ ...inp, width: '50%' }} />
        </div>
      </div>
      <div style={{ fontSize: 12, color: 'var(--muted)' }}>Amounts follow the bank: positive is money out, negative is money in.</div>
      <div style={{ fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>Then</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 10, alignItems: 'center' }}>
        <select value={a.cat_id || ''} onChange={(e) => setA('cat_id', e.target.value || null)} style={inp}>
          <option value="">Leave category alone</option>
          {groups.map((g) => (
            <optgroup key={g.group_name} label={g.group_name}>
              {g.categories.filter((x) => !x.hidden).map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
            </optgroup>
          ))}
        </select>
        <input value={a.display_name || ''} onChange={(e) => setA('display_name', e.target.value)} placeholder="Show merchant as" style={inp} />
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}><input type="checkbox" checked={!!a.exclude} onChange={(e) => setA('exclude', e.target.checked)} /> Exclude from totals</label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13 }}><input type="checkbox" checked={!!a.transfer} onChange={(e) => setA('transfer', e.target.checked)} /> Mark as transfer</label>
      </div>
      <div style={{ fontSize: 13, color: 'var(--text2)' }}>
        {preview ? `Matches ${preview.count.toLocaleString()} transaction${preview.count === 1 ? '' : 's'} you have not set by hand` : 'Add a condition to see matches'}
        {preview && preview.sample.length > 0 && (
          <span style={{ color: 'var(--muted)' }}>, for example {preview.sample.slice(0, 3).map((s) => s.display_name || s.merchant_name || s.name).join(', ')}</span>
        )}
      </div>
      {err && <div style={{ fontSize: 13, color: 'var(--neg)' }}>{err}</div>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
        <button type="button" className="press" disabled={busy} onClick={() => save(false)} style={btn}>Save</button>
        <button type="button" className="press" disabled={busy} onClick={() => save(true)} style={btn}>Save and apply to past</button>
        <button type="button" onClick={onCancel} style={ghost}>Cancel</button>
      </div>
    </div>
  )
}

function RulesTab({ accounts, groups }) {
  const [rules, setRules] = useState([])
  const [editing, setEditing] = useState(null)
  const load = () => api.rules().then(setRules).catch((e) => toast(e.message))
  useEffect(() => { load() }, [])

  const toggle = async (r) => {
    try { await api.updateRule(r.id, { ...r, enabled: !r.enabled }); load() } catch (e) { toast(e.message) }
  }
  const remove = async (r) => {
    try { await api.deleteRule(r.id); load() } catch (e) { toast(e.message) }
  }
  const applyAll = async () => {
    try { const out = await api.applyRules(); toast(`${out.changed} transaction${out.changed === 1 ? '' : 's'} updated.`); load() } catch (e) { toast(e.message) }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 13, color: 'var(--muted)' }}>Rules run in priority order, lowest first, on every sync. They never change a category you set by hand.</div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button type="button" onClick={applyAll} style={ghost}>Re-run all rules</button>
          <button type="button" className="press" onClick={() => setEditing({ ...EMPTY })} style={btn}>New rule</button>
        </div>
      </div>
      {editing && !editing.id && <RuleEditor initial={editing} accounts={accounts} groups={groups} onSaved={() => { setEditing(null); load() }} onCancel={() => setEditing(null)} />}
      <div style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
        {rules.map((r, i) => (
          <div key={r.id} style={{ borderTop: i ? '1px solid var(--line2)' : 0 }}>
            {editing && editing.id === r.id ? (
              <div style={{ padding: 10 }}><RuleEditor initial={editing} accounts={accounts} groups={groups} onSaved={() => { setEditing(null); load() }} onCancel={() => setEditing(null)} /></div>
            ) : (
              <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 12, padding: '12px 16px', opacity: r.enabled ? 1 : 0.55 }}>
                <span className="num" style={{ width: 40, fontSize: 12, color: 'var(--muted)' }}>{r.priority}</span>
                <span style={{ flex: '1 1 260px', minWidth: 0 }}>
                  <span style={{ display: 'block', fontSize: 14, fontWeight: 600 }}>{r.name}</span>
                  <span style={{ display: 'block', fontSize: 12, color: 'var(--muted)' }}>{describe(r, groups)}</span>
                </span>
                <span className="num" style={{ fontSize: 12, color: 'var(--muted)' }}>{r.hits} hit{r.hits === 1 ? '' : 's'}</span>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
                  <input type="checkbox" checked={r.enabled} onChange={() => toggle(r)} /> On
                </label>
                <button type="button" onClick={() => setEditing({ ...r })} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12 }}>Edit</button>
                <button type="button" onClick={() => remove(r)} style={{ ...ghost, height: 30, padding: '0 10px', fontSize: 12, color: 'var(--neg)' }}>Delete</button>
              </div>
            )}
          </div>
        ))}
        {!rules.length && <div style={{ padding: 16, fontSize: 14, color: 'var(--muted)' }}>No rules yet. Change a category on any transaction and choose Make rule, or click New rule.</div>}
      </div>
    </div>
  )
}

export default function Rules({ accounts }) {
  const [tab, setTab] = useState('rules')
  const groups = useCategories()
  const tabBtn = (k, l) => (
    <button key={k} type="button" onClick={() => setTab(k)} aria-current={tab === k ? 'page' : undefined}
      style={{ height: 34, padding: '0 14px', borderRadius: 8, border: 0, background: tab === k ? 'var(--active)' : 'transparent', color: tab === k ? 'var(--text)' : 'var(--text2)', fontWeight: tab === k ? 600 : 400, fontSize: 13 }}>{l}</button>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', gap: 6 }}>{tabBtn('rules', 'Rules')}{tabBtn('categories', 'Categories')}</div>
      {tab === 'rules' && <RulesTab accounts={accounts} groups={groups} />}
      {tab === 'categories' && <div style={{ fontSize: 14, color: 'var(--muted)' }}>Categories tab arrives in the next task.</div>}
    </div>
  )
}
```

- [ ] **Step 2: Add the nav item and page**

In `frontend/src/App.jsx`, replace:

```js
const PAGES = [['dashboard', 'Dashboard'], ['transactions', 'Transactions'], ['debt', 'Debt payoff']]
```

with:

```js
const PAGES = [['dashboard', 'Dashboard'], ['transactions', 'Transactions'], ['rules', 'Rules'], ['debt', 'Debt payoff']]
```

After the import line `import Debt from './pages/Debt'` add:

```js
import Rules from './pages/Rules'
```

And replace:

```jsx
            {page === 'debt' && <Debt />}
```

with:

```jsx
            {page === 'rules' && <Rules accounts={accounts} />}
            {page === 'debt' && <Debt />}
```

- [ ] **Step 3: Build**

Run from `frontend\`: `npm run build`
Expected: `✓ built`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Rules.jsx frontend/src/App.jsx
git diff --cached --name-only
git commit -m "Frontend: Rules page with editor, live match count, enable switch, and apply to past

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 16: Categories tab

**Files:**
- Modify: `frontend/src/pages/Rules.jsx`

- [ ] **Step 1: Add the CategoriesTab component**

In `frontend/src/pages/Rules.jsx`, above `export default function Rules`, add:

```jsx
function CategoriesTab({ groups }) {
  const [editing, setEditing] = useState(null) // { id, name }
  const [draft, setDraft] = useState({ name: '', group_name: '', type: 'expense' })
  const [showHidden, setShowHidden] = useState(false)

  const patch = async (id, body) => {
    try { await api.patchCategory(id, body); await loadCategories(true) } catch (e) { toast(e.message) }
  }
  const add = async (e) => {
    e.preventDefault()
    try { await api.addCategory(draft); await loadCategories(true); setDraft({ name: '', group_name: '', type: 'expense' }); toast('Category added.') } catch (x) { toast(x.message) }
  }
  const commitRename = async () => {
    if (editing && editing.name.trim()) await patch(editing.id, { name: editing.name.trim() })
    setEditing(null)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <form onSubmit={add} className="card" style={{ padding: 14, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
        <span style={{ fontSize: 13, color: 'var(--muted)' }}>New category</span>
        <input required value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder="Name" style={{ ...inp, flex: '1 1 160px' }} />
        <input required list="cat-groups-tab" value={draft.group_name} onChange={(e) => setDraft({ ...draft, group_name: e.target.value })} placeholder="Group" style={{ ...inp, flex: '1 1 160px' }} />
        <datalist id="cat-groups-tab">{groups.map((g) => <option key={g.group_name} value={g.group_name} />)}</datalist>
        <select value={draft.type} onChange={(e) => setDraft({ ...draft, type: e.target.value })} style={inp}>
          <option value="expense">Expense</option>
          <option value="income">Income</option>
          <option value="transfer">Transfer</option>
        </select>
        <button type="submit" className="press" style={btn}>Add</button>
        <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: 'var(--muted)' }}>
          <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} /> Show hidden
        </label>
      </form>
      {groups.map((g) => {
        const items = g.categories.filter((c) => showHidden || !c.hidden)
        if (!items.length) return null
        return (
          <section key={g.group_name}>
            <h3 style={{ margin: '0 0 8px', fontSize: 12, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--muted)' }}>{g.group_name}</h3>
            <div style={{ border: '1px solid var(--line)', borderRadius: 12 }}>
              {items.map((c, i) => (
                <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 14px', borderTop: i ? '1px solid var(--line2)' : 0, fontSize: 14, opacity: c.hidden ? 0.55 : 1 }}>
                  {editing && editing.id === c.id ? (
                    <input autoFocus value={editing.name} onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                      onBlur={commitRename} onKeyDown={(e) => { if (e.key === 'Enter') commitRename(); if (e.key === 'Escape') setEditing(null) }}
                      style={{ ...inp, height: 30, flex: 1 }} />
                  ) : (
                    <button type="button" onClick={() => c.id !== 'UNCATEGORIZED' && setEditing({ id: c.id, name: c.name })} title="Rename"
                      style={{ flex: 1, textAlign: 'left', border: 0, background: 'transparent', color: 'var(--text)', font: 'inherit', padding: 0 }}>
                      {c.name}{c.custom ? <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--muted)' }}>custom</span> : null}
                    </button>
                  )}
                  <span style={{ fontSize: 12, color: 'var(--muted)', width: 64 }}>{c.type}</span>
                  {c.id !== 'UNCATEGORIZED' && (
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
                      <input type="checkbox" checked={!c.hidden} onChange={(e) => patch(c.id, { hidden: !e.target.checked })} /> Shown
                    </label>
                  )}
                </div>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
```

Then replace:

```jsx
      {tab === 'categories' && <div style={{ fontSize: 14, color: 'var(--muted)' }}>Categories tab arrives in the next task.</div>}
```

with:

```jsx
      {tab === 'categories' && <CategoriesTab groups={groups} />}
```

- [ ] **Step 2: Build**

Run from `frontend\`: `npm run build`
Expected: `✓ built`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Rules.jsx
git diff --cached --name-only
git commit -m "Frontend: Categories tab with rename, hide, and add

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 17: Verify end to end and hand off

**Files:**
- Modify: `HANDOFF.md` (local only, never committed)

- [ ] **Step 1: Full test run**

Run: `.venv\Scripts\python -m pytest backend/tests -q`
Expected: all pass, no warnings about missing modules.

- [ ] **Step 2: Backend import check against the real database**

Run: `.venv\Scripts\python -c "import os, sys; os.environ['OPEN_BROWSER']='0'; sys.path.insert(0,'backend'); import app, categories, rules; categories.seed(); print('missing before backfill:', len(rules.missing_ids()))"`
Expected: a number. Do not run `rules.categorize()` here; the server's startup does it.

- [ ] **Step 3: Server restart**

The running server has the old backend. It must be restarted by the user: close the `start.bat` window and run `start.bat` again. If the engineer is an agent with browser tools, check whether the server has restarted by opening `http://127.0.0.1:8765` and looking for the Rules nav item after a hard refresh. If the Rules item appears but category badges all read "Uncategorized", the backend has not restarted yet.

- [ ] **Step 4: Browser checks once the server has restarted**

In the running app:
1. Transactions page: every row shows a category badge with a group and name. Rows for card payments and transfers look muted.
2. Click a badge, type part of a category, press Enter. The badge changes. If other transactions share the merchant, the make-rule bar appears with a count. Click Make rule and see the toast.
3. Category filter narrows the list. "Hide transfers and excluded" removes payments.
4. Rules page lists the rule just made with a hit count. Edit it, change the merchant text, watch the match count update. Save and apply to past.
5. Categories tab: rename a category, hide one, add a custom one, and pick the custom one from a badge.
6. Dashboard: "Spent this month" no longer includes card payments.

- [ ] **Step 5: Update the local handoff**

Rewrite the "Where things stand", "In progress", and "Next" sections of `HANDOFF.md` to say the categories and rules round is built, which browser checks passed, which did not, and whether the server was restarted. Do not commit `HANDOFF.md`.

- [ ] **Step 6: Final commit check**

Run: `git status --short`
Expected: only `HANDOFF.md` modified, which is gitignored and so does not appear. If anything else shows, commit it with a message describing it. Then `git push origin main`.
