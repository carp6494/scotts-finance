"""Tags on transactions, tags from rules, and the tag filter."""
import json
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import rules  # noqa: E402
import tags  # noqa: E402
from conftest import add_tx  # noqa: E402

FOOD = "FOOD_AND_DRINK_FAST_FOOD"


def names(tid):
    return [g["name"] for g in tags.for_transactions([tid]).get(tid, [])]


def add_rule(conditions, actions, priority=100):
    c, a = app._clean_rule(conditions, actions)
    return db.run("INSERT INTO rules (name, priority, conditions, actions) VALUES ('r',?,?,?)",
                  (priority, json.dumps(c), json.dumps(a))).lastrowid


def test_add_and_remove_a_tag(fresh):
    add_tx("a")
    out = app.tag_transaction("a", app.TagReq(name="  Tax  "))
    assert [g["name"] for g in out["tags"]] == ["Tax"]
    tag_id = out["tags"][0]["id"]
    assert app.untag_transaction("a", tag_id)["tags"] == []
    assert tags.get(tag_id)["name"] == "Tax"  # the tag itself stays


def test_names_ignore_case_and_get_different_colors(fresh):
    one, same, two = tags.ensure("tax"), tags.ensure("TAX"), tags.ensure("business")
    assert one["id"] == same["id"] and same["name"] == "tax"
    assert one["color"] != two["color"] and two["color"] in tags.PALETTE


def test_bad_names_are_refused(fresh):
    add_tx("a")
    for bad in ("", "   ", "x" * 33):
        with pytest.raises(HTTPException) as e:
            app.tag_transaction("a", app.TagReq(name=bad))
        assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        app.tag_transaction("missing", app.TagReq(name="tax"))
    assert e.value.status_code == 404


def test_rule_adds_tags_even_to_rows_set_by_hand(fresh):
    add_tx("a", merchant="Clinic")
    add_tx("b", merchant="Clinic", cat_id=FOOD, source="user")
    add_tx("c", merchant="Other")
    add_rule({"merchant": "clinic"}, {"tags": ["tax", "medical"]})
    assert rules.categorize() >= 2
    assert names("a") == ["medical", "tax"] and names("b") == ["medical", "tax"] and names("c") == []
    assert db.one("SELECT cat_id, cat_source FROM transactions WHERE transaction_id='b'") == {"cat_id": FOOD, "cat_source": "user"}


def test_every_matching_rule_tags_not_only_the_first(fresh):
    add_tx("a", merchant="Clinic")
    add_rule({"merchant": "clinic"}, {"cat_id": FOOD, "tags": ["one"]}, priority=1)
    add_rule({"merchant": "clinic"}, {"tags": ["two"]}, priority=2)
    rules.categorize()
    assert names("a") == ["one", "two"]


def test_a_removed_tag_is_not_added_back_by_the_rule(fresh):
    add_tx("a", merchant="Clinic")
    add_rule({"merchant": "clinic"}, {"tags": ["tax"]})
    rules.categorize()
    tags.remove("a", tags.by_name("tax")["id"])
    assert rules.categorize() == 0 and names("a") == []
    tags.add("a", "tax")  # adding it by hand again is allowed
    assert names("a") == ["tax"]


def test_running_rules_twice_adds_nothing_new(fresh):
    add_tx("a", merchant="Clinic")
    add_rule({"merchant": "clinic"}, {"tags": ["tax"]})
    assert rules.categorize() == 1
    assert rules.categorize() == 0


def test_rule_keeps_working_after_a_rename_and_stops_after_a_delete(fresh):
    add_tx("a", merchant="Clinic")
    rid = add_rule({"merchant": "clinic"}, {"tags": ["tax"]})
    tag_id = tags.by_name("tax")["id"]
    app.patch_tag(tag_id, app.TagPatch(name="Taxes"))
    rules.categorize()
    assert names("a") == ["Taxes"]
    assert app._rule_out(db.one("SELECT * FROM rules WHERE id=?", (rid,)))["actions"]["tags"] == ["Taxes"]
    app.delete_tag(tag_id)
    add_tx("b", merchant="Clinic")
    rules.categorize()
    assert names("a") == [] and names("b") == []


def test_rename_cannot_take_another_tags_name(fresh):
    tags.ensure("tax")
    other = tags.ensure("business")
    with pytest.raises(HTTPException) as e:
        app.patch_tag(other["id"], app.TagPatch(name="TAX"))
    assert e.value.status_code == 400
    with pytest.raises(HTTPException):
        app.patch_tag(other["id"], app.TagPatch(color="#123456"))
    assert app.patch_tag(other["id"], app.TagPatch(color=tags.PALETTE[3]))["color"] == tags.PALETTE[3]


def test_tag_filter_search_and_counts(fresh):
    add_tx("a", merchant="Clinic", amount=40, cat_id=FOOD)
    add_tx("b", merchant="Cafe", amount=10, cat_id=FOOD)
    tag_id = tags.add("a", "tax")["id"]
    out = app.transactions(tag_id=tag_id)
    assert out["total"] == 1 and out["rows"][0]["transaction_id"] == "a" and out["rows"][0]["tags"][0]["name"] == "tax"
    assert app.transactions(q="tax")["total"] == 1
    listed = {g["name"]: g["count"] for g in app.list_tags()["tags"]}
    assert listed == {"tax": 1}
    both = {r["transaction_id"]: r["tags"] for r in app.transactions()["rows"]}
    assert both["b"] == []


def test_summary_follows_the_tag_filter(fresh):
    from datetime import date
    today = date.today().isoformat()
    add_tx("a", amount=40, cat_id=FOOD, date=today)
    add_tx("b", amount=10, cat_id=FOOD, date=today)
    tag_id = tags.add("a", "tax")["id"]
    assert app.summary()["spent_month"] == 50
    assert app.summary(tag_id=tag_id)["spent_month"] == 40


def test_prune_drops_links_to_deleted_transactions(fresh):
    add_tx("a")
    tag_id = tags.add("a", "tax")["id"]
    db.run("DELETE FROM transactions WHERE transaction_id='a'")
    tags.prune()
    assert db.q("SELECT * FROM transaction_tags") == [] and tags.get(tag_id)
