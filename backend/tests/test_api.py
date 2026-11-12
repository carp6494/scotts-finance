"""Route functions called directly, against the temp database from conftest."""
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import rules  # noqa: E402
from conftest import add_tx  # noqa: E402


def seeded(fresh):
    add_tx("a", merchant="Joes BBQ", amount=20, detail="FOOD_AND_DRINK_FAST_FOOD", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")
    add_tx("b", merchant="Joes BBQ", amount=15, detail="FOOD_AND_DRINK_FAST_FOOD", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")
    add_tx("c", merchant="Card payment", amount=100, detail="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", cat_id="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT", source="plaid")
    add_tx("d", merchant="Refund", amount=-5, detail="FOOD_AND_DRINK_FAST_FOOD", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")


def test_list_carries_category_fields_and_spending_only(fresh):
    seeded(fresh)
    rows = app.transactions()["rows"]
    assert {"cat_id", "cat_name", "cat_group", "cat_type", "cat_source", "excluded", "is_transfer", "display_name"} <= set(rows[0])
    assert app.transactions()["total"] == 4
    assert app.transactions(spending_only=1)["total"] == 3  # the card payment is a transfer type
    db.run("UPDATE transactions SET excluded=1 WHERE transaction_id='d'")
    assert app.transactions(spending_only=1)["total"] == 2


def test_search_matches_category_name(fresh):
    seeded(fresh)
    assert app.transactions(q="fast food")["total"] == 3


def test_patch_category_locks_and_remembers(fresh):
    seeded(fresh)
    out = app.patch_transaction("a", app.TxPatch(cat_id="FOOD_AND_DRINK_RESTAURANT"))
    assert out["cat_source"] == "user" and out["cat_name"] == "Restaurant"
    assert out["similar"] == 1  # b differs, d has a different merchant
    assert db.one("SELECT cat_id FROM merchant_memory WHERE merchant_key='joes bbq'")["cat_id"] == "FOOD_AND_DRINK_RESTAURANT"
    notes = app.patch_transaction("b", app.TxPatch(notes="hello"))
    assert notes["cat_source"] == "plaid" and notes["notes"] == "hello"


def test_patch_rejects_unknown_category(fresh):
    seeded(fresh)
    with pytest.raises(HTTPException) as e:
        app.patch_transaction("a", app.TxPatch(cat_id="NOPE"))
    assert e.value.status_code == 400


def test_rule_validation(fresh):
    bad = [
        dict(conditions={"amount_min": 100, "amount_max": 5}, actions={"cat_id": "FOOD_AND_DRINK_COFFEE"}),
        dict(conditions={"day_min": 0, "day_max": 10}, actions={"cat_id": "FOOD_AND_DRINK_COFFEE"}),
        dict(conditions={"day_max": 32}, actions={"cat_id": "FOOD_AND_DRINK_COFFEE"}),
        dict(conditions={"merchant": "x"}, actions={"cat_id": "NOPE"}),
        dict(conditions={"merchant": ""}, actions={"cat_id": "FOOD_AND_DRINK_COFFEE"}),
        dict(conditions={"merchant": "x"}, actions={}),
    ]
    for body in bad:
        with pytest.raises(HTTPException) as e:
            app.add_rule(app.RuleReq(name="r", **body))
        assert e.value.status_code == 400, body


def test_zero_bounds_are_kept(fresh):
    r = app.add_rule(app.RuleReq(name="zero", conditions={"amount_min": 0, "amount_max": 20}, actions={"cat_id": "FOOD_AND_DRINK_COFFEE"}))
    assert r["conditions"] == {"amount_min": 0.0, "amount_max": 20.0}
    with pytest.raises(HTTPException):
        app.add_rule(app.RuleReq(name="neg", conditions={"amount_min": 0, "amount_max": -5}, actions={"cat_id": "FOOD_AND_DRINK_COFFEE"}))


def test_rule_crud_preview_apply(fresh):
    seeded(fresh)
    p = app.preview_rule(app.PreviewReq(conditions={"merchant": "joes"}))
    assert p["count"] == 2
    r = app.add_rule(app.RuleReq(name="Joes", conditions={"merchant": "joes"}, actions={"cat_id": "FOOD_AND_DRINK_RESTAURANT"}, apply_past=True))
    assert r["changed"] == 2
    assert [x["id"] for x in app.list_rules()] == [r["id"]]
    u = app.update_rule(r["id"], app.RuleReq(name="Joes", enabled=False, conditions={"merchant": "joes"}, actions={"cat_id": "FOOD_AND_DRINK_RESTAURANT"}))
    assert u["enabled"] is False
    with pytest.raises(HTTPException) as e:
        app.update_rule(9999, app.RuleReq(name="x", conditions={"merchant": "x"}, actions={"cat_id": "FOOD_AND_DRINK_COFFEE"}))
    assert e.value.status_code == 404
    assert app.delete_rule(r["id"]) == {"ok": True}
    assert app.list_rules() == []


def test_summary_ignores_transfers_and_excluded(fresh):
    seeded(fresh)
    today = __import__("datetime").date.today().isoformat()
    db.run("UPDATE transactions SET date=?", (today,))
    add_tx("inc", merchant="Pay", amount=-1000, cat_id="INCOME_WAGES", source="plaid", date=today)
    db.run("UPDATE transactions SET excluded=1 WHERE transaction_id='b'")
    s = app.summary()
    assert s["spent_month"] == 20.0  # a only: b excluded, c transfer type, d is money in
    assert s["income_month"] == 1000.0
