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


def enable_wol() -> None:
    """Turn on Wake-on-LAN for the network card and switch off Windows Fast Startup (which blocks it). Needs admin: asks once."""
    if sys.platform != "win32":
        return
    script = ("Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object { "
              "Set-NetAdapterPowerManagement -Name $_.Name -WakeOnMagicPacket Enabled -ErrorAction SilentlyContinue; "
              "Set-NetAdapterAdvancedProperty -Name $_.Name -DisplayName 'Wake on Magic Packet' -DisplayValue 'Enabled' -ErrorAction SilentlyContinue }; "
              "reg add 'HKLM\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Power' /v HiberbootEnabled /t REG_DWORD /d 0 /f")
    if os.environ.get("AOD_SERVICE") == "1":
        subprocess.Popen(["powershell", "-NoProfile", "-Command", script], creationflags=0x08000000)
    else:
        arg = script.replace("'", "''")
        subprocess.Popen(["powershell", "-NoProfile", "-Command",
                          f"Start-Process powershell -Verb RunAs -WindowStyle Hidden -ArgumentList '-NoProfile','-Command','{arg}'"],
                         creationflags=0x08000000)


# ---------------------------------------------------------------- file operations
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def _protected(p: Path) -> bool:
    p = p.resolve()
    if p == Path(p.anchor) or p == USER_HOME.resolve():
        return True
    win = os.environ.get("SystemRoot")
    return bool(win) and (p == Path(win) or Path(win) in p.parents)


def fs_op(op: str, path: str, name: str = "") -> dict:
    p = Path(path)
    if op == "mkdir":
        (p / name).mkdir(parents=False, exist_ok=False)
        return {"ok": True}
    if not p.exists():
        raise OSError("Not found")
    if _protected(p):
        raise OSError("That location is protected")
    if op == "rename":
        if not name or any(c in name for c in '\\/:*?"<>|'):
            raise OSError("Bad name")
        p.rename(p.with_name(name))
        return {"ok": True}
    if op == "delete":
        if sys.platform == "win32":
            kind = "DeleteDirectory" if p.is_dir() else "DeleteFile"
            ps = ("Add-Type -AssemblyName Microsoft.VisualBasic; "
                  f"[Microsoft.VisualBasic.FileIO.FileSystem]::{kind}($env:AOD_TARGET,'OnlyErrorDialogs','SendToRecycleBin')")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], env=dict(os.environ, AOD_TARGET=str(p)),
                               capture_output=True, text=True, timeout=60, creationflags=0x08000000)
            if r.returncode:
                raise OSError(r.stderr.strip()[:200] or "Could not delete")
        else:
            import shutil
            from aod_paths import DATA_DIR
            trash = DATA_DIR / "trash"
            trash.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), str(unique_path(trash, p.name)))
        return {"ok": True}
    raise OSError("Unknown operation")


def search_files(root: str, q: str, limit: int = 200, seconds: float = 4.0) -> list:
    q = q.lower().strip()
    out, end = [], time.time() + seconds
    if not q:
        return out
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if not d.startswith(".") and d not in ("node_modules", "$Recycle.Bin", "Windows")]
        for n in dns + fns:
            if q in n.lower():
                full = os.path.join(dp, n)
                try:
                    out.append({"name": n, "path": full, "dir": os.path.isdir(full),
                                "size": 0 if os.path.isdir(full) else os.path.getsize(full)})
                except OSError:
                    pass
                if len(out) >= limit:
                    return out
        if time.time() > end:
            break
    return out


def thumbnail(path: str, size: int = 112):
    p = Path(path)
    if p.suffix.lower() not in IMG_EXT or not p.is_file() or p.stat().st_size > 30 * 1024 * 1024:
        return None
    import io
    from PIL import Image
    with Image.open(p) as im:
        im = im.convert("RGB")
        im.thumbnail((size, size))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=70)
        return buf.getvalue()


def install_vigem() -> None:
    """Download the ViGEmBus driver (virtual Xbox controller) and run its installer; Windows asks for permission."""
    import json
    import tempfile
    import urllib.request
    try:
        req = urllib.request.Request("https://api.github.com/repos/nefarius/ViGEmBus/releases/latest",
                                     headers={"User-Agent": "AOD"})
        with urllib.request.urlopen(req, timeout=20) as r:
            assets = json.load(r)["assets"]
        a = next(x for x in assets if x["name"].lower().endswith(".exe"))
        dest = Path(tempfile.mkdtemp(prefix="aod_vigem_")) / a["name"]
        with urllib.request.urlopen(urllib.request.Request(a["browser_download_url"], headers={"User-Agent": "AOD"}),
                                    timeout=60) as r, open(dest, "wb") as f:
            f.write(r.read())
        if sys.platform == "win32":
            os.startfile(str(dest))             # shows the normal installer + UAC prompt
    except Exception as e:
        print("ViGEmBus install failed:", e)
