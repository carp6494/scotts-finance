"""OFX and QFX import: SGML and XML files, bank IDs, signs, and the shared duplicate check."""
import os

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import ofx  # noqa: E402
from conftest import add_tx  # noqa: E402

SGML = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
SECURITY:NONE
ENCODING:USASCII
CHARSET:1252

<OFX>
<CREDITCARDMSGSRSV1><CCSTMTTRNRS><CCSTMTRS>
<BANKTRANLIST>
<DTSTART>20261101
<DTEND>20261130
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20261105120000.000[-5:EST]
<TRNAMT>-25.00
<FITID>A1
<NAME>STORE 123 ANYTOWN
</STMTTRN>
<STMTTRN>
<TRNTYPE>CREDIT
<DTPOSTED>20261110
<TRNAMT>100.00
<FITID>A2
<NAME>PAYMENT THANK YOU
<MEMO>Online payment
</STMTTRN>
<STMTTRN>
<TRNTYPE>DEBIT
<DTPOSTED>20261112
<TRNAMT>-4.50
<FITID>A3
<NAME>COFFEE &amp; CO
</STMTTRN>
</BANKTRANLIST>
</CCSTMTRS></CCSTMTTRNRS></CREDITCARDMSGSRSV1>
</OFX>
"""

XML = """<?xml version="1.0" encoding="UTF-8"?>
<?OFX OFXHEADER="200" VERSION="220"?>
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT</TRNTYPE><DTPOSTED>20261103</DTPOSTED><TRNAMT>-12.34</TRNAMT><FITID>X9</FITID><NAME></NAME><MEMO>Corner Market</MEMO></STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


@pytest.fixture
def card(fresh):
    db.run("INSERT INTO accounts (account_id, name, type) VALUES ('card','Store Card','credit')")
    return "card"


def imp(text, flip=False):
    return app.import_csv("card", app.ImportReq(csv=text, flip=flip))


def test_parse_sgml():
    rows = ofx.parse(SGML)
    assert [(r["date"], r["amount"], r["fitid"], r["name"]) for r in rows] == [
        ("2026-11-05", -25.0, "A1", "STORE 123 ANYTOWN"),
        ("2026-11-10", 100.0, "A2", "PAYMENT THANK YOU"),
        ("2026-11-12", -4.5, "A3", "COFFEE & CO"),
    ]


def test_parse_xml_uses_memo_when_name_is_blank():
    assert ofx.parse(XML) == [{"date": "2026-11-03", "amount": -12.34, "fitid": "X9", "name": "Corner Market"}]


def test_looks_like_ofx():
    assert ofx.looks_like(SGML) and ofx.looks_like(XML)
    assert not ofx.looks_like("Date,Description,Amount\n11/05/2026,Coffee,5.00\n")


def test_import_flips_ofx_signs_to_money_out_positive(card):
    assert imp(SGML) == {"read": 3, "added": 3, "duplicates": 0}
    got = {r["name"]: r["amount"] for r in db.q("SELECT name, amount FROM transactions")}
    assert got == {"STORE 123 ANYTOWN": 25.0, "PAYMENT THANK YOU": -100.0, "COFFEE & CO": 4.5}


def test_same_file_twice_adds_nothing(card):
    imp(SGML)
    assert imp(SGML) == {"read": 3, "added": 0, "duplicates": 3}


def test_row_the_account_already_has_is_skipped(card):
    add_tx("bank-1", amount=25.0, account="card", date="2026-11-06", name="STORE 123")
    assert imp(SGML) == {"read": 3, "added": 2, "duplicates": 1}


def test_flip_box_is_ignored_because_ofx_fixes_the_signs(card):
    imp(XML, flip=True)
    assert db.one("SELECT amount FROM transactions")["amount"] == 12.34


def test_payment_gets_card_payment_category(card):
    imp(SGML)
    row = db.one("SELECT category FROM transactions WHERE name='PAYMENT THANK YOU'")
    assert row["category"] == "LOAN_PAYMENTS"


def test_file_with_no_transactions_is_refused(card):
    with pytest.raises(app.HTTPException):
        imp("<OFX><BANKTRANLIST></BANKTRANLIST></OFX>")
