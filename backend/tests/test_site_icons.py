"""Website icons. Nothing here touches the network."""
import os
import time

import pytest

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import logos  # noqa: E402
import site_icons  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 200


@pytest.fixture
def sites(tmp_path, monkeypatch):
    monkeypatch.setattr(site_icons, "SITES", tmp_path)
    db.run("DELETE FROM settings WHERE key='site_icons'")
    started = []
    monkeypatch.setattr(site_icons._pool, "submit", lambda fn, host: started.append(host))
    site_icons._pending.clear()
    return started


def test_host_rules():
    h = site_icons.host_of
    assert h("https://www.Shop.com/menu?x=1") == "www.shop.com"
    assert h("shop.com") == "shop.com"
    assert h("http://shop.com") == "shop.com"  # the fetch itself always uses https
    for bad in ("", None, "localhost", "http://127.0.0.1/", "https://[::1]/", "https://10.0.0.5", "router.local",
                "intranet", "https://shop.internal/x", "https://bad host.com", "https://shop.example"):
        assert h(bad) is None, bad


def test_private_addresses_are_refused(monkeypatch):
    monkeypatch.setattr(site_icons.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("192.168.1.10", 443))])
    assert not site_icons._public("sneaky.com")
    monkeypatch.setattr(site_icons.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443)), (2, 1, 6, "", ("127.0.0.1", 443))])
    assert not site_icons._public("mixed.com")
    monkeypatch.setattr(site_icons.socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert site_icons._public("fine.com")


def test_icon_links_best_first():
    html = """<html><head>
      <link rel="icon" href="/small.png" sizes="16x16">
      <link rel="apple-touch-icon" href="https://cdn.shop.com/touch.png">
      <link rel="icon" type="image/svg+xml" href="/logo.svg">
      <link rel="mask-icon" href="/mask.png">
      <link rel="shortcut icon" href="big.png" sizes="512x512">
      <link rel="stylesheet" href="/site.css">
    </head></html>"""
    assert site_icons.icon_links(html, "https://shop.com/a/") == [
        "https://cdn.shop.com/touch.png", "https://shop.com/a/big.png", "https://shop.com/small.png", "https://shop.com/favicon.ico"]
    assert site_icons.icon_links("", "https://shop.com/") == ["https://shop.com/favicon.ico"]
    assert site_icons.icon_links("<<<not html", "https://shop.com/") == ["https://shop.com/favicon.ico"]


def test_image_check():
    assert site_icons.image_ext("text/html", PNG) == "png"
    assert site_icons.image_ext("image/x-icon", b"\x00\x00\x01\x00" + b"0" * 100) == "ico"
    assert site_icons.image_ext("image/png", b"<html>not an image</html>" + b" " * 100) is None
    assert site_icons.image_ext("text/html", b"<html></html>") is None
    assert site_icons.image_ext("image/svg+xml", b"<svg></svg>" + b" " * 100) is None


def test_logo_for_starts_one_fetch_then_uses_the_file(sites):
    assert site_icons.logo_for("https://shop.com") is None
    assert site_icons.logo_for("https://shop.com/again") is None
    assert sites == ["shop.com"]
    (site_icons.SITES / (site_icons._key("shop.com") + ".png")).write_bytes(PNG)
    assert site_icons.logo_for("shop.com") == f"/logos/sites/{site_icons._key('shop.com')}.png"


def test_a_failed_site_waits_thirty_days(sites):
    miss = site_icons.SITES / (site_icons._key("gone.com") + ".miss")
    miss.write_bytes(b"")
    assert site_icons.logo_for("gone.com") is None and sites == []
    old = time.time() - 31 * 86400
    os.utime(miss, (old, old))
    site_icons.logo_for("gone.com")
    assert sites == ["gone.com"]


def test_setting_turns_fetching_off_but_keeps_saved_icons(sites):
    assert app.get_site_icons_setting() == {"enabled": True}
    assert app.put_site_icons_setting(app.ToggleReq(enabled=False)) == {"enabled": False}
    assert site_icons.logo_for("shop.com") is None and sites == []
    (site_icons.SITES / (site_icons._key("shop.com") + ".png")).write_bytes(PNG)
    assert site_icons.logo_for("shop.com") is not None
    app.put_site_icons_setting(app.ToggleReq(enabled=True))
    site_icons.logo_for("other.com")
    assert sites == ["other.com"]


def test_fetch_saves_the_icon_and_records_misses(sites, monkeypatch):
    pages = {"https://shop.com/": ("https://shop.com/", "text/html", b'<link rel="icon" href="/i.png" sizes="128x128">'),
             "https://shop.com/i.png": ("https://shop.com/i.png", "image/png", PNG)}
    monkeypatch.setattr(site_icons, "_get", lambda client, url, cap: pages.get(url))
    assert site_icons.fetch("shop.com") == f"/logos/sites/{site_icons._key('shop.com')}.png"
    assert site_icons.fetch("empty.com") is None
    assert (site_icons.SITES / (site_icons._key("empty.com") + ".miss")).exists()


def test_merchant_logo_order(sites):
    assert logos.merchant_logo("Corner Shop", None, None) is None
    logos.merchant_logo("Corner Shop", None, "https://shop.com")
    assert sites == ["shop.com"]
    logos.merchant_logo("Corner Shop", "https://plaid.example/logo.png", "https://other.com")
    assert sites == ["shop.com"]  # a Plaid logo address means no website fetch
