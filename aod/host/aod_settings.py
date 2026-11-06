"""Small persistent settings shared by the dashboard, the phone and the tray."""
import json
import threading

from aod_paths import DATA_DIR

FILE = DATA_DIR / "settings.json"
DEFAULTS = {"autolock": False, "autolock_secs": 60, "notify_downloads": True}
_lock = threading.Lock()


def load() -> dict:
    try:
        data = json.loads(FILE.read_text())
    except Exception:
        data = {}
    return {**DEFAULTS, **{k: v for k, v in data.items() if k in DEFAULTS or k in ("auto_update", "notify")}}


def update(changes: dict) -> dict:
    with _lock:
        try:
            data = json.loads(FILE.read_text())
        except Exception:
            data = {}
        for k, v in changes.items():
            if k in DEFAULTS:
                if isinstance(DEFAULTS[k], bool):
                    data[k] = bool(v)
                else:
                    data[k] = max(10, min(3600, int(v)))
        FILE.write_text(json.dumps(data))
    return load()
