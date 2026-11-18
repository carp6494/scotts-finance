"""Read transactions out of an OFX or QFX file.

Banks send two shapes. OFX 1.x is SGML: tags often have no closing tag and the
value runs to the end of the line. OFX 2.x is XML. QFX is OFX with an Intuit
header. Both are read here with one tolerant pass, no extra library.

Signs follow the file: negative is money out. The caller flips them to the
app's convention, where positive is money out.
"""
import html
import re

_TXN = re.compile(r"<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|(?=</BANKTRANLIST>))", re.I | re.S)


def looks_like(text):
    """True when the text is an OFX or QFX file rather than a CSV."""
    return bool(re.search(r"<OFX>|OFXHEADER", text[:4000], re.I))


def _field(block, tag):
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.I)
    return html.unescape(m.group(1)).strip() if m else ""


def _date(s):
    m = re.match(r"(\d{4})(\d{2})(\d{2})", s or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _amount(s):
    s = (s or "").strip().replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")  # some banks write 12,34
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def parse(text):
    """Return one dict per transaction: date (YYYY-MM-DD), amount, fitid, name."""
    out = []
    for block in _TXN.findall(text):
        d, amt = _date(_field(block, "DTPOSTED")), _amount(_field(block, "TRNAMT"))
        if not d or amt is None:
            continue
        name = _field(block, "NAME") or _field(block, "MEMO") or _field(block, "PAYEE")
        out.append({"date": d, "amount": amt, "fitid": _field(block, "FITID"), "name": name})
    return out
