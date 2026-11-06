"""AOD extras: system info, processes, power, clipboard, files."""
import asyncio
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil

from aod_paths import USER_HOME

WIN = sys.platform == "win32"
NO_WINDOW = 0x08000000 if WIN else 0


def sysinfo(lan_ip: str) -> dict:
    mac = ""
    for nic, addrs in psutil.net_if_addrs().items():
        if any(a.family == socket.AF_INET and a.address == lan_ip for a in addrs):
            for a in addrs:
                if a.family == psutil.AF_LINK:
                    mac = a.address.replace("-", ":")
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage(USER_HOME.anchor or "/")
    bat = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
    return {
        "host": socket.gethostname(), "ip": lan_ip, "mac": mac,
        "cpu": psutil.cpu_percent(interval=0.2),
        "ram_used": vm.used, "ram_total": vm.total,
        "disk_used": disk.used, "disk_total": disk.total,
        "battery": None if bat is None else {"pct": bat.percent, "plugged": bat.power_plugged},
        "uptime": int(time.time() - psutil.boot_time()),
    }


def processes(limit: int = 60) -> list:
    procs = list(psutil.process_iter(["pid", "name"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except Exception:
            pass
    time.sleep(0.3)
    out = []
    for p in procs:
        try:
            out.append({"pid": p.pid, "name": p.info["name"] or "?",
                        "cpu": round(p.cpu_percent(None) / (psutil.cpu_count() or 1), 1),
                        "mem": p.memory_info().rss})
        except Exception:
            continue
    out.sort(key=lambda x: x["mem"], reverse=True)
    return out[:limit]


def kill(pid: int) -> bool:
    if pid == os.getpid() or pid <= 4:
        return False
    try:
        p = psutil.Process(pid)
        p.terminate()
        try:
            p.wait(2)
        except psutil.TimeoutExpired:
            p.kill()
        return True
    except Exception:
        return False


POWER = {
    "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
    "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    "shutdown": ["shutdown", "/s", "/t", "5"],
    "restart": ["shutdown", "/r", "/t", "5"],
    "logoff": ["shutdown", "/l"],
    "cancel": ["shutdown", "/a"],
}


def power(action: str) -> bool:
    if not WIN or action not in POWER:
        return False
    subprocess.Popen(POWER[action], creationflags=NO_WINDOW)
    return True


# ---- clipboard ----
def clip_get() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except Exception:
        return ""


def clip_set(s: str) -> None:
    try:
        import pyperclip
        pyperclip.copy(s)
    except Exception:
        pass


# ---- files ----
def roots() -> list:
    home = USER_HOME
    r = [{"name": n, "path": str(home / n)} for n in ("Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music")
         if (home / n).exists()]
    r.insert(0, {"name": "Home", "path": str(home)})
    if WIN:
        import string
        r += [{"name": f"{d}:", "path": f"{d}:\\"} for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    else:
        r.append({"name": "/", "path": "/"})
    return r


def listdir(path: str) -> dict:
    p = Path(path).expanduser().resolve()
    items = []
    for e in os.scandir(p):
        try:
            st = e.stat()
            items.append({"name": e.name, "dir": e.is_dir(), "size": 0 if e.is_dir() else st.st_size,
                          "mtime": st.st_mtime})
        except OSError:
            continue
    items.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    parent = str(p.parent) if p.parent != p else None
    return {"path": str(p), "parent": parent, "items": items}


def unique_path(d: Path, name: str) -> Path:
    name = Path(name).name or "file"
    p = d / name
    i = 1
    while p.exists():
        p = d / f"{Path(name).stem} ({i}){Path(name).suffix}"
        i += 1
    return p


def idle_seconds() -> float:
    """Seconds since anyone last touched this PC's keyboard or mouse (including phone input)."""
    if not WIN:
        return 1e9
    import ctypes
    from ctypes import wintypes

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 1e9
    return ((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0
