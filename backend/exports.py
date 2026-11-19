"""Files to take out of the app: the full transactions CSV, QuickBooks files per account, and the tax summary.

Inside the app a purchase is a positive amount. Every file here writes money out
as negative, the way banks and QuickBooks expect. Pending rows are left out.
"""
import csv
import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape

import db
import tags

NAME_SQL = "COALESCE(NULLIF(t.display_name,''), NULLIF(t.merchant_name,''), t.name)"
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe(s):
    """Keep a spreadsheet from running text as a formula."""
    s = "" if s is None else str(s)
    return "'" + s if s.startswith(FORMULA_START) else s


def _money(v):
    return f"{-(v or 0) + 0:.2f}"  # flip to money out negative; + 0 turns -0.0 into 0.0


def _us_date(d):
    return f"{d[5:7]}/{d[8:10]}/{d[0:4]}"


def _write(header, body):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    w.writerows(body)
    return buf.getvalue()


def _where(start=None, end=None, account_id=None):
    where, args = ["COALESCE(t.pending,0)=0"], []
    if start:
        where.append("t.date>=?")
        args.append(start)
    if end:
        where.append("t.date<=?")
        args.append(end)
    if account_id:
        where.append("t.account_id=?")
        args.append(account_id)
    return " AND ".join(where), args


def transactions_csv(start=None, end=None, account_id=None):
    """Every transaction, one row per split line, with category, tags, owed by, and notes."""
    where, args = _where(start, end, account_id)
    found = db.q(f"""SELECT t.transaction_id, t.date, a.name AS account, {NAME_SQL} AS descr, c.name AS category,
                            l.amount, l.owed_by, COALESCE(t.is_transfer,0) AS is_transfer, t.notes
                     FROM tx_lines l JOIN transactions t ON t.transaction_id=l.transaction_id
                     LEFT JOIN accounts a ON a.account_id=t.account_id LEFT JOIN categories c ON c.id=l.cat_id
                     WHERE {where} ORDER BY t.date, t.transaction_id, l.split_id""", args)
    tag_map = tags.for_transactions([r["transaction_id"] for r in found])
    body = [[_us_date(r["date"]), _safe(r["account"]), _safe(r["descr"]), _safe(r["category"]),
             _safe("; ".join(g["name"] for g in tag_map.get(r["transaction_id"], []))), _money(r["amount"]),
             _safe(r["owed_by"]), "Yes" if r["is_transfer"] else "", _safe(r["notes"])] for r in found]
    return _write(["Date", "Account", "Description", "Category", "Tags", "Amount", "Owed by", "Transfer", "Notes"], body)


def _account(account_id):
    a = db.one("SELECT * FROM accounts WHERE account_id=?", (account_id,))
    if not a:
        raise KeyError(account_id)
    return a


def _bank_rows(account_id, start, end):
    """One row per transaction, as the bank would show it. Splits do not apply here."""
    _account(account_id)
    where, args = _where(start, end, account_id)
    return db.q(f"""SELECT t.transaction_id, t.date, t.amount, {NAME_SQL} AS descr, t.name AS raw_name
                    FROM transactions t WHERE {where} ORDER BY t.date, t.transaction_id""", args)


def quickbooks_csv(account_id, start=None, end=None):
    """The three column layout QuickBooks Online takes for a bank upload."""
    body = [[_us_date(r["date"]), _safe(r["descr"]), _money(r["amount"])] for r in _bank_rows(account_id, start, end)]
    return _write(["Date", "Description", "Amount"], body)


QBO_BANK_ID = "3000"  # QuickBooks Desktop refuses a Web Connect file without a bank ID it knows; 3000 is the common one


def _ofx_text(s, limit=None):
    s = " ".join(str(s or "").split())
    return escape(s[:limit] if limit else s)


def _ofx_date(d):
    return d.replace("-", "") + "120000"


def qbo(account_id, start=None, end=None):
    """A QuickBooks Web Connect file (OFX 1.02) for one account."""
    a = _account(account_id)
    found = _bank_rows(account_id, start, end)
    card = a["type"] in ("credit", "loan")
    now = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    first = start or (found[0]["date"] if found else datetime.now().strftime("%Y-%m-%d"))
    last = end or (found[-1]["date"] if found else datetime.now().strftime("%Y-%m-%d"))
    acct_id = _ofx_text(a["mask"] or a["account_id"], 22)
    lines = ["OFXHEADER:100", "DATA:OFXSGML", "VERSION:102", "SECURITY:NONE", "ENCODING:USASCII", "CHARSET:1252",
             "COMPRESSION:NONE", "OLDFILEUID:NONE", "NEWFILEUID:NONE", "",
             "<OFX>", "<SIGNONMSGSRSV1>", "<SONRS>", "<STATUS>", "<CODE>0", "<SEVERITY>INFO", "</STATUS>",
             f"<DTSERVER>{now}", "<LANGUAGE>ENG", "<FI>", "<ORG>Finance App", f"<FID>{QBO_BANK_ID}", "</FI>",
             f"<INTU.BID>{QBO_BANK_ID}", "</SONRS>", "</SIGNONMSGSRSV1>"]
    if card:
        lines += ["<CREDITCARDMSGSRSV1>", "<CCSTMTTRNRS>", "<TRNUID>1", "<STATUS>", "<CODE>0", "<SEVERITY>INFO", "</STATUS>",
                  "<CCSTMTRS>", "<CURDEF>USD", "<CCACCTFROM>", f"<ACCTID>{acct_id}", "</CCACCTFROM>"]
    else:
        acct_type = "SAVINGS" if (a["subtype"] or "").lower() == "savings" else "CHECKING"
        lines += ["<BANKMSGSRSV1>", "<STMTTRNRS>", "<TRNUID>1", "<STATUS>", "<CODE>0", "<SEVERITY>INFO", "</STATUS>",
                  "<STMTRS>", "<CURDEF>USD", "<BANKACCTFROM>", "<BANKID>000000000", f"<ACCTID>{acct_id}",
                  f"<ACCTTYPE>{acct_type}", "</BANKACCTFROM>"]
    lines += ["<BANKTRANLIST>", f"<DTSTART>{_ofx_date(first)}", f"<DTEND>{_ofx_date(last)}"]
    for r in found:
        name = r["descr"] or r["raw_name"] or ""
        lines += ["<STMTTRN>", f"<TRNTYPE>{'DEBIT' if (r['amount'] or 0) > 0 else 'CREDIT'}",
                  f"<DTPOSTED>{_ofx_date(r['date'])}", f"<TRNAMT>{_money(r['amount'])}",
                  f"<FITID>{_ofx_text(r['transaction_id'], 255)}", f"<NAME>{_ofx_text(name, 32)}"]
        if len(" ".join(name.split())) > 32:
            lines.append(f"<MEMO>{_ofx_text(name, 255)}")
        lines.append("</STMTTRN>")
    balance = (a["current"] or 0) * (-1 if card else 1)
    lines += ["</BANKTRANLIST>", "<LEDGERBAL>", f"<BALAMT>{balance + 0:.2f}", f"<DTASOF>{now}", "</LEDGERBAL>"]
    lines += ["</CCSTMTRS>", "</CCSTMTTRNRS>", "</CREDITCARDMSGSRSV1>"] if card else ["</STMTRS>", "</STMTTRNRS>", "</BANKMSGSRSV1>"]
    lines.append("</OFX>")
    return "\r\n".join(lines) + "\r\n"


def tax_summary_csv(year):
    """Totals for one year by category and by tag.

    Same rules as the spending totals: transfers, excluded rows, owed lines, and deposits
    linked as money paid back are left out. A split counts once per line.
    """
    y = str(int(year))
    sums = """COUNT(DISTINCT t.transaction_id) AS n,
              COALESCE(SUM(CASE WHEN l.amount>0 THEN l.amount END),0) AS out_amt,
              COALESCE(SUM(CASE WHEN l.amount<0 THEN -l.amount END),0) AS in_amt"""
    lines = "tx_lines l JOIN transactions t ON t.transaction_id=l.transaction_id"
    keep = """substr(t.date,1,4)=? AND COALESCE(t.pending,0)=0 AND COALESCE(t.excluded,0)=0
              AND COALESCE(t.is_transfer,0)=0 AND l.owed_by IS NULL
              AND NOT EXISTS (SELECT 1 FROM paybacks p WHERE p.payment_id=t.transaction_id)"""
    cats = db.q(f"""SELECT COALESCE(c.name,'Uncategorized') AS name, {sums}
                    FROM {lines} LEFT JOIN categories c ON c.id=l.cat_id WHERE {keep}
                    GROUP BY 1 ORDER BY 1 COLLATE NOCASE""", [y])
    tagged = db.q(f"""SELECT g.name, {sums}
                      FROM {lines} JOIN transaction_tags x ON x.transaction_id=t.transaction_id
                      JOIN tags g ON g.id=x.tag_id WHERE {keep}
                      GROUP BY g.id ORDER BY g.name COLLATE NOCASE""", [y])
    body = [[group, _safe(r["name"]), r["n"], f"{r['out_amt']:.2f}", f"{r['in_amt']:.2f}"]
            for group, found in (("Category", cats), ("Tag", tagged)) for r in found]
    return _write(["Group", "Name", "Transactions", "Money out", "Money in"], body)
