"""Exports: the full transactions CSV, QuickBooks files per account, and the year-end tax summary."""
import csv
import io
import os

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import db  # noqa: E402
import exports  # noqa: E402
import ofx  # noqa: E402
import splits  # noqa: E402
import tags  # noqa: E402
from conftest import add_tx  # noqa: E402

GROC, HARD, WAGES = "FOOD_AND_DRINK_GROCERIES", "HOME_IMPROVEMENT_HARDWARE", "INCOME_WAGES"


def rows(text):
    return list(csv.reader(io.StringIO(text)))


@pytest.fixture
def data(fresh):
    db.run("INSERT INTO accounts (account_id, name, type, subtype, mask) VALUES ('chk','Checking','depository','checking','0000')")
    db.run("INSERT INTO accounts (account_id, name, type, subtype) VALUES ('card','Travel Card','credit','credit card')")
    add_tx("t1", amount=40.0, account="card", date="2026-03-02", name="CORNER MARKET", cat_id=GROC)
    add_tx("t2", amount=-1000.0, account="chk", date="2026-03-15", name="ACME PAYROLL", cat_id=WAGES)
    add_tx("t3", amount=60.0, account="card", date="2026-04-01", name="BIG BOX", cat_id=HARD)
    add_tx("t4", amount=500.0, account="chk", date="2026-04-03", name="CARD PAYMENT", cat_id=HARD)
    db.run("UPDATE transactions SET is_transfer=1 WHERE transaction_id='t4'")
    add_tx("t5", amount=9.0, account="card", date="2025-12-30", name="OLD", cat_id=GROC)
    add_tx("t6", amount=7.0, account="card", date="2026-04-05", name="PENDING", cat_id=GROC)
    db.run("UPDATE transactions SET pending=1 WHERE transaction_id='t6'")
    return db


def test_transactions_csv_columns_and_signs(data):
    out = rows(exports.transactions_csv(start="2026-01-01", end="2026-12-31"))
    assert out[0] == ["Date", "Account", "Description", "Category", "Tags", "Amount", "Owed by", "Transfer", "Notes"]
    body = {r[2]: r for r in out[1:]}
    assert set(body) == {"CORNER MARKET", "ACME PAYROLL", "BIG BOX", "CARD PAYMENT"}  # no pending, no other year
    assert body["CORNER MARKET"][:6] == ["03/02/2026", "Travel Card", "CORNER MARKET", "Groceries", "", "-40.00"]
    assert body["ACME PAYROLL"][5] == "1000.00"
    assert body["CARD PAYMENT"][7] == "Yes"


def test_transactions_csv_one_row_per_split_line(data):
    splits.save("t3", [{"amount": 45.0, "cat_id": HARD}, {"amount": 15.0, "owed_by": "Sam"}])
    out = [r for r in rows(exports.transactions_csv())[1:] if r[2] == "BIG BOX"]
    assert sorted((r[3], r[5], r[6]) for r in out) == [("", "-15.00", "Sam"), ("Hardware", "-45.00", "")]


def test_transactions_csv_tags_and_account_filter(data):
    tags.add("t1", "Medical")
    tags.add("t1", "Alex")
    out = rows(exports.transactions_csv(account_id="card"))
    assert {r[2] for r in out[1:]} == {"CORNER MARKET", "BIG BOX", "OLD"}
    assert next(r for r in out if r[2] == "CORNER MARKET")[4] == "Alex; Medical"


def test_text_that_starts_like_a_formula_is_made_safe(data):
    add_tx("t9", amount=1.0, account="card", date="2026-05-01", name="=HYPERLINK(1)", cat_id=GROC)
    out = rows(exports.transactions_csv())
    assert any(r[2] == "'=HYPERLINK(1)" for r in out)


def test_quickbooks_csv_has_three_columns_one_row_per_transaction(data):
    splits.save("t3", [{"amount": 45.0, "cat_id": HARD}, {"amount": 15.0, "cat_id": GROC}])
    out = rows(exports.quickbooks_csv("card", start="2026-01-01"))
    assert out == [["Date", "Description", "Amount"], ["03/02/2026", "CORNER MARKET", "-40.00"], ["04/01/2026", "BIG BOX", "-60.00"]]


def test_qbo_reads_back_with_our_own_parser(data):
    text = exports.qbo("card", start="2026-01-01", end="2026-12-31")
    assert "<INTU.BID>" in text and "<CCSTMTRS>" in text
    got = ofx.parse(text)
    assert [(r["date"], r["amount"], r["fitid"], r["name"]) for r in got] == [
        ("2026-03-02", -40.0, "t1", "CORNER MARKET"), ("2026-04-01", -60.0, "t3", "BIG BOX")]


def test_qbo_bank_account_uses_bank_layout(data):
    text = exports.qbo("chk")
    assert "<STMTRS>" in text and "<ACCTTYPE>CHECKING" in text and "<ACCTID>0000" in text


def test_qbo_unknown_account():
    with pytest.raises(KeyError):
        exports.qbo("nope")


def test_tax_summary_by_category_and_tag(data):
    tags.add("t1", "Medical")
    tags.add("t3", "Medical")
    splits.save("t3", [{"amount": 45.0, "cat_id": HARD}, {"amount": 15.0, "owed_by": "Sam"}])
    out = rows(exports.tax_summary_csv(2026))
    assert out[0] == ["Group", "Name", "Transactions", "Money out", "Money in"]
    body = {(r[0], r[1]): r[2:] for r in out[1:]}
    assert body[("Category", "Groceries")] == ["1", "40.00", "0.00"]  # owed line and pending left out
    assert body[("Category", "Hardware")] == ["1", "45.00", "0.00"]  # transfer left out
    assert body[("Category", "Wages")] == ["1", "0.00", "1000.00"]
    assert body[("Tag", "Medical")] == ["2", "85.00", "0.00"]


def test_download_endpoints_send_a_file_and_skip_the_cache(data):
    import app
    r = app.export_quickbooks("card", fmt="qbo")
    assert r.headers["content-disposition"] == 'attachment; filename="quickbooks-travel-card.qbo"'
    assert r.headers["cache-control"] == "no-store"
    assert app.export_tax_summary(2026).headers["content-disposition"].endswith('tax-summary-2026.csv"')
    with pytest.raises(app.HTTPException):
        app.export_quickbooks("card", fmt="pdf")
    with pytest.raises(app.HTTPException):
        app.export_quickbooks("nope")
