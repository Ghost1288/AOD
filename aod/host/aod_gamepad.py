"""Optional virtual Xbox 360 controller (needs the free ViGEmBus driver + `pip install vgamepad`).

The phone sends the standard-gamepad state of a Bluetooth controller; games on the PC then see a real XInput pad.
If the driver is missing, apply() raises and the phone falls back to keyboard+mouse mapping.
"""

# Standard Gamepad API button index -> XUSB_GAMEPAD_<name>
BTN = {0: "A", 1: "B", 2: "X", 3: "Y", 4: "LEFT_SHOULDER", 5: "RIGHT_SHOULDER", 8: "BACK", 9: "START",
       10: "LEFT_THUMB", 11: "RIGHT_THUMB", 12: "DPAD_UP", 13: "DPAD_DOWN", 14: "DPAD_LEFT", 15: "DPAD_RIGHT",
       16: "GUIDE"}


def importable() -> bool:
    try:
        import vgamepad  # noqa: F401
        return True
    except Exception:
        return False


def _c(v, lo=-1.0, hi=1.0) -> float:
    return max(lo, min(hi, float(v)))


class Pad:
    def __init__(self):
        self.pad = None
        self.vg = None
        self.prev = 0

    def _ensure(self):
        if self.pad is None:
            import vgamepad as vg
            self.vg = vg
            self.pad = vg.VX360Gamepad()     # raises if ViGEmBus is not installed

    def apply(self, axes, mask: int) -> None:
        self._ensure()
        p, vg = self.pad, self.vg
        lx, ly, rx, ry, lt, rt = (float(x) for x in axes)
        p.left_joystick_float(x_value_float=_c(lx), y_value_float=_c(-ly))   # browser Y is down-positive
        p.right_joystick_float(x_value_float=_c(rx), y_value_float=_c(-ry))
        p.left_trigger_float(value_float=_c(lt, 0, 1))
        p.right_trigger_float(value_float=_c(rt, 0, 1))
        mask = int(mask)
        changed = mask ^ self.prev
        for i, name in BTN.items():
            if (changed >> i) & 1:
                b = getattr(vg.XUSB_BUTTON, "XUSB_GAMEPAD_" + name)
                (p.press_button if (mask >> i) & 1 else p.release_button)(button=b)
        self.prev = mask
        p.update()

    def release(self) -> None:
        if self.pad is not None:
            try:
                self.pad.reset()
                self.pad.update()
            except Exception:
                pass
        self.prev = 0


pad = Pad()
