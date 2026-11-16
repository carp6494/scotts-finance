"""Split lines: saving, totals, unsplit, rules, and bank changes."""
import json
import os
from datetime import date

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import categories  # noqa: E402
import db  # noqa: E402
import rules  # noqa: E402
import splits  # noqa: E402
from conftest import add_tx  # noqa: E402

GROC = "FOOD_AND_DRINK_GROCERIES"
CLOTH = "GENERAL_MERCHANDISE_CLOTHING_AND_ACCESSORIES"
FOOD = "FOOD_AND_DRINK_RESTAURANT"
THIS_MONTH = date.today().strftime("%Y-%m") + "-01"  # the summary counts this month only


def spent(**kw):
    return app.summary(**kw)["spent_month"]


def store_trip(tid="w"):
    return splits.save(tid, [{"cat_id": GROC, "amount": 60}, {"cat_id": CLOTH, "amount": 40}])


def test_save_and_read_lines(fresh):
    add_tx("w", amount=100.0, cat_id=GROC)
    out = store_trip()
    assert [(l["cat_id"], l["amount"]) for l in out] == [(GROC, 60.0), (CLOTH, 40.0)]
    row = app.transactions()["rows"][0]
    assert [l["display_amount"] for l in row["splits"]] == [-60.0, -40.0] and row["split_off"] is None


def test_lines_must_add_up_and_be_valid(fresh):
    add_tx("w", amount=100.0)
    bad = (
        [{"cat_id": GROC, "amount": 100}],
        [{"cat_id": GROC, "amount": 60}, {"cat_id": CLOTH, "amount": 30}],
        [{"cat_id": GROC, "amount": 60}, {"amount": 40}],
        [{"cat_id": GROC, "amount": 60}, {"cat_id": CLOTH, "owed_by": "Sam", "amount": 40}],
        [{"cat_id": "NOPE", "amount": 60}, {"cat_id": CLOTH, "amount": 40}],
        [{"cat_id": GROC, "amount": 100}, {"cat_id": CLOTH, "amount": 0}],
    )
    for lines in bad:
        with pytest.raises(ValueError):
            splits.save("w", lines)
    assert splits.lines("w") == []


def test_pending_and_missing_cannot_be_split(fresh):
    add_tx("p", amount=50.0)
    db.run("UPDATE transactions SET pending=1 WHERE transaction_id='p'")
    with pytest.raises(ValueError):
        splits.save("p", [{"cat_id": GROC, "amount": 25}, {"cat_id": CLOTH, "amount": 25}])
    with pytest.raises(LookupError):
        splits.save("nope", [{"cat_id": GROC, "amount": 25}, {"cat_id": CLOTH, "amount": 25}])


def test_owed_line_only_on_money_out(fresh):
    add_tx("dep", amount=-50.0)
    with pytest.raises(ValueError):
        splits.save("dep", [{"cat_id": GROC, "amount": -25}, {"owed_by": "Sam", "amount": -25}])


def test_totals_count_each_line_and_skip_owed(fresh):
    add_tx("w", amount=100.0, cat_id=GROC, date=THIS_MONTH)
    add_tx("d", amount=80.0, cat_id=FOOD, date=THIS_MONTH)
    assert spent() == 180.0
    store_trip()
    splits.save("d", [{"cat_id": FOOD, "amount": 40}, {"owed_by": "Sam", "amount": 40}])
    assert spent() == 140.0
    assert (spent(cat_id=GROC), spent(cat_id=CLOTH), spent(cat_id=FOOD)) == (60.0, 40.0, 40.0)


def test_category_filter_and_search_follow_lines(fresh):
    add_tx("w", amount=100.0, cat_id=GROC)
    add_tx("x", amount=5.0, cat_id=GROC)
    store_trip()
    assert {r["transaction_id"] for r in app.transactions(cat_id=CLOTH)["rows"]} == {"w"}
    assert {r["transaction_id"] for r in app.transactions(cat_id=GROC)["rows"]} == {"w", "x"}
    word = categories.get(CLOTH)["name"].split()[0].lower()
    assert {r["transaction_id"] for r in app.transactions(q=word)["rows"]} == {"w"}


def test_unsplit_goes_back_to_one_category(fresh):
    add_tx("w", amount=100.0, category="FOOD_AND_DRINK", detail=GROC)
    rules.categorize(["w"])
    store_trip()
    splits.unsplit("w")
    assert splits.lines("w") == []
    assert db.one("SELECT cat_id FROM transactions WHERE transaction_id='w'")["cat_id"] == GROC


def test_category_rules_skip_split_rows(fresh):
    add_tx("w", amount=100.0, name="WALMART", detail=GROC)
    rules.categorize(["w"])
    store_trip()
    c, a = app._clean_rule({"merchant": "walmart"}, {"cat_id": CLOTH})
    db.run("INSERT INTO rules (name, priority, conditions, actions) VALUES ('r',1,?,?)", (json.dumps(c), json.dumps(a)))
    rules.categorize()
    assert db.one("SELECT cat_id FROM transactions WHERE transaction_id='w'")["cat_id"] == GROC


def test_bank_amount_change_sends_split_back_to_review(fresh):
    add_tx("w", amount=100.0)
    store_trip()
    db.run("UPDATE transactions SET reviewed=1, amount=103.5 WHERE transaction_id='w'")
    assert splits.check(["w"]) == ["w"]
    row = app.transactions()["rows"][0]
    assert row["reviewed"] == 0 and row["split_off"] == 3.5


def test_bank_delete_takes_lines_and_paybacks(fresh):
    add_tx("d", amount=80.0)
    add_tx("v", amount=-40.0, date="2026-11-08")
    splits.save("d", [{"cat_id": FOOD, "amount": 40}, {"owed_by": "Sam", "amount": 40}])
    owed_id = next(l["id"] for l in splits.lines("d") if l["owed_by"])
    splits.link(owed_id, payment_id="v")
    db.run("DELETE FROM transactions WHERE transaction_id='d'")
    splits.prune()
    assert db.one("SELECT COUNT(*) AS n FROM splits")["n"] == 0
    assert db.one("SELECT COUNT(*) AS n FROM paybacks")["n"] == 0


def test_routes_turn_errors_into_status_codes(fresh):
    from fastapi import HTTPException
    add_tx("w", amount=100.0)
    with pytest.raises(HTTPException) as e:
        app.save_splits("w", app.SplitReq(lines=[app.SplitLine(amount=100, cat_id=GROC)]))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        app.save_splits("nope", app.SplitReq(lines=[app.SplitLine(amount=50, cat_id=GROC), app.SplitLine(amount=50, cat_id=CLOTH)]))
    assert e.value.status_code == 404
    out = app.save_splits("w", app.SplitReq(lines=[app.SplitLine(amount=60, cat_id=GROC), app.SplitLine(amount=40, cat_id=CLOTH)]))
    assert len(out["splits"]) == 2
