"""App sign-in with an authenticator code (TOTP), plus session cookies.

First run: /api/auth/setup returns a QR code to scan into an authenticator app
(Google Authenticator, Microsoft Authenticator, 1Password...). After that every
browser session must enter a 6-digit code. Sessions last 12 hours.
"""
import io
import secrets
import time

import pyotp
import qrcode
import qrcode.image.svg

import db
from secure import decrypt, encrypt

db.run("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

SESSION_HOURS = 12
COOKIE = "sf_session"
_sessions = {}  # token -> expiry epoch (memory only; restart = sign in again)


def _get(key):
    row = db.one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else None


def _set(key, value):
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))


def is_enrolled():
    return _get("totp_confirmed") == "1"


def setup():
    """Create (or reuse an unconfirmed) secret and return its QR code as SVG."""
    enc = _get("totp_secret")
    if is_enrolled():
        return None
    if not enc:
        enc = encrypt(pyotp.random_base32())
        _set("totp_secret", enc)
    secret = decrypt(enc)
    uri = pyotp.TOTP(secret).provisioning_uri(name="Scott", issuer_name="Scott's Finance")
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
    buf = io.BytesIO()
    img.save(buf)
    return {"svg": buf.getvalue().decode(), "secret": secret}


def verify(code: str):
    enc = _get("totp_secret")
    if not enc:
        return None
    ok = pyotp.TOTP(decrypt(enc)).verify((code or "").replace(" ", ""), valid_window=1)
    if not ok:
        return None
    if not is_enrolled():
        _set("totp_confirmed", "1")
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_HOURS * 3600
    return token


def valid(token):
    exp = _sessions.get(token or "")
    if not exp:
        return False
    if exp < time.time():
        _sessions.pop(token, None)
        return False
    return True


def logout(token):
    _sessions.pop(token or "", None)
