import json

import db
import rules
from conftest import add_tx

TX = {"transaction_id": "t1", "account_id": "acc-1", "date": "2026-11-15", "amount": 42.5,
      "name": "SQ *JOES BBQ 1234 SPRINGFIELD", "merchant_name": "Joes BBQ", "display_name": None}


def test_empty_conditions_match_everything():
    assert rules.match({}, TX)
    assert rules.match(None, TX)


def test_merchant_substring_case_insensitive():
    assert rules.match({"merchant": "joes"}, TX)
    assert rules.match({"merchant": "BBQ"}, TX)
    assert not rules.match({"merchant": "walmart"}, TX)


def test_merchant_checks_display_name_and_raw_name():
    assert rules.match({"merchant": "springfield"}, TX)  # from name
    assert rules.match({"merchant": "renamed"}, {**TX, "display_name": "Renamed Place"})


def test_text_matches_raw_name_only():
    assert rules.match({"text": "SQ *"}, TX)
    assert not rules.match({"text": "Joes BBQ"}, {**TX, "name": "SOMETHING ELSE"})


def test_amount_bounds_inclusive():
    assert rules.match({"amount_min": 42.5}, TX)
    assert rules.match({"amount_max": 42.5}, TX)
    assert rules.match({"amount_min": 40, "amount_max": 45}, TX)
    assert not rules.match({"amount_min": 50}, TX)
    assert not rules.match({"amount_max": 10}, TX)
    assert not rules.match({"amount_min": 1}, {**TX, "amount": None})


def test_account_exact():
    assert rules.match({"account_id": "acc-1"}, TX)
    assert not rules.match({"account_id": "acc-2"}, TX)


def test_day_of_month_bounds():
    assert rules.match({"day_min": 15, "day_max": 15}, TX)
    assert rules.match({"day_min": 10}, TX)
    assert not rules.match({"day_max": 14}, TX)
    assert not rules.match({"day_min": 1}, {**TX, "date": "bad"})


def test_all_conditions_must_hold():
    assert rules.match({"merchant": "joes", "amount_min": 40, "account_id": "acc-1"}, TX)
    assert not rules.match({"merchant": "joes", "amount_min": 40, "account_id": "acc-2"}, TX)


def test_merchant_key():
    assert rules.merchant_key(TX) == "joes bbq"
    assert rules.merchant_key({"merchant_name": None, "name": "  RAW NAME "}) == "raw name"
    assert rules.merchant_key({"merchant_name": None, "name": None}) == ""


def add_rule(name, conditions, actions, priority=100, enabled=1):
    db.run("INSERT INTO rules (name, priority, enabled, conditions, actions) VALUES (?,?,?,?,?)",
           (name, priority, enabled, json.dumps(conditions), json.dumps(actions)))
    return db.one("SELECT id FROM rules WHERE name=?", (name,))["id"]


def tx(tid):
    return db.one("SELECT * FROM transactions WHERE transaction_id=?", (tid,))


def test_plaid_fallback_and_uncategorized(fresh):
    add_tx("a", detail="FOOD_AND_DRINK_GROCERIES")
    add_tx("b")
    assert rules.categorize() == 2
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_GROCERIES" and tx("a")["cat_source"] == "plaid"
    assert tx("b")["cat_id"] == "UNCATEGORIZED" and tx("b")["cat_source"] == "none"


def test_plaid_fallback_inserts_unseen_code(fresh):
    add_tx("a", detail="FOOD_AND_DRINK_BRAND_NEW")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_BRAND_NEW"
    assert db.one("SELECT name FROM categories WHERE id='FOOD_AND_DRINK_BRAND_NEW'")["name"] == "Brand new"


def test_import_rows_use_primary_category(fresh):
    add_tx("a", category="LOAN_PAYMENTS", detail=None)
    rules.categorize()
    assert tx("a")["cat_id"] == "LOAN_PAYMENTS"


def test_rule_beats_plaid_and_counts_hits(fresh):
    rid = add_rule("Joes", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"})
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    add_tx("b", merchant="Walmart", detail="GENERAL_MERCHANDISE_SUPERSTORES")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_RESTAURANT" and tx("a")["cat_source"] == f"rule:{rid}"
    assert tx("b")["cat_id"] == "GENERAL_MERCHANDISE_SUPERSTORES"
    r = db.one("SELECT hits, last_applied FROM rules WHERE id=?", (rid,))
    assert r["hits"] == 1 and r["last_applied"]


def test_priority_order_and_tie_break(fresh):
    low = add_rule("second", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_FAST_FOOD"}, priority=200)
    high = add_rule("first", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"}, priority=10)
    add_tx("a", merchant="Joes BBQ")
    rules.categorize()
    assert tx("a")["cat_source"] == f"rule:{high}"
    db.run("UPDATE rules SET priority=10 WHERE id=?", (low,))
    rules.categorize()
    assert tx("a")["cat_source"] == f"rule:{low}"  # lower id wins the tie


def test_user_set_transaction_is_never_touched(fresh):
    add_rule("Joes", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT", "exclude": True})
    add_tx("a", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_COFFEE", source="user")
    assert rules.categorize() == 0
    row = tx("a")
    assert row["cat_id"] == "FOOD_AND_DRINK_COFFEE" and row["cat_source"] == "user" and row["excluded"] == 0


def test_merchant_memory_applies_when_no_rule(fresh):
    db.run("INSERT INTO merchant_memory (merchant_key, cat_id) VALUES ('joes bbq', 'FOOD_AND_DRINK_RESTAURANT')")
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_RESTAURANT" and tx("a")["cat_source"] == "merchant"


def test_disabled_rule_is_skipped(fresh):
    add_rule("Joes", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"}, enabled=0)
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    assert tx("a")["cat_source"] == "plaid"


def test_rerun_falls_back_when_rule_stops_matching(fresh):
    rid = add_rule("Joes", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"})
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    assert tx("a")["cat_source"] == f"rule:{rid}"
    db.run("UPDATE rules SET conditions=? WHERE id=?", (json.dumps({"merchant": "nobody"}), rid))
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_FAST_FOOD" and tx("a")["cat_source"] == "plaid"
    assert db.one("SELECT hits FROM rules WHERE id=?", (rid,))["hits"] == 0


def test_flag_only_rule_keeps_walking_for_category(fresh):
    add_rule("Rename", {"merchant": "sq *joes"}, {"display_name": "Joe's BBQ", "exclude": True}, priority=1)
    add_rule("Cat", {"merchant": "joes"}, {"cat_id": "FOOD_AND_DRINK_RESTAURANT"}, priority=2)
    add_tx("a", merchant="SQ *JOES BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    row = tx("a")
    assert row["display_name"] == "Joe's BBQ" and row["excluded"] == 1
    assert row["cat_id"] == "FOOD_AND_DRINK_RESTAURANT"


def test_flags_are_never_cleared_by_rerun(fresh):
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize()
    db.run("UPDATE transactions SET excluded=1, is_transfer=1, display_name='Mine' WHERE transaction_id='a'")
    rules.categorize()
    row = tx("a")
    assert row["excluded"] == 1 and row["is_transfer"] == 1 and row["display_name"] == "Mine"


def test_categorize_subset_only_touches_given_ids(fresh):
    add_tx("a", detail="FOOD_AND_DRINK_GROCERIES")
    add_tx("b", detail="FOOD_AND_DRINK_COFFEE")
    assert rules.categorize(["a"]) == 1
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_GROCERIES"
    assert tx("b")["cat_id"] is None


def test_bad_rule_json_is_skipped(fresh):
    db.run("INSERT INTO rules (name, conditions, actions) VALUES ('broken', 'not json', '{}')")
    add_tx("a", detail="FOOD_AND_DRINK_GROCERIES")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_GROCERIES"


def test_similar_count(fresh):
    add_tx("a", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")
    add_tx("b", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")
    add_tx("c", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_RESTAURANT", source="plaid")
    add_tx("d", merchant="Joes BBQ", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="user")
    add_tx("e", merchant="Other", cat_id="FOOD_AND_DRINK_FAST_FOOD", source="plaid")
    assert rules.similar_count("a", "FOOD_AND_DRINK_RESTAURANT") == 1  # only b


def test_preview_counts_non_user_matches(fresh):
    add_tx("a", merchant="Joes BBQ", source="plaid", cat_id="UNCATEGORIZED", date="2026-11-01")
    add_tx("b", merchant="Joes BBQ", source="user", cat_id="UNCATEGORIZED", date="2026-11-02")
    add_tx("c", merchant="Walmart", source="plaid", cat_id="UNCATEGORIZED", date="2026-11-03")
    p = rules.preview({"merchant": "joes"})
    assert p["count"] == 1
    assert [r["transaction_id"] for r in p["sample"]] == ["a"]


def test_remember_writes_merchant_memory(fresh):
    add_tx("a", merchant="Joes BBQ")
    rules.remember("a", "FOOD_AND_DRINK_RESTAURANT")
    assert db.one("SELECT cat_id FROM merchant_memory WHERE merchant_key='joes bbq'")["cat_id"] == "FOOD_AND_DRINK_RESTAURANT"
    rules.remember("a", "FOOD_AND_DRINK_COFFEE")
    assert db.one("SELECT cat_id FROM merchant_memory WHERE merchant_key='joes bbq'")["cat_id"] == "FOOD_AND_DRINK_COFFEE"
    assert db.one("SELECT COUNT(*) AS n FROM merchant_memory")["n"] == 1


def test_rule_json_that_is_not_an_object_is_skipped(fresh):
    db.run("INSERT INTO rules (name, conditions, actions) VALUES ('list', '[1,2]', '{}')")
    db.run("INSERT INTO rules (name, conditions, actions) VALUES ('str', '\"x\"', '[1]')")
    add_tx("a", detail="FOOD_AND_DRINK_GROCERIES")
    rules.categorize()
    assert tx("a")["cat_id"] == "FOOD_AND_DRINK_GROCERIES"


def test_similar_count_matches_python_merchant_key(fresh):
    add_tx("a", merchant="CAFÉ MÜLLER", cat_id="FOOD_AND_DRINK_COFFEE", source="plaid")
    add_tx("b", merchant="café müller", cat_id="FOOD_AND_DRINK_COFFEE", source="plaid")
    add_tx("c", merchant="\tcafé müller\t", cat_id="FOOD_AND_DRINK_COFFEE", source="plaid")
    add_tx("d", merchant="", name="café müller", cat_id="FOOD_AND_DRINK_COFFEE", source="plaid")
    assert rules.similar_count("a", "FOOD_AND_DRINK_RESTAURANT") == 3


def test_rule_display_name_does_not_overwrite_existing(fresh):
    add_rule("Rename", {"merchant": "joes"}, {"display_name": "Rule Name"})
    add_tx("a", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    db.run("UPDATE transactions SET display_name='Mine' WHERE transaction_id='a'")
    rules.categorize()
    assert tx("a")["display_name"] == "Mine"
    add_tx("b", merchant="Joes BBQ", detail="FOOD_AND_DRINK_FAST_FOOD")
    rules.categorize(["b"])
    assert tx("b")["display_name"] == "Rule Name"
