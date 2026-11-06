"""AOD security: self-signed TLS cert, paired-device registry, PIN, approval prompt."""
import datetime
import hashlib
import ipaddress
import json
import secrets
import socket
import sys
import threading
import time
from pathlib import Path

DATA_DIR = Path.home() / ".aod"
DATA_DIR.mkdir(exist_ok=True)
CERT_FILE = DATA_DIR / "cert.pem"
KEY_FILE = DATA_DIR / "key.pem"
DEVICES_FILE = DATA_DIR / "devices.json"

PIN_LIFETIME = 600          # seconds a PIN stays valid
MAX_TRIES = 5               # wrong PINs per IP before lockout
LOCKOUT = 300               # seconds


_VIRTUAL = ("tailscale", "vpn", "proton", "wireguard", "wg", "tun", "tap", "wintun", "mullvad", "nord", "virtual",
            "vethernet", "vmware", "vbox", "docker", "wsl", "hyper-v", "loopback", "bluetooth", "zerotier")


def lan_ip() -> str:
    """The PC's real home-network address. Skips VPN / virtual adapters (a VPN can hijack the default route)."""
    try:
        import psutil
        stats = psutil.net_if_stats()
        cands = []
        for name, addrs in psutil.net_if_addrs().items():
            if any(v in name.lower() for v in _VIRTUAL) or (name in stats and not stats[name].isup):
                continue
            for a in addrs:
                if a.family != socket.AF_INET:
                    continue
                ip = ipaddress.ip_address(a.address)
                if ip.is_private and not ip.is_link_local and not ip.is_loopback \
                        and ip not in ipaddress.ip_network("100.64.0.0/10"):
                    cands.append(a.address)
        if cands:
            return sorted(cands, key=lambda x: (not x.startswith("192.168."), x))[0]
    except Exception:
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def tailscale_ip():
    """This PC's Tailscale address (100.64.0.0/10), or None if Tailscale isn't running."""
    try:
        import psutil
        net = ipaddress.ip_network("100.64.0.0/10")
        for addrs in psutil.net_if_addrs().values():
            for a in addrs:
                if a.family == socket.AF_INET and ipaddress.ip_address(a.address) in net:
                    return a.address
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- TLS cert
def ensure_cert():
    """Create a long-lived self-signed cert once. Returns (cert, key, sha256 fingerprint).
    The phone app pins the fingerprint, so the cert is never regenerated automatically."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    if not (CERT_FILE.exists() and KEY_FILE.exists()):
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AOD host")])
        san = [x509.DNSName("localhost"), x509.DNSName(socket.gethostname()),
               x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(lan_ip())))
        except ValueError:
            pass
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                .public_key(key.public_key()).serial_number(x509.random_serial_number())
                .not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=3650))
                .add_extension(x509.SubjectAlternativeName(san), critical=False)
                .sign(key, hashes.SHA256()))
        KEY_FILE.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
        CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        try:
            KEY_FILE.chmod(0o600)
        except Exception:
            pass
    cert = x509.load_pem_x509_certificate(CERT_FILE.read_bytes())
    fp = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    return CERT_FILE, KEY_FILE, fp


# ---------------------------------------------------------------- devices
class Devices:
    """Paired phones. Only a hash of each token is stored on disk."""

    def __init__(self):
        self.lock = threading.Lock()
        try:
            self.items = json.loads(DEVICES_FILE.read_text())
        except Exception:
            self.items = {}

    def _save(self):
        DEVICES_FILE.write_text(json.dumps(self.items, indent=1))
        try:
            DEVICES_FILE.chmod(0o600)
        except Exception:
            pass

    @staticmethod
    def _h(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def add(self, name: str, ip: str) -> str:
        token = secrets.token_urlsafe(32)
        did = secrets.token_hex(4)
        with self.lock:
            self.items[did] = {"name": name[:60] or "Phone", "hash": self._h(token),
                               "created": time.time(), "last_seen": time.time(), "ip": ip}
            self._save()
        return token

    def check(self, token) -> str | None:
        if not token:
            return None
        h = self._h(token)
        for did, d in self.items.items():
            if secrets.compare_digest(d["hash"], h):
                return did
        return None

    def touch(self, did: str, ip: str):
        d = self.items.get(did)
        if d and time.time() - d.get("last_seen", 0) > 30:
            d["last_seen"], d["ip"] = time.time(), ip
            with self.lock:
                self._save()

    def revoke(self, did: str) -> bool:
        with self.lock:
            ok = self.items.pop(did, None) is not None
            self._save()
        return ok

    def revoke_all(self):
        with self.lock:
            self.items.clear()
            self._save()

    def public_list(self):
        return [{"id": k, "name": v["name"], "created": v["created"],
                 "last_seen": v["last_seen"], "ip": v.get("ip", "")} for k, v in self.items.items()]


# ---------------------------------------------------------------- state
class State:
    def __init__(self):
        self.enabled = True            # kill switch (tray: Pause)
        self.pairing_allowed = True    # tray: allow new devices
        self.pin = self._new_pin()
        self.pin_time = time.time()
        self.failed = {}               # ip -> (count, locked_until)
        self.prompt_lock = threading.Lock()

    @staticmethod
    def _new_pin() -> str:
        return f"{secrets.randbelow(10**6):06d}"

    def current_pin(self) -> str:
        if time.time() - self.pin_time > PIN_LIFETIME:
            self.rotate_pin()
        return self.pin

    def rotate_pin(self):
        self.pin, self.pin_time = self._new_pin(), time.time()

    def locked(self, ip: str) -> bool:
        c, until = self.failed.get(ip, (0, 0))
        return c >= MAX_TRIES and time.time() < until

    def fail(self, ip: str):
        c, until = self.failed.get(ip, (0, 0))
        if time.time() > until and c >= MAX_TRIES:
            c = 0
        c += 1
        self.failed[ip] = (c, time.time() + LOCKOUT)

    def pin_ok(self, ip: str, pin: str) -> bool:
        ok = secrets.compare_digest(str(pin), self.current_pin())
        if not ok:
            self.fail(ip)
        return ok


def ask_approval(state: State, name: str, ip: str) -> bool:
    """Blocking yes/no prompt on the PC. Called from a worker thread."""
    with state.prompt_lock:
        text = f"Allow \"{name}\" ({ip}) to see and control this PC?"
        if sys.platform == "win32":
            import ctypes
            MB_YESNO, MB_ICONQUESTION, MB_TOPMOST, MB_SETFOREGROUND = 0x4, 0x20, 0x40000, 0x10000
            r = ctypes.windll.user32.MessageBoxW(
                0, text, "AOD - new device", MB_YESNO | MB_ICONQUESTION | MB_TOPMOST | MB_SETFOREGROUND)
            return r == 6  # IDYES
        print(f"[AOD] {text} (auto-approved on this platform)")
        return True
