"""Create rule from a transaction: the draft, the new conditions, the preview count, and the Cash and ATM group."""
import os

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import categories  # noqa: E402
import db  # noqa: E402
import rules  # noqa: E402
import tags  # noqa: E402
import transfers  # noqa: E402
from conftest import add_tx  # noqa: E402

WD, ATM_FEE = "TRANSFER_OUT_WITHDRAWAL", "BANK_FEES_ATM_FEES"


@pytest.fixture
def atm(fresh):
    db.run("INSERT INTO accounts (account_id, name, type) VALUES ('chk','Checking','depository')")
    db.run("INSERT INTO accounts (account_id, name, type) VALUES ('sav','Savings','depository')")
    add_tx("w1", amount=60.0, account="chk", date="2026-10-01", name="TRANSFUND 1820 S MAIN ANYTOWN", detail=WD)
    add_tx("w2", amount=40.0, account="chk", date="2026-10-08", name="TRANSFUND 900 E OAK ANYTOWN", detail=WD)
    add_tx("w3", amount=200.0, account="chk", date="2026-10-09", name="Electronic Withdrawal", detail=WD)
    add_tx("r1", amount=-3.0, account="chk", date="2026-10-02", name="ATM FEE REBATE", detail=ATM_FEE)
    rules.categorize()
    return db


def test_cash_and_atm_group_is_seeded(fresh):
    got = {c["id"]: (c["group_name"], c["name"], c["type"]) for c in db.q("SELECT * FROM categories WHERE group_name='Cash and ATM'")}
    assert got == {
        "EXTRA_ATM_WITHDRAWAL": ("Cash and ATM", "ATM withdrawal", "expense"),
        ATM_FEE: ("Cash and ATM", "ATM fee", "expense"),
        "EXTRA_ATM_DEPOSIT": ("Cash and ATM", "ATM deposit", "income"),
        "EXTRA_MOBILE_CHECK_DEPOSIT": ("Cash and ATM", "Mobile check deposit", "income"),
    }


def test_old_atm_fee_name_is_moved_but_a_renamed_one_is_kept(fresh):
    db.run("UPDATE categories SET group_name='Bank fees', name='Atm fees' WHERE id=?", (ATM_FEE,))
    categories.seed()
    assert categories.get(ATM_FEE)["name"] == "ATM fee"
    db.run("UPDATE categories SET group_name='Bank fees', name='Cash machine fees' WHERE id=?", (ATM_FEE,))
    categories.seed()
    assert categories.get(ATM_FEE)["name"] == "Cash machine fees"


def test_cash_and_atm_group_sits_after_bank_fees(fresh):
    names = [g["group_name"] for g in categories.grouped()]
    assert names.index("Cash and ATM") == names.index("Bank fees") + 1


def test_name_key_stops_at_the_first_number():
    assert rules.name_key({"name": "TRANSFUND 1820 S MAIN ANYTOWN"}) == "TRANSFUND"
    assert rules.name_key({"name": "PAI ATM 4660 W ELM ANYTOWN"}) == "PAI ATM"
    assert rules.name_key({"name": "Electronic Withdrawal"}) == "Electronic Withdrawal"
    assert rules.name_key({"name": "SQ *JOES BBQ 1234"}) == "SQ *JOES BBQ"
    assert rules.name_key({"name": "Coffee", "merchant_name": "Corner Coffee"}) == "Corner Coffee"
    assert rules.name_key({"name": "12345 STORE"}) == "12345 STORE"


def test_draft_comes_from_what_was_changed(atm):
    app.patch_transaction("w1", app.TxPatch(cat_id="EXTRA_ATM_WITHDRAWAL", display_name="ATM"))
    tags.add("w1", "Cash")
    d = rules.draft("w1")
    assert d["conditions"] == {"merchant": "TRANSFUND", "direction": "out"}
    assert d["actions"] == {"cat_id": "EXTRA_ATM_WITHDRAWAL", "display_name": "ATM", "tags": ["Cash"]}
    assert d["bank_category"] == {"id": WD, "name": "Withdrawal"}


def test_draft_leaves_out_a_category_the_app_picked(atm):
    assert "cat_id" not in rules.draft("w2")["actions"]


def test_direction_and_bank_category_conditions(atm):
    t = {"amount": 60.0, "category_detail": WD}
    assert rules.match({"direction": "out", "bank_category": WD}, t)
    assert not rules.match({"direction": "in"}, t)
    assert not rules.match({"bank_category": ATM_FEE}, t)
    assert not rules.match({"direction": "out"}, {"amount": None})


def test_preview_counts_rows_that_would_change(atm):
    p = rules.preview({"bank_category": WD, "direction": "out"}, actions={"cat_id": "EXTRA_ATM_WITHDRAWAL"})
    assert (p["count"], p["changes"]) == (3, 3)
    db.run("UPDATE transactions SET cat_id='EXTRA_ATM_WITHDRAWAL' WHERE transaction_id='w2'")
    p = rules.preview({"bank_category": WD}, actions={"cat_id": "EXTRA_ATM_WITHDRAWAL"})
    assert (p["count"], p["changes"]) == (3, 2)


def test_rule_with_new_conditions_saves_and_applies(atm):
    r = app.add_rule(app.RuleReq(name="ATM", conditions={"merchant": "TRANSFUND", "direction": "out"},
                                 actions={"cat_id": "EXTRA_ATM_WITHDRAWAL"}, apply_past=True))
    assert r["changed"] == 2
    got = {x["transaction_id"]: x["cat_id"] for x in db.q("SELECT transaction_id, cat_id FROM transactions")}
    assert got["w1"] == got["w2"] == "EXTRA_ATM_WITHDRAWAL" and got["w3"] == WD


def test_bad_direction_is_refused(atm):
    with pytest.raises(app.HTTPException):
        app.add_rule(app.RuleReq(name="x", conditions={"direction": "sideways"}, actions={"exclude": True}))


def test_atm_rows_are_never_linked_as_transfers(atm):
    db.run("UPDATE transactions SET cat_id='EXTRA_ATM_WITHDRAWAL' WHERE transaction_id='w1'")
    add_tx("d1", amount=-60.0, account="sav", date="2026-10-01", name="DEPOSIT")
    assert transfers.detect() == 0
    assert db.one("SELECT COUNT(*) n FROM transfers")["n"] == 0


def test_draft_endpoint(atm):
    assert app.rule_draft("w1")["conditions"]["merchant"] == "TRANSFUND"
    with pytest.raises(app.HTTPException):
        app.rule_draft("nope")


def _made(tid):
    return rules.made_by([db.one("SELECT * FROM transactions WHERE transaction_id=?", (tid,))]).get(tid, [])


def test_made_by_names_the_rule_that_set_the_category(atm):
    r = app.add_rule(app.RuleReq(name="ATM", conditions={"merchant": "TRANSFUND"},
                                 actions={"cat_id": "EXTRA_ATM_WITHDRAWAL"}, apply_past=True))
    assert _made("w1") == [r["id"]]
    assert _made("w3") == []
    app.patch_transaction("w1", app.TxPatch(cat_id="GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE"))
    assert _made("w1") == []


def test_made_by_counts_tags_names_and_excludes(atm):
    t = app.add_rule(app.RuleReq(name="Tag", conditions={"merchant": "TRANSFUND"}, actions={"tags": ["Cash"]}, apply_past=True))
    n = app.add_rule(app.RuleReq(name="Name", conditions={"merchant": "Electronic"}, actions={"display_name": "Bank pull", "exclude": True}, apply_past=True))
    assert _made("w2") == [t["id"]]
    assert _made("w3") == [n["id"]]
    assert app.transactions()["rows"][0]["rules"] is not None


def test_new_rules_go_last_and_order_decides_the_winner(atm):
    a = app.add_rule(app.RuleReq(name="A", conditions={"merchant": "TRANSFUND"}, actions={"cat_id": "EXTRA_ATM_WITHDRAWAL"}, apply_past=True))
    b = app.add_rule(app.RuleReq(name="B", conditions={"merchant": "TRANSFUND"}, actions={"cat_id": ATM_FEE}, apply_past=True))
    assert [r["id"] for r in app.list_rules()] == [a["id"], b["id"]]
    assert _made("w1") == [a["id"]]
    assert app.order_rules(app.RuleOrder(ids=[b["id"], a["id"]]))["changed"] == 2
    assert db.one("SELECT cat_id FROM transactions WHERE transaction_id='w1'")["cat_id"] == ATM_FEE
    app.update_rule(a["id"], app.RuleReq(name="A2", conditions={"merchant": "TRANSFUND"}, actions={"cat_id": "EXTRA_ATM_WITHDRAWAL"}))
    assert [r["id"] for r in app.list_rules()] == [b["id"], a["id"]]
    with pytest.raises(app.HTTPException):
        app.order_rules(app.RuleOrder(ids=[a["id"]]))
