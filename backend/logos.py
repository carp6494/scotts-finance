"""Logo cache. Every logo is downloaded or copied once, then served from disk.

Order of preference for a merchant:
  1. Ticker logos bundled in assets/ticker-logos (copied once into data/logos)
  2. Plaid's merchant logo_url (downloaded once in the background)
  3. None (the UI shows a letter tile)
"""
import base64
import hashlib
import logging
import os
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from db import DATA, ROOT

log = logging.getLogger("logos")

LOGOS = DATA / "logos"
for sub in ("tickers", "merchants", "institutions"):
    (LOGOS / sub).mkdir(parents=True, exist_ok=True)

TICKER_SRC = Path(os.getenv("TICKER_LOGOS") or (ROOT / "assets" / "ticker-logos"))
BRAND = ROOT / "frontend" / "public" / "brand"

MERCHANT_TICKERS = {
    "walmart": "WMT", "wal-mart": "WMT", "costco": "COST", "target": "TGT", "home depot": "HD",
    "lowe's": "LOW", "lowes": "LOW", "best buy": "BBY", "netflix": "NFLX", "spotify": "SPOT",
    "amazon": "AMZN", "apple": "AAPL", "chipotle": "CMG", "starbucks": "SBUX", "mcdonald": "MCD",
    "murphy usa": "MUSA", "casey": "CASY", "t-mobile": "TMUS", "verizon": "VZ", "at&t": "T",
    "uber": "UBER", "doordash": "DASH", "kroger": "KR", "walgreens": "WBA", "cvs": "CVS",
    "dollar general": "DG", "dollar tree": "DLTR", "exxon": "XOM", "chevron": "CVX", "shell": "SHEL",
    "o'reilly": "ORLY", "autozone": "AZO", "disney": "DIS", "google": "GOOGL", "microsoft": "MSFT",
    "paypal": "PYPL", "venmo": "PYPL", "comcast": "CMCSA", "xfinity": "CMCSA", "spectrum": "CHTR",
    "chewy": "CHWY", "petsmart": "PETS", "tractor supply": "TSCO", "ulta": "ULTA", "nike": "NKE",
    "dick's": "DKS", "academy": "ASO", "wendy's": "WEN", "domino": "DPZ", "taco bell": "YUM",
    "kfc": "YUM", "pizza hut": "YUM", "chili's": "EAT", "olive garden": "DRI", "texas roadhouse": "TXRH",
    "capital one": "COF", "synchrony": "SYF", "citi": "C", "chase": "JPM", "wells fargo": "WFC",
    "bank of america": "BAC", "american express": "AXP", "schwab": "SCHW", "fidelity": "FNF",
}

_pool = ThreadPoolExecutor(max_workers=4)
_pending = set()
_plock = threading.Lock()


def ticker_logo(ticker: str):
    if not ticker:
        return None
    dest = LOGOS / "tickers" / f"{ticker}.png"
    if not dest.exists():
        src = TICKER_SRC / f"{ticker}.png"
        if not src.exists():
            return None
        try:
            shutil.copyfile(src, dest)
        except OSError:
            return None
    return f"/logos/tickers/{ticker}.png"


def ticker_for(name: str):
    n = (name or "").lower()
    for key, t in MERCHANT_TICKERS.items():
        if key in n:
            return t
    return None


def _download(url: str, dest: Path):
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        is_image = r.headers.get("content-type", "").startswith("image/") or r.content[:4] in (
            b"\x89PNG", b"GIF8", b"RIFF") or r.content[:3] == b"\xff\xd8\xff"
        if r.status_code == 200 and is_image:
            dest.write_bytes(r.content)
    except Exception as e:
        log.info("logo download failed %s: %s", url, e)
    finally:
        with _plock:
            _pending.discard(url)


def merchant_logo(name: str, logo_url: str = None):
    t = ticker_logo(ticker_for(name))
    if t:
        return t
    if not logo_url:
        return None
    key = hashlib.sha1(logo_url.encode()).hexdigest()[:16]
    dest = LOGOS / "merchants" / f"{key}.png"
    if dest.exists():
        return f"/logos/merchants/{key}.png"
    with _plock:
        if logo_url not in _pending:
            _pending.add(logo_url)
            _pool.submit(_download, logo_url, dest)
    return None


def save_institution_logo(institution_id: str, b64: str):
    if not (institution_id and b64):
        return
    dest = LOGOS / "institutions" / f"{institution_id}.png"
    if not dest.exists():
        try:
            dest.write_bytes(base64.b64decode(b64))
        except Exception:
            pass


def account_logo(acct: dict, institution_name: str, institution_id: str):
    """Best logo for an account tile: card brand first, then bank."""
    text = f"{acct.get('name') or ''} {acct.get('official_name') or ''} {institution_name or ''}".lower()
    if "discover" in text and (BRAND / "discover-card.png").exists():
        return "/brand/discover-card.png"
    for key, t in (("lowe", "LOW"), ("best buy", "BBY"), ("capital one", "COF"), ("venture", "COF")):
        if key in text:
            p = ticker_logo(t)
            if p:
                return p
    if institution_id and (LOGOS / "institutions" / f"{institution_id}.png").exists():
        return f"/logos/institutions/{institution_id}.png"
    t = ticker_logo(ticker_for(institution_name))
    return t
