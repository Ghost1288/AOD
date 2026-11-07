"""Follow the desktop that currently receives input (Windows).

When AOD runs as SYSTEM (service mode) this lets it capture and control the lock screen, the sign-in screen and
UAC prompts, which live on a separate "secure desktop". For a normal user process it does nothing useful.
"""
import sys
import threading
import time

WIN = sys.platform == "win32"
_tl = threading.local()

if WIN:
    import ctypes
    from ctypes import wintypes

    _u = ctypes.windll.user32
    _u.OpenInputDesktop.restype = wintypes.HANDLE
    _u.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _u.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    _u.CloseDesktop.argtypes = [wintypes.HANDLE]
    _u.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD)]

    def _name(h) -> str:
        buf, need = ctypes.create_unicode_buffer(256), wintypes.DWORD()
        _u.GetUserObjectInformationW(h, 2, buf, ctypes.sizeof(buf), ctypes.byref(need))   # UOI_NAME
        return buf.value


def sync(min_interval: float = 0.2) -> bool:
    """Attach the calling thread to the current input desktop. True if the desktop changed."""
    if not WIN:
        return False
    now = time.monotonic()
    if now - getattr(_tl, "t", 0) < min_interval:
        return False
    _tl.t = now
    h = _u.OpenInputDesktop(0, False, 0x10000000)        # GENERIC_ALL; fails unless we are SYSTEM on a secure desktop
    if not h:
        return False
    name = _name(h)
    if name == getattr(_tl, "name", None):
        _u.CloseDesktop(h)
        return False
    if _u.SetThreadDesktop(h):
        old, _tl.h, _tl.name = getattr(_tl, "h", None), h, name
        if old:
            _u.CloseDesktop(old)
        return True
    _u.CloseDesktop(h)
    return False


def list_windows() -> list:
    """Visible top-level windows with a title (Windows only): [{hwnd, title}]."""
    if not WIN:
        return []
    out = []
    own = _u.GetShellWindow()
    cb_t = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(h, _):
        try:
            if h != own and _u.IsWindowVisible(h) and not _u.IsIconic(h):
                n = _u.GetWindowTextLengthW(h)
                if n:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    _u.GetWindowTextW(h, buf, n + 1)
                    r = wintypes.RECT()
                    _u.GetWindowRect(h, ctypes.byref(r))
                    if r.right - r.left > 120 and r.bottom - r.top > 80 and buf.value not in ("Program Manager",):
                        out.append({"hwnd": int(h), "title": buf.value[:120]})
        except Exception:
            pass
        return True
    _u.EnumWindows(cb_t(cb), 0)
    return out


def window_rect(hwnd):
    """(left, top, width, height) of a window in screen pixels, or None if it is gone / minimised."""
    if not WIN or not hwnd:
        return None
    try:
        h = wintypes.HWND(int(hwnd))
        if not _u.IsWindow(h) or _u.IsIconic(h):
            return None
        r = wintypes.RECT()
        ctypes.windll.dwmapi.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r))   # visible frame, no shadow
        if r.right <= r.left:
            _u.GetWindowRect(h, ctypes.byref(r))
        w, hh = (r.right - r.left) // 2 * 2, (r.bottom - r.top) // 2 * 2
        return (r.left, r.top, w, hh) if w >= 64 and hh >= 64 else None
    except Exception:
        return None
