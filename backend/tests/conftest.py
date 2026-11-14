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
import overture  # noqa: E402

overture.DB_PATH = _TMP / "overture.db"  # never read the real extract in data/


@pytest.fixture
def lookup():
    """Write a small Overture extract. Call it with rows of (name, address, city, region, postal, lat, lon, website)."""
    import sqlite3

    def make(rows):
        overture.reset()
        overture.DB_PATH.unlink(missing_ok=True)
        con = sqlite3.connect(overture.DB_PATH)
        con.executescript(overture.SCHEMA)
        for i, (name, address, city, region, postal, lat, lon, website) in enumerate(rows):
            con.execute("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (str(i), name, overture.norm_name(name), address, city, overture.norm_city(city), region, postal, "US",
                         lat, lon, website, "shop", None, 0.9))
        con.commit()
        con.close()

    yield make
    overture.reset()
    overture.DB_PATH.unlink(missing_ok=True)


@pytest.fixture
def fresh():
    """Empty every table the engine touches, then reseed categories."""
    for t in ("transactions", "rules", "merchant_memory", "merchant_places", "categories", "accounts",
              "tags", "transaction_tags", "removed_tags"):
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
