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
