"""AOD self-updater for the Windows host.

Looks at the newest GitHub Release of the AOD repo (version.json), and when a newer build exists:
  - installed app (AOD.exe):   downloads AOD-Setup.exe and runs it silently
  - script copy (start_aod.bat): downloads aod-host.zip and overwrites the .py/static files
then restarts AOD. Updates only happen when nobody is connected.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import aod_version
from aod_paths import DATA_DIR

REPO = os.environ.get("AOD_REPO", "Ghost1288/AOD")
BASE_URL = f"https://github.com/{REPO}/releases/latest/download/"
SETTINGS = DATA_DIR / "settings.json"
FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).parent
EXIT_RESTART = 75           # start_aod.bat restarts AOD on this exit code
CHECK_EVERY = 6 * 3600
DETACHED = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text())
    except Exception:
        return {}


class Updater:
    def __init__(self, busy_fn):
        self.busy = busy_fn            # True while a phone is connected
        self.latest = None
        self.status = "Not checked yet"
        self.applying = False
        self.auto = _load_settings().get("auto_update", True)
        self.notify_on = _load_settings().get("notify", True)
        self.notify = lambda title, msg: None      # set by the tray icon

    def _note(self, msg: str) -> None:
        if self.notify_on:
            try:
                self.notify("AOD", msg)
            except Exception:
                pass

    def set_notify(self, on: bool) -> None:
        self.notify_on = on
        s = _load_settings()
        s["notify"] = on
        SETTINGS.parent.mkdir(exist_ok=True)
        SETTINGS.write_text(json.dumps(s))

    # ---- settings
    def set_auto(self, on: bool) -> None:
        self.auto = on
        s = _load_settings()
        s["auto_update"] = on
        SETTINGS.parent.mkdir(exist_ok=True)
        SETTINGS.write_text(json.dumps(s))

    # ---- network
    def _open(self, name: str, timeout: int = 20):
        # A normal browser UA, not a custom one: some antivirus/proxy filters quietly block uncommon
        # User-Agents on download links even though the server itself doesn't care.
        req = urllib.request.Request(BASE_URL + name,
                                     headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AOD-updater"})
        return urllib.request.urlopen(req, timeout=timeout)

    @staticmethod
    def _explain(e: Exception) -> str:
        if isinstance(e, urllib.error.HTTPError):
            return f"HTTP {e.code}" + ({401: " (unauthorized)", 403: " (blocked)", 404: " (not found)",
                                        429: " (rate limited, try later)"}.get(e.code, ""))
        if isinstance(e, urllib.error.URLError):
            return str(getattr(e, "reason", e) or e)[:80]
        return e.__class__.__name__

    def check(self) -> bool:
        self.status = "Checking for updates..."
        self._note("Checking for updates...")
        last_err = None
        for attempt in range(2):                 # one retry: GitHub's CDN occasionally blips
            try:
                with self._open("version.json") as r:
                    self.latest = json.load(r)
                self.status = (f"Update available: {self.latest['version']}" if self.available()
                               else "Up to date")
                self._note(f"Update found: {self.latest['version']}. Installing when no phone is connected."
                           if self.available() else f"You're up to date (v{aod_version.VERSION}).")
                return self.available()
            except Exception as e:
                last_err = e
                if attempt == 0:
                    time.sleep(2)
        self.status = f"Couldn't check for updates ({self._explain(last_err)})"
        self._note("Couldn't check for updates. Will try again later.")
        return self.available()

    def available(self) -> bool:
        try:
            key = "exe_build" if FROZEN else "build"
            return bool(self.latest) and int(self.latest.get(key, self.latest["build"])) > aod_version.BUILD
        except Exception:
            return False

    def public(self) -> dict:
        return {"current": aod_version.VERSION, "latest": (self.latest or {}).get("version"),
                "available": self.available(), "status": self.status, "auto": self.auto,
                "mode": "installer" if FROZEN else "script",
                "service": os.environ.get("AOD_SERVICE") == "1"}

    def _download(self, name: str, dest: Path) -> None:
        with self._open(name, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)

    # ---- apply
    def apply(self) -> None:
        if self.applying or not self.available():
            return
        self.applying = True
        try:
            self.status = "Downloading update..."
            self._note(f"Updating to {self.latest['version']}... AOD will restart.")
            tmp = Path(tempfile.mkdtemp(prefix="aod_update_"))
            if FROZEN:
                self._apply_installer(tmp)
            else:
                self._apply_zip(tmp)
        except Exception as e:
            self.status = f"Update failed: {e}"
            self.applying = False

    def _apply_installer(self, tmp: Path) -> None:
        setup = tmp / "AOD-Setup.exe"
        self._download(self.latest.get("exe", "AOD-Setup.exe"), setup)
        self.status = "Installing update..."
        if os.environ.get("AOD_SERVICE") == "1":      # running as SYSTEM: install as the real user, then let the launcher restart us
            import aod_launcher
            aod_launcher.run_as_user(f'"{setup}" /SILENT /SUPPRESSMSGBOXES /CLOSEAPPLICATIONS /NORUN=1')
            time.sleep(1)
            os._exit(aod_launcher.EXIT_UPDATING)
        subprocess.Popen([str(setup), "/SILENT", "/SUPPRESSMSGBOXES", "/CLOSEAPPLICATIONS",
                          "/RESTARTAPPLICATIONS"], creationflags=DETACHED)
        time.sleep(1)
        os._exit(0)

    def _apply_zip(self, tmp: Path) -> None:
        z = tmp / "host.zip"
        self._download(self.latest.get("host_zip", "aod-host.zip"), z)
        out = tmp / "x"
        with zipfile.ZipFile(z) as zf:
            zf.extractall(out)
        for src in out.rglob("*"):
            rel = src.relative_to(out)
            if src.is_dir() or ".venv" in rel.parts or "__pycache__" in rel.parts:
                continue
            dst = APP_DIR / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        self.status = "Restarting..."
        if os.environ.get("AOD_LOOP") == "1":       # started by start_aod.bat: it restarts us
            os._exit(EXIT_RESTART)
        env = dict(os.environ, AOD_START_DELAY="3", AOD_NO_BROWSER="1")
        subprocess.Popen([sys.executable, str(APP_DIR / "aod_host.py")], cwd=APP_DIR, env=env,
                         creationflags=DETACHED)
        os._exit(0)

    # ---- background loop
    def start(self) -> None:
        def loop():
            time.sleep(20)
            while True:
                self.check()
                if self.auto and self.available():
                    while self.busy():          # never interrupt a live session
                        time.sleep(60)
                    self.apply()
                time.sleep(CHECK_EVERY)
        threading.Thread(target=loop, daemon=True).start()

    def check_and_apply_now(self) -> None:
        threading.Thread(target=lambda: (self.check() and self.apply()), daemon=True).start()
