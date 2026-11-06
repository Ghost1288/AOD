"""Game-grade input for AOD (Windows SendInput with hardware scancodes and raw relative mouse).

Many games ignore the "virtual key" events normal automation uses; they only accept scancodes and
relative mouse motion. Everything here is a no-op on other platforms.
Note: a game running as administrator ignores input from a non-admin AOD. Run AOD as admin for those.
"""
import sys

WIN = sys.platform == "win32"

# ---- scancode table (set 1): name -> (scancode, extended)
SC = {"esc": (0x01, 0), "tab": (0x0F, 0), "enter": (0x1C, 0), "space": (0x39, 0), "backspace": (0x0E, 0),
      "shift": (0x2A, 0), "ctrl": (0x1D, 0), "alt": (0x38, 0), "capslock": (0x3A, 0),
      "up": (0x48, 1), "down": (0x50, 1), "left": (0x4B, 1), "right": (0x4D, 1),
      "delete": (0x53, 1), "home": (0x47, 1), "end": (0x4F, 1), "pageup": (0x49, 1), "pagedown": (0x51, 1),
      "insert": (0x52, 1), ",": (0x33, 0), ".": (0x34, 0), "/": (0x35, 0), ";": (0x27, 0), "'": (0x28, 0),
      "[": (0x1A, 0), "]": (0x1B, 0), "-": (0x0C, 0), "=": (0x0D, 0), "`": (0x29, 0)}
for i, ch in enumerate("1234567890"):
    SC[ch] = (0x02 + i, 0)
for row, start in (("qwertyuiop", 0x10), ("asdfghjkl", 0x1E), ("zxcvbnm", 0x2C)):
    for i, ch in enumerate(row):
        SC[ch] = (start + i, 0)
for i in range(1, 11):
    SC[f"f{i}"] = (0x3A + i, 0)
SC["f11"], SC["f12"] = (0x57, 0), (0x58, 0)

if WIN:
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = ctypes.c_size_t

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    _SendInput = ctypes.windll.user32.SendInput

    def _send(inp):
        _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _key(scan, ext, down):
        flags = 0x0008 | (0x0001 if ext else 0) | (0 if down else 0x0002)   # SCANCODE | EXTENDED | KEYUP
        _send(INPUT(type=1, ki=KEYBDINPUT(0, scan, flags, 0, 0)))

    MOUSE_FLAGS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010), "middle": (0x0020, 0x0040)}

    def _mouse(dx=0, dy=0, flags=0, data=0):
        _send(INPUT(type=0, mi=MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)))
else:
    def _key(scan, ext, down): pass
    def _mouse(dx=0, dy=0, flags=0, data=0): pass
    MOUSE_FLAGS = {"left": (2, 4), "right": (8, 16), "middle": (32, 64)}


class GameInput:
    """One per phone session. Remembers what is held so everything can be released on disconnect."""

    def __init__(self):
        self.keys, self.buttons = set(), set()

    def key(self, name: str, down: bool) -> None:
        sc = SC.get(name)
        if not sc:
            return
        (self.keys.add if down else self.keys.discard)(name)
        _key(sc[0], sc[1], down)

    def button(self, b: str, down: bool) -> None:
        if b not in MOUSE_FLAGS:
            return
        (self.buttons.add if down else self.buttons.discard)(b)
        _mouse(flags=MOUSE_FLAGS[b][0 if down else 1])

    def move(self, dx: int, dy: int) -> None:
        if dx or dy:
            _mouse(int(dx), int(dy), 0x0001)          # MOUSEEVENTF_MOVE (relative, raw)

    def wheel(self, notches: int) -> None:
        _mouse(flags=0x0800, data=int(notches) * 120)

    def release_all(self) -> None:
        for k in list(self.keys):
            self.key(k, False)
        for b in list(self.buttons):
            self.button(b, False)
