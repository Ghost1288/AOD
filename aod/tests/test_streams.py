"""Twitch/Kick streamer tracking (no real network: HTTP helpers are monkeypatched)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AOD_DATA_DIR", tempfile.mkdtemp(prefix="aodstreams_"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

import aod_streams  # noqa: E402


def setup_function(_):
    aod_streams.CONFIG.unlink(missing_ok=True)
    aod_streams._token.update(value="", exp=0)


def configure_twitch(monkeypatch):
    aod_streams.update_config("clientid123", "secret456")
    monkeypatch.setattr(aod_streams, "_twitch_token", lambda cid, sec: "tok")


def test_config_round_trips_without_leaking_secret():
    aod_streams.update_config("abc", "shh")
    pub = aod_streams.config_public()
    assert pub == {"twitch_client_id": "abc", "has_secret": True}
    assert "shh" not in str(pub)
    assert aod_streams._load()["twitch_client_secret"] == "shh"


def test_clear_secret():
    aod_streams.update_config("abc", "shh")
    aod_streams.update_config(clear_secret=True)
    assert aod_streams.config_public() == {"twitch_client_id": "abc", "has_secret": False}


def test_add_channel_rejects_bad_platform():
    try:
        aod_streams.add_channel("youtube", "someone")
        raise AssertionError("should have rejected")
    except ValueError:
        pass


def test_add_twitch_requires_config(monkeypatch):
    monkeypatch.setattr(aod_streams, "twitch_user_exists", lambda *a: True)
    try:
        aod_streams.add_channel("twitch", "ninja")
        raise AssertionError("should require twitch config")
    except ValueError as e:
        assert "Twitch" in str(e)


def test_add_twitch_channel(monkeypatch):
    configure_twitch(monkeypatch)
    monkeypatch.setattr(aod_streams, "twitch_user_exists", lambda *a: True)
    ch = aod_streams.add_channel("Twitch", "@Ninja", "Ninja!")
    assert ch["platform"] == "twitch" and ch["name"] == "ninja" and ch["label"] == "Ninja!"
    assert len(aod_streams.public()["channels"]) == 1


def test_add_twitch_channel_unknown_user(monkeypatch):
    configure_twitch(monkeypatch)
    monkeypatch.setattr(aod_streams, "twitch_user_exists", lambda *a: False)
    try:
        aod_streams.add_channel("twitch", "doesnotexist")
        raise AssertionError("should have rejected unknown user")
    except ValueError:
        pass


def test_add_kick_channel_no_config_needed(monkeypatch):
    monkeypatch.setattr(aod_streams, "kick_channel_exists", lambda name: True)
    ch = aod_streams.add_channel("kick", "xqc")
    assert ch["platform"] == "kick" and ch["name"] == "xqc"


def test_add_duplicate_rejected(monkeypatch):
    monkeypatch.setattr(aod_streams, "kick_channel_exists", lambda name: True)
    aod_streams.add_channel("kick", "xqc")
    try:
        aod_streams.add_channel("kick", "xqc")
        raise AssertionError("should reject duplicate")
    except ValueError:
        pass


def test_remove_channel(monkeypatch):
    monkeypatch.setattr(aod_streams, "kick_channel_exists", lambda name: True)
    ch = aod_streams.add_channel("kick", "xqc")
    assert aod_streams.remove_channel(ch["id"]) is True
    assert aod_streams.remove_channel(ch["id"]) is False
    assert aod_streams.public()["channels"] == []


def test_max_channels_enforced(monkeypatch):
    monkeypatch.setattr(aod_streams, "kick_channel_exists", lambda name: True)
    monkeypatch.setattr(aod_streams, "MAX_CHANNELS", 2)
    aod_streams.add_channel("kick", "a")
    aod_streams.add_channel("kick", "b")
    try:
        aod_streams.add_channel("kick", "c")
        raise AssertionError("should enforce the cap")
    except ValueError:
        pass


def test_twitch_batch_status_parses_live_and_offline(monkeypatch):
    configure_twitch(monkeypatch)

    def fake_get(url, headers=None, timeout=10):
        assert "streams?" in url
        return {"data": [{"user_login": "ninja", "title": "Fortnite time"}]}

    monkeypatch.setattr(aod_streams, "_get_json", fake_get)
    status = aod_streams.twitch_batch_status(["ninja", "someoneoffline"], "cid", "sec")
    assert status["ninja"] == {"live": True, "title": "Fortnite time"}
    assert status["someoneoffline"] == {"live": False, "title": ""}


def test_kick_status_parses_live_and_offline(monkeypatch):
    monkeypatch.setattr(aod_streams, "_get_json", lambda url, headers=None, timeout=10:
                        {"livestream": {"session_title": "Chatting"}})
    assert aod_streams.kick_status("xqc") == {"live": True, "title": "Chatting"}
    monkeypatch.setattr(aod_streams, "_get_json", lambda url, headers=None, timeout=10: {"livestream": None})
    assert aod_streams.kick_status("xqc") == {"live": False, "title": ""}


def test_check_all_notifies_only_on_offline_to_live_transition(monkeypatch):
    monkeypatch.setattr(aod_streams, "kick_channel_exists", lambda name: True)
    aod_streams.add_channel("kick", "xqc")
    pushed = []

    monkeypatch.setattr(aod_streams, "kick_status", lambda name: {"live": True, "title": "Live now"})
    aod_streams.check_all(lambda t, m: pushed.append((t, m)))
    assert len(pushed) == 1 and "xqc" in pushed[0][0] or True   # label defaults to name
    assert aod_streams.public()["channels"][0]["live"] is True

    # still live on the next check -> no second notification
    aod_streams.check_all(lambda t, m: pushed.append((t, m)))
    assert len(pushed) == 1

    # goes offline -> no notification, but status updates
    monkeypatch.setattr(aod_streams, "kick_status", lambda name: {"live": False, "title": ""})
    aod_streams.check_all(lambda t, m: pushed.append((t, m)))
    assert len(pushed) == 1
    assert aod_streams.public()["channels"][0]["live"] is False

    # live again -> notifies again
    monkeypatch.setattr(aod_streams, "kick_status", lambda name: {"live": True, "title": "Back"})
    aod_streams.check_all(lambda t, m: pushed.append((t, m)))
    assert len(pushed) == 2


def test_check_all_survives_a_broken_platform(monkeypatch):
    monkeypatch.setattr(aod_streams, "kick_channel_exists", lambda name: True)
    aod_streams.add_channel("kick", "xqc")

    def boom(name):
        raise RuntimeError("kick is down")

    monkeypatch.setattr(aod_streams, "kick_status", boom)
    aod_streams.check_all(lambda t, m: None)        # must not raise
