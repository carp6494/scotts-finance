"""CSV import: a row the account already has, from any source, is skipped."""
import os

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
from conftest import add_tx  # noqa: E402

HEAD = "Date,Description,Amount\n"


@pytest.fixture
def card(fresh):
    db.run("INSERT INTO accounts (account_id, name, type) VALUES ('card','Store Card','credit')")
    return "card"


def imp(body):
    return app.import_csv("card", app.ImportReq(csv=HEAD + body))


def test_row_a_day_from_an_existing_row_is_skipped(card):
    add_tx("bank-1", amount=25.0, account="card", date="2026-11-05", name="STORE 123")
    assert imp("11/06/2026,Store #123 Anytown,25.00\n11/07/2026,Other Shop,9.99\n") == {"read": 2, "added": 1, "duplicates": 1}


def test_two_identical_rows_against_one_existing_row(card):
    add_tx("bank-1", amount=5.0, account="card", date="2026-11-05")
    assert imp("11/05/2026,Coffee,5.00\n11/05/2026,Coffee,5.00\n") == {"read": 2, "added": 1, "duplicates": 1}


def test_three_days_away_is_added(card):
    add_tx("bank-1", amount=25.0, account="card", date="2026-11-05")
    assert imp("11/08/2026,Store,25.00\n") == {"read": 1, "added": 1, "duplicates": 0}


def test_same_file_twice_adds_nothing_the_second_time(card):
    body = "11/05/2026,Coffee,5.00\n11/05/2026,Coffee,5.00\n11/09/2026,Hardware,30.00\n"
    assert imp(body)["added"] == 3
    assert imp(body) == {"read": 3, "added": 0, "duplicates": 3}


def test_same_date_match_wins_over_a_nearer_row_in_the_file(card):
    add_tx("bank-1", amount=5.0, account="card", date="2026-11-05")
    assert imp("11/06/2026,Coffee,5.00\n11/05/2026,Coffee,5.00\n")["added"] == 1
    assert db.one("SELECT date FROM transactions WHERE transaction_id LIKE 'imp-%'")["date"] == "2026-11-06"
