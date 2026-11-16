"""Money owed back: open items, paybacks, suggestions, and what the bank does to them."""
import os
from datetime import date

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import splits  # noqa: E402
from conftest import add_tx  # noqa: E402

FOOD = "FOOD_AND_DRINK_RESTAURANT"
GROC = "FOOD_AND_DRINK_GROCERIES"
INCOME = "INCOME_OTHER_INCOME"
THIS_MONTH = date.today().strftime("%Y-%m") + "-01"


def dinner(tid="d", who="Sam", amount=80.0, when="2026-11-05"):
    """A charge split in half: the owner's meal, and a part owed back. Returns the owed line id."""
    add_tx(tid, amount=amount, cat_id=FOOD, date=when)
    splits.save(tid, [{"cat_id": FOOD, "amount": amount / 2}, {"owed_by": who, "amount": amount / 2}])
    return next(l["id"] for l in splits.lines(tid) if l["owed_by"])


def open_of(split_id):
    for p in splits.owed()["people"]:
        for it in p["items"]:
            if it["split_id"] == split_id:
                return it["open"]
    return 0.0


def test_open_items_group_by_person_ignoring_case(fresh):
    dinner("d1", "Sam")
    dinner("d2", " sam ", amount=20.0)
    dinner("d3", "Alex", amount=10.0)
    o = splits.owed()
    assert o["total"] == 55.0
    assert [(p["name"], p["total"]) for p in o["people"]] == [("Sam", 50.0), ("Alex", 5.0)]
    assert o["names"] == ["Alex", "Sam"]


def test_linked_payment_clears_the_item_and_is_not_income(fresh):
    sid = dinner(when=THIS_MONTH)
    add_tx("v", amount=-40.0, cat_id=INCOME, date=THIS_MONTH, name="VENMO CASHOUT")
    assert app.summary()["income_month"] == 40.0
    splits.link(sid, payment_id="v")
    o = splits.owed()
    assert o["total"] == 0 and o["people"] == []
    assert app.summary()["income_month"] == 0.0
    row = next(r for r in app.transactions()["rows"] if r["transaction_id"] == "v")
    assert row["payback_from"] == "Sam"


def test_partial_payment_and_one_payment_for_two_items(fresh):
    a = dinner("d1", amount=80.0)
    b = dinner("d2", amount=20.0)
    add_tx("v1", amount=-25.0, date="2026-11-06")
    splits.link(a, payment_id="v1")
    assert open_of(a) == 15.0
    with pytest.raises(ValueError):
        splits.link(b, payment_id="v1")
    add_tx("v2", amount=-25.0, date="2026-11-07")
    splits.link(a, payment_id="v2")
    splits.link(b, payment_id="v2")
    assert splits.owed()["total"] == 0


def test_cash_unlink_and_paid_back_lately(fresh):
    sid = dinner()
    pb = splits.link(sid, cash=True)
    o = splits.owed()
    assert o["total"] == 0 and [r["split_id"] for r in o["recent"]] == [sid]
    with pytest.raises(ValueError):
        splits.link(sid, cash=True)
    splits.unlink(pb["id"])
    assert splits.owed()["total"] == 40.0
    with pytest.raises(LookupError):
        splits.unlink(pb["id"])


def test_payments_are_deposits_on_or_after_the_charge(fresh):
    sid = dinner(when="2026-11-05")
    add_tx("early", amount=-40.0, date="2026-11-01")
    add_tx("late", amount=-40.0, date="2026-11-09")
    add_tx("charge", amount=12.0, date="2026-11-09")
    add_tx("pend", amount=-40.0, date="2026-11-10")
    db.run("UPDATE transactions SET pending=1 WHERE transaction_id='pend'")
    assert [p["transaction_id"] for p in splits.payments(sid)] == ["late"]


def test_suggestion_and_not_this(fresh):
    sid = dinner(when="2026-11-05")
    add_tx("v", amount=-40.0, date="2026-11-08", name="VENMO CASHOUT")
    add_tx("odd", amount=-39.0, date="2026-11-08")
    s = splits.owed()["suggestions"]
    assert [(x["split_id"], x["payment_id"], x["owed_by"]) for x in s] == [(sid, "v", "Sam")]
    splits.dismiss(sid, "v")
    assert splits.owed()["suggestions"] == []


def test_deleted_payment_reopens_the_item(fresh):
    sid = dinner()
    add_tx("v", amount=-40.0, date="2026-11-08")
    splits.link(sid, payment_id="v")
    db.run("DELETE FROM transactions WHERE transaction_id='v'")
    splits.prune()
    assert splits.owed()["total"] == 40.0


def test_resplit_keeps_paid_lines_and_guards_them(fresh):
    sid = dinner()
    splits.link(sid, cash=True)
    splits.save("d", [{"cat_id": GROC, "amount": 40}, {"owed_by": "sam", "amount": 40}])
    assert next(l["id"] for l in splits.lines("d") if l["owed_by"]) == sid
    assert db.one("SELECT COUNT(*) AS n FROM paybacks")["n"] == 1
    with pytest.raises(splits.PaybackLinked):
        splits.save("d", [{"cat_id": FOOD, "amount": 40}, {"owed_by": "Alex", "amount": 40}])
    with pytest.raises(splits.PaybackLinked):
        splits.unsplit("d")
    splits.unsplit("d", force=True)
    assert db.one("SELECT COUNT(*) AS n FROM paybacks")["n"] == 0


def test_unsplit_route_says_409_when_a_payback_is_linked(fresh):
    from fastapi import HTTPException
    sid = dinner()
    splits.link(sid, cash=True)
    with pytest.raises(HTTPException) as e:
        app.unsplit_transaction("d")
    assert e.value.status_code == 409
    assert app.unsplit_transaction("d", force=1) == {"ok": True}
