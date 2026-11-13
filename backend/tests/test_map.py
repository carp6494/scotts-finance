"""The map route and the spot filter on the transaction list."""
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import places  # noqa: E402
from conftest import add_tx  # noqa: E402

FOOD = "FOOD_AND_DRINK_FAST_FOOD"


def at(tid, lat, lon, *, amount=10.0, merchant="Shop", precision="exact", source="plaid", city="Seattle", **kw):
    add_tx(tid, amount=amount, merchant=merchant, cat_id=kw.pop("cat_id", FOOD), source="plaid", **kw)
    db.run("UPDATE transactions SET place_lat=?, place_lon=?, place_precision=?, place_source=?, place_city=?, place_region='WA' WHERE transaction_id=?",
           (lat, lon, precision, source, city, tid))


def test_one_point_per_business_per_spot(fresh):
    at("a", 47.61001, -122.33001, amount=20, merchant="Cafe")
    at("b", 47.61004, -122.33004, amount=5, merchant="Cafe")
    at("c", 47.61002, -122.33002, amount=30, merchant="Books")
    at("d", 47.70, -122.30, amount=7, merchant="Cafe")
    out = app.map_points()
    assert [(p["name"], p["total"], p["count"]) for p in out["points"]] == [("Books", 30.0, 1), ("Cafe", 25.0, 2), ("Cafe", 7.0, 1)]
    assert out["points"][0]["city"] == "Seattle" and out["points"][0]["precision"] == "exact"
    assert len({p["id"] for p in out["points"]}) == 3
    assert out["total"] == 62.0


def test_businesses_sharing_a_point_stand_apart(fresh):
    for i in range(6):
        at(f"t{i}", 47.6, -122.3, amount=60 - i, merchant=f"Shop {i}", precision="city")
    at("x", 47.6, -122.3, amount=5, merchant="Exact A")
    pts = app.map_points()["points"]
    city = [p for p in pts if p["precision"] == "city"]
    assert (city[0]["show_lat"], city[0]["show_lon"]) == (47.6, -122.3)  # the biggest stays on the point
    shown = {(p["show_lat"], p["show_lon"]) for p in pts}
    assert len(shown) == len(pts)  # no two bars on the same place
    assert all(abs(p["show_lat"] - 47.6) < 0.02 and abs(p["show_lon"] + 122.3) < 0.03 for p in pts)
    assert all((p["lat"], p["lon"]) == (47.6, -122.3) for p in pts)  # the true spot is kept


def test_only_spending_counts(fresh):
    at("a", 47.6, -122.3, amount=20)
    at("refund", 47.6, -122.3, amount=-5)
    at("payment", 47.6, -122.3, amount=100, cat_id="LOAN_PAYMENTS_CREDIT_CARD_PAYMENT")
    at("skip", 47.6, -122.3, amount=9)
    at("moved", 47.6, -122.3, amount=9)
    at("pending", 47.6, -122.3, amount=9)
    db.run("UPDATE transactions SET excluded=1 WHERE transaction_id='skip'")
    db.run("UPDATE transactions SET is_transfer=1 WHERE transaction_id='moved'")
    db.run("UPDATE transactions SET pending=1 WHERE transaction_id='pending'")
    out = app.map_points()
    assert len(out["points"]) == 1 and out["points"][0]["total"] == 20.0 and out["points"][0]["count"] == 1


def test_headquarters_are_hidden_until_asked_for(fresh):
    at("a", 47.6, -122.3, amount=20)
    at("b", 37.2, -121.9, amount=15, precision="hq", source="hq", city="Los Gatos")
    out = app.map_points()
    assert len(out["points"]) == 1 and out["hq"] == {"count": 1, "total": 15.0}
    out = app.map_points(hq=1)
    assert {p["precision"] for p in out["points"]} == {"exact", "hq"}


def test_unplaced_rows_are_counted(fresh):
    at("a", 47.6, -122.3, amount=20)
    add_tx("b", amount=12, cat_id=FOOD, source="plaid")
    out = app.map_points()
    assert out["unplaced"] == {"count": 1, "total": 12.0}


def test_filters(fresh):
    at("a", 47.6, -122.3, amount=20, merchant="Cafe", account="acc-1", date="2026-01-10")
    at("b", 47.6, -122.3, amount=30, merchant="Books", account="acc-2", date="2026-03-10", cat_id="GENERAL_MERCHANDISE_BOOKSTORES_AND_NEWSSTANDS")
    assert app.map_points(account_id="acc-2")["total"] == 30.0
    assert app.map_points(cat_id=FOOD)["total"] == 20.0
    assert app.map_points(q="boo")["total"] == 30.0
    assert app.map_points(start="2026-02-01")["total"] == 30.0
    assert app.map_points(end="2026-02-01")["total"] == 20.0
    assert app.map_points(start="2026-01-01", end="2026-12-31")["total"] == 50.0


def test_best_precision_wins_for_one_business_at_one_spot(fresh):
    at("a", 47.6, -122.3, precision="city")
    at("b", 47.6, -122.3, precision="exact")
    pts = app.map_points()["points"]
    assert len(pts) == 1 and pts[0]["precision"] == "exact"


def test_clicking_a_bar_lists_that_business_at_that_spot(fresh):
    at("a", 47.61001, -122.33001, merchant="Cafe")
    at("b", 47.61004, -122.33004, merchant="Cafe")
    at("c", 47.61002, -122.33002, merchant="Books")
    at("d", 47.70, -122.30, merchant="Cafe")
    p = next(x for x in app.map_points()["points"] if x["name"] == "Cafe" and x["count"] == 2)
    rows = app.transactions(spot=f"{p['lat']},{p['lon']}", merchant=p["name"])["rows"]
    assert {r["transaction_id"] for r in rows} == {"a", "b"}
    assert rows[0]["place_precision"] == "exact"
    assert app.transactions(spot=f"{p['lat']},{p['lon']}", merchant="Cafe", start="2027-01-01")["total"] == 0
    assert app.transactions(merchant="Cafe")["total"] == 3
    with pytest.raises(HTTPException):
        app.transactions(spot="nonsense")


def test_renamed_merchant_is_one_business(fresh):
    at("a", 47.6, -122.3, merchant="SQ CAFE 123")
    at("b", 47.6, -122.3, merchant="Cafe")
    db.run("UPDATE transactions SET display_name='Cafe' WHERE transaction_id='a'")
    pts = app.map_points()["points"]
    assert len(pts) == 1 and pts[0]["name"] == "Cafe" and pts[0]["count"] == 2
    assert app.transactions(merchant="Cafe")["total"] == 2


def test_refresh_runs_once_per_rules_version(fresh):
    db.run("DELETE FROM settings WHERE key='places_sig'")
    add_tx("a", merchant="Nobody")
    assert places.refresh_if_stale() == 1
    assert places.refresh_if_stale() is None
