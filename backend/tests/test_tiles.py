"""Map squares: fixed services, saved to disk, each group behind a setting. No network here."""
import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("OPEN_BROWSER", "0")

import app  # noqa: E402
import db  # noqa: E402
import tiles  # noqa: E402


@pytest.fixture
def net(tmp_path, monkeypatch):
    monkeypatch.setattr(tiles, "TILES", tmp_path)
    db.run("DELETE FROM settings WHERE key LIKE 'tiles_%'")
    asked = []

    def fake(url):
        asked.append(url)
        return None if "missing" in url or "/9/9/9" in url else b"square:" + url.encode()

    monkeypatch.setattr(tiles, "_fetch", fake)
    monkeypatch.setattr(tiles, "_buildings_url", lambda: "https://tiles.openfreemap.org/planet/v1/{z}/{x}/{y}.pbf")
    return asked


def test_defaults_only_usgs_is_on(net):
    assert tiles.settings() == {"usgs": True, "terrain": False, "buildings": False}


def test_fetch_once_then_serve_from_disk(net):
    body, media = tiles.get("imagery", 5, 7, 12)
    assert media == "image/jpeg" and body.startswith(b"square:")
    assert net == ["https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/tile/5/12/7"]  # row before column
    assert tiles.get("imagery", 5, 7, 12)[0] == body
    assert len(net) == 1
    assert tiles.path_for("imagery", 5, 7, 12).exists()
    tiles.get("hybrid", 5, 7, 12)
    assert "USGSImageryTopo" in net[-1]


def test_only_the_listed_services_and_real_squares(net):
    for bad in (("streets", 1, 0, 0), ("../etc", 1, 0, 0), ("imagery", 17, 0, 0), ("imagery", -1, 0, 0),
                ("imagery", 3, 8, 0), ("imagery", 3, 0, -1), ("dem", 15, 0, 0)):
        with pytest.raises(ValueError):
            tiles.get(*bad)
    assert net == []


def test_switched_off_group_fetches_nothing_but_keeps_saved_squares(net):
    with pytest.raises(tiles.Refused):
        tiles.get("dem", 5, 7, 12)
    with pytest.raises(tiles.Refused):
        tiles.get("buildings", 14, 3731, 6400)
    assert net == []
    tiles.set_setting("terrain", True)
    tiles.set_setting("buildings", True)
    assert tiles.get("dem", 5, 7, 12)[1] == "image/png"
    assert net[-1] == "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/5/7/12.png"
    assert tiles.get("buildings", 14, 3731, 6400)[1] == "application/x-protobuf"
    assert net[-1] == "https://tiles.openfreemap.org/planet/v1/14/3731/6400.pbf"
    tiles.set_setting("terrain", False)
    assert tiles.get("dem", 5, 7, 12) is not None  # already on disk
    with pytest.raises(tiles.Refused):
        tiles.get("dem", 5, 7, 13)
    with pytest.raises(ValueError):
        tiles.set_setting("streets", True)


def test_a_missing_square_is_not_saved(net):
    assert tiles.get("imagery", 9, 9, 9) is None
    assert not tiles.path_for("imagery", 9, 9, 9).exists()


def test_saved_and_clear(net):
    tiles.get("imagery", 5, 7, 12)
    tiles.get("imagery", 5, 7, 13)
    s = tiles.saved()
    assert s["count"] == 2 and s["bytes"] > 0
    assert tiles.clear() == 2
    assert tiles.saved() == {"count": 0, "bytes": 0}


def test_routes(net):
    r = app.map_tile("imagery", 5, 7, 12)
    assert r.status_code == 200 and r.media_type == "image/jpeg" and "private" in r.headers["cache-control"]
    assert app.map_tile("imagery", 9, 9, 9).status_code == 204
    with pytest.raises(HTTPException) as e:
        app.map_tile("dem", 5, 7, 12)
    assert e.value.status_code == 403
    with pytest.raises(HTTPException) as e:
        app.map_tile("nope", 5, 7, 12)
    assert e.value.status_code == 404
    out = app.put_map_settings(app.MapSettingsReq(terrain=True))
    assert out["usgs"] is True and out["terrain"] is True and out["buildings"] is False and out["saved"]["count"] == 1
    assert app.map_tile("dem", 5, 7, 12).status_code == 200
    assert app.clear_saved_map()["removed"] == 2
    assert any(r.path == "/api/tiles/{source}/{z}/{x}/{y}" for r in app.app.routes)  # under /api/, so sign-in applies
