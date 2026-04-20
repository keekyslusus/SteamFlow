#!/usr/bin/env python
import base64
import logging
import os
import shutil
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

plugindir = Path(__file__).parent.resolve()
if str(plugindir) not in sys.path:
    sys.path.insert(0, str(plugindir))
lib_path = plugindir / "lib"
if str(lib_path) not in sys.path:
    sys.path.insert(0, str(lib_path))

import vdf

try:
    import winreg
except ImportError:
    import _winreg as winreg


LOG_FILE = plugindir / "steam_switch_worker.log"
LOCK_FILE = plugindir / "steam_switch_worker.lock"
NOTIFICATION_TITLE = "Steam Switch Failed"
STEAM_RELAUNCH_SETTLE_SECONDS = 4.0
STEAM_GAMES_URI = "steam://nav/games"
STEAM_PROCESS_IMAGE_NAMES = (
    "steam.exe",
    "steamwebhelper.exe",
    "GameOverlayUI.exe",
    "steamservice.exe",
)
STEAM_TREE_KILL_IMAGE_NAMES = {"steam.exe"}


log_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=512 * 1024,
    backupCount=1,
    encoding="utf-8",
)
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger = logging.getLogger("steam_switch_worker")
logger.handlers.clear()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def build_hidden_process_kwargs():
    kwargs = {}
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kwargs


HIDDEN_PROCESS_KWARGS = build_hidden_process_kwargs()


class FileLock:
    def __init__(self, lock_file):
        self.lock_file = Path(lock_file)
        self.fd = None

    def acquire(self, timeout=0):
        start_time = time.time()
        while True:
            try:
                self.fd = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode("ascii", errors="ignore"))
                return True
            except FileExistsError:
                try:
                    if time.time() - self.lock_file.stat().st_mtime > 60:
                        logger.warning("Removing stale lock file")
                        self.lock_file.unlink()
                        continue
                except OSError:
                    pass

                if timeout == 0 or (time.time() - start_time) >= timeout:
                    return False
                time.sleep(0.1)

    def release(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
        try:
            self.lock_file.unlink()
        except OSError:
            pass


def run_hidden(command, timeout=20):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="oem",
        errors="replace",
        timeout=timeout,
        **HIDDEN_PROCESS_KWARGS,
    )


def show_error_notification(message):
    message = str(message or "").strip()
    if not message:
        return

    escaped_title = NOTIFICATION_TITLE.replace("'", "''")
    escaped_message = message.replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Error
$notify.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Error
$notify.BalloonTipTitle = '{escaped_title}'
$notify.BalloonTipText = '{escaped_message}'
$notify.Visible = $true
$notify.ShowBalloonTip(5000)
Start-Sleep -Milliseconds 5500
$notify.Dispose()
"""
    encoded_script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")

    try:
        subprocess.Popen(
            [
                "powershell.exe",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encoded_script,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            **HIDDEN_PROCESS_KWARGS,
        )
    except Exception:
        logger.exception("Failed to show Steam switch error notification")


def fail_worker(message, exit_code=1):
    logger.error("%s", message)
    show_error_notification(message)
    sys.exit(exit_code)


def is_windows_process_running(image_name):
    result = run_hidden(["tasklist", "/FI", f"IMAGENAME eq {image_name}"], timeout=10)
    combined_output = " ".join(filter(None, [result.stdout, result.stderr])).lower()
    return image_name.lower() in combined_output


def wait_for_processes_to_stop(image_names, timeout_seconds=10):
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        remaining_processes = [
            image_name
            for image_name in image_names
            if is_windows_process_running(image_name)
        ]
        if not remaining_processes:
            return True
        time.sleep(0.5)
    return False


def terminate_steam_processes():
    for image_name in STEAM_PROCESS_IMAGE_NAMES:
        if not is_windows_process_running(image_name):
            continue

        logger.info("Stopping process %s", image_name)
        command = ["taskkill", "/F"]
        if image_name in STEAM_TREE_KILL_IMAGE_NAMES:
            command.append("/T")
        command.extend(["/IM", image_name])

        result = run_hidden(command, timeout=20)
        output_text = " ".join(filter(None, [result.stdout, result.stderr])).strip()

        if not is_windows_process_running(image_name):
            continue

        if image_name not in STEAM_TREE_KILL_IMAGE_NAMES:
            logger.warning(
                "taskkill did not stop helper process %s (code=%s): %s",
                image_name,
                result.returncode,
                output_text,
            )
            continue

        raise RuntimeError(output_text or f"taskkill exited with code {result.returncode}")

    if wait_for_processes_to_stop(STEAM_PROCESS_IMAGE_NAMES, timeout_seconds=10):
        logger.info("Steam processes stopped")
        return

    remaining_processes = [
        image_name
        for image_name in STEAM_PROCESS_IMAGE_NAMES
        if is_windows_process_running(image_name)
    ]
    raise RuntimeError(f"Steam processes still running: {', '.join(remaining_processes)}")


def get_loginusers_path(steam_path):
    path = steam_path / "config" / "loginusers.vdf"
    return path if path.exists() else None


def get_loginusers_backup_path(loginusers_path):
    return loginusers_path.with_name(f"{loginusers_path.name}_last")


def load_loginusers_data(loginusers_path):
    for candidate_path in (loginusers_path, get_loginusers_backup_path(loginusers_path)):
        if not candidate_path or not candidate_path.exists():
            continue
        try:
            with open(candidate_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                parsed = vdf.load(file_obj)
            users = parsed.get("users")
            if not isinstance(users, dict):
                parsed["users"] = {}
            return parsed
        except Exception:
            logger.exception("Failed to load loginusers data from %s", candidate_path)
    return {}


def save_loginusers_data(loginusers_path, data):
    backup_path = get_loginusers_backup_path(loginusers_path)
    temp_path = loginusers_path.with_name(f"{loginusers_path.name}.tmp")

    if loginusers_path.exists():
        shutil.copy2(loginusers_path, backup_path)

    with open(temp_path, "w", encoding="utf-8", newline="\n") as file_obj:
        vdf.dump(data, file_obj, pretty=True)
        file_obj.flush()
        os.fsync(file_obj.fileno())
    temp_path.replace(loginusers_path)


def set_loginusers_autologin_account(loginusers_path, steamid64):
    target_steamid64 = str(steamid64 or "").strip()
    data = load_loginusers_data(loginusers_path)
    users = data.get("users", {})
    if not isinstance(users, dict) or target_steamid64 not in users:
        return None

    for current_steamid64, raw_user_data in list(users.items()):
        user_data = raw_user_data if isinstance(raw_user_data, dict) else {}
        user_data["MostRecent"] = "1" if current_steamid64 == target_steamid64 else "0"
        if current_steamid64 == target_steamid64:
            user_data["AllowAutoLogin"] = "1"
            user_data["RememberPassword"] = "1"
        users[current_steamid64] = user_data

    save_loginusers_data(loginusers_path, data)
    normalized_user_data = users.get(target_steamid64, {})
    return normalized_user_data if isinstance(normalized_user_data, dict) else {}


def set_steam_registry_autologin_user(account_name):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
        winreg.SetValueEx(key, "AutoLoginUser", 0, winreg.REG_SZ, str(account_name or ""))
        winreg.SetValueEx(key, "RememberPassword", 0, winreg.REG_DWORD, 1)
        winreg.FlushKey(key)


def launch_steam_client(steam_path):
    try:
        os.startfile(STEAM_GAMES_URI)
        logger.info("Launched Steam via URI %s", STEAM_GAMES_URI)
        return
    except Exception:
        logger.exception("Failed to launch Steam via URI %s", STEAM_GAMES_URI)

    steam_exe = steam_path / "steam.exe"
    if not steam_exe.exists():
        raise FileNotFoundError(f"Steam executable not found at {steam_exe}")

    subprocess.Popen(
        [str(steam_exe)],
        cwd=str(steam_path),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        **HIDDEN_PROCESS_KWARGS,
    )
    logger.info("Launched Steam executable directly")


def main():
    if len(sys.argv) != 3:
        fail_worker(f"Invalid arguments count: {len(sys.argv)}")

    steam_path = Path(sys.argv[1])
    target_steamid64 = str(sys.argv[2] or "").strip()
    logger.info("Worker started for target SteamID64 ending with %s", target_steamid64[-4:] if target_steamid64 else "")

    if not steam_path.exists():
        fail_worker(f"Steam path does not exist: {steam_path}")
    if not target_steamid64.isdigit():
        fail_worker(f"Invalid target SteamID64: {target_steamid64}")

    loginusers_path = get_loginusers_path(steam_path)
    if not loginusers_path:
        fail_worker(f"loginusers.vdf not found under {steam_path}")

    lock = FileLock(LOCK_FILE)
    if not lock.acquire(timeout=5):
        fail_worker("Could not acquire Steam switch worker lock")

    try:
        terminate_steam_processes()
        updated_loginuser_data = set_loginusers_autologin_account(loginusers_path, target_steamid64)
        if updated_loginuser_data is None:
            fail_worker("Target account not found in loginusers.vdf")

        target_account_name = str(updated_loginuser_data.get("AccountName", "") or "").strip()
        logger.info("Updated loginusers.vdf for account %s", target_account_name or target_steamid64)
        set_steam_registry_autologin_user(target_account_name)
        logger.info("Updated Steam registry AutoLoginUser=%s", target_account_name)

        logger.info("Waiting %.1f seconds before relaunch", STEAM_RELAUNCH_SETTLE_SECONDS)
        time.sleep(STEAM_RELAUNCH_SETTLE_SECONDS)
        launch_steam_client(steam_path)
        logger.info("Steam launch requested")
    except Exception as error:
        logger.exception("Steam switch worker failed")
        error_message = str(error).strip()
        show_error_notification(error_message or "Steam switch worker failed")
        sys.exit(1)
    finally:
        lock.release()


if __name__ == "__main__":
    main()
