"""System-tray icon for the AOD host."""
import os
import sys
import webbrowser
from pathlib import Path

_icon = None
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return f'"{pyw if pyw.exists() else exe}" "{Path(__file__).with_name("aod_host.py")}"'


def autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "AOD")
            return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, "AOD", 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(k, "AOD")
            except OSError:
                pass


def _icon_image(paused: bool):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    color = (139, 147, 167, 255) if paused else (74, 222, 128, 255)
    d.ellipse((6, 6, 58, 58), outline=color, width=8)
    d.ellipse((24, 24, 40, 40), fill=color)
    return img


def stop() -> None:
    """Remove the tray icon (so no ghost icon is left behind when AOD quits)."""
    try:
        if _icon is not None:
            _icon.stop()
    except Exception:
        pass


def start(admin_url, state, devices, set_enabled, updater):
    global _icon
    try:
        import pystray
    except Exception as e:
        print("Tray icon unavailable:", e)
        return

    def dashboard(icon=None, item=None):
        webbrowser.open(admin_url)

    def toggle_pause(icon, item):
        set_enabled(not state.enabled)
        icon.icon = _icon_image(not state.enabled)

    def toggle_pairing(icon, item):
        state.pairing_allowed = not state.pairing_allowed

    def toggle_autostart(icon, item):
        set_autostart(not autostart_enabled())

    def revoke_all(icon, item):
        devices.revoke_all()
        set_enabled(False)
        set_enabled(True)

    def toggle_auto_update(icon, item):
        updater.set_auto(not updater.auto)

    def check_updates(icon, item):
        updater.check_and_apply_now()

    def toggle_notify(icon, item):
        updater.set_notify(not updater.notify_on)

    def quit_(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem("Open AOD dashboard (QR + PIN)", dashboard, default=True),
        pystray.MenuItem("Pause AOD (disconnect everyone)", toggle_pause, checked=lambda i: not state.enabled),
        pystray.MenuItem("Allow new devices to pair", toggle_pairing, checked=lambda i: state.pairing_allowed),
        pystray.MenuItem("Start with Windows", toggle_autostart, checked=lambda i: autostart_enabled(),
                         visible=sys.platform == "win32"),
        pystray.MenuItem("Update automatically", toggle_auto_update, checked=lambda i: updater.auto),
        pystray.MenuItem("Check for updates now", check_updates),
        pystray.MenuItem("Notify when checking for updates", toggle_notify, checked=lambda i: updater.notify_on),
        pystray.MenuItem("Unpair all devices", revoke_all),
        pystray.MenuItem("Quit", quit_),
    )
    _icon = pystray.Icon("AOD", _icon_image(False), "AOD", menu)
    updater.notify = lambda title, msg: _icon.notify(msg, title)    # Windows toast / balloon
    _icon.run_detached()
