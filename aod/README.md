# AOD 2.0

Control your Windows PC from your Android phone: live screen, audio, mouse, keyboard, files, task manager, power.
Works on your home Wi-Fi. (Access from anywhere is the next phase.)

## Quick start

**PC:** double-click `host/start_aod.bat`. It installs Python and every dependency, then starts AOD with a tray icon.
The dashboard (pairing QR codes and PIN) opens automatically in your browser; you can reopen it from the tray icon, or at http://127.0.0.1:8766/.

**Phone, option A (browser):** scan the "Browser" QR with the camera. Chrome warns about the certificate (it is your PC's own
self-signed one): Advanced, Proceed. Approve the phone on the PC when asked.

**Phone, option B (app, recommended):** install the AOD app (see "Building the installers"), open it, scan the
"AOD Android app" QR. The app pins your PC's certificate, so there is no warning and no one else can impersonate your PC.

## What's in 2.0

- WebRTC H.264 video (low latency) with automatic fallback to JPEG streaming
- PC audio streamed to the phone (tap the speaker button)
- On-screen cursor, pinch-to-zoom, touchpad or direct-touch mode, keyboard and shortcut bar
- Clipboard sync both ways
- File browser: download from the PC, upload from the phone
- Task manager: CPU/RAM/disk/battery, end processes
- Power: lock, sleep, sign out, restart, shut down; media and volume keys
- Wake-on-LAN (app only; needs "Wake on Magic Packet" enabled in the PC's network adapter / BIOS)
- Security: HTTPS, one-time rotating PIN, approve each new phone on the PC, lockout after 5 wrong PINs,
  list/revoke devices, tray "Pause" kill switch, tokens stored hashed
- Tray app, start with Windows, installer

## Building the installers (no local tools needed)

Push this folder to a GitHub repo. The workflows in `.github/workflows` build:
- `AOD-windows-installer` (AOD-Setup.exe, adds the firewall rule and optional auto-start)
- `AOD-android` (app-debug.apk; allow "install unknown apps" on the phone)

Run them from the repo's Actions tab, then download the artifacts.

## Known limits

- Can't control the lock screen or UAC prompts (needs a Windows service; planned).
- Same Wi-Fi only for now.
- Audio capture uses WASAPI loopback via `soundcard`; if it fails, video still works.
- Android 10+ required for the app.

## Files

- `host/` Windows host (Python): `aod_host.py`, `aod_security.py`, `aod_rtc.py`, `aod_features.py`, `aod_tray.py`, `static/`
- `android/` the Android app (Kotlin WebView wrapper)
- `installer/aod.iss` Inno Setup script
