"""The self-updater's check()/available() logic (no real network: _open is monkeypatched)."""
import io
import json
import os
import sys
import tempfile
import urllib.error
from pathlib import Path

os.environ.setdefault("AOD_DATA_DIR", tempfile.mkdtemp(prefix="aodupdate_"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))

import aod_update  # noqa: E402
import aod_version  # noqa: E402


def make_updater(monkeypatch):
    monkeypatch.setattr(aod_update.time, "sleep", lambda *_: None)   # skip the retry delay in tests
    return aod_update.Updater(lambda: False)


def fake_response(payload: dict):
    class _R(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    return _R(json.dumps(payload).encode())


def test_check_reports_update_available(monkeypatch):
    u = make_updater(monkeypatch)
    monkeypatch.setattr(u, "_open", lambda name, timeout=20: fake_response(
        {"version": "9.9.9", "build": aod_version.BUILD + 1}))
    assert u.check() is True
    assert "Update available" in u.status


def test_check_reports_up_to_date(monkeypatch):
    u = make_updater(monkeypatch)
    monkeypatch.setattr(u, "_open", lambda name, timeout=20: fake_response(
        {"version": aod_version.VERSION, "build": aod_version.BUILD}))
    assert u.check() is False
    assert u.status == "Up to date"


def test_check_shows_http_status_code(monkeypatch):
    u = make_updater(monkeypatch)

    def boom(name, timeout=20):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)

    monkeypatch.setattr(u, "_open", boom)
    u.check()
    assert u.status == "Couldn't check for updates (HTTP 403 (blocked))"


def test_check_shows_rate_limit_hint(monkeypatch):
    u = make_updater(monkeypatch)
    monkeypatch.setattr(u, "_open", lambda name, timeout=20: (_ for _ in ()).throw(
        urllib.error.HTTPError("url", 429, "Too Many Requests", {}, None)))
    u.check()
    assert "429" in u.status and "rate limited" in u.status


def test_check_shows_connection_reason(monkeypatch):
    u = make_updater(monkeypatch)
    monkeypatch.setattr(u, "_open", lambda name, timeout=20: (_ for _ in ()).throw(
        urllib.error.URLError("[Errno 11001] getaddrinfo failed")))
    u.check()
    assert "getaddrinfo failed" in u.status


def test_check_retries_once_then_succeeds(monkeypatch):
    u = make_updater(monkeypatch)
    calls = {"n": 0}

    def flaky(name, timeout=20):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError("url", 502, "Bad Gateway", {}, None)
        return fake_response({"version": aod_version.VERSION, "build": aod_version.BUILD})

    monkeypatch.setattr(u, "_open", flaky)
    u.check()
    assert calls["n"] == 2
    assert u.status == "Up to date"


def test_available_uses_exe_build_when_frozen(monkeypatch):
    u = make_updater(monkeypatch)
    u.latest = {"version": "x", "build": aod_version.BUILD, "exe_build": aod_version.BUILD + 1}
    monkeypatch.setattr(aod_update, "FROZEN", True)
    assert u.available() is True
    monkeypatch.setattr(aod_update, "FROZEN", False)
    assert u.available() is False


def test_public_hides_internal_state(monkeypatch):
    u = make_updater(monkeypatch)
    p = u.public()
    assert set(p) == {"current", "latest", "available", "status", "auto", "mode", "service"}
