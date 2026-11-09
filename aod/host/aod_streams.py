"""Track Twitch and Kick streamers and tell your phone when one of them goes live.

Twitch needs a free app (Client ID + secret from https://dev.twitch.tv/console/apps) entered once on the
dashboard; this uses the app-only (client-credentials) token, never your Twitch login. Kick's channel info is
public and needs no key.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from aod_paths import DATA_DIR

CONFIG = DATA_DIR / "streamers.json"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 AOD"
MAX_CHANNELS = 40
POLL_EVERY = 90           # seconds
_lock = threading.Lock()
_token = {"value": "", "exp": 0}


def _load() -> dict:
    try:
        c = json.loads(CONFIG.read_text())
    except Exception:
        c = {}
    c.setdefault("twitch_client_id", "")
    c.setdefault("twitch_client_secret", "")
    c.setdefault("channels", [])
    return c


def _save(c: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(c))
    try:
        os.chmod(CONFIG, 0o600)
    except Exception:
        pass


def public() -> dict:
    """Safe to send to the phone: channels + whether Twitch is configured, never the client secret."""
    c = _load()
    chans = [{k: ch.get(k) for k in ("id", "platform", "name", "label", "live", "title")} for ch in c["channels"]]
    return {"channels": chans, "twitch_ready": bool(c["twitch_client_id"] and c["twitch_client_secret"])}


def config_public() -> dict:
    c = _load()
    return {"twitch_client_id": c["twitch_client_id"], "has_secret": bool(c["twitch_client_secret"])}


def update_config(client_id: str = None, client_secret: str = None, clear_secret: bool = False) -> dict:
    with _lock:
        c = _load()
        if client_id is not None:
            c["twitch_client_id"] = str(client_id).strip()[:64]
        if clear_secret:
            c["twitch_client_secret"] = ""
        elif client_secret:
            c["twitch_client_secret"] = str(client_secret).strip()[:128]
        _save(c)
    _token.update(value="", exp=0)        # force a fresh app token next check
    return config_public()


# ---- HTTP helpers ----

def _get_json(url: str, headers: dict = None, timeout: int = 10):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def _post_json(url: str, data: dict, timeout: int = 10):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


# ---- Twitch ----

def _twitch_token(client_id: str, client_secret: str):
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    j = _post_json("https://id.twitch.tv/oauth2/token", {
        "client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"})
    _token.update(value=j["access_token"], exp=time.time() + int(j.get("expires_in", 3600)))
    return _token["value"]


def twitch_user_exists(login: str, client_id: str, client_secret: str) -> bool:
    tok = _twitch_token(client_id, client_secret)
    j = _get_json(f"https://api.twitch.tv/helix/users?login={urllib.parse.quote(login)}",
                  {"Client-Id": client_id, "Authorization": f"Bearer {tok}"})
    return bool(j.get("data"))


def twitch_batch_status(logins: list, client_id: str, client_secret: str) -> dict:
    """{login: {"live": bool, "title": str}} for up to 100 logins in one call."""
    if not logins:
        return {}
    tok = _twitch_token(client_id, client_secret)
    q = "&".join(f"user_login={urllib.parse.quote(n)}" for n in logins[:100])
    j = _get_json(f"https://api.twitch.tv/helix/streams?{q}", {"Client-Id": client_id, "Authorization": f"Bearer {tok}"})
    live = {s["user_login"].lower(): s.get("title", "") for s in j.get("data", [])}
    return {n.lower(): {"live": n.lower() in live, "title": live.get(n.lower(), "")} for n in logins}


# ---- Kick (public, no key) ----

def kick_status(name: str) -> dict:
    j = _get_json(f"https://kick.com/api/v2/channels/{urllib.parse.quote(name)}")
    live = j.get("livestream")
    return {"live": bool(live), "title": (live or {}).get("session_title", "") if live else ""}


def kick_channel_exists(name: str) -> bool:
    try:
        _get_json(f"https://kick.com/api/v2/channels/{urllib.parse.quote(name)}")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise


# ---- tracked channels ----

def add_channel(platform: str, name: str, label: str = "") -> dict:
    platform = platform.strip().lower()
    name = name.strip().lstrip("@").lower()
    if platform not in ("twitch", "kick"):
        raise ValueError("Platform must be twitch or kick")
    if not name:
        raise ValueError("Enter a username")
    c = _load()
    if len(c["channels"]) >= MAX_CHANNELS:
        raise ValueError(f"You're already tracking {MAX_CHANNELS} streamers")
    if any(ch["platform"] == platform and ch["name"] == name for ch in c["channels"]):
        raise ValueError("Already tracking that streamer")
    if platform == "twitch":
        if not (c["twitch_client_id"] and c["twitch_client_secret"]):
            raise ValueError("Add a Twitch Client ID and secret on the dashboard first")
        if not twitch_user_exists(name, c["twitch_client_id"], c["twitch_client_secret"]):
            raise ValueError("No Twitch channel with that name")
    else:
        if not kick_channel_exists(name):
            raise ValueError("No Kick channel with that name")
    ch = {"id": uuid.uuid4().hex[:8], "platform": platform, "name": name, "label": (label or name)[:40],
          "live": False, "title": "", "notified": False}
    with _lock:
        c = _load()
        c["channels"].append(ch)
        _save(c)
    return {k: ch[k] for k in ("id", "platform", "name", "label")}


def remove_channel(cid: str) -> bool:
    with _lock:
        c = _load()
        keep = [ch for ch in c["channels"] if ch["id"] != cid]
        changed = len(keep) != len(c["channels"])
        c["channels"] = keep
        _save(c)
        return changed


def check_all(push=None) -> list:
    """Refresh live status for every tracked channel; calls push(title, body) on each offline->live transition."""
    c = _load()
    chans = c["channels"]
    twitch_names = [ch["name"] for ch in chans if ch["platform"] == "twitch"]
    twitch_status = {}
    if twitch_names and c["twitch_client_id"] and c["twitch_client_secret"]:
        try:
            twitch_status = twitch_batch_status(twitch_names, c["twitch_client_id"], c["twitch_client_secret"])
        except Exception as e:
            print("twitch status error:", e)
    for ch in chans:
        try:
            if ch["platform"] == "twitch":
                st = twitch_status.get(ch["name"], {"live": False, "title": ""})
            else:
                st = kick_status(ch["name"])
            was_live = ch.get("live", False)
            ch["live"], ch["title"] = st["live"], st.get("title", "")
            if ch["live"] and not was_live and push:
                url = f"https://twitch.tv/{ch['name']}" if ch["platform"] == "twitch" else f"https://kick.com/{ch['name']}"
                push(f"{ch['label']} is live!", (ch["title"] or "Streaming now") + " — " + url)
        except Exception as e:
            print(f"stream check error ({ch['platform']}/{ch['name']}):", e)
    with _lock:
        _save({**c, "channels": chans})
    return chans


def start(push) -> None:
    def loop():
        time.sleep(30)
        while True:
            try:
                if _load()["channels"]:
                    check_all(push)
            except Exception as e:
                print("streamers loop error:", e)
            time.sleep(POLL_EVERY)
    threading.Thread(target=loop, daemon=True).start()
