import rules

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
