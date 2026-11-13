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
    assert places.coverage() == {"plaid": 1, "overture": 0, "history": 0, "hq": 1, "user": 0, "none": 1, "total": 3, "located": 2, "lookup": False}


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


# ---------- coordinates from zip and city, and precision ----------

def loc(**kw):
    base = {"address": None, "city": None, "region": None, "postal_code": None, "country": None, "lat": None, "lon": None, "store_number": None}
    base.update(kw)
    return json.dumps({"location": base})


def put(tid, raw, merchant="Corner Shop", channel="in store"):
    add_tx(tid, merchant=merchant)
    db.run("UPDATE transactions SET raw=?, payment_channel=? WHERE transaction_id=?", (raw, channel, tid))


def test_precision_exact_for_bank_coordinates(fresh):
    put("a", PLAID_RAW)
    places.fill()
    assert row("a")["place_precision"] == "exact" and row("a")["place_lat"] == 36.15


def test_zip_center_when_bank_gave_no_coordinates(fresh):
    put("a", loc(city="New York", region="NY", postal_code="10001", country="US"))
    places.fill()
    r = row("a")
    assert r["place_source"] == "plaid" and r["place_precision"] == "zip"
    assert abs(r["place_lat"] - 40.75) < 0.1 and abs(r["place_lon"] + 73.99) < 0.1
    assert r["place_city"] == "New York" and r["place_postal"] == "10001"  # nothing the bank sent is lost


def test_city_center_when_there_is_no_zip(fresh):
    put("a", loc(city="Seattle", region="WA"))
    places.fill()
    r = row("a")
    assert r["place_precision"] == "city" and abs(r["place_lat"] - 47.6) < 0.3
    assert places.fill() == 0


def test_no_coordinates_for_other_countries_or_unknown_cities(fresh):
    put("a", loc(city="Stockholm", country="SE"))
    put("b", loc(city="Xyzzyville", region="WA"))
    places.fill()
    assert row("a")["place_lat"] is None and row("a")["place_precision"] is None and row("a")["place_source"] == "plaid"
    assert row("b")["place_lat"] is None and row("b")["place_precision"] is None


def test_headquarters_precision(fresh):
    put("a", ONLINE_RAW, merchant="Amazon")
    places.fill()
    assert row("a")["place_precision"] == "hq"


def test_user_place_gets_city_center_and_drops_it_when_the_city_changes(fresh):
    put("a", loc(city="Seattle", region="WA"))
    places.fill()
    places.set_user_place("a", {"city": "Portland", "region": "OR"})
    r = row("a")
    assert r["place_source"] == "user" and r["place_precision"] == "city" and abs(r["place_lat"] - 45.5) < 0.3


def test_user_typed_coordinates_are_exact(fresh):
    put("a", "{}", merchant="Nobody")
    places.set_user_place("a", {"city": "Seattle", "region": "WA", "lat": 47.6, "lon": -122.3})
    assert row("a")["place_precision"] == "exact" and row("a")["place_lat"] == 47.6


def test_older_user_rows_are_located_on_a_full_fill(fresh):
    put("a", "{}", merchant="Nobody")
    db.run("UPDATE transactions SET place_source='user', place_city='Seattle', place_region='WA' WHERE transaction_id='a'")
    places.fill()
    r = row("a")
    assert r["place_source"] == "user" and r["place_precision"] == "city" and r["place_lat"] is not None


# ---------- Overture lookup ----------

SHOP = ("Corner Shop", "12 Oak Ave", "Seattle", "WA", "98101", 47.61, -122.33, "https://cornershop.example")


def test_lookup_fills_a_city_only_bank_row(fresh, lookup):
    lookup([SHOP])
    put("a", loc(city="Seattle", region="WA", store_number="7"))
    places.fill()
    r = row("a")
    assert r["place_source"] == "overture" and r["place_precision"] == "exact"
    assert r["place_address"] == "12 Oak Ave" and r["place_lat"] == 47.61 and r["place_website"] == "https://cornershop.example"
    assert r["place_store"] == "7"
    assert places.fill() == 0


def test_lookup_adds_missing_parts_to_a_bank_row(fresh, lookup):
    lookup([SHOP])
    put("a", loc(city="Seattle", region="WA", lat=47.6101, lon=-122.3301))
    put("b", loc(address="12 Oak Avenue", city="Seattle", region="WA"))
    places.fill()
    a, b = row("a"), row("b")
    assert a["place_source"] == "plaid" and a["place_address"] == "12 Oak Ave" and a["place_lat"] == 47.6101
    assert b["place_source"] == "plaid" and b["place_address"] == "12 Oak Avenue" and b["place_lat"] == 47.61 and b["place_precision"] == "exact"


def test_lookup_skips_when_several_places_share_the_name(fresh, lookup):
    lookup([SHOP, ("Corner Shop", "99 Pine St", "Seattle", "WA", "98104", 47.60, -122.32, None)])
    put("a", loc(city="Seattle", region="WA"))
    places.fill()
    assert row("a")["place_source"] == "plaid" and row("a")["place_precision"] == "city" and row("a")["place_address"] is None


def test_lookup_needs_the_same_city(fresh, lookup):
    lookup([SHOP])
    put("a", loc(city="Spokane", region="WA"))
    places.fill()
    assert row("a")["place_source"] == "plaid" and row("a")["place_address"] is None


def test_lookup_by_name_alone_for_in_person_rows_only(fresh, lookup):
    lookup([SHOP, ("Amazon", "1 Warehouse Rd", "Kent", "WA", "98032", 47.4, -122.2, None),
            ("Web Shop", "8 Net Ln", "Kent", "WA", "98032", 47.4, -122.2, None)])
    put("a", "{}")
    put("b", "{}", merchant="Web Shop", channel="online")
    put("c", ONLINE_RAW, merchant="Amazon")
    places.fill()
    assert row("a")["place_source"] == "overture" and row("a")["place_address"] == "12 Oak Ave"
    assert row("b")["place_source"] == "none"
    assert row("c")["place_source"] == "hq"  # a known headquarters beats a same-named local place


def test_bank_address_and_coordinates_are_never_replaced(fresh, lookup):
    lookup([("Shop", "500 Other Rd", "Springfield", "OK", "62799", 1.0, 2.0, None)])
    put("a", PLAID_RAW, merchant="Shop")
    places.fill()
    r = row("a")
    assert r["place_address"] == "1 Main St" and r["place_lat"] == 36.15 and r["place_postal"] == "62701"


# ---------- looser lookup and merchant history ----------

def test_lookup_accepts_a_longer_or_shorter_form_of_the_name(fresh, lookup):
    lookup([("Corner Shop Family Store", "12 Oak Ave", "Seattle", "WA", "98101", 47.61, -122.33, None),
            ("Blue Door", "5 Elm St", "Seattle", "WA", "98101", 47.62, -122.34, None)])
    put("a", loc(city="Seattle", region="WA"))
    put("b", loc(city="Seattle", region="WA"), merchant="Blue Door Cafe")
    places.fill()
    assert row("a")["place_address"] == "12 Oak Ave" and row("b")["place_address"] == "5 Elm St"


def test_loose_lookup_still_needs_one_clear_winner(fresh, lookup):
    lookup([("Corner Shop East", "1 A St", "Seattle", "WA", "98101", 47.61, -122.33, None),
            ("Corner Shop West", "2 B St", "Seattle", "WA", "98101", 47.62, -122.34, None),
            ("Joes Tavern", "3 C St", "Seattle", "WA", "98101", 47.62, -122.34, None)])
    put("a", loc(city="Seattle", region="WA"))
    put("b", loc(city="Seattle", region="WA"), merchant="Joes")  # too short to match loosely
    places.fill()
    assert row("a")["place_address"] is None and row("b")["place_address"] is None


def test_lookup_reaches_a_neighboring_suburb(fresh, lookup):
    lookup([("Corner Shop", "12 Oak Ave", "Shoreline", "WA", "98133", 47.66, -122.34, None)])
    put("a", loc(city="Seattle", region="WA"))
    put("b", loc(city="Spokane", region="WA"))
    places.fill()
    assert row("a")["place_source"] == "overture" and row("a")["place_city"] == "Shoreline"
    assert row("b")["place_address"] is None  # far away, so no match


def test_merchant_history_fills_rows_the_bank_left_blank(fresh):
    put("a", loc(address="12 Oak Ave", city="Seattle", region="WA", lat=47.61, lon=-122.33))
    put("b", "{}", channel="online")
    put("c", "{}", merchant="Somewhere Else")
    assert places.fill() == 3
    b = row("b")
    assert b["place_source"] == "history" and b["place_address"] == "12 Oak Ave" and b["place_lat"] == 47.61 and b["place_precision"] == "exact"
    assert row("c")["place_source"] == "none"
    assert places.fill() == 0


def test_merchant_history_needs_one_spot(fresh):
    put("a", loc(city="Seattle", region="WA"))
    put("b", loc(city="Spokane", region="WA"))
    put("c", "{}")
    put("d", loc(address="1 A St", city="Tacoma", region="WA"), merchant="Twin")
    put("e", loc(address="2 B St", city="Tacoma", region="WA"), merchant="Twin")
    put("f", "{}", merchant="Twin")
    places.fill()
    assert row("c")["place_source"] == "none" and row("f")["place_source"] == "none"


def test_merchant_history_works_for_a_later_single_row(fresh):
    put("a", loc(city="Seattle", region="WA"))
    places.fill()
    put("b", "{}")
    assert places.fill(["b"]) == 1
    assert row("b")["place_source"] == "history" and row("b")["place_city"] == "Seattle" and row("b")["place_precision"] == "city"


# ---------- chains with several branches ----------

BRANCHES = [("Corner Shop", "1 Far Rd", "Seattle", "WA", "98199", 47.70, -122.40, None),
            ("Corner Shop Market", "2 Near St", "Seattle", "WA", "98101", 47.611, -122.331, "https://cornershop.example"),
            ("Corner Shop", "3 Mid Ave", "Seattle", "WA", "98105", 47.66, -122.30, None)]


def home_near_downtown():
    for i in range(3):
        put(f"h{i}", loc(address=f"{i} Home St", city="Seattle", region="WA", lat=47.61 + i * 0.001, lon=-122.33), merchant=f"Home {i}")


def test_several_branches_pick_the_nearest_and_say_likely(fresh, lookup):
    lookup(BRANCHES)
    home_near_downtown()
    put("a", loc(city="Seattle", region="WA"))
    places.fill()
    r = row("a")
    assert r["place_source"] == "overture" and r["place_precision"] == "likely" and r["place_address"] == "2 Near St"
    assert places.line(r) == "likely 2 Near St, Seattle, WA"
    assert places.fill() == 0


def test_no_guess_without_enough_purchases_to_know_the_usual_area(fresh, lookup):
    lookup(BRANCHES)
    put("a", loc(city="Seattle", region="WA"))
    places.fill()
    assert row("a")["place_source"] == "plaid" and row("a")["place_address"] is None


def test_bank_coordinates_choose_the_branch_and_stay_exact(fresh, lookup):
    lookup(BRANCHES)
    home_near_downtown()
    put("a", loc(city="Seattle", region="WA", lat=47.6601, lon=-122.3001))
    put("b", loc(city="Seattle", region="WA", lat=47.50, lon=-122.10))
    places.fill()
    a, b = row("a"), row("b")
    assert a["place_source"] == "plaid" and a["place_precision"] == "exact" and a["place_address"] == "3 Mid Ave" and a["place_lat"] == 47.6601
    assert b["place_address"] is None and b["place_precision"] == "exact"  # no branch at that spot


def test_typing_a_place_replaces_a_likely_one(fresh, lookup):
    lookup(BRANCHES)
    home_near_downtown()
    put("a", loc(city="Seattle", region="WA"))
    places.fill()
    places.set_user_place("a", {"address": "1 Far Rd", "city": "Seattle", "region": "WA", "postal": "98199"})
    r = row("a")
    assert r["place_source"] == "user" and r["place_address"] == "1 Far Rd" and r["place_precision"] == "zip"
    assert not places.line(r).startswith("likely")
