"""Tests the assistant's tool loop with a scripted fake model (no network)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["AOD_DATA_DIR"] = tempfile.mkdtemp(prefix="aodai_")
os.environ["AOD_USER_HOME"] = tempfile.mkdtemp(prefix="aodaihome_")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
import aod_ai  # noqa: E402


class IO:
    sent = []

    def shot(self):
        from PIL import Image
        import io
        b = io.BytesIO()
        Image.new("RGB", (640, 360), "purple").save(b, "JPEG")
        return b.getvalue(), 640, 360, {"left": 0, "top": 0, "width": 1920, "height": 1080}

    def inp(self, m):
        self.sent.append(m)

    def clip_get(self):
        return "clip"

    def clip_set(self, s):
        pass


def script(assistant, replies):
    it = iter(replies)
    assistant._call = lambda cfg: next(it)


def tool(i, name, **a):
    return {"content": [{"type": "tool_use", "id": f"t{i}", "name": name, "input": a}], "stop_reason": "tool_use"}


def text(s):
    return {"content": [{"type": "text", "text": s}], "stop_reason": "end_turn"}


def make(confirm_ok=True):
    aod_ai.update({"key": "sk-test"})
    out, asks = [], []
    a = aod_ai.Assistant(IO(), out.append, lambda t: (asks.append(t), confirm_ok)[1])
    return a, out, asks


def test_screenshot_click_maps_coordinates():
    a, out, _ = make()
    script(a, [tool(1, "screenshot"), tool(2, "click", x=320, y=180), text("Done")])
    a.run("click the middle")
    abs_msg = next(m for m in IO.sent if m["t"] == "abs")
    assert abs(abs_msg["x"] - 0.5) < 1e-6 and abs(abs_msg["y"] - 0.5) < 1e-6
    assert out[-1] == {"kind": "done"} and any(o.get("text") == "Done" for o in out)


def test_risky_tool_needs_approval_and_denial_blocks_it():
    a, out, asks = make(confirm_ok=False)
    script(a, [tool(1, "run_command", command="echo hi"), text("ok")])
    a.run("run it")
    assert asks and "echo hi" in asks[0]
    last_user = [m for m in a.history if m["role"] == "user" and not isinstance(m["content"], str)][-1]
    assert "denied" in str(last_user["content"]).lower()


def test_risky_tool_runs_when_approved():
    a, out, asks = make(confirm_ok=True)
    script(a, [tool(1, "run_command", command="echo approved"), text("ok")])
    a.run("run it")
    res = str([m for m in a.history if m["role"] == "user" and not isinstance(m["content"], str)][-1]["content"])
    assert "approved" in res


def test_run_dialog_keystroke_counts_as_risky():
    assert aod_ai.is_risky("press_keys", {"keys": ["win", "r"]}, False)
    assert not aod_ai.is_risky("press_keys", {"keys": ["ctrl", "l"]}, False)
    assert aod_ai.is_risky("type_text", {"text": "x"}, True)       # "ask before every action" mode


def test_open_url_rejects_non_http():
    a, _, _ = make()
    assert "Only http" in a.t_open_url({"url": "file:///c:/windows/system32/calc.exe"})


def test_stop_rewinds_history_and_error_is_reported():
    a, out, _ = make()
    def boom(cfg):
        raise RuntimeError("API error 500")
    a._call = boom
    a.run("hello")
    assert a.history == [] and any(o["kind"] == "error" for o in out)


def test_busy_guard():
    a, out, _ = make()
    a.busy = True
    a.run("again")
    assert out and out[0]["kind"] == "error"


def test_old_screenshots_are_dropped_from_history():
    a, _, _ = make()
    a.history.append({"role": "user", "content": "go"})
    for i in range(4):
        a.history.append({"role": "assistant", "content": [{"type": "tool_use", "id": f"x{i}", "name": "screenshot", "input": {}}]})
        a.history.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"x{i}", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "AAAA"}}]}]})
    imgs = str(a._messages()).count("'type': 'image'")
    assert imgs == 2


def test_config_never_exposes_key():
    aod_ai.update({"key": "sk-secret"})
    assert "sk-secret" not in str(aod_ai.public())
