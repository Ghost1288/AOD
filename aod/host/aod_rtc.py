"""AOD screen capture + WebRTC (H.264 video, optional system audio)."""
import asyncio
import io
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

import mss
import numpy as np

import aod_desktop
from PIL import Image

try:
    import dxcam  # optional: GPU desktop duplication, far faster than mss for games
    DX_OK = True
except Exception:
    DX_OK = False

try:
    from aiortc import (MediaStreamTrack, RTCPeerConnection, RTCSessionDescription,
                        RTCRtpSender)
    from av import AudioFrame, VideoFrame
    RTC_OK = True
except Exception as e:  # host still works with the JPEG fallback
    print("WebRTC unavailable, using JPEG streaming:", e)
    RTC_OK = False
    MediaStreamTrack = object


class Capturer:
    """All mss calls run on one dedicated thread (mss handles are thread-bound)."""

    def __init__(self):
        self.ex = ThreadPoolExecutor(max_workers=1)
        self.sct = None
        self.cams, self.last, self.dx_failed = {}, {}, False

    def _sct(self):
        if self.sct is None:
            self.sct = mss.mss()
        return self.sct

    def _reset(self):
        """The input desktop changed (lock screen / UAC): rebuild capture handles for the new desktop."""
        try:
            if self.sct:
                self.sct.close()
        except Exception:
            pass
        self.sct = None
        self.cams.clear()
        self.last.clear()
        self.dx_failed = False

    def _grab(self, idx):
        if aod_desktop.sync():
            self._reset()
        s = self._sct()
        return s.grab(s.monitors[max(1, min(idx, len(s.monitors) - 1))])

    def _np(self, idx):
        """Latest frame as a BGRA numpy array (dxcam when available, else mss)."""
        if aod_desktop.sync():
            self._reset()
        if DX_OK and not self.dx_failed:
            try:
                cam = self.cams.get(idx)
                if cam is None:
                    cam = self.cams[idx] = dxcam.create(output_idx=max(0, idx - 1), output_color="BGRA")
                f = cam.grab()
                if f is None:
                    f = self.last.get(idx)       # screen unchanged since last frame
                if f is not None:
                    self.last[idx] = f
                    return np.ascontiguousarray(f)
            except Exception as e:
                print("dxcam failed, using mss:", e)
                self.dx_failed = True
        shot = self._grab(idx)
        return np.frombuffer(shot.bgra, np.uint8).reshape(shot.height, shot.width, 4)

    async def grab_np(self, idx):
        return await asyncio.get_running_loop().run_in_executor(self.ex, self._np, idx)

    def _monitors(self):
        if aod_desktop.sync():
            self._reset()
        return [dict(m) for m in self._sct().monitors[1:]]

    async def grab(self, idx):
        return await asyncio.get_running_loop().run_in_executor(self.ex, self._grab, idx)

    async def monitors(self):
        return await asyncio.get_running_loop().run_in_executor(self.ex, self._monitors)

    async def jpeg(self, idx, scale, quality) -> bytes:
        shot = await self.grab(idx)

        def enc():
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            if scale < 1:
                img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                                 Image.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality)
            return buf.getvalue()
        return await asyncio.get_running_loop().run_in_executor(None, enc)


class ScreenTrack(MediaStreamTrack):
    kind = "video"
    MAX_W = 1920

    def __init__(self, capturer: Capturer, state: dict):
        super().__init__()
        self.cap, self.state = capturer, state
        self.t0 = None
        self.last = 0.0

    async def recv(self):
        gap = 1.0 / max(3, self.state["fps"])
        wait = self.last + gap - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self.last = time.monotonic()
        arr = await self.cap.grab_np(self.state["mon"])
        h, w = arr.shape[:2]
        frame = VideoFrame.from_ndarray(arr, format="bgra")
        scale = min(self.state.get("rtc_scale", 1.0), self.MAX_W / w)
        ow, oh = max(2, int(w * scale) // 2 * 2), max(2, int(h * scale) // 2 * 2)
        frame = frame.reformat(width=ow, height=oh, format="yuv420p")
        if self.t0 is None:
            self.t0 = time.monotonic()
        frame.pts = int((time.monotonic() - self.t0) * 90000)
        frame.time_base = Fraction(1, 90000)
        return frame


class AudioTrack(MediaStreamTrack):
    """Captures what the PC is playing (WASAPI loopback via `soundcard`)."""
    kind = "audio"
    RATE, N = 48000, 960  # 20 ms

    def __init__(self):
        super().__init__()
        self.q = queue.Queue(maxsize=25)
        self.run = True
        self.n = 0
        self.t0 = None
        threading.Thread(target=self._capture, daemon=True).start()

    def _capture(self):
        try:
            import soundcard as sc
            spk = sc.default_speaker()
            mic = sc.get_microphone(spk.name, include_loopback=True)
            with mic.recorder(samplerate=self.RATE, channels=2, blocksize=self.N) as rec:
                while self.run:
                    data = rec.record(numframes=self.N)
                    pcm = (np.clip(data, -1, 1) * 32767).astype(np.int16)
                    try:
                        self.q.put_nowait(pcm)
                    except queue.Full:
                        pass
        except Exception as e:
            print("Audio capture unavailable:", e)

    async def recv(self):
        if self.t0 is None:
            self.t0 = time.monotonic()
        due = self.t0 + self.n * self.N / self.RATE
        await asyncio.sleep(max(0, due - time.monotonic()))
        try:
            pcm = self.q.get_nowait()
        except queue.Empty:
            pcm = np.zeros((self.N, 2), np.int16)
        frame = AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="stereo")
        frame.sample_rate = self.RATE
        frame.pts = self.n * self.N
        frame.time_base = Fraction(1, self.RATE)
        self.n += 1
        return frame

    def stop(self):
        self.run = False
        super().stop()


async def answer_offer(sdp: str, capturer: Capturer, state: dict, want_audio: bool, on_closed):
    """Returns (RTCPeerConnection, answer_sdp)."""
    pc = RTCPeerConnection()

    @pc.on("connectionstatechange")
    async def _():
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await on_closed()

    await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
    pc.addTrack(ScreenTrack(capturer, state))
    if want_audio:
        pc.addTrack(AudioTrack())
    caps = RTCRtpSender.getCapabilities("video").codecs
    h264 = [c for c in caps if c.mimeType.lower() == "video/h264"]
    rest = [c for c in caps if c.mimeType.lower() != "video/h264"]
    for t in pc.getTransceivers():
        if t.kind == "video" and h264:
            t.setCodecPreferences(h264 + rest)
    await pc.setLocalDescription(await pc.createAnswer())
    return pc, pc.localDescription.sdp


def set_bitrate(game: bool) -> None:
    """H.264 target bitrates (bits/s). Game mode trades bandwidth for sharpness; LAN/Tailscale can take it."""
    try:
        from aiortc.codecs import h264
        h264.MIN_BITRATE, h264.DEFAULT_BITRATE, h264.MAX_BITRATE = (
            (3_000_000, 10_000_000, 25_000_000) if game else (1_000_000, 3_000_000, 8_000_000))
    except Exception as e:
        print("Could not set bitrate:", e)
