#!/usr/bin/env python3
"""AOD server: runs on your PC.

Streams your screen to the AOD phone app (a web app served from this same
process), accepts mouse/keyboard input, browses/transfers files and runs power
actions. Everything except the static page requires the pairing token.

Run:  python server.py        (or double-click start.bat on Windows)
"""
from __future__ import annotations

import argparse
import asyncio
import hmac
import io
import json
import logging
import os
import secrets
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import zlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

# Must happen before anything creates windows / reads screen coordinates, so
# screenshot pixels and mouse coordinates agree on high-DPI displays.
if sys.platform == "win32":
    import ctypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from aiohttp import WSMsgType, web
from PIL import Image, ImageDraw

log = logging.getLogger("aod")

FAKE = os.environ.get("AOD_FAKE") == "1"  # test mode: synthetic screen, no real input
BASE = Path(__file__).resolve().parent
WEB = BASE / "web"
CONFIG = BASE / "aod_config.json"
STATIC_FILES = ["app.js", "style.css", "manifest.json", "icon-192.png", "icon-512.png"]


# --------------------------------------------------------------------------- state
class Settings:
    token: str = ""
    roots: list[Path] = []
    view_only: bool = False
    max_upload: int = 2 * 1024**3
    max_sessions: int = 3
    sessions: int = 0
    tickets: dict[str, tuple[Path, float]] = {}
    sockets: set = set()


S = Settings()
FAILS: dict[str, list[float]] = {}  # ip -> [count, first_failure_time]


def load_token(reset: bool = False) -> str:
    if CONFIG.exists() and not reset:
        try:
            tok = json.loads(CONFIG.read_text())["token"]
            if isinstance(tok, str) and len(tok) >= 16:
                return tok
        except Exception:
            pass
    tok = secrets.token_urlsafe(24)
    CONFIG.write_text(json.dumps({"token": tok}))
    try:
        os.chmod(CONFIG, 0o600)
    except OSError:
        pass
    return tok


def check_token(tok) -> bool:
    return isinstance(tok, str) and hmac.compare_digest(tok.encode(), S.token.encode())


def throttled(ip: str) -> bool:
    rec = FAILS.get(ip)
    return bool(rec and rec[0] >= 10 and time.time() - rec[1] < 60)


def note_fail(ip: str) -> None:
    now = time.time()
    rec = FAILS.get(ip)
    if not rec or now - rec[1] >= 60:
        FAILS[ip] = [1, now]
    else:
        rec[0] += 1
    log.warning("rejected token from %s", ip)


def auth(request: web.Request) -> None:
    ip = request.remote or "?"
    if throttled(ip):
        raise web.HTTPTooManyRequests(text="Too many attempts, wait a minute")
    if not check_token(request.headers.get("X-AOD-Token", "")):
        note_fail(ip)
        raise web.HTTPUnauthorized()


# --------------------------------------------------------------------------- screen capture
CAPTURE_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="capture")
_tls = threading.local()  # mss handles are thread-bound on Windows
FAKE_MON = {"left": 0, "top": 0, "width": 1280, "height": 720}


def _sct():
    sct = getattr(_tls, "sct", None)
    if sct is None:
        import mss

        sct = _tls.sct = mss.mss()
    return sct


def _drop_sct() -> None:
    sct = getattr(_tls, "sct", None)
    _tls.sct = None
    try:
        if sct:
            sct.close()
    except Exception:
        pass


def _encode(im: Image.Image, scale: float, quality: int) -> bytes:
    if scale < 0.999:
        size = (max(1, int(im.width * scale)), max(1, int(im.height * scale)))
        im = im.resize(size, Image.BILINEAR, reducing_gap=2.0)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=quality)
    return buf.getvalue()


def list_monitors() -> list[dict]:
    if FAKE:
        return [{"i": 1, "w": 1280, "h": 720, "left": 0, "top": 0}]
    mons = _sct().monitors
    return [
        {"i": i, "w": m["width"], "h": m["height"], "left": m["left"], "top": m["top"]}
        for i, m in enumerate(mons)
        if i >= 1
    ]


def grab(idx: int, scale: float, quality: int, last_crc):
    """Returns (jpeg bytes or None if unchanged, crc, monitor dict)."""
    if FAKE:
        stamp = time.strftime("%H:%M:%S")
        crc = zlib.crc32(stamp.encode())
        if crc == last_crc:
            return None, crc, dict(FAKE_MON)
        im = Image.new("RGB", (1280, 720), (16, 24, 40))
        d = ImageDraw.Draw(im)
        d.rectangle((40, 40, 1240, 680), outline=(255, 179, 71), width=4)
        d.text((80, 80), f"AOD fake screen  {stamp}", fill=(255, 179, 71))
        return _encode(im, scale, quality), crc, dict(FAKE_MON)
    try:
        sct = _sct()
        mons = sct.monitors
        if not 1 <= idx < len(mons):
            idx = 1
        mon = dict(mons[idx])
        shot = sct.grab(mon)
        crc = zlib.crc32(shot.raw)
        if crc == last_crc:
            return None, crc, mon
        im = Image.frombuffer("RGB", shot.size, shot.raw, "raw", "BGRX", 0, 1)
        return _encode(im, scale, quality), crc, mon
    except Exception:
        _drop_sct()
        raise


# --------------------------------------------------------------------------- input
NAMED_KEYS = [
    "enter", "backspace", "tab", "esc", "space", "delete", "home", "end", "up", "down",
    "left", "right", "insert", "caps_lock", "print_screen", "menu", "pageup", "pagedown",
    "ctrl", "alt", "shift", "win", "prev", "playpause", "next", "voldown", "volup", "mute",
] + [f"f{i}" for i in range(1, 13)]
MODIFIERS = {"ctrl", "alt", "shift", "win"}


class Inputs:
    def __init__(self) -> None:
        self.log: list[tuple] = []
        self.pos = [640, 360]
        if FAKE:
            return
        from pynput.keyboard import Controller as KC
        from pynput.keyboard import Key
        from pynput.mouse import Button
        from pynput.mouse import Controller as MC

        self.mouse, self.kb = MC(), KC()
        self.buttons = {"left": Button.left, "right": Button.right, "middle": Button.middle}
        alias = {
            "pageup": "page_up", "pagedown": "page_down", "win": "cmd", "esc": "esc",
            "prev": "media_previous", "playpause": "media_play_pause", "next": "media_next",
            "voldown": "media_volume_down", "volup": "media_volume_up", "mute": "media_volume_mute",
        }
        self.keys = {}
        for name in NAMED_KEYS:
            key = getattr(Key, alias.get(name, name), None)
            if key is not None:
                self.keys[name] = key

    def _rec(self, *item) -> None:
        self.log.append(item)
        del self.log[:-200]

    def cursor_pos(self) -> tuple[int, int]:
        if FAKE:
            return self.pos[0], self.pos[1]
        return self.mouse.position

    def move_rel(self, dx: int, dy: int) -> None:
        if FAKE:
            self.pos[0] += dx
            self.pos[1] += dy
            return self._rec("move", dx, dy)
        self.mouse.move(dx, dy)

    def move_abs(self, x: int, y: int) -> None:
        if FAKE:
            self.pos[:] = [x, y]
            return self._rec("abs", x, y)
        self.mouse.position = (x, y)

    def click(self, b: str, n: int) -> None:
        if FAKE:
            return self._rec("click", b, n)
        self.mouse.click(self.buttons[b], n)

    def button(self, b: str, down: bool) -> None:
        if FAKE:
            return self._rec("down" if down else "up", b)
        (self.mouse.press if down else self.mouse.release)(self.buttons[b])

    def scroll(self, n: int) -> None:
        if FAKE:
            return self._rec("scroll", n)
        self.mouse.scroll(0, n)

    def _k(self, name: str):
        name = name.lower()
        if name in NAMED_KEYS:
            return name if FAKE else self.keys[name]
        if len(name) == 1:
            return name
        raise ValueError(f"unknown key {name!r}")

    def key(self, name: str, n: int = 1) -> None:
        k = self._k(name)
        if FAKE:
            return self._rec("key", name, n)
        for _ in range(n):
            self.kb.press(k)
            self.kb.release(k)

    def hotkey(self, names: list[str]) -> None:
        keys = [self._k(x) for x in names]
        if FAKE:
            return self._rec("hotkey", tuple(names))
        pressed = []
        try:
            for k in keys:
                self.kb.press(k)
                pressed.append(k)
        finally:
            for k in reversed(pressed):
                self.kb.release(k)

    def type(self, text: str) -> None:
        if FAKE:
            return self._rec("text", text)
        self.kb.type(text)


INPUT = Inputs()


def num(m: dict, key: str, lo: float, hi: float, default: float = 0) -> float:
    try:
        v = float(m.get(key, default))
    except (TypeError, ValueError):
        return default
    if v != v:  # NaN
        return default
    return max(lo, min(hi, v))


def btn_name(m: dict) -> str:
    b = m.get("b", "left")
    return b if b in ("left", "right", "middle") else "left"


class Session:
    def __init__(self) -> None:
        self.monitor = 1
        self.scale = 0.6
        self.quality = 55
        self.fps = 12
        self.active = True
        self.force = True
        self.mon: dict | None = None


def handle(sess: Session, m: dict) -> None:
    t = m.get("t")
    if t == "cfg":
        sess.quality = int(num(m, "quality", 20, 95, sess.quality))
        sess.scale = num(m, "scale", 0.2, 1.0, sess.scale)
        sess.fps = int(num(m, "fps", 2, 30, sess.fps))
        sess.monitor = int(num(m, "monitor", 1, 16, sess.monitor))
        sess.force = True
        return
    if t == "pause":
        sess.active = False
        return
    if t == "resume":
        sess.active = True
        sess.force = True
        return
    if S.view_only:
        return
    if t == "move":
        INPUT.move_rel(int(num(m, "dx", -3000, 3000)), int(num(m, "dy", -3000, 3000)))
    elif t == "abs":
        mon = sess.mon or FAKE_MON
        x = mon["left"] + int(num(m, "x", 0, 1) * (mon["width"] - 1))
        y = mon["top"] + int(num(m, "y", 0, 1) * (mon["height"] - 1))
        INPUT.move_abs(x, y)
    elif t == "click":
        INPUT.click(btn_name(m), int(num(m, "n", 1, 3, 1)))
    elif t in ("down", "up"):
        INPUT.button(btn_name(m), t == "down")
    elif t == "scroll":
        INPUT.scroll(int(num(m, "dy", -30, 30)))
    elif t == "key":
        INPUT.key(str(m.get("key", "")), int(num(m, "n", 1, 50, 1)))
    elif t == "hotkey":
        keys = m.get("keys")
        if isinstance(keys, list) and 1 <= len(keys) <= 4 and all(isinstance(k, str) for k in keys):
            INPUT.hotkey(keys)
    elif t == "text":
        text = m.get("text")
        if isinstance(text, str):
            INPUT.type(text[:500])


async def stream(ws: web.WebSocketResponse, sess: Session) -> None:
    """Frame format: float32 cursor x, float32 cursor y (0..1 of the monitor), then JPEG
    bytes. A frame with no JPEG bytes means only the cursor moved."""
    loop = asyncio.get_running_loop()
    last_crc = None
    last_cur = None
    while not ws.closed:
        t0 = time.monotonic()
        if not sess.active:
            await asyncio.sleep(0.25)
            continue
        if sess.force:
            sess.force, last_crc = False, None
        try:
            jpeg, crc, mon = await loop.run_in_executor(
                CAPTURE_POOL, grab, sess.monitor, sess.scale, sess.quality, last_crc
            )
        except Exception as exc:
            log.warning("capture failed (%s); retrying", exc)
            await asyncio.sleep(1)
            continue
        sess.mon = mon
        cx, cy = INPUT.cursor_pos()
        nx = round((cx - mon["left"]) / mon["width"], 4)
        ny = round((cy - mon["top"]) / mon["height"], 4)
        if jpeg is not None or (nx, ny) != last_cur:
            try:
                await ws.send_bytes(struct.pack("<ff", nx, ny) + (jpeg or b""))
            except ConnectionResetError:
                return
            last_cur = (nx, ny)
            if jpeg is not None:
                last_crc = crc
        await asyncio.sleep(max(0.005, 1 / sess.fps - (time.monotonic() - t0)))


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ip = request.remote or "?"
    if throttled(ip):
        raise web.HTTPTooManyRequests()
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=1 << 20)
    await ws.prepare(request)
    try:
        first = await ws.receive(timeout=8)
        data = json.loads(first.data) if first.type == WSMsgType.TEXT else {}
    except (asyncio.TimeoutError, ValueError):
        data = {}
    if not isinstance(data, dict) or data.get("t") != "auth" or not check_token(data.get("token")):
        note_fail(ip)
        await ws.send_json({"t": "denied"})
        await ws.close()
        return ws
    if S.sessions >= S.max_sessions:
        await ws.send_json({"t": "busy"})
        await ws.close()
        return ws

    S.sessions += 1
    S.sockets.add(ws)
    sess = Session()
    task = None
    log.info("phone connected from %s", ip)
    try:
        mons = await asyncio.get_running_loop().run_in_executor(CAPTURE_POOL, list_monitors)
        await ws.send_json(
            {"t": "hello", "host": socket.gethostname(), "monitors": mons, "view_only": S.view_only}
        )
        task = asyncio.create_task(stream(ws, sess))
        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
                if isinstance(data, dict):
                    handle(sess, data)
            except Exception as exc:
                log.debug("bad message: %s", exc)
    finally:
        if task:
            task.cancel()
        S.sessions -= 1
        S.sockets.discard(ws)
        log.info("phone disconnected (%s)", ip)
    return ws


# --------------------------------------------------------------------------- files
def resolve_allowed(raw: str) -> Path:
    try:
        p = Path(raw).expanduser().resolve()
    except (OSError, ValueError):
        raise web.HTTPBadRequest(text="Bad path")
    if any(p == r or p.is_relative_to(r) for r in S.roots):
        return p
    raise web.HTTPForbidden(text="Outside the allowed folders")


def list_dir(p: Path) -> list[dict]:
    out = []
    try:
        with os.scandir(p) as it:
            for e in it:
                try:
                    st = e.stat()
                    is_dir = e.is_dir()
                except OSError:
                    continue
                out.append(
                    {
                        "name": e.name,
                        "path": e.path,
                        "dir": is_dir,
                        "size": 0 if is_dir else st.st_size,
                        "mtime": int(st.st_mtime),
                    }
                )
                if len(out) >= 3000:
                    break
    except PermissionError:
        raise web.HTTPForbidden(text="Permission denied")
    out.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return out


async def api_files(request: web.Request) -> web.Response:
    auth(request)
    q = request.query.get("path", "")
    if not q:
        if len(S.roots) > 1:
            entries = [
                {"name": r.name or str(r), "path": str(r), "dir": True, "size": 0, "mtime": 0}
                for r in S.roots
            ]
            return web.json_response({"path": "", "parent": None, "entries": entries})
        p = S.roots[0]
    else:
        p = resolve_allowed(q)
    if not p.is_dir():
        raise web.HTTPNotFound()
    entries = await asyncio.get_running_loop().run_in_executor(None, list_dir, p)
    parent = None
    if p not in S.roots:
        parent = str(p.parent)
    elif len(S.roots) > 1:
        parent = ""
    return web.json_response({"path": str(p), "parent": parent, "entries": entries})


async def read_json(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Expected JSON")
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="Expected a JSON object")
    return data


async def api_ticket(request: web.Request) -> web.Response:
    auth(request)
    p = resolve_allowed(str((await read_json(request)).get("path", "")))
    if not p.is_file():
        raise web.HTTPNotFound()
    now = time.time()
    for k in [k for k, (_, exp) in S.tickets.items() if exp < now]:
        del S.tickets[k]
    key = secrets.token_urlsafe(16)
    S.tickets[key] = (p, now + 60)
    return web.json_response({"ticket": key})


async def api_download(request: web.Request) -> web.StreamResponse:
    rec = S.tickets.get(request.query.get("ticket", ""))
    if not rec or rec[1] < time.time():
        raise web.HTTPNotFound()
    p = resolve_allowed(str(rec[0]))
    if not p.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(
        p,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(p.name)}",
            "Cache-Control": "no-store",
        },
    )


def clean_name(raw: str) -> str:
    name = os.path.basename(raw.replace("\\", "/"))
    name = "".join(c for c in name if c >= " " and c not in '<>:"|?*').strip(" .")
    return name if name and name not in (".", "..") else ""


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    for i in range(1, 1000):
        cand = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not cand.exists():
            return cand
    raise web.HTTPConflict(text="Too many files with that name")


async def api_upload(request: web.Request) -> web.Response:
    auth(request)
    if S.view_only:
        raise web.HTTPForbidden(text="View-only mode")
    dest = resolve_allowed(request.query.get("path", ""))
    if not dest.is_dir():
        raise web.HTTPBadRequest(text="Not a folder")
    reader = await request.multipart()
    saved = []
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name != "file" or not part.filename:
            continue
        name = clean_name(part.filename)
        if not name:
            raise web.HTTPBadRequest(text="Bad file name")
        target = unique_path(dest / name)
        size = 0
        try:
            with open(target, "wb") as f:
                while chunk := await part.read_chunk(1 << 20):
                    size += len(chunk)
                    if size > S.max_upload:
                        raise web.HTTPRequestEntityTooLarge(S.max_upload, size)
                    f.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        saved.append(target.name)
        log.info("received %s (%d bytes)", target, size)
    return web.json_response({"saved": saved})


# --------------------------------------------------------------------------- power
def run_power(action: str) -> bool:
    if FAKE:
        INPUT._rec("power", action)
        return True
    if sys.platform != "win32":
        return False
    if action == "lock":
        ctypes.windll.user32.LockWorkStation()
    elif action == "sleep":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
    elif action == "restart":
        subprocess.Popen(["shutdown", "/r", "/t", "10"])
    elif action == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "10"])
    elif action == "cancel":
        subprocess.Popen(["shutdown", "/a"])
    else:
        return False
    return True


async def api_power(request: web.Request) -> web.Response:
    auth(request)
    if S.view_only:
        raise web.HTTPForbidden(text="View-only mode")
    action = (await read_json(request)).get("action")
    if action not in ("lock", "sleep", "restart", "shutdown", "cancel"):
        raise web.HTTPBadRequest(text="Unknown action")
    log.warning("power action: %s", action)
    if not run_power(action):
        raise web.HTTPNotImplemented(text="Power actions are only supported on Windows")
    return web.json_response({"ok": True})


# --------------------------------------------------------------------------- app
async def index(request: web.Request) -> web.StreamResponse:
    return web.FileResponse(WEB / "index.html")


async def add_headers(request: web.Request, response: web.StreamResponse) -> None:
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'none'"
    )
    if request.path in ("/", "/app.js", "/style.css"):
        response.headers["Cache-Control"] = "no-cache"


async def on_shutdown(app: web.Application) -> None:
    for ws in list(S.sockets):
        await ws.close(code=1001)


def build_app() -> web.Application:
    app = web.Application()
    app.on_response_prepare.append(add_headers)
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_get("/api/files", api_files)
    app.router.add_post("/api/ticket", api_ticket)
    app.router.add_get("/api/download", api_download)
    app.router.add_post("/api/upload", api_upload)
    app.router.add_post("/api/power", api_power)
    for name in STATIC_FILES:
        path = WEB / name
        app.router.add_get("/" + name, lambda r, p=path: web.FileResponse(p))
    return app


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # no packet is sent; just picks the LAN interface
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def print_pairing(url: str) -> None:
    print("\n  AOD is running.\n")
    print("  Open this on your phone (same Wi-Fi), or scan the QR code:\n")
    print(f"  {url}\n")
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        try:
            qr.print_ascii(invert=True)
        except Exception:
            pass
        qr.make_image().save(BASE / "aod_pair.png")
        print("\n  (The same QR code is saved as aod_pair.png)")
    except Exception:
        pass
    print("\n  The link contains your private token. Don't share it.")
    print("  Press Ctrl+C to stop.\n", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="AOD: control your PC from your phone")
    ap.add_argument("--host", default="0.0.0.0", help="address to listen on (default all)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--root", action="append", help="folder the phone may browse (repeatable; default: your home folder)")
    ap.add_argument("--view-only", action="store_true", help="screen view and downloads only; no input, uploads or power")
    ap.add_argument("--reset-token", action="store_true", help="generate a new pairing token (signs out all phones)")
    ap.add_argument("--cert", help="TLS certificate (enables https)")
    ap.add_argument("--key", help="TLS private key")
    ap.add_argument("--public-host", help="host or IP to put in the pairing link (e.g. a Tailscale address)")
    ap.add_argument("--max-upload-mb", type=int, default=2048)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    S.token = load_token(args.reset_token)
    S.view_only = args.view_only
    S.max_upload = args.max_upload_mb * 1024 * 1024
    S.roots = [Path(r).expanduser().resolve() for r in (args.root or [Path.home()])]

    ctx = None
    if args.cert or args.key:
        if not (args.cert and args.key):
            ap.error("--cert and --key must be used together")
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(args.cert, args.key)

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    scheme = "https" if ctx else "http"
    host = args.public_host or lan_ip()
    print_pairing(f"{scheme}://{host}:{args.port}/#token={S.token}")
    if S.view_only:
        print("  View-only mode: input, uploads and power actions are disabled.\n")
    web.run_app(build_app(), host=args.host, port=args.port, ssl_context=ctx, print=None, access_log=None)


if __name__ == "__main__":
    main()
