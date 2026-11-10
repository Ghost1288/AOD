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

AOD tries to open itself up to Tailscale in Windows Firewall automatically on every startup. If the phone still times
out specifically over Tailscale (LAN works fine, but it connects): Windows usually treats Tailscale's network adapter
as "Public" and only lets AOD through on your home ("Private") network, so AOD couldn't fix the rule itself — the
dashboard's Away from home card shows the exact command to run once as Administrator to fix it.

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

## New in this version
- **Desktop app**: AOD opens in its own window (like Discord). Closing it hides it to the tray; "Start with Windows" launches it hidden.
- **Service mode** (dashboard > Security & service, or install_service.bat): AOD starts at boot, before login, and can see/control the lock screen and UAC prompts.
- **Apps tab**: your own shortcut buttons (keys, text, launch app, run command, power), an app launcher with search, and a run-command box.
- **Fingerprint lock** (Power tab > Smart features): the phone app asks for fingerprint/PIN on open. **Auto-lock PC** locks Windows when your phone disconnects.
- **PC notifications**: "download finished" and "process closed" alerts on your phone (turn on in Smart features). Tap the bell on a process to be told when it closes.
- **Share to PC**: in any app choose Share > AOD to open a link on the PC, copy text to its clipboard, or send files (saved to Downloads\AOD).
- **Adaptive quality**: AOD lowers resolution and frame rate when the connection is weak and raises them again when it recovers (Screen > settings > Auto quality).
- **Screenshots and recording**: 📷 saves a full-resolution screenshot to your phone and to `Pictures\AOD` on the PC; ⏺ records the stream to `Videos\AOD` on the PC.
- **Tablet and landscape layouts**: side navigation rail on large screens, compact bars in landscape.
- **Wake-on-LAN**: dashboard > "Set up Wake-on-LAN" prepares Windows; the phone app's "Wake PC" button on the offline screen then switches the PC on from home Wi-Fi.
- **Files**: thumbnails, search, rename, new folder, delete (to the Recycle Bin).
- **Single window streaming** (🪟 on the Screen tab), **clipboard history**, **activity log**, **panic button** (phone Power tab, dashboard, tray), alerts on your phone when someone tries to pair.
- **Wake from anywhere**: run `relay/aod_relay.py --key SECRET` on an always-on device at home (Raspberry Pi, NAS, old PC; with Tailscale on it), then enter its address and key in the phone app (Power tab > Wake from anywhere).
- **AI assistant** (phone Assistant tab; add an Anthropic API key in the dashboard): plain-language control of the PC, web search and page reading, **page watches** (it can watch a page and alert your phone, optionally only when something you care about happens), **screen mode** (ask about what is on screen without it touching anything), **voice input** and **spoken replies**. Risky actions ask for approval on the phone.
- **Game library** (Apps tab > 🎮 Games): a grid of your installed Steam games with cover art. Tap to launch; the gear icon lets you save a resolution/quality/frame-rate preset per game that's applied automatically next time you launch it.
- **Scenes**: one-tap buttons (defaults: Gaming, Work, Movie) that launch an app, set the PC's system volume, and switch the stream to a saved quality preset, all in one tap. Edit or add your own from the shortcut editor (choose type "Scene").
- **Follow my mouse** (🖱 button next to the window picker on the Screen tab): when turned on, the phone's view automatically switches to whatever window the PC's physical mouse cursor is currently over. Toggle it off any time, or pick a window manually to turn it off automatically.
- **Streamer alerts** (Apps tab > 📺 Streams): pick Twitch and/or Kick streamers to track and get a notification on your phone the moment one goes live, with a tap-through link. Kick needs no setup; Twitch needs a free Client ID + secret from dev.twitch.tv entered once on the dashboard (it's an app-only token — your Twitch login is never used or stored).
