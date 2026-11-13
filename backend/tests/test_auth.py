"""Sign-in sessions: stored hashed in the database, lifetime set by the user."""
import importlib
import os

import pyotp
import pytest
from fastapi import HTTPException, Response

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402


class Clock:
    def __init__(self):
        self.t = 1_800_000_000.0

    def __call__(self):
        return self.t

    def forward(self, hours):
        self.t += hours * 3600


@pytest.fixture
def clock(monkeypatch):
    db.run("DELETE FROM sessions")
    db.run("DELETE FROM settings")
    c = Clock()
    monkeypatch.setattr(auth, "_now", c)
    return c


def sign_in():
    enc = db.one("SELECT value FROM settings WHERE key='totp_secret'")
    secret = auth.decrypt(enc["value"]) if enc else auth.setup()["secret"]
    token = auth.verify(pyotp.TOTP(secret).now())
    assert token
    return token


class Req:
    def __init__(self, token):
        self.cookies = {auth.COOKIE: token}


def test_default_is_twelve_hours(clock):
    token = sign_in()
    assert auth.session_hours() == 12
    clock.forward(11)
    assert auth.valid(token)
    clock.forward(2)
    assert not auth.valid(token)


def test_session_survives_a_restart(clock):
    token = sign_in()
    importlib.reload(auth)
    assert auth.valid(token)


def test_only_a_hash_is_stored(clock):
    token = sign_in()
    rows = db.q("SELECT * FROM sessions")
    assert len(rows) == 1
    assert token not in [str(v) for v in rows[0].values()]


def test_logout_ends_the_session(clock):
    token = sign_in()
    auth.logout(token)
    assert not auth.valid(token)
    assert db.q("SELECT * FROM sessions") == []


def test_unknown_or_empty_token_is_rejected(clock):
    sign_in()
    assert not auth.valid(None)
    assert not auth.valid("")
    assert not auth.valid("not-a-token")


def test_longer_setting_extends_this_session_and_later_ones(clock):
    token = sign_in()
    auth.set_session_hours(720, token)
    assert auth.session_hours() == 720
    clock.forward(24 * 29)
    assert auth.valid(token)
    later = sign_in()
    clock.forward(24 * 2)
    assert not auth.valid(token)
    assert auth.valid(later)


def test_shorter_setting_cuts_every_session(clock):
    auth.set_session_hours(720)
    other = sign_in()
    mine = sign_in()
    auth.set_session_hours(12, mine)
    clock.forward(13)
    assert not auth.valid(other)
    assert not auth.valid(mine)


def test_thirty_days_is_the_cap(clock):
    assert max(auth.SESSION_CHOICES) == 720
    for bad in (721, 8760, 0, -1, 13):
        with pytest.raises(ValueError):
            auth.set_session_hours(bad)
    assert auth.session_hours() == 12


def test_bad_stored_value_falls_back_to_default(clock):
    db.run("INSERT OR REPLACE INTO settings (key, value) VALUES ('session_hours', '99999')")
    assert auth.session_hours() == 12


def test_expired_rows_are_removed_at_sign_in(clock):
    sign_in()
    clock.forward(13)
    sign_in()
    assert len(db.q("SELECT * FROM sessions")) == 1


def test_setting_routes(clock):
    token = sign_in()
    assert app.get_session_setting() == {"hours": 12, "choices": [12, 24, 168, 720]}
    resp = Response()
    out = app.put_session_setting(app.SessionReq(hours=720), Req(token), resp)
    assert out["hours"] == 720
    cookie = resp.headers["set-cookie"]
    assert f"Max-Age={720 * 3600}" in cookie and "HttpOnly" in cookie and "SameSite=strict" in cookie
    with pytest.raises(HTTPException) as e:
        app.put_session_setting(app.SessionReq(hours=9999), Req(token), Response())
    assert e.value.status_code == 400


def test_setting_route_sits_behind_the_sign_in_check():
    paths = [r.path for r in app.app.routes]
    assert "/api/settings/session" in paths
    assert not "/api/settings/session".startswith("/api/auth/")
