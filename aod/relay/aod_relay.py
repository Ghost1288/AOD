#!/usr/bin/env python3
"""AOD wake relay: run this on something that is always on at home (Raspberry Pi, NAS, old PC, router with Python).

It lets the AOD phone app wake your PC from anywhere: the phone (over Tailscale or any route) asks the relay,
and the relay sends the Wake-on-LAN packet on your home network.

    python3 aod_relay.py --key SOMETHING-SECRET            # listens on port 8767
    python3 aod_relay.py --key SOMETHING-SECRET --port 8767

In the AOD phone app: Power tab > Wake from anywhere > address http://<relay-tailscale-ip>:8767 and the same key.
Only standard library, no installs needed.
"""
import argparse
import hmac
import socket
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    if len(raw) != 6:
        raise ValueError("bad MAC")
    return b"\xff" * 6 + raw * 16


def send_wol(mac: str) -> None:
    pkt = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):
            s.sendto(pkt, ("255.255.255.255", port))


def make_handler(key: str):
    recent = []                      # rate limit: 10 wake requests per minute

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path != "/wake":
                return self._reply(404, "not found")
            if not hmac.compare_digest(q.get("key", [""])[0], key):
                return self._reply(403, "wrong key")
            now = time.time()
            recent[:] = [t for t in recent if now - t < 60]
            if len(recent) >= 10:
                return self._reply(429, "slow down")
            recent.append(now)
            try:
                send_wol(q.get("mac", [""])[0])
            except Exception as e:
                return self._reply(400, f"bad request: {e}")
            self._reply(200, "wake packet sent")

        def _reply(self, code, text):
            self.send_response(code)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(text.encode())

        def log_message(self, *a):
            pass
    return H


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="shared secret, also typed into the phone app")
    ap.add_argument("--port", type=int, default=8767)
    a = ap.parse_args()
    print(f"AOD wake relay listening on port {a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), make_handler(a.key)).serve_forever()
