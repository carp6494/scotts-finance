import os


def test_uses_temp_database():
    import db
    assert str(db.DB_PATH) == os.environ["FINANCE_DB"]
    assert db.DB_PATH.name == "test.db"
