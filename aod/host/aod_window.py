"""The AOD desktop window (WebView2 via pywebview), like Discord: closing it hides to the tray."""
import subprocess
import sys
import webbrowser

_window = None
_ok = False
last_error = ""


def available() -> bool:
    try:
        import webview  # noqa: F401
        return True
    except Exception as e:
        global last_error
        last_error = f"window library missing ({e})"
        print("pywebview missing:", e)
    if getattr(sys, "frozen", False):
        return False
    try:        # script install (start_aod.bat): fetch the window library once, then continue
        subprocess.run([sys.executable, "-m", "pip", "install", "pywebview"], timeout=240,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import webview  # noqa: F401
        return True
    except Exception as e:
        print("Could not install pywebview:", e)
        return False


def run(url: str, hidden: bool = False) -> bool:
    """Blocks on the main thread while the window exists. Returns False if no window could be created."""
    global _window, _ok
    try:
        import webview
        _window = webview.create_window("AOD", url, width=1020, height=800, min_size=(720, 560),
                                        background_color="#171a21", hidden=hidden, text_select=True)

        def closing():
            _window.hide()          # keep running in the tray
            return False
        _window.events.closing += closing
        _ok = True
        webview.start()
        return True
    except Exception as e:
        global last_error
        last_error = f"{e.__class__.__name__}: {e}"
        import traceback
        traceback.print_exc()
        print("Desktop window unavailable, using the browser:", e)
        _ok = False
        return False


def _app_window(url: str) -> bool:
    """No window library? Open Edge/Chrome in "app mode": a chromeless window of its own (no tabs or address bar)."""
    import os
    import shutil
    from aod_paths import DATA_DIR
    cands = [shutil.which("msedge"), shutil.which("chrome")]
    for var in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
        base = os.environ.get(var)
        if base:
            cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    for exe in cands:
        if exe and os.path.exists(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1020,800", "--no-first-run",
                                  "--no-default-browser-check", f"--user-data-dir={DATA_DIR / 'appwindow'}"])
                return True
            except Exception as e:
                print("App window failed:", e)
    return False


def show(url: str = "") -> None:
    if _ok and _window is not None:
        try:
            _window.show()
            _window.restore()
            return
        except Exception:
            pass
    if url and not _app_window(url):
        webbrowser.open(url)
