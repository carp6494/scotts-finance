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


def page():
    return {r["transaction_id"]: r for r in app.transactions()["rows"]}


def test_options_name_the_other_account(own):
    payment("o1", "i1")
    add_tx("i2", amount=-50.0, account="sav", date="2026-11-05")
    info = transfers.for_transactions(["o1", "i1"])
    assert [o["id"] for o in info["o1"]["options"]] == ["i2", "i1"]
    card = info["o1"]["options"][1]
    assert card == {"id": "i1", "account": "Travel Card", "date": "2026-11-06", "display_amount": 50.0}
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
