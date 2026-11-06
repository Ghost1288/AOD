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

## Away from home (Tailscale)

Install **Tailscale** (tailscale.com/download) on the PC and the phone and sign in to the same account. AOD detects it
automatically: the dashboard shows a third QR, and the Android app uses the PC's Tailscale address whenever the home
Wi-Fi address can't be reached. Traffic is encrypted by Tailscale as well as by AOD's own HTTPS. Wake-on-LAN only works at home.

## Gaming mode

Tap **🎮 Game** on the Screen tab. It goes landscape, switches to 60 fps with a high-bitrate low-latency stream, and shows:
- **Layouts:** Shooter (WASD stick + mouse-look + Fire/Aim/Jump...), Racing, Platformer/retro. Change in the gear menu.
- **Bluetooth controller:** pair a controller with the phone (Android Bluetooth settings) and press a button. If the PC has the
  ViGEmBus driver and `vgamepad`, games see a real Xbox controller; otherwise the stick/buttons are mapped to keyboard + mouse.
- Input uses hardware scancodes and raw relative mouse movement, which most games need. Games running as administrator
  need AOD run as administrator too.
- Faster capture (DXGI) is used when `dxcam` is installed (the optional installs in `start_aod.bat`). Borderless-window
  games capture best.

## Auto-updates

Every push to GitHub (`.github/workflows/release.yml`) builds the Android app and the Windows installer and publishes them as a
GitHub Release (with `version.json`). The repo must be **public** so the apps can read releases without logging in.

- **Windows host:** checks at startup and every 6 hours, and only installs when no phone is connected. Script copy
  (`start_aod.bat`) overwrites its own files and restarts; installed copy runs the new installer silently.
  Tray menu: "Update automatically" and "Check for updates now". The dashboard shows version and status.
- **Android app:** checks each time you open it, downloads the new APK and hands it to Android's installer (you tap Install).
  The first time it asks for "install unknown apps" permission. The web screens update automatically with the host.
- The Android key is fixed (`android/app/aod.jks`) so updates install over the old version. Uninstall any older
  AOD APK once (it was signed with a different key).

## Known limits

- Can't control the lock screen or UAC prompts (needs a Windows service; planned).
- Same Wi-Fi only for now.
- Audio capture uses WASAPI loopback via `soundcard`; if it fails, video still works.
- Android 10+ required for the app.

## Files

- `host/` Windows host (Python): `aod_host.py`, `aod_security.py`, `aod_rtc.py`, `aod_features.py`, `aod_tray.py`, `static/`
- `android/` the Android app (Kotlin WebView wrapper)
- `installer/aod.iss` Inno Setup script
