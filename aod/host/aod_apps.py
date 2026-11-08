"""Launch apps, run commands, and store the phone's custom shortcut buttons."""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from aod_paths import DATA_DIR, SERVICE, USER_HOME

WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if WIN else 0
SHORTCUTS = DATA_DIR / "shortcuts.json"
_cache = {"t": 0, "apps": []}
_lock = threading.Lock()


# ---- installed apps (Start Menu shortcuts)
def _start_menu_dirs():
    return [Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
            USER_HOME / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"]


def list_apps(query: str = "") -> list:
    with _lock:
        if time.time() - _cache["t"] > 60:
            found = {}
            for root in _start_menu_dirs():
                if root.exists():
                    for p in root.rglob("*.lnk"):
                        name = p.stem
                        if "uninstall" in name.lower() or name.lower() in found:
                            continue
                        found[name.lower()] = {"name": name, "path": str(p)}
            _cache.update(t=time.time(), apps=sorted(found.values(), key=lambda a: a["name"].lower()))
        apps = _cache["apps"]
    q = query.strip().lower()
    return [a for a in apps if q in a["name"].lower()][:200] if q else apps[:200]


# ---- launching / running
def launch(target: str) -> bool:
    """Open an app, file, folder, website, or run a command line. Returns True if it started."""
    target = target.strip()
    if not target:
        return False
    is_path_or_url = "://" in target or target.lower().startswith(("http://", "https://")) or Path(target).exists()
    if SERVICE and WIN:                      # we run as SYSTEM: start things as the signed-in user instead
        import aod_launcher
        cmd = f'cmd.exe /c start "" "{target}"' if is_path_or_url else f"cmd.exe /c {target}"
        return aod_launcher.run_as_user(cmd)
    try:
        if is_path_or_url and WIN:
            os.startfile(target)             # noqa: S606
        else:
            subprocess.Popen(target, shell=True, cwd=USER_HOME, creationflags=NO_WINDOW)
        return True
    except Exception:
        return False


def run_cmd(cmd: str, timeout: int = 20) -> dict:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors="replace",
                           timeout=timeout, cwd=USER_HOME, creationflags=NO_WINDOW)
        out = (r.stdout or "") + (r.stderr or "")
        return {"out": out[-8000:], "code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"out": f"(stopped after {timeout} s)", "code": -1}
    except Exception as e:
        return {"out": str(e), "code": -1}


# ---- shortcut buttons
TYPES = {"keys", "text", "launch", "run", "power", "scene"}


DEFAULT_SCENES = [
    {"id": "gaming", "label": "Gaming", "icon": "", "type": "scene",
     "value": json.dumps({"launch": "", "volume": 80, "client": {"sc": 0.85, "q": 75, "fps": 60}})},
    {"id": "work", "label": "Work", "icon": "", "type": "scene",
     "value": json.dumps({"launch": "", "volume": 35, "client": {"sc": 0.7, "q": 60, "fps": 20}})},
    {"id": "movie", "label": "Movie", "icon": "", "type": "scene",
     "value": json.dumps({"launch": "", "volume": 65, "client": {"sc": 1.0, "q": 80, "fps": 30}})},
]


def load_shortcuts() -> list:
    try:
        return json.loads(SHORTCUTS.read_text())
    except Exception:
        try:
            save_shortcuts(DEFAULT_SCENES)
        except Exception:
            pass
        return list(DEFAULT_SCENES)


def save_shortcuts(items) -> list:
    clean = []
    for it in items[:60] if isinstance(items, list) else []:
        if isinstance(it, dict) and it.get("type") in TYPES:
            clean.append({"id": str(it.get("id", ""))[:20], "label": str(it.get("label", ""))[:24],
                          "icon": str(it.get("icon", ""))[:4], "type": it["type"],
                          "value": str(it.get("value", ""))[:1000]})
    SHORTCUTS.write_text(json.dumps(clean))
    return clean
