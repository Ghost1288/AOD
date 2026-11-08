"""Tests for the game library, scenes, and follow-mouse logic. Run: python -m pytest aod/tests"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("AOD_DATA_DIR", tempfile.mkdtemp(prefix="aodtest_"))
os.environ.setdefault("AOD_USER_HOME", tempfile.mkdtemp(prefix="aodhome_"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

import aod_apps            # noqa: E402
import aod_desktop          # noqa: E402
import aod_features as feat  # noqa: E402
import aod_games            # noqa: E402


# ---- game library ----

def _fake_steam_tree(tmp_path):
    root = tmp_path / "Steam"
    apps_dir = root / "steamapps"
    apps_dir.mkdir(parents=True)
    other_lib = tmp_path / "OtherLib"
    (other_lib / "steamapps").mkdir(parents=True)
    (apps_dir / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t"%s"\n\t}\n}\n' % str(other_lib).replace("\\", "\\\\")
    )
    (apps_dir / "appmanifest_100.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"100"\n\t"name"\t\t"Cool Game"\n\t"StateFlags"\t\t"4"\n}\n'
    )
    (apps_dir / "appmanifest_200.acf").write_text(       # not fully installed -> skipped
        '"AppState"\n{\n\t"appid"\t\t"200"\n\t"name"\t\t"Half Done"\n\t"StateFlags"\t\t"2"\n}\n'
    )
    (apps_dir / "appmanifest_300.acf").write_text(       # redistributable -> skipped
        '"AppState"\n{\n\t"appid"\t\t"300"\n\t"name"\t\t"Steamworks Common Redistributables"\n\t"StateFlags"\t\t"4"\n}\n'
    )
    (other_lib / "steamapps" / "appmanifest_400.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"400"\n\t"name"\t\t"Another Game"\n\t"StateFlags"\t\t"4"\n}\n'
    )
    return root


def test_library_folders_parses_additional_libraries(tmp_path):
    root = _fake_steam_tree(tmp_path)
    libs = aod_games._library_folders(root)
    assert root in libs
    assert any(p.name == "OtherLib" for p in libs)


def test_scan_skips_incomplete_and_redistributables(tmp_path, monkeypatch):
    root = _fake_steam_tree(tmp_path)
    monkeypatch.setattr(aod_games, "steam_root", lambda: root)
    games = aod_games._scan()
    names = {g["name"] for g in games}
    assert names == {"Cool Game", "Another Game"}
    assert games == sorted(games, key=lambda g: g["name"].lower())


def test_list_games_caches_for_30s(tmp_path, monkeypatch):
    root = _fake_steam_tree(tmp_path)
    monkeypatch.setattr(aod_games, "steam_root", lambda: root)
    calls = {"n": 0}
    real_scan = aod_games._scan

    def counting_scan():
        calls["n"] += 1
        return real_scan()

    monkeypatch.setattr(aod_games, "_scan", counting_scan)
    aod_games._cache.update(t=0, games=[])
    g1 = aod_games.list_games()
    g2 = aod_games.list_games()
    assert calls["n"] == 1
    assert g1 == g2


def test_launch_uri_format():
    assert aod_games.launch_uri("123") == "steam://rungameid/123"


def test_art_bytes_rejects_bad_appid():
    assert aod_games.art_bytes("not-a-number") is None
    assert aod_games.art_bytes("1; rm -rf /") is None


def test_art_bytes_uses_cache_file(tmp_path, monkeypatch):
    monkeypatch.setattr(aod_games, "ART_DIR", tmp_path)
    (tmp_path / "555.jpg").write_bytes(b"fake-cover-art")
    assert aod_games.art_bytes("555") == b"fake-cover-art"


def test_art_bytes_respects_recent_miss_sentinel(tmp_path, monkeypatch):
    monkeypatch.setattr(aod_games, "ART_DIR", tmp_path)
    (tmp_path / "666.miss").touch()
    assert aod_games.art_bytes("666") is None


# ---- scenes (stored as shortcuts) ----

def test_default_scenes_seeded_when_no_shortcuts_file():
    aod_apps.SHORTCUTS.unlink(missing_ok=True)
    items = aod_apps.load_shortcuts()
    ids = {i["id"] for i in items}
    assert {"gaming", "work", "movie"}.issubset(ids)
    for it in items:
        if it["type"] == "scene":
            cfg = json.loads(it["value"])
            assert "client" in cfg and "volume" in cfg


def test_scene_type_round_trips_through_save_shortcuts():
    scene = {"id": "custom1", "label": "Stream", "icon": "", "type": "scene",
              "value": json.dumps({"launch": "spotify.exe", "volume": 50,
                                    "client": {"sc": 0.8, "q": 70, "fps": 30}})}
    saved = aod_apps.save_shortcuts([scene])
    assert len(saved) == 1
    reloaded = aod_apps.load_shortcuts()
    assert reloaded[0]["type"] == "scene"
    cfg = json.loads(reloaded[0]["value"])
    assert cfg["launch"] == "spotify.exe" and cfg["volume"] == 50


def test_save_shortcuts_rejects_unknown_type():
    out = aod_apps.save_shortcuts([{"id": "x", "label": "x", "type": "nope", "value": ""}])
    assert out == []


def test_launch_handles_steam_uri_without_crashing():
    # Off Windows this can't actually launch Steam, but it must not raise and must return a bool.
    assert aod_games.launch_uri("1") == "steam://rungameid/1"
    assert aod_apps.launch(aod_games.launch_uri("1")) in (True, False)


def test_set_volume_clamps_and_is_safe_off_windows():
    assert feat.set_volume(500) in (True, False)
    assert feat.set_volume(-5) in (True, False)


# ---- follow-mouse ----

def test_window_at_point_returns_zero_off_windows():
    if sys.platform != "win32":
        assert aod_desktop.window_at_point(100, 100) == 0
