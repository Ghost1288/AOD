"""AOD service launcher (Windows only).

Install once (as administrator) and AOD starts at boot, before anyone signs in, and keeps running inside the
active console session as SYSTEM. That is what lets it control the sign-in screen, the lock screen and UAC prompts.
It is a Scheduled Task ("AOD", run as SYSTEM at startup) that runs this launcher; the launcher starts AOD in
the console session, restarts it if it stops, and follows the session when users sign in or out.

    python aod_launcher.py install | remove | run
"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

WIN = sys.platform == "win32"
TASK = "AOD"
PROGRAM_DATA = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "AOD"
FROZEN = getattr(sys, "frozen", False)
HERE = Path(sys.executable).parent if FROZEN else Path(__file__).parent
EXIT_RESTART, EXIT_UPDATING = 75, 76

if WIN:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    uenv = ctypes.WinDLL("userenv", use_last_error=True)
    wts = ctypes.WinDLL("wtsapi32", use_last_error=True)
    HANDLE = wintypes.HANDLE

    class STARTUPINFO(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
                    ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                    ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD), ("dwXCountChars", wintypes.DWORD),
                    ("dwYCountChars", wintypes.DWORD), ("dwFillAttribute", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                    ("lpReserved2", ctypes.POINTER(ctypes.c_byte)), ("hStdInput", HANDLE),
                    ("hStdOutput", HANDLE), ("hStdError", HANDLE)]

    class PROCESS_INFORMATION(ctypes.Structure):
        _fields_ = [("hProcess", HANDLE), ("hThread", HANDLE), ("dwProcessId", wintypes.DWORD),
                    ("dwThreadId", wintypes.DWORD)]

    k32.WTSGetActiveConsoleSessionId.restype = wintypes.DWORD
    k32.GetCurrentProcess.restype = HANDLE
    k32.WaitForSingleObject.argtypes = [HANDLE, wintypes.DWORD]
    k32.TerminateProcess.argtypes = [HANDLE, wintypes.UINT]
    k32.GetExitCodeProcess.argtypes = [HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [HANDLE]
    adv.OpenProcessToken.argtypes = [HANDLE, wintypes.DWORD, ctypes.POINTER(HANDLE)]
    adv.DuplicateTokenEx.argtypes = [HANDLE, wintypes.DWORD, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                     ctypes.POINTER(HANDLE)]
    adv.SetTokenInformation.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    adv.CreateProcessAsUserW.argtypes = [HANDLE, wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
                                         ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p,
                                         wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFO),
                                         ctypes.POINTER(PROCESS_INFORMATION)]
    wts.WTSQueryUserToken.argtypes = [wintypes.ULONG, ctypes.POINTER(HANDLE)]
    uenv.CreateEnvironmentBlock.argtypes = [ctypes.POINTER(ctypes.c_void_p), HANDLE, wintypes.BOOL]
    uenv.DestroyEnvironmentBlock.argtypes = [ctypes.c_void_p]
    uenv.GetUserProfileDirectoryW.argtypes = [HANDLE, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]

NO_SESSION = 0xFFFFFFFF
CREATE_UNICODE_ENV, CREATE_NO_WINDOW = 0x400, 0x08000000


def console_session() -> int:
    return k32.WTSGetActiveConsoleSessionId()


def _system_token(session: int):
    """A copy of our own (SYSTEM) token, moved into the given session."""
    tok = HANDLE()
    adv.OpenProcessToken(k32.GetCurrentProcess(), 0xF01FF, ctypes.byref(tok))
    dup = HANDLE()
    adv.DuplicateTokenEx(tok, 0x02000000, None, 2, 1, ctypes.byref(dup))   # impersonation level 2, primary token
    k32.CloseHandle(tok)
    sid = wintypes.DWORD(session)
    adv.SetTokenInformation(dup, 12, ctypes.byref(sid), ctypes.sizeof(sid))   # TokenSessionId
    return dup


def _user_token(session: int):
    tok = HANDLE()
    return tok if wts.WTSQueryUserToken(session, ctypes.byref(tok)) else None


def user_profile(token) -> str:
    size = wintypes.DWORD(260)
    buf = ctypes.create_unicode_buffer(260)
    return buf.value if uenv.GetUserProfileDirectoryW(token, buf, ctypes.byref(size)) else ""


def _spawn(token, cmdline: str, cwd=None, inherit_env: bool = False):
    env = ctypes.c_void_p()
    uenv.CreateEnvironmentBlock(ctypes.byref(env), token, inherit_env)
    si = STARTUPINFO()
    si.cb = ctypes.sizeof(si)
    si.lpDesktop = "winsta0\\default"
    pi = PROCESS_INFORMATION()
    ok = adv.CreateProcessAsUserW(token, None, ctypes.create_unicode_buffer(cmdline), None, None, False,
                                  CREATE_UNICODE_ENV | CREATE_NO_WINDOW, env, cwd, ctypes.byref(si), ctypes.byref(pi))
    if env:
        uenv.DestroyEnvironmentBlock(env)
    if not ok:
        print("CreateProcessAsUser failed:", ctypes.get_last_error())
        return None
    k32.CloseHandle(pi.hThread)
    return pi.hProcess


def run_as_user(cmdline: str) -> bool:
    """Start a program as the signed-in user (used when AOD itself runs as SYSTEM)."""
    if not WIN:
        return False
    tok = _user_token(console_session())
    if not tok:
        return False
    h = _spawn(tok, cmdline)
    if h:
        k32.CloseHandle(h)
    k32.CloseHandle(tok)
    return bool(h)


# ------------------------------------------------------------------ the loop
def _host_cmd() -> str:
    return f'"{sys.executable}"' if FROZEN else f'"{sys.executable}" "{HERE / "aod_host.py"}"'


def run() -> None:
    os.environ.update(AOD_SERVICE="1", AOD_DATA_DIR=str(PROGRAM_DATA), AOD_NO_BROWSER="1", AOD_LOOP="1")
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
    child, child_session, last_start = None, None, 0.0
    while True:
        session = console_session()
        if child and (session != child_session or k32.WaitForSingleObject(child, 0) == 0):
            code = wintypes.DWORD(0)
            if k32.WaitForSingleObject(child, 0) != 0:                  # session changed: stop it
                k32.TerminateProcess(child, 1)
                code.value = EXIT_RESTART
            else:
                k32.GetExitCodeProcess(child, ctypes.byref(code))
            k32.CloseHandle(child)
            child = None
            if code.value == 0:                                         # deliberate Quit
                return
            if code.value == EXIT_UPDATING:
                time.sleep(45)                                          # installer is replacing files
            elif code.value != EXIT_RESTART and time.time() - last_start < 10:
                time.sleep(10)                                          # crash loop: slow down
        if not child and session != NO_SESSION:
            utok = _user_token(session)
            home = user_profile(utok) if utok else ""
            if utok:
                k32.CloseHandle(utok)
            os.environ["AOD_USER_HOME"] = home
            if not home:
                os.environ.pop("AOD_USER_HOME", None)
            tok = _system_token(session)
            child = _spawn(tok, _host_cmd(), cwd=str(HERE), inherit_env=True)
            k32.CloseHandle(tok)
            child_session, last_start = session, time.time()
        time.sleep(2)


# ------------------------------------------------------------------ install / remove
def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate(arg: str) -> None:
    params = f'"{HERE / "aod_launcher.py"}" {arg}' if not FROZEN else f"--{arg}-service"
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)


def _ask_running_aod_to_quit() -> None:
    try:
        req = urllib.request.Request("http://127.0.0.1:8766/_admin/quit", method="POST",
                                     headers={"X-AOD-Admin": "1"})
        urllib.request.urlopen(req, timeout=3).read()
        time.sleep(1.5)
    except Exception:
        pass


def install() -> None:
    if not _is_admin():
        _elevate("install")
        return
    _ask_running_aod_to_quit()
    PROGRAM_DATA.mkdir(parents=True, exist_ok=True)
    src = Path(os.environ.get("AOD_USER_HOME") or Path.home()) / ".aod"
    if src.exists():                                                    # keep pairings, certificate, shortcuts
        for f in src.iterdir():
            if f.is_file() and not (PROGRAM_DATA / f.name).exists():
                shutil.copy2(f, PROGRAM_DATA / f.name)
    subprocess.run(["icacls", str(PROGRAM_DATA), "/inheritance:r", "/grant:r", "SYSTEM:(OI)(CI)F",
                    "Administrators:(OI)(CI)F"], capture_output=True)
    cmd = f'"{sys.executable}" --launcher' if FROZEN else f'"{sys.executable}" "{HERE / "aod_launcher.py"}" run'
    subprocess.run(["schtasks", "/Create", "/TN", TASK, "/TR", cmd, "/SC", "ONSTART", "/RU", "SYSTEM",
                    "/RL", "HIGHEST", "/F"], check=True)
    subprocess.run(["schtasks", "/Run", "/TN", TASK])
    print("AOD service installed. It now starts at boot and works on the lock screen.")


def remove() -> None:
    if not _is_admin():
        _elevate("remove")
        return
    _ask_running_aod_to_quit()
    subprocess.run(["schtasks", "/End", "/TN", TASK], capture_output=True)
    subprocess.run(["schtasks", "/Delete", "/TN", TASK, "/F"], capture_output=True)
    print("AOD service removed.")


if __name__ == "__main__":
    {"install": install, "remove": remove, "run": run}.get(sys.argv[1] if len(sys.argv) > 1 else "run", run)()
