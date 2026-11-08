"""Finds installed Steam games and their cover art, for the phone's Game library."""
import os
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

from aod_paths import DATA_DIR

WIN = sys.platform == "win32"
ART_DIR = DATA_DIR / "game_art"
SKIP_NAMES = {"steamworks common redistributables", "proton", "steam linux runtime"}
_cache = {"t": 0, "games": []}
_lock = threading.Lock()


def steam_root() -> Path | None:
    if WIN:
        try:
            import winreg
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        return Path(winreg.QueryValueEx(k, "InstallPath")[0])
                except OSError:
                    continue
        except Exception:
            pass
        for p in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
            if Path(p).exists():
                return Path(p)
    return None


def _library_folders(root: Path) -> list:
    libs = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    try:
        text = vdf.read_text(errors="ignore")
        for p in re.findall(r'"path"\s*"([^"]+)"', text):
            libs.append(Path(p.replace("\\\\", "\\")))
    except Exception:
        pass
    return libs


def _scan() -> list:
    root = steam_root()
    if not root:
        return []
    games = []
    for lib in _library_folders(root):
        apps_dir = lib / "steamapps"
        if not apps_dir.is_dir():
            continue
        for f in apps_dir.glob("appmanifest_*.acf"):
            try:
                text = f.read_text(errors="ignore")
                appid = re.search(r'"appid"\s*"(\d+)"', text)
                name = re.search(r'"name"\s*"([^"]+)"', text)
                state = re.search(r'"StateFlags"\s*"(\d+)"', text)
                if not (appid and name):
                    continue
                if name.group(1).strip().lower() in SKIP_NAMES:
                    continue
                if state and int(state.group(1)) & 4 == 0:     # not fully installed
                    continue
                games.append({"appid": appid.group(1), "name": name.group(1).strip()})
            except Exception:
                continue
    games.sort(key=lambda g: g["name"].lower())
    return games


def list_games() -> list:
    with _lock:
        if time.time() - _cache["t"] > 30:
            _cache.update(t=time.time(), games=_scan())
        return list(_cache["games"])


def launch_uri(appid: str) -> str:
    return f"steam://rungameid/{appid}"


def art_bytes(appid: str, timeout: int = 10):
    """Cached cover art (downloaded once from Steam's public CDN); None if it couldn't be fetched."""
    if not re.fullmatch(r"\d{1,10}", str(appid)):
        return None
    ART_DIR.mkdir(parents=True, exist_ok=True)
    f = ART_DIR / f"{appid}.jpg"
    miss = ART_DIR / f"{appid}.miss"
    if f.exists():
        return f.read_bytes()
    if miss.exists() and time.time() - miss.stat().st_mtime < 86400:
        return None
    for url in (f"https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg",
               f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/header.jpg"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AOD"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read(2_000_000)
            f.write_bytes(data)
            return data
        except Exception:
            continue
    try:
        miss.touch()
    except Exception:
        pass
    return None
