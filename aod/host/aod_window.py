"""The AOD desktop window (WebView2 via pywebview), like Discord: closing it hides to the tray."""
import webbrowser

_window = None
_ok = False


def available() -> bool:
    try:
        import webview  # noqa: F401
        return True
    except Exception:
        return False


def run(url: str, hidden: bool = False) -> bool:
    """Blocks on the main thread while the window exists. Returns False if no window could be created."""
    global _window, _ok
    try:
        import webview
        _window = webview.create_window("AOD", url, width=1020, height=800, min_size=(720, 560),
                                        background_color="#0b0d12", hidden=hidden, text_select=True)

        def closing():
            _window.hide()          # keep running in the tray
            return False
        _window.events.closing += closing
        _ok = True
        webview.start()
        return True
    except Exception as e:
        print("Desktop window unavailable, using the browser:", e)
        _ok = False
        return False


def show(url: str = "") -> None:
    if _ok and _window is not None:
        try:
            _window.show()
            _window.restore()
            return
        except Exception:
            pass
    if url:
        webbrowser.open(url)
