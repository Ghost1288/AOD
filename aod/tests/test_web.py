"""Page watches, web safety and the assistant's web/look modes (no network)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AOD_DATA_DIR", tempfile.mkdtemp(prefix="aodweb_"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
import aod_ai     # noqa: E402
import aod_watch  # noqa: E402
import aod_web    # noqa: E402


def fake_pages(monkeypatch, pages):
    state = {"i": 0}
    monkeypatch.setattr(aod_web, "check_url", lambda u: u)
    monkeypatch.setattr(aod_web, "fetch", lambda u, timeout=20: ("Shop", pages[min(state["i"], len(pages) - 1)]))
    return state


def test_private_addresses_refused():
    for u in ("http://127.0.0.1/", "http://192.168.1.1/", "http://localhost:8765/", "file:///c:/x", "ftp://a.b/"):
        try:
            aod_web.check_url(u)
            raise AssertionError(u)
        except ValueError:
            pass


def test_html_to_text_drops_scripts():
    title, text = aod_web.html_to_text("<title>T</title><script>evil()</script><p>Hello <b>you</b></p>")
    assert title == "T" and text == "Hello you"


def test_watch_alerts_on_change_only(monkeypatch):
    st = fake_pages(monkeypatch, ["price 300", "price 300", "price 250"])
    sent = []
    w = aod_watch.add("https://example.com/x", "Shop")
    assert aod_watch.check(w["id"], lambda t, m: sent.append((t, m))) == "No change"
    st["i"] = 2
    aod_watch.check(w["id"], lambda t, m: sent.append((t, m)))
    assert len(sent) == 1 and "Shop" in sent[0][0] and "250" in sent[0][1]
    aod_watch.check(w["id"], lambda t, m: sent.append((t, m)))
    assert len(sent) == 1                       # same content again: no repeat alert
    assert aod_watch.remove(w["id"]) and not aod_watch.public()


def test_watch_with_question_lets_ai_decide(monkeypatch):
    st = fake_pages(monkeypatch, ["price 300", "price 290", "price 199"])
    aod_ai.update({"key": "sk-test"})
    monkeypatch.setattr(aod_ai, "quick", lambda prompt, **k: '{"alert": %s, "summary": "Now 199"}' % ("true" if "199" in prompt else "false"))
    sent = []
    w = aod_watch.add("https://example.com/y", "Kettle", question="alert me when it is under 200")
    st["i"] = 1
    aod_watch.check(w["id"], lambda t, m: sent.append(m))
    assert sent == []                           # changed, but not what I asked about
    st["i"] = 2
    aod_watch.check(w["id"], lambda t, m: sent.append(m))
    assert sent == ["Now 199"]


def test_watch_every_has_minimum(monkeypatch):
    fake_pages(monkeypatch, ["a"])
    w = aod_watch.add("https://example.com/z", every=1)
    assert w["every"] == aod_watch.MIN_EVERY
    aod_watch.remove(w["id"])


def make():
    from test_ai import IO, make as mk
    return IO, mk


def test_server_search_falls_back_to_local(monkeypatch):
    a = aod_ai.Assistant.__new__(aod_ai.Assistant)
    sys.path.insert(0, str(Path(__file__).parent))
    from test_ai import IO
    out = []
    aod_ai.update({"key": "sk-test"})
    a.__init__(IO(), out.append, lambda t: True)
    calls = {"n": 0}

    def call(cfg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise aod_ai.NoServerSearch()
        return {"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
    a._call = call
    a.run("search something")
    assert a.server_search is False and any(o.get("text") == "ok" for o in out)
    assert any(t["name"] == "web_search" and "input_schema" in t for t in a._tools())


def test_look_mode_attaches_screenshot_and_limits_tools():
    sys.path.insert(0, str(Path(__file__).parent))
    from test_ai import IO
    out = []
    aod_ai.update({"key": "sk-test"})
    a = aod_ai.Assistant(IO(), out.append, lambda t: True)
    seen = {}

    def call(cfg):
        seen["tools"] = [t["name"] for t in a._tools()]
        seen["first"] = a.history[0]["content"]
        return {"content": [{"type": "text", "text": "A purple window"}], "stop_reason": "end_turn"}
    a._call = call
    a.run("what is this?", mode="look")
    assert seen["tools"] == ["screenshot"]
    assert any(b["type"] == "image" for b in seen["first"])
    assert any(o.get("text") == "A purple window" for o in out)


def test_pause_turn_continues():
    sys.path.insert(0, str(Path(__file__).parent))
    from test_ai import IO
    out = []
    aod_ai.update({"key": "sk-test"})
    a = aod_ai.Assistant(IO(), out.append, lambda t: True)
    replies = iter([{"content": [{"type": "server_tool_use", "id": "s1", "name": "web_search", "input": {"query": "x"}}], "stop_reason": "pause_turn"},
                    {"content": [{"type": "text", "text": "found it"}], "stop_reason": "end_turn"}])
    a._call = lambda cfg: next(replies)
    a.run("look it up")
    assert any(o.get("text") == "found it" for o in out) and any(o["kind"] == "tool" for o in out)
