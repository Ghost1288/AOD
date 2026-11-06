"""AOD host (Windows): screen + audio streaming, remote input, files, tasks, power.

Run:  python aod_host.py        (or the installed AOD app)
"""
import asyncio
import io
import json
import os
import ssl
import sys
import threading
import time
from pathlib import Path

from aod_paths import DATA_DIR, SERVICE, USER_HOME

from aiohttp import web, WSMsgType

try:  # real pixel coordinates on high-DPI Windows screens
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

from pynput.keyboard import Controller as Keyboard, Key
from pynput.mouse import Controller as Mouse, Button

import aod_apps
import aod_desktop
import aod_events
import aod_features as feat
import aod_gamepad
import aod_gameinput
import aod_rtc
import aod_security as sec
import aod_settings
import aod_window
import aod_update
import aod_version

PORT = int(os.environ.get("AOD_PORT", "8765"))
ADMIN_PORT = PORT + 1
ADMIN_URL = f"http://127.0.0.1:{ADMIN_PORT}/"
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
STATIC = BASE / "static"
APP_VERSION = aod_version.VERSION

mouse, keyboard = Mouse(), Keyboard()
devices = sec.Devices()
state = sec.State()
capturer = aod_rtc.Capturer()
sessions = set()          # live websockets (for the kill switch)
updater = aod_update.Updater(lambda: bool(sessions))
events = aod_events.Events()
LOOP = None
CERT, KEY, FINGERPRINT = sec.ensure_cert()

SPECIAL_KEYS = {
    "enter": Key.enter, "backspace": Key.backspace, "tab": Key.tab, "esc": Key.esc,
    "space": Key.space, "delete": Key.delete, "up": Key.up, "down": Key.down,
    "left": Key.left, "right": Key.right, "home": Key.home, "end": Key.end,
    "pageup": Key.page_up, "pagedown": Key.page_down, "ctrl": Key.ctrl, "alt": Key.alt,
    "shift": Key.shift, "win": Key.cmd, "printscreen": Key.print_screen,
    "volup": Key.media_volume_up, "voldown": Key.media_volume_down, "mute": Key.media_volume_mute,
    "playpause": Key.media_play_pause, "next": Key.media_next, "prev": Key.media_previous,
    **{f"f{i}": getattr(Key, f"f{i}") for i in range(1, 13)},
}
BUTTONS = {"left": Button.left, "right": Button.right, "middle": Button.middle}


# ------------------------------------------------------------------ auth
def authed(request: web.Request) -> str:
    if not state.enabled:
        raise web.HTTPServiceUnavailable(text="AOD is paused on the PC")
    h = request.headers.get("Authorization", "")
    token = h[7:] if h.startswith("Bearer ") else request.query.get("token")
    did = devices.check(token)
    if not did:
        raise web.HTTPUnauthorized()
    devices.touch(did, request.remote)
    return did


def loopback_only(request: web.Request) -> None:
    if request.remote not in ("127.0.0.1", "::1") or request.headers.get("X-AOD-Admin") != "1" and request.method != "GET":
        raise web.HTTPForbidden()


# ------------------------------------------------------------------ pairing
async def pair(request: web.Request) -> web.Response:
    ip = request.remote
    if not state.pairing_allowed or not state.enabled:
        return web.json_response({"error": "pairing is turned off on the PC"}, status=403)
    if state.locked(ip):
        return web.json_response({"error": "too many wrong PINs, try again in a few minutes"}, status=429)
    data = await request.json()
    if not state.pin_ok(ip, data.get("pin", "")):
        return web.json_response({"error": "wrong PIN"}, status=401)
    name = str(data.get("name") or "Phone")[:60]
    loop = asyncio.get_running_loop()
    if not await loop.run_in_executor(None, sec.ask_approval, state, name, ip):
        return web.json_response({"error": "denied on the PC"}, status=403)
    token = devices.add(name, ip)
    state.rotate_pin()
    return web.json_response({"token": token})


# ------------------------------------------------------------------ input
def apply_input(msg: dict, mon: dict) -> None:
    t = msg.get("t")
    if t == "move":
        mouse.move(int(msg["dx"]), int(msg["dy"]))
    elif t == "abs":
        mouse.position = (mon["left"] + int(msg["x"] * mon["width"]),
                          mon["top"] + int(msg["y"] * mon["height"]))
    elif t == "click":
        mouse.click(BUTTONS.get(msg.get("b", "left"), Button.left), int(msg.get("n", 1)))
    elif t == "down":
        mouse.press(BUTTONS.get(msg.get("b", "left"), Button.left))
    elif t == "up":
        mouse.release(BUTTONS.get(msg.get("b", "left"), Button.left))
    elif t == "scroll":
        mouse.scroll(int(msg.get("dx", 0)), int(msg.get("dy", 0)))
    elif t == "text":
        keyboard.type(str(msg["s"])[:2000])
    elif t == "key":
        combo = [SPECIAL_KEYS[k] if k in SPECIAL_KEYS else k
                 for k in msg.get("keys", []) if k in SPECIAL_KEYS or len(k) == 1]
        for k in combo:
            keyboard.press(k)
        for k in reversed(combo):
            keyboard.release(k)


# ------------------------------------------------------------------ websocket
async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    authed(request)
    ws = web.WebSocketResponse(max_msg_size=1 << 20, heartbeat=20)
    await ws.prepare(request)
    sessions.add(ws)
    loop = asyncio.get_running_loop()

    st = {"mon": 1, "scale": 0.6, "quality": 55, "fps": 15, "rtc_scale": 1.0, "game": False}
    gi = aod_gameinput.GameInput()
    mons = await capturer.monitors()
    tasks, pcs = {}, []
    last_clip = {"v": await loop.run_in_executor(None, feat.clip_get)}

    def mon_geom():
        return mons[min(st["mon"], len(mons)) - 1]

    async def send_info():
        m = mon_geom()
        await ws.send_json({"t": "info", "monitors": len(mons), "current": st["mon"],
                            "w": m["width"], "h": m["height"], "rtc": aod_rtc.RTC_OK,
                            "pad": aod_gamepad.importable(), "version": APP_VERSION})

    async def jpeg_loop():
        while not ws.closed:
            t0 = time.monotonic()
            data = await capturer.jpeg(st["mon"], st["scale"], int(st["quality"]))
            await ws.send_bytes(data)
            await asyncio.sleep(max(0, 1 / st["fps"] - (time.monotonic() - t0)))

    async def cursor_loop():
        last = None
        while not ws.closed:
            if st["game"]:
                await asyncio.sleep(0.25)
                continue
            aod_desktop.sync()
            m = mon_geom()
            x, y = mouse.position
            cur = (round((x - m["left"]) / m["width"], 4), round((y - m["top"]) / m["height"], 4))
            if cur != last:
                last = cur
                await ws.send_json({"t": "cur", "x": cur[0], "y": cur[1]})
            await asyncio.sleep(0.04)

    async def clip_loop():
        while not ws.closed:
            await asyncio.sleep(1)
            v = await loop.run_in_executor(None, feat.clip_get)
            if v != last_clip["v"] and len(v) < 200_000:
                last_clip["v"] = v
                await ws.send_json({"t": "clip", "s": v})

    async def rtc_closed():
        if not ws.closed and "jpeg" not in tasks and "rtc_failed" not in tasks:
            await ws.send_json({"t": "rtc_closed"})

    tasks["cursor"] = asyncio.create_task(cursor_loop())
    tasks["clip"] = asyncio.create_task(clip_loop())
    await send_info()

    try:
        async for m in ws:
            if m.type != WSMsgType.TEXT:
                continue
            aod_desktop.sync()
            try:
                msg = json.loads(m.data)
            except ValueError:
                continue
            t = msg.get("t")
            if t == "cfg":
                for k, lo, hi in (("scale", 0.2, 1.0), ("quality", 20, 90), ("fps", 3, 60), ("rtc_scale", 0.25, 1.0)):
                    if k in msg:
                        st[k] = min(hi, max(lo, float(msg[k])))
            elif t == "monitor":
                mons = await capturer.monitors()
                st["mon"] = min(max(1, int(msg["i"])), len(mons))
                await send_info()
            elif t == "jpeg":
                if "jpeg" not in tasks:
                    tasks["jpeg"] = asyncio.create_task(jpeg_loop())
            elif t == "offer" and aod_rtc.RTC_OK:
                try:
                    pc, sdp = await aod_rtc.answer_offer(msg["sdp"], capturer, st,
                                                         bool(msg.get("audio", True)), rtc_closed)
                    pcs.append(pc)
                    await ws.send_json({"t": "answer", "sdp": sdp})
                except Exception as e:
                    print("WebRTC failed:", e)
                    tasks["rtc_failed"] = None
                    await ws.send_json({"t": "rtc_error", "error": str(e)})
            elif t == "game":
                st["game"] = bool(msg.get("on"))
                aod_rtc.set_bitrate(st["game"])
                if not st["game"]:
                    gi.release_all()
                    aod_gamepad.pad.release()
            elif t == "g_key":
                gi.key(str(msg.get("k", "")), bool(msg.get("d")))
            elif t == "g_btn":
                gi.button(str(msg.get("b", "")), bool(msg.get("d")))
            elif t == "g_mouse":
                gi.move(int(msg.get("dx", 0)), int(msg.get("dy", 0)))
            elif t == "g_wheel":
                gi.wheel(int(msg.get("dy", 0)))
            elif t == "g_release":
                gi.release_all()
                aod_gamepad.pad.release()
            elif t == "pad":
                try:
                    aod_gamepad.pad.apply(msg["a"], int(msg["m"]))
                except Exception as e:
                    print("Virtual gamepad unavailable:", e)
                    await ws.send_json({"t": "pad_error"})
            elif t == "clip_set":
                s = str(msg.get("s", ""))[:200_000]
                last_clip["v"] = s
                await loop.run_in_executor(None, feat.clip_set, s)
            elif t == "clip_get":
                await ws.send_json({"t": "clip", "s": await loop.run_in_executor(None, feat.clip_get)})
            else:
                try:
                    apply_input(msg, mon_geom())
                except Exception as e:
                    print("input error:", e)
    finally:
        gi.release_all()
        aod_gamepad.pad.release()
        sessions.discard(ws)
        schedule_autolock()
        for task in tasks.values():
            if task:
                task.cancel()
        for pc in pcs:
            await pc.close()
    return ws


# ------------------------------------------------------------------ REST (authenticated)
async def api_sysinfo(request):
    authed(request)
    info = await asyncio.get_running_loop().run_in_executor(None, feat.sysinfo, sec.lan_ip())
    info["ts"] = sec.tailscale_ip()
    return web.json_response(info)


def _shot_dir(kind: str) -> Path:
    return USER_HOME / kind / "AOD"


async def api_screenshot(request):
    authed(request)
    q = request.query
    mons = await capturer.monitors()
    idx = min(max(1, int(q.get("mon") or st_mon())), len(mons))
    data = await capturer.jpeg(idx, 1.0, 92)
    name = time.strftime("AOD-%Y%m%d-%H%M%S.jpg")
    if q.get("save") == "1":
        d = _shot_dir("Pictures")
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_bytes(data)
        events.push("Screenshot saved", str(d / name))
    headers = {"Content-Disposition": f'attachment; filename="{name}"'} if q.get("dl") == "1" else {}
    return web.Response(body=data, content_type="image/jpeg", headers=headers)


def st_mon() -> int:
    return 1


async def api_record(request):
    authed(request)
    if request.method == "POST":
        on = bool((await request.json()).get("on"))
        if on and not aod_rtc.RECORDER.on:
            path = _shot_dir("Videos") / time.strftime("AOD-%Y%m%d-%H%M%S.mp4")
            aod_rtc.RECORDER.start(path, lambda p: events.push(
                "Recording saved" if p else "Recording failed", str(p) if p else "No video was being streamed"))
        elif not on:
            aod_rtc.RECORDER.stop()
    r = aod_rtc.RECORDER
    return web.json_response({"on": r.on, "path": str(r.path) if r.path else None})


async def api_procs(request):
    authed(request)
    return web.json_response(await asyncio.get_running_loop().run_in_executor(None, feat.processes))


async def api_kill(request):
    authed(request)
    pid = int((await request.json())["pid"])
    return web.json_response({"ok": feat.kill(pid)})


async def api_power(request):
    authed(request)
    action = (await request.json()).get("action")
    return web.json_response({"ok": feat.power(action)})


async def api_roots(request):
    authed(request)
    return web.json_response(feat.roots())


async def api_files(request):
    authed(request)
    try:
        return web.json_response(feat.listdir(request.query.get("path") or str(USER_HOME)))
    except OSError as e:
        return web.json_response({"error": str(e)}, status=400)


async def api_download(request):
    authed(request)
    p = Path(request.query.get("path", "")).resolve()
    if not p.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Content-Disposition": f'attachment; filename="{p.name}"'})


async def api_upload(request):
    authed(request)
    dest = Path(request.query.get("dir") or USER_HOME / "Downloads" / "AOD").expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    saved = []
    reader = await request.multipart()
    while (part := await reader.next()) is not None:
        if not part.filename:
            continue
        target = feat.unique_path(dest, part.filename)
        with open(target, "wb") as f:
            while chunk := await part.read_chunk(1 << 20):
                f.write(chunk)
        saved.append(str(target))
    return web.json_response({"saved": saved})


async def api_devices(request):
    authed(request)
    return web.json_response(devices.public_list())


async def api_device_revoke(request):
    did = authed(request)
    target = request.match_info["id"]
    ok = devices.revoke(target)
    if target == did:
        for w in list(sessions):
            await w.close()
    return web.json_response({"ok": ok})


async def _in_thread(fn, *a):
    return await asyncio.get_running_loop().run_in_executor(None, fn, *a)


async def api_shortcuts_get(request):
    authed(request)
    return web.json_response(aod_apps.load_shortcuts())


async def api_shortcuts_put(request):
    authed(request)
    return web.json_response(aod_apps.save_shortcuts(await request.json()))


async def api_apps(request):
    authed(request)
    return web.json_response(await _in_thread(aod_apps.list_apps, request.query.get("q", "")))


async def api_launch(request):
    authed(request)
    ok = await _in_thread(aod_apps.launch, str((await request.json()).get("target", "")))
    return web.json_response({"ok": ok})


async def api_run(request):
    authed(request)
    return web.json_response(await _in_thread(aod_apps.run_cmd, str((await request.json()).get("cmd", ""))))


async def api_events(request):
    authed(request)
    after = int(request.query.get("after", "-1"))
    wait = min(30.0, float(request.query.get("wait", "0")))
    evs, last = await events.wait(after, wait)
    return web.json_response({"events": evs, "last": last})


async def api_watch(request):
    authed(request)
    name = events.watch_pid(int((await request.json())["pid"]))
    return web.json_response({"ok": bool(name), "name": name})


def settings_payload() -> dict:
    return {**aod_settings.load(), "service": SERVICE}


async def api_settings_get(request):
    authed(request)
    return web.json_response(settings_payload())


async def api_settings_post(request):
    authed(request)
    aod_settings.update(await request.json())
    return web.json_response(settings_payload())


async def api_share(request):
    """Used by Android's Share menu: open a link on the PC or put text on its clipboard."""
    authed(request)
    data = await request.json()
    kind, text = data.get("kind"), str(data.get("text", ""))[:200_000]
    if kind == "open" and text.lower().startswith(("http://", "https://")):
        ok = await _in_thread(aod_apps.launch, text)
    elif kind == "clip":
        await _in_thread(feat.clip_set, text)
        ok = True
    else:
        ok = False
    if ok:
        events.push("Shared from phone", ("Opened " if kind == "open" else "Copied: ") + text[:80])
    return web.json_response({"ok": ok})


def schedule_autolock() -> None:
    """Lock the PC a while after the last phone disconnects, unless someone is using the PC."""
    s = aod_settings.load()
    if s["autolock"] and not sessions and LOOP:
        LOOP.call_later(int(s["autolock_secs"]), check_autolock)


def check_autolock() -> None:
    s = aod_settings.load()
    if sessions or not s["autolock"]:
        return
    if feat.idle_seconds() >= int(s["autolock_secs"]) - 2:      # nobody has touched the PC since
        feat.power("lock")


# ------------------------------------------------------------------ admin page (PC only)
def urls():
    ip = sec.lan_ip()
    base = f"https://{ip}:{PORT}"
    pin = state.current_pin()
    return ip, base, pin


async def admin_page(request):
    loopback_only(request)
    return web.FileResponse(STATIC / "admin.html")


async def admin_state(request):
    loopback_only(request)
    ip, base, pin = urls()
    return web.json_response({
        "url": base, "pin": pin, "pin_expires": int(sec.PIN_LIFETIME - (time.time() - state.pin_time)),
        "enabled": state.enabled, "pairing_allowed": state.pairing_allowed,
        "devices": devices.public_list(), "version": APP_VERSION, "window_error": aod_window.last_error,
        "rtc": aod_rtc.RTC_OK, "fingerprint": FINGERPRINT, "update": updater.public(),
        "tailscale": sec.tailscale_ip(), "dx": aod_rtc.DX_OK, "pad": aod_gamepad.importable(),
        "settings": settings_payload()})


def qr_png(data: str) -> bytes:
    import qrcode
    buf = io.BytesIO()
    qrcode.make(data, box_size=6, border=2).save(buf, "PNG")
    return buf.getvalue()


async def admin_qr(request):
    loopback_only(request)
    ip, base, pin = urls()
    kind = request.query.get("kind", "app")
    ts = sec.tailscale_ip()
    if kind == "app":
        data = f"aod://pair?host={ip}&port={PORT}&fp={FINGERPRINT}&pin={pin}" + (f"&ts={ts}" if ts else "")
    elif kind == "remote" and ts:
        data = f"https://{ts}:{PORT}/?pin={pin}"
    else:
        data = f"{base}/?pin={pin}"
    return web.Response(body=qr_png(data), content_type="image/png", headers={"Cache-Control": "no-store"})


async def admin_action(request):
    loopback_only(request)
    a = request.match_info["a"]
    if a == "revoke_all":
        devices.revoke_all()
        for w in list(sessions):
            await w.close()
    elif a == "revoke":
        devices.revoke(request.query.get("id", ""))
    elif a == "pause":
        set_enabled(not state.enabled)
    elif a == "pairing":
        state.pairing_allowed = not state.pairing_allowed
    elif a == "new_pin":
        state.rotate_pin()
    elif a == "quit":
        def _bye():
            import aod_tray
            aod_tray.stop()
            os._exit(0)
        LOOP.call_later(0.4, _bye)      # let this HTTP response finish first
    elif a == "show":
        show_ui()
    elif a == "setting":
        k, v = request.query.get("k", ""), request.query.get("v", "")
        aod_settings.update({k: (v == "1") if k in ("autolock", "notify_downloads") else v})
    elif a == "wol":
        threading.Thread(target=feat.enable_wol, daemon=True).start()
    elif a == "service_install":
        import aod_launcher
        threading.Thread(target=aod_launcher.install, daemon=True).start()
    elif a == "service_remove":
        import aod_launcher
        threading.Thread(target=aod_launcher.remove, daemon=True).start()
    elif a == "notify":
        body = await request.json()
        events.push(str(body.get("title", "AOD")), str(body.get("text", "")))
    elif a == "update":
        updater.check_and_apply_now()
    elif a == "autoupd":
        updater.set_auto(not updater.auto)
    return web.json_response({"ok": True})


def set_enabled(on: bool) -> None:
    """Kill switch. Pausing also drops every live connection."""
    state.enabled = on
    if not on:
        for w in list(sessions):
            asyncio.run_coroutine_threadsafe(w.close(), LOOP)



async def on_startup(app):
    global LOOP
    LOOP = asyncio.get_running_loop()


def make_app() -> web.Application:
    app = web.Application()
    r = app.router
    r.add_post("/api/pair", pair)
    r.add_get("/ws", ws_handler)
    r.add_get("/api/sysinfo", api_sysinfo)
    r.add_get("/api/procs", api_procs)
    r.add_post("/api/kill", api_kill)
    r.add_post("/api/power", api_power)
    r.add_get("/api/roots", api_roots)
    r.add_get("/api/files", api_files)
    r.add_get("/api/download", api_download)
    r.add_get("/api/screenshot", api_screenshot)
    r.add_get("/api/record", api_record)
    r.add_post("/api/record", api_record)
    r.add_post("/api/upload", api_upload)
    r.add_get("/api/shortcuts", api_shortcuts_get)
    r.add_put("/api/shortcuts", api_shortcuts_put)
    r.add_get("/api/apps", api_apps)
    r.add_post("/api/launch", api_launch)
    r.add_post("/api/run", api_run)
    r.add_get("/api/events", api_events)
    r.add_post("/api/watch", api_watch)
    r.add_get("/api/settings", api_settings_get)
    r.add_post("/api/settings", api_settings_post)
    r.add_post("/api/share", api_share)
    r.add_get("/api/devices", api_devices)
    r.add_delete("/api/devices/{id}", api_device_revoke)
    r.add_get("/", lambda req: web.FileResponse(STATIC / "index.html"))
    r.add_static("/", STATIC)
    return app


def make_admin_app() -> web.Application:
    """PC-only dashboard: plain HTTP on 127.0.0.1, so no certificate warning and unreachable from the network."""
    app = web.Application()
    r = app.router
    r.add_get("/", admin_page)
    r.add_get("/_admin/state", admin_state)
    r.add_get("/_admin/qr.png", admin_qr)
    r.add_post("/_admin/{a}", admin_action)
    return app


async def start_site(site) -> None:
    """Bind a port, retrying for ~10 s (an old copy may still be shutting down after an update)."""
    for attempt in range(10):
        try:
            await site.start()
            return
        except OSError:
            if attempt == 9:
                raise
            await asyncio.sleep(1)


def already_running() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(ADMIN_URL + "_admin/state", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def fatal(msg: str) -> None:
    print(msg)
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(0, msg, "AOD", 0x10)
        except Exception:
            pass


async def serve() -> None:
    global LOOP
    LOOP = asyncio.get_running_loop()
    events.loop = LOOP

    def broadcast(ev):
        for w in list(sessions):
            asyncio.ensure_future(w.send_json({"t": "notify", **ev}))
    events.listeners.append(broadcast)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)
    r1 = web.AppRunner(make_app())
    await r1.setup()
    await start_site(web.TCPSite(r1, "0.0.0.0", PORT, ssl_context=ctx))
    r2 = web.AppRunner(make_admin_app())
    await r2.setup()
    await start_site(web.TCPSite(r2, "127.0.0.1", ADMIN_PORT))
    print("AOD is running.")
    await asyncio.Event().wait()


def server_thread() -> None:
    try:
        asyncio.run(serve())
    except OSError as e:
        fatal(f"AOD couldn't start: port {PORT} or {ADMIN_PORT} is in use by another program ({e}).\n\n"
              "If AOD is already running, close it from its tray icon (or end AOD.exe / python in Task Manager) and try again.")
        os._exit(1)


def show_ui() -> None:
    aod_window.show(ADMIN_URL)


def ask_running_instance_to_show() -> None:
    import urllib.request
    try:
        req = urllib.request.Request(ADMIN_URL + "_admin/show", method="POST", headers={"X-AOD-Admin": "1"})
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass


def main() -> None:
    import time as _t
    argv = sys.argv[1:]
    if "--launcher" in argv or "--install-service" in argv or "--remove-service" in argv:
        import aod_launcher
        {"--launcher": aod_launcher.run, "--install-service": aod_launcher.install,
         "--remove-service": aod_launcher.remove}[next(a for a in argv if a.startswith("--") and a != "--hidden")]()
        return
    if sys.stdout is None or SERVICE:      # windowed exe / service: keep a log file instead of a console
        sys.stdout = sys.stderr = open(DATA_DIR / "aod.log", "a", buffering=1, encoding="utf-8")
    import aod_tray
    _t.sleep(float(os.environ.get("AOD_START_DELAY", "0")))   # after a self-update restart
    if already_running():
        print("AOD is already running on this PC. Showing its window.")
        ask_running_instance_to_show()
        return
    ip, base, pin = urls()
    print("\n=== AOD host ===")
    print(f"Phone (same Wi-Fi):   {base}")
    print(f"Pairing PIN:          {pin}\n")
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(f"{base}/?pin={pin}")
        qr.print_ascii(invert=True)
    except Exception:
        pass
    threading.Thread(target=server_thread, daemon=True).start()
    aod_tray.start(ADMIN_URL, state, devices, set_enabled, updater, open_ui=show_ui)
    updater.start()
    events.start_download_watcher()
    hidden = "--hidden" in argv
    headless = SERVICE or os.environ.get("AOD_NO_BROWSER") == "1"
    for _ in range(50):                    # wait until the dashboard server answers
        if already_running():
            break
        _t.sleep(0.2)
    if not headless and aod_window.available() and aod_window.run(ADMIN_URL, hidden=hidden):
        return
    if not headless and not hidden:        # no window support: use the browser
        import webbrowser
        webbrowser.open(ADMIN_URL)
    while True:
        _t.sleep(3600)


if __name__ == "__main__":
    main()
