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
