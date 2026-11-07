"""Tests for the parts of AOD that run anywhere (no Windows, no GUI). Run: python -m pytest aod/tests"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ["AOD_DATA_DIR"] = tempfile.mkdtemp(prefix="aodtest_")
os.environ["AOD_USER_HOME"] = tempfile.mkdtemp(prefix="aodhome_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "relay"))

import aod_apps          # noqa: E402
import aod_events        # noqa: E402
import aod_features as feat   # noqa: E402
import aod_security as sec    # noqa: E402
import aod_settings      # noqa: E402
import aod_relay         # noqa: E402


def test_settings_clamp_and_persist():
    aod_settings.update({"autolock": True, "autolock_secs": 5})
    s = aod_settings.load()
    assert s["autolock"] is True and s["autolock_secs"] == 10
    aod_settings.update({"autolock_secs": 99999})
    assert aod_settings.load()["autolock_secs"] == 3600


def test_events_long_poll():
    import asyncio

    async def go():
        ev = aod_events.Events()
        ev.loop = asyncio.get_running_loop()
        ev.push("a", "one")
        items, last = await ev.wait(0, 0.1)
        assert items and items[0]["title"] == "a"
        asyncio.get_running_loop().call_later(0.2, lambda: ev.push("b", "two"))
        items2, last2 = await ev.wait(last, 3)
        assert [e["title"] for e in items2] == ["b"]
        assert (await ev.wait(last2, 0.1))[0] == []
        assert (await ev.wait(-1, 0.1))[1] == last2
    asyncio.run(go())


def test_shortcuts_roundtrip_and_limit():
    aod_apps.save_shortcuts([{"type": "text", "label": str(i), "value": "x"} for i in range(100)])
    assert len(aod_apps.load_shortcuts()) <= 60


def test_run_cmd_output():
    r = aod_apps.run_cmd("echo hello", timeout=10)
    assert "hello" in r["out"] and r["code"] == 0


def test_devices_token_hashed_and_revocable():
    d = sec.Devices()
    tok = d.add("Test phone", "1.2.3.4")
    assert d.check(tok)
    assert tok not in (sec.DATA_DIR / "devices.json").read_text()
    did = d.check(tok)
    d.revoke(did)
    assert not d.check(tok)
    assert not d.check("garbage") and not d.check(None)


def test_pin_lockout():
    s = sec.State()
    pin = s.pin
    assert not s.pin_ok("9.9.9.9", "000000" if pin != "000000" else "111111")
    for _ in range(10):
        s.pin_ok("9.9.9.9", "bad")
    assert s.locked("9.9.9.9")
    assert not s.pin_ok("9.9.9.9", pin)       # even the right PIN is refused while locked


def test_file_operations(tmp_path):
    d = tmp_path / "sandbox"
    d.mkdir()
    feat.fs_op("mkdir", str(d), "sub")
    assert (d / "sub").is_dir()
    f = d / "a.txt"
    f.write_text("hi")
    feat.fs_op("rename", str(f), "b.txt")
    assert (d / "b.txt").exists()
    assert [x["name"] for x in feat.search_files(str(d), "b.t")] == ["b.txt"]
    feat.fs_op("delete", str(d / "b.txt"))
    assert not (d / "b.txt").exists()


def test_file_operations_refuse_dangerous():
    import aod_paths
    for bad in (aod_paths.USER_HOME, Path(Path.cwd().anchor)):
        try:
            feat.fs_op("delete", str(bad))
            raise AssertionError("should have refused")
        except OSError:
            pass
    try:
        feat.fs_op("rename", str(Path(tempfile.gettempdir())), "bad/name")
    except OSError:
        pass


def test_thumbnail_only_images(tmp_path):
    from PIL import Image
    p = tmp_path / "x.png"
    Image.new("RGB", (400, 300), "red").save(p)
    assert feat.thumbnail(str(p))[:2] == b"\xff\xd8"
    t = tmp_path / "x.txt"
    t.write_text("no")
    assert feat.thumbnail(str(t)) is None


def test_wol_magic_packet():
    pkt = aod_relay.magic_packet("aa:bb:cc:dd:ee:ff")
    assert len(pkt) == 102 and pkt[:6] == b"\xff" * 6 and pkt[6:12] == bytes.fromhex("aabbccddeeff")
    for bad in ("zz", "aa:bb"):
        try:
            aod_relay.magic_packet(bad)
            raise AssertionError
        except ValueError:
            pass
