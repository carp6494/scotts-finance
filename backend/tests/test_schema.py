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
