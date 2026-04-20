import copy
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import vdf

try:
    import winreg
except ImportError:
    import _winreg as winreg


class SteamPluginAccountsMixin:
    STEAM_PROCESS_IMAGE_NAMES = (
        "steam.exe",
        "steamwebhelper.exe",
        "GameOverlayUI.exe",
        "steamservice.exe",
    )

    def get_loginusers_backup_path(self):
        loginusers_path = self.get_loginusers_path()
        if not loginusers_path:
            return None
        return loginusers_path.with_name(f"{loginusers_path.name}_last")

    def _normalize_loginusers_data(self, parsed):
        normalized = parsed if isinstance(parsed, dict) else {}
        users = normalized.get("users")
        if not isinstance(users, dict):
            normalized["users"] = {}
        return normalized

    def _get_cached_loginusers_data(self, candidate_path, current_mtime):
        with self.state_lock:
            cache_path = self.loginusers_cache_path
            cache_mtime = self.loginusers_cache_mtime
            cache_data = self.loginusers_cache_data

        if (
            candidate_path
            and cache_data is not None
            and candidate_path == cache_path
            and current_mtime <= cache_mtime
        ):
            return copy.deepcopy(cache_data)
        return None

    def _store_loginusers_cache(self, candidate_path, current_mtime, parsed):
        normalized = self._normalize_loginusers_data(parsed)
        with self.state_lock:
            self.loginusers_cache_path = candidate_path
            self.loginusers_cache_mtime = current_mtime
            self.loginusers_cache_data = copy.deepcopy(normalized)
        return copy.deepcopy(normalized)

    def load_loginusers_data(self):
        paths_to_try = [self.get_loginusers_path(), self.get_loginusers_backup_path()]
        parse_failed = False
        for candidate_path in paths_to_try:
            if not candidate_path or not candidate_path.exists():
                continue

            try:
                current_mtime = candidate_path.stat().st_mtime
            except OSError:
                current_mtime = 0

            cached_data = self._get_cached_loginusers_data(candidate_path, current_mtime)
            if cached_data is not None:
                return cached_data

            try:
                with open(candidate_path, "r", encoding="utf-8", errors="ignore") as file_obj:
                    parsed = vdf.load(file_obj)
                return self._store_loginusers_cache(candidate_path, current_mtime, parsed)
            except Exception:
                parse_failed = True
                continue

        if parse_failed:
            self.log_exception("Failed to load Steam loginusers.vdf")
        return {}

    def save_loginusers_data(self, data):
        loginusers_path = self.get_loginusers_path()
        if not loginusers_path:
            raise FileNotFoundError("Steam loginusers.vdf not found")

        backup_path = self.get_loginusers_backup_path()
        temp_path = loginusers_path.with_name(f"{loginusers_path.name}.tmp")

        if backup_path and loginusers_path.exists():
            shutil.copy2(loginusers_path, backup_path)

        with open(temp_path, "w", encoding="utf-8", newline="\n") as file_obj:
            vdf.dump(data, file_obj, pretty=True)
        temp_path.replace(loginusers_path)

        try:
            current_mtime = loginusers_path.stat().st_mtime
        except OSError:
            current_mtime = 0
        self._store_loginusers_cache(loginusers_path, current_mtime, data)

    def get_steam_account_avatar_path(self, steamid64):
        if not self.steam_path or not steamid64:
            return None
        avatar_path = self.steam_path / "config" / "avatarcache" / f"{steamid64}.png"
        if avatar_path.exists():
            return avatar_path
        return None

    def get_steam_account_label(self, account_data):
        if not isinstance(account_data, dict):
            return "Steam account"
        return (
            str(account_data.get("persona_name", "") or "").strip()
            or str(account_data.get("account_name", "") or "").strip()
            or str(account_data.get("steamid64", "") or "").strip()
            or "Steam account"
        )

    def get_known_steam_accounts(self):
        users = self.load_loginusers_data().get("users", {})
        if not isinstance(users, dict):
            return []

        accounts = []
        for steamid64, raw_user_data in users.items():
            steamid64 = str(steamid64 or "").strip()
            if not steamid64.isdigit():
                continue

            user_data = raw_user_data if isinstance(raw_user_data, dict) else {}
            avatar_path = self.get_steam_account_avatar_path(steamid64)
            try:
                timestamp = int(user_data.get("Timestamp", 0) or 0)
            except (TypeError, ValueError):
                timestamp = 0

            account = {
                "steamid64": steamid64,
                "account_name": str(user_data.get("AccountName", "") or "").strip(),
                "persona_name": str(user_data.get("PersonaName", "") or "").strip(),
                "remember_password": str(user_data.get("RememberPassword", "0")).strip() == "1",
                "allow_auto_login": str(user_data.get("AllowAutoLogin", "0")).strip() == "1",
                "most_recent": str(user_data.get("MostRecent", "0")).strip() == "1",
                "timestamp": timestamp,
                "icon_path": str(avatar_path) if avatar_path else None,
            }
            account["label"] = self.get_steam_account_label(account)
            accounts.append(account)

        accounts.sort(
            key=lambda account: (
                not account["most_recent"],
                -account["timestamp"],
                account["label"].lower(),
            )
        )
        return accounts

    def get_switchable_steam_accounts(self):
        active_steamid64 = self.get_active_steam_user_steamid64()
        return [
            account
            for account in self.get_known_steam_accounts()
            if account.get("steamid64") != active_steamid64
        ]

    def show_switch_error_message(self, message):
        show_msg = getattr(self, "show_msg", None)
        if callable(show_msg):
            try:
                show_msg("Steam Switch Failed", str(message or ""), self.DEFAULT_ICON)
            except Exception:
                pass

    def has_multiple_known_steam_accounts(self):
        return len(self.get_known_steam_accounts()) > 1

    def set_loginusers_autologin_account(self, steamid64):
        target_steamid64 = str(steamid64 or "").strip()
        data = self.load_loginusers_data()
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

        self.save_loginusers_data(data)
        normalized_user_data = users.get(target_steamid64, {})
        return normalized_user_data if isinstance(normalized_user_data, dict) else {}

    def set_steam_registry_autologin_user(self, account_name):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            winreg.SetValueEx(key, "AutoLoginUser", 0, winreg.REG_SZ, str(account_name or ""))
            winreg.SetValueEx(key, "RememberPassword", 0, winreg.REG_DWORD, 1)

    def _is_windows_process_running(self, image_name):
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        combined_output = " ".join(filter(None, [result.stdout, result.stderr])).lower()
        return image_name.lower() in combined_output

    def terminate_steam_processes(self):
        for image_name in self.STEAM_PROCESS_IMAGE_NAMES:
            if not self._is_windows_process_running(image_name):
                continue
            result = subprocess.run(
                ["taskkill", "/F", "/T", "/IM", image_name],
                capture_output=True,
                text=True,
                timeout=20,
            )
            output_text = " ".join(filter(None, [result.stdout, result.stderr])).strip()
            if self._is_windows_process_running(image_name):
                raise RuntimeError(output_text or f"taskkill exited with code {result.returncode}")

        deadline = time.time() + 10
        while time.time() < deadline:
            if not any(self._is_windows_process_running(image_name) for image_name in self.STEAM_PROCESS_IMAGE_NAMES):
                return
            time.sleep(0.5)

        remaining_processes = [
            image_name
            for image_name in self.STEAM_PROCESS_IMAGE_NAMES
            if self._is_windows_process_running(image_name)
        ]
        if remaining_processes:
            raise RuntimeError(f"Steam processes still running: {', '.join(remaining_processes)}")

    def terminate_steam_client(self):
        if not self._is_windows_process_running("steam.exe"):
            return
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/IM", "steam.exe"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        output_text = " ".join(filter(None, [result.stdout, result.stderr])).strip()
        if self._is_windows_process_running("steam.exe"):
            raise RuntimeError(output_text or f"taskkill exited with code {result.returncode}")

    def launch_steam_client_executable(self):
        if not self.steam_path:
            self.steam_path = self.get_steam_path()
        if not self.steam_path:
            raise FileNotFoundError("Steam installation not found")

        steam_exe = self.steam_path / "steam.exe"
        if not steam_exe.exists():
            raise FileNotFoundError(f"Steam executable not found at {steam_exe}")

        try:
            subprocess.Popen([str(steam_exe)], cwd=str(self.steam_path))
        except Exception:
            os.startfile(str(steam_exe))

    def start_steam_switch_worker(self, steamid64):
        worker_script = self.plugin_dir / "steam_switch_worker.py"
        if not worker_script.exists():
            raise FileNotFoundError(f"Steam switch worker not found at {worker_script}")

        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = (
                subprocess.CREATE_NO_WINDOW
                | subprocess.DETACHED_PROCESS
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )

        subprocess.Popen(
            [sys.executable, str(worker_script), str(self.steam_path), str(steamid64)],
            startupinfo=startupinfo,
            creationflags=creationflags,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            cwd=str(self.plugin_dir),
        )

    def switch_steam_account(self, steamid64):
        target_steamid64 = str(steamid64 or "").strip()
        if not target_steamid64.isdigit():
            message = "Invalid Steam account"
            self.show_switch_error_message(message)
            return message

        if not self.steam_path:
            self.steam_path = self.get_steam_path()
        if not self.steam_path:
            message = "Steam installation not found"
            self.show_switch_error_message(message)
            return message

        target_account = self.get_steam_user_details(target_steamid64)
        if not target_account:
            message = "Steam account not found in loginusers.vdf"
            self.show_switch_error_message(message)
            return message

        target_label = self.get_steam_account_label(target_account)
        if self.get_active_steam_user_steamid64() == target_steamid64:
            return f"{target_label} is already the active Steam account"

        try:
            self.start_steam_switch_worker(target_steamid64)
            schedule_refresh = getattr(self, "schedule_installed_games_refresh", None)
            if callable(schedule_refresh):
                schedule_refresh(delay_seconds=5, reset_user_paths=True)
            return f"Switching Steam account to {target_label}..."
        except Exception:
            self.log_exception(f"Failed to start Steam switch worker for {target_label}")
            message = f"Failed to start Steam switch worker for {target_label}"
            self.show_switch_error_message(message)
            return message

    def get_loginusers_path(self):
        if not self.steam_path:
            return None
        path = self.steam_path / "config" / "loginusers.vdf"
        if path.exists():
            return path
        return None

    def get_steam_user_details(self, steamid64):
        if not steamid64:
            return {}

        try:
            user_data = self.load_loginusers_data().get("users", {}).get(str(steamid64), {})
            return {
                "steamid64": str(steamid64),
                "account_name": user_data.get("AccountName"),
                "persona_name": user_data.get("PersonaName"),
            }
        except Exception:
            self.log_exception("Failed to load Steam loginusers.vdf")
            return {}

    def get_last_known_steam_user_id(self):
        try:
            users = self.load_loginusers_data().get("users", {})
            if not isinstance(users, dict):
                return None

            selected_steamid64 = None
            selected_timestamp = -1
            fallback_steamid64 = None
            fallback_timestamp = -1

            for steamid64, user_data in users.items():
                steamid64 = str(steamid64 or "").strip()
                if not steamid64.isdigit():
                    continue
                if not isinstance(user_data, dict):
                    user_data = {}

                try:
                    timestamp = int(user_data.get("Timestamp", 0) or 0)
                except (TypeError, ValueError):
                    timestamp = 0

                is_most_recent = str(user_data.get("MostRecent", "0")).strip() == "1"
                if is_most_recent and timestamp >= selected_timestamp:
                    selected_steamid64 = steamid64
                    selected_timestamp = timestamp

                if timestamp >= fallback_timestamp:
                    fallback_steamid64 = steamid64
                    fallback_timestamp = timestamp

            chosen_steamid64 = selected_steamid64 or fallback_steamid64
            if not chosen_steamid64:
                return None

            return str(int(chosen_steamid64) - 76561197960265728)
        except Exception:
            self.log_exception("Failed to resolve last known Steam user from loginusers.vdf")
            return None

    def get_active_steam_user_id(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam\ActiveProcess") as key:
                active_user, _ = winreg.QueryValueEx(key, "ActiveUser")
            active_user = str(active_user).strip()
            if active_user and active_user != "0":
                return active_user
        except Exception:
            pass
        return self.get_last_known_steam_user_id()

    def get_active_steam_user_steamid64(self):
        active_user_id = self.get_active_steam_user_id()
        if not active_user_id:
            return None
        try:
            return str(76561197960265728 + int(active_user_id))
        except (TypeError, ValueError):
            return None
