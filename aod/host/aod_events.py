"""Notifications from the PC to the phone: a small event queue plus watchers (finished downloads, ended programs)."""
import asyncio
import threading
import time

import psutil

import aod_settings
from aod_paths import USER_HOME

TEMP_EXT = {".crdownload", ".part", ".tmp", ".download", ".opdownload", ".partial", ".!ut", ".aria2"}


def _fmt(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024 or unit == "GB":
            return f"{b:.0f} {unit}" if unit == "B" else f"{b:.1f} {unit}"
        b /= 1024


class Events:
    def __init__(self):
        self.items, self.next_id = [], 1
        self.loop = None
        self.waiters = []
        self.listeners = []          # called on the event loop for each new event
        self.lock = threading.Lock()
        self.watching = set()

    @property
    def last_id(self) -> int:
        return self.next_id - 1

    def push(self, title: str, text: str) -> None:
        """Thread-safe."""
        with self.lock:
            ev = {"id": self.next_id, "title": title[:80], "text": text[:300], "ts": time.time()}
            self.next_id += 1
            self.items = (self.items + [ev])[-100:]
        if self.loop:
            self.loop.call_soon_threadsafe(self._wake, ev)

    def _wake(self, ev) -> None:
        for fut in self.waiters:
            if not fut.done():
                fut.set_result(True)
        for fn in self.listeners:
            try:
                fn(ev)
            except Exception:
                pass

    async def wait(self, after: int, timeout: float):
        """Long-poll. after < 0 means 'just tell me the newest id'."""
        if after < 0:
            return [], self.last_id
        if not any(e["id"] > after for e in self.items):
            fut = asyncio.get_running_loop().create_future()
            self.waiters.append(fut)
            try:
                await asyncio.wait_for(fut, timeout)
            except asyncio.TimeoutError:
                pass
            finally:
                self.waiters.remove(fut)
        return [e for e in self.items if e["id"] > after], self.last_id

    # ---- watchers
    def watch_pid(self, pid: int) -> str:
        try:
            proc = psutil.Process(pid)
            name = proc.name()
        except Exception:
            return ""
        if pid in self.watching:
            return name

        def run():
            try:
                proc.wait()
            except Exception:
                pass
            self.watching.discard(pid)
            self.push("Finished", f"{name} has closed")
        self.watching.add(pid)
        threading.Thread(target=run, daemon=True).start()
        return name

    def start_download_watcher(self) -> None:
        folder = USER_HOME / "Downloads"

        def scan():
            out = {}
            try:
                for e in folder.iterdir():
                    if e.is_file() and not e.name.startswith(".") and e.suffix.lower() not in TEMP_EXT:
                        st = e.stat()
                        out[str(e)] = (st.st_size, st.st_mtime)
            except OSError:
                pass
            return out

        def run():
            done = set(scan())              # files that already exist never notify
            seen = {}
            while True:
                time.sleep(3)
                files = scan()
                if not aod_settings.load()["notify_downloads"]:
                    done |= set(files)
                    continue
                for path, (size, mtime) in files.items():
                    if path in done:
                        continue
                    if seen.get(path) == size and size > 0 and time.time() - mtime >= 2:
                        done.add(path)
                        self.push("Download finished", f"{path.replace(chr(92), '/').split('/')[-1]} ({_fmt(size)})")
                    else:
                        seen[path] = size
        threading.Thread(target=run, daemon=True).start()
