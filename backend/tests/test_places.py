import json

import db
import places
from conftest import add_tx

PLAID_RAW = json.dumps({"location": {"address": "1 Main St", "city": "Springfield", "region": "OK", "postal_code": "62701",
                                     "country": "US", "lat": 36.15, "lon": -95.99, "store_number": "42"},
                        "counterparties": [{"name": "Shop", "website": "shop.example"}]})
ONLINE_RAW = json.dumps({"location": {"address": None, "city": None, "region": None, "postal_code": None, "country": None,
                                      "lat": None, "lon": None, "store_number": None},
                         "counterparties": [{"name": "Amazon", "website": "https://www.amazon.com/"}]})


def row(tid):
    return db.one("SELECT * FROM transactions WHERE transaction_id=?", (tid,))


def test_extract_plaid_location():
    p = places.extract(PLAID_RAW)
    assert p["city"] == "Springfield" and p["lat"] == 36.15 and p["store_number"] == "42"
    assert places.extract(ONLINE_RAW) is None
    assert places.extract("not json") is None
    assert places.extract(None) is None


def test_domain_of():
    assert places.domain_of("https://www.amazon.com/gp") == "amazon.com"
    assert places.domain_of("Amazon.com") == "amazon.com"
    assert places.domain_of("") is None


def test_fill_plaid(fresh):
    add_tx("a", merchant="Shop")
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='a'", (PLAID_RAW,))
    assert places.fill() == 1
    r = row("a")
    assert r["place_source"] == "plaid" and r["place_city"] == "Springfield" and r["place_lat"] == 36.15 and r["place_store"] == "42"


def test_fill_hq_by_domain(fresh):
    add_tx("a", merchant="Amazon")
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='a'", (ONLINE_RAW,))
    places.fill()
    r = row("a")
    assert r["place_source"] == "hq" and r["place_city"] == "Seattle" and r["place_region"] == "WA"
    assert r["place_lat"] is not None


def test_fill_hq_by_name_when_no_website(fresh):
    add_tx("a", merchant="Netflix")
    db.run("UPDATE transactions SET raw='{}', website=NULL WHERE transaction_id='a'")
    places.fill()
    assert row("a")["place_source"] == "hq" and row("a")["place_city"] == "Los Gatos"


def test_fill_none(fresh):
    add_tx("a", merchant="Nobody Knows LLC")
    places.fill()
    assert row("a")["place_source"] == "none" and row("a")["place_city"] is None


def test_user_override_wins_and_is_skipped_on_refill(fresh):
    add_tx("a", merchant="Shop")
    add_tx("b", merchant="Shop")
    db.run("UPDATE transactions SET raw=? WHERE transaction_id IN ('a','b')", (PLAID_RAW,))
    places.set_user_place("a", {"address": "9 Elm", "city": "Riverside", "region": "OK", "postal": "62702", "country": "US"})
    assert row("a")["place_source"] == "user" and row("a")["place_city"] == "Riverside"
    assert row("b")["place_source"] == "user" and row("b")["place_city"] == "Riverside"  # same merchant moves too
    db.run("UPDATE transactions SET place_city='Changed' WHERE transaction_id='a'")
    places.fill()
    assert row("a")["place_city"] == "Changed"  # user rows are never touched by fill
    places.clear_user_place("a")
    assert row("a")["place_source"] == "plaid" and row("b")["place_source"] == "plaid"


def test_fill_is_idempotent_and_subset(fresh):
    add_tx("a", merchant="Shop")
    add_tx("b", merchant="Shop")
    db.run("UPDATE transactions SET raw=? WHERE transaction_id IN ('a','b')", (PLAID_RAW,))
    assert places.fill(["a"]) == 1
    assert row("b")["place_source"] is None
    assert places.fill() == 1
    assert places.fill() == 0


def test_line_formats():
    assert places.line({"place_source": "plaid", "place_address": "1 Main St", "place_city": "Springfield", "place_region": "OK"}) == "1 Main St, Springfield, OK"
    assert places.line({"place_source": "plaid", "place_address": None, "place_city": "Springfield", "place_region": "OK"}) == "Springfield, OK"
    assert places.line({"place_source": "hq", "place_address": None, "place_city": "Seattle", "place_region": "WA"}) == "Seattle, WA · headquarters"
    assert places.line({"place_source": "user", "place_address": "9 Elm", "place_city": "Riverside", "place_region": "OK"}) == "9 Elm, Riverside, OK"
    assert places.line({"place_source": "none"}) == ""
    assert places.line({"place_source": None}) == ""


def test_coverage(fresh):
    add_tx("a", merchant="Shop"); add_tx("b", merchant="Amazon"); add_tx("c", merchant="Nobody")
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='a'", (PLAID_RAW,))
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='b'", (ONLINE_RAW,))
    places.fill()
    assert places.coverage() == {"plaid": 1, "hq": 1, "user": 0, "none": 1, "total": 3}


def test_extract_coordinates_without_city():
    raw = json.dumps({"location": {"lat": 1.5, "lon": 2.5}})
    assert places.extract(raw)["lat"] == 1.5
    assert places.extract(json.dumps({"location": "1 Main St"})) is None
    assert places.extract(json.dumps({"location": ["x"]})) is None


def test_fill_survives_bad_rows_and_is_idempotent_with_numeric_raw(fresh):
    add_tx("bad", merchant="Shop"); add_tx("num", merchant="Shop"); add_tx("ok", merchant="Amazon")
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='bad'", (json.dumps({"location": "oops"}),))
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='num'", (json.dumps({"location": {"address": 100, "city": "Springfield", "postal_code": 12345, "store_number": 42}}),))
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='ok'", (ONLINE_RAW,))
    assert places.fill() == 3  # bad -> none, num -> plaid, ok -> hq
    assert places.fill() == 0
    assert row("num")["place_address"] == "100" and row("num")["place_store"] == "42"


def test_user_place_keeps_plaid_coordinates(fresh):
    add_tx("a", merchant="Shop")
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='a'", (PLAID_RAW,))
    places.fill()
    places.set_user_place("a", {"city": "Riverside", "region": "CA"})
    r = row("a")
    assert r["place_source"] == "user" and r["place_city"] == "Riverside" and r["place_lat"] == 36.15


def test_clear_reverts_hq_row(fresh):
    add_tx("a", merchant="Amazon")
    db.run("UPDATE transactions SET raw=? WHERE transaction_id='a'", (ONLINE_RAW,))
    places.fill()
    places.set_user_place("a", {"city": "Riverside"})
    places.clear_user_place("a")
    assert row("a")["place_source"] == "hq"


def test_domain_of_schemes():
    assert places.domain_of("mailto:help@amazon.com") is None or places.domain_of("mailto:help@amazon.com") != "mailto"
    assert places.domain_of("//amazon.com/x") == "amazon.com"
    assert places.domain_of("HTTPS://WWW.Amazon.com:443/a") == "amazon.com"
