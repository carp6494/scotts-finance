"""App sign-in with an authenticator code (TOTP), plus session cookies.

First run: /api/auth/setup returns a QR code to scan into an authenticator app
(Google Authenticator, Microsoft Authenticator, 1Password...). After that every
new browser session must enter a 6-digit code.

Sessions are stored in the database as a SHA-256 hash of the cookie token, so
they survive a restart and the token itself is never on disk. A session lasts
for the "Stay signed in for" setting: 12 hours by default, 30 days at most.
"""
import hashlib
import io
import secrets
import time

import pyotp
import qrcode
import qrcode.image.svg

import db
from secure import decrypt, encrypt

db.run("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
db.run("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, created REAL NOT NULL, expires REAL NOT NULL)")

SESSION_CHOICES = (12, 24, 168, 720)  # hours: 12 hours, 1 day, 7 days, 30 days
DEFAULT_SESSION_HOURS = 12
COOKIE = "sf_session"


def _now():
    return time.time()


def _hash(token):
    return hashlib.sha256((token or "").encode()).hexdigest()


def _get(key):
    row = db.one("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else None


def _set(key, value):
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))


def session_hours():
    """How long a new sign-in lasts. Anything not on the list reads as the default."""
    try:
        hours = int(_get("session_hours") or DEFAULT_SESSION_HOURS)
    except ValueError:
        return DEFAULT_SESSION_HOURS
    return hours if hours in SESSION_CHOICES else DEFAULT_SESSION_HOURS


def set_session_hours(hours, token=None):
    """Save the setting. No session may outlive it; the caller's session restarts its clock."""
    if hours not in SESSION_CHOICES:
        raise ValueError("Pick 12 hours, 1 day, 7 days or 30 days.")
    _set("session_hours", str(hours))
    limit = _now() + hours * 3600
    db.run("UPDATE sessions SET expires=? WHERE expires>?", (limit, limit))
    if token:
        db.run("UPDATE sessions SET expires=? WHERE token_hash=?", (limit, _hash(token)))


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
    now = _now()
    db.run("DELETE FROM sessions WHERE expires<?", (now,))
    db.run("INSERT INTO sessions (token_hash, created, expires) VALUES (?,?,?)",
           (_hash(token), now, now + session_hours() * 3600))
    return token


def valid(token):
    if not token:
        return False
    row = db.one("SELECT expires FROM sessions WHERE token_hash=?", (_hash(token),))
    if not row:
        return False
    if row["expires"] < _now():
        logout(token)
        return False
    return True


def logout(token):
    if token:
        db.run("DELETE FROM sessions WHERE token_hash=?", (_hash(token),))
