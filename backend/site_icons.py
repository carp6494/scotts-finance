"""Shop icons from the shop's own website, for merchants with no other logo.

One background fetch per domain. The request carries a generic user agent and nothing
about the owner or the purchase. Limits: HTTPS only, public host names only, at most
3 redirects, 10 second timeout, 300 KB per icon, common image types only. A domain
that fails is not tried again for 30 days. The "site_icons" setting turns this off.
"""
import hashlib
import ipaddress
import logging
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

import db
from logos import LOGOS

log = logging.getLogger("site_icons")

SITES = LOGOS / "sites"
SITES.mkdir(parents=True, exist_ok=True)

MAX_ICON = 300 * 1024
MAX_PAGE = 600 * 1024
RETRY_DAYS = 30
TIMEOUT = 10
AGENT = "Mozilla/5.0 (compatible; icon-fetch)"
TYPES = {"image/png": "png", "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico", "image/jpeg": "jpg",
         "image/gif": "gif", "image/webp": "webp"}
MAGIC = ((b"\x89PNG", "png"), (b"\x00\x00\x01\x00", "ico"), (b"\xff\xd8\xff", "jpg"), (b"GIF8", "gif"))

_pool = ThreadPoolExecutor(max_workers=2)
_pending = set()
_lock = threading.Lock()

db.run("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")


def enabled():
    row = db.one("SELECT value FROM settings WHERE key='site_icons'")
    return not row or row["value"] != "0"


def set_enabled(on: bool):
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('site_icons', ?)", ("1" if on else "0",))


def host_of(website):
    """'https://www.Shop.example/menu' -> 'www.shop.example'. None when it is not a usable public name."""
    w = str(website or "").strip()
    if not w:
        return None
    if "://" not in w:
        w = "https://" + w.lstrip("/")
    try:
        host = (urlsplit(w).hostname or "").lower().rstrip(".")
    except ValueError:
        return None
    return host if allowed_host(host) else None


def allowed_host(host):
    if not host or len(host) > 253 or "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
        return False
    try:
        ipaddress.ip_address(host)
        return False  # no raw addresses
    except ValueError:
        pass
    last = host.rsplit(".", 1)[-1]
    return not (last.isdigit() or last in ("local", "localhost", "internal", "lan", "home", "test", "invalid", "example"))


def _public(host):
    """True when every address the name resolves to is on the public internet."""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError:
        return False
    addrs = {i[4][0] for i in infos}
    return bool(addrs) and all(ipaddress.ip_address(a).is_global for a in addrs)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower().split()
        href = a.get("href", "").strip()
        if not href or "icon" not in " ".join(rel) or "mask-icon" in rel:
            return
        m = re.search(r"(\d+)\s*x\s*\d+", a.get("sizes", "").lower())
        size = int(m.group(1)) if m else (180 if "apple-touch-icon" in rel else 32)
        if href.lower().split("?")[0].endswith(".svg") or "svg" in a.get("type", "").lower():
            return
        self.found.append((size, href))


def icon_links(html, base):
    """Icon addresses named by a page, best first: 64 pixels and up nearest to 128, then the small ones."""
    p = _Links()
    try:
        p.feed(html or "")
    except Exception:
        pass
    out = []
    for size, href in sorted(p.found, key=lambda f: (f[0] < 64, abs(f[0] - 128))):
        url = urljoin(base, href)
        if url not in out:
            out.append(url)
    fallback = urljoin(base, "/favicon.ico")
    return out + ([fallback] if fallback not in out else [])


def _get(client, url, cap):
    """GET with every hop checked. Returns (final_url, content_type, body) or None."""
    for _ in range(4):
        parts = urlsplit(url)
        if parts.scheme != "https" or not allowed_host((parts.hostname or "").lower()) or not _public(parts.hostname):
            return None
        with client.stream("GET", url) as r:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code != 200:
                return None
            body = b""
            for chunk in r.iter_bytes():
                body += chunk
                if len(body) > cap:
                    return None
            return url, r.headers.get("content-type", "").split(";")[0].strip().lower(), body
    return None


def image_ext(content_type, body):
    for magic, ext in MAGIC:
        if body[:len(magic)] == magic:
            return ext
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp"
    return TYPES.get(content_type) if content_type in TYPES and len(body) > 64 and b"<" not in body[:64] else None


def _key(host):
    return hashlib.sha1(host.encode()).hexdigest()[:16]


def cached(host):
    for f in SITES.glob(_key(host) + ".*"):
        if f.suffix != ".miss":
            return f"/logos/sites/{f.name}"
    return None


def _missed_recently(host):
    f = SITES / (_key(host) + ".miss")
    return f.exists() and time.time() - f.stat().st_mtime < RETRY_DAYS * 86400


def fetch(host):
    """Download the site's icon. Returns the served path or None. Records a miss on failure."""
    saved = None
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": AGENT, "Accept": "*/*"}) as client:
            page = _get(client, f"https://{host}/", MAX_PAGE)
            base, html = (page[0], page[2].decode("utf-8", "replace")) if page else (f"https://{host}/", "")
            for url in icon_links(html, base)[:4]:
                got = _get(client, url, MAX_ICON)
                ext = image_ext(got[1], got[2]) if got else None
                if ext:
                    dest = SITES / f"{_key(host)}.{ext}"
                    dest.write_bytes(got[2])
                    saved = f"/logos/sites/{dest.name}"
                    break
    except Exception as e:
        log.info("icon fetch failed for a site: %s", type(e).__name__)
    miss = SITES / (_key(host) + ".miss")
    if saved:
        miss.unlink(missing_ok=True)
    else:
        miss.write_bytes(b"")
    with _lock:
        _pending.discard(host)
    return saved


def logo_for(website):
    """Served path of the site's icon when it is on disk. Otherwise start one background fetch and return None."""
    host = host_of(website)
    if not host:
        return None
    have = cached(host)
    if have:
        return have
    if _missed_recently(host) or not enabled():
        return None
    with _lock:
        if host in _pending:
            return None
        _pending.add(host)
    _pool.submit(fetch, host)
    return None
