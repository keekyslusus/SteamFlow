import json
import threading
import time

try:
    from PIL import Image
except ImportError:
    Image = None


class SteamPluginProfileMixin:
    def load_profile_cache(self):
        if not self.profile_cache_file.exists():
            return {}
        try:
            with open(self.profile_cache_file, "r", encoding="utf-8") as file_obj:
                cache_data = json.load(file_obj)
            return cache_data if isinstance(cache_data, dict) else {}
        except Exception:
            self.log_exception("Failed to load active Steam profile cache")
            return {}

    def save_profile_cache(self, cache_data):
        try:
            with open(self.profile_cache_file, "w", encoding="utf-8") as file_obj:
                json.dump(cache_data, file_obj)
        except Exception:
            self.log_exception("Failed to save active Steam profile cache")

    def ensure_active_profile_summary_loaded(self):
        with self.state_lock:
            if self.active_profile_summary_loaded:
                return
        cache_data = self.load_profile_cache()
        with self.state_lock:
            self.active_profile_summary = cache_data if isinstance(cache_data, dict) else {}
            self.active_profile_summary_loaded = True

    def active_profile_summary_is_fresh(self):
        if not self.has_owned_api_key() or not self.is_owned_api_key_bound_to_active_user():
            return False

        self.ensure_active_profile_summary_loaded()
        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return False

        with self.state_lock:
            summary = dict(self.active_profile_summary)
        if str(summary.get("steamid64", "") or "") != steamid64:
            return False
        return (time.time() - float(summary.get("fetched_at", 0) or 0)) < self.PROFILE_SUMMARY_CACHE_TTL_SECONDS

    def fetch_active_profile_summary(self, steamid64):
        api_key = self.get_owned_api_key()
        if not api_key or not steamid64:
            return None

        try:
            api_url = (
                "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
                f"?key={api_key}&steamids={steamid64}"
            )
            response = self._http_get(api_url, timeout=1.2, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(response.data.decode("utf-8"))
            players = data.get("response", {}).get("players", [])
            if not isinstance(players, list) or not players:
                return None

            player_data = players[0] if isinstance(players[0], dict) else {}
            return {
                "steamid64": steamid64,
                "personaname": str(player_data.get("personaname", "") or "").strip(),
                "personastate": int(player_data.get("personastate", 0) or 0),
                "gameextrainfo": str(player_data.get("gameextrainfo", "") or "").strip(),
                "fetched_at": time.time(),
            }
        except Exception:
            self.log_exception("Failed to fetch active Steam profile summary")
            return None

    def schedule_active_profile_summary_refresh(self, force=False):
        if not self.has_owned_api_key() or not self.is_owned_api_key_bound_to_active_user():
            return

        self.ensure_active_profile_summary_loaded()
        with self.state_lock:
            if self.pending_profile_summary_refresh:
                return
            if not force and self.active_profile_summary_is_fresh():
                return
            self.pending_profile_summary_refresh = True

        threading.Thread(target=self._refresh_active_profile_summary_worker, daemon=True).start()

    def _refresh_active_profile_summary_worker(self):
        try:
            self.refresh_active_profile_summary()
        finally:
            with self.state_lock:
                self.pending_profile_summary_refresh = False

    def refresh_active_profile_summary(self):
        if not self.has_owned_api_key() or not self.is_owned_api_key_bound_to_active_user():
            return

        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return

        summary = self.fetch_active_profile_summary(steamid64)
        if not summary:
            return

        with self.state_lock:
            self.active_profile_summary = summary
            self.active_profile_summary_loaded = True
        self.save_profile_cache(summary)

    def get_active_profile_summary(self):
        if not self.has_owned_api_key() or not self.is_owned_api_key_bound_to_active_user():
            return None

        self.ensure_active_profile_summary_loaded()
        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return None

        with self.state_lock:
            summary = dict(self.active_profile_summary)

        if str(summary.get("steamid64", "") or "") != steamid64:
            self.schedule_active_profile_summary_refresh(force=True)
            return None

        if not summary:
            self.schedule_active_profile_summary_refresh(force=True)
            return None

        if not self.active_profile_summary_is_fresh():
            self.schedule_active_profile_summary_refresh()
        return summary

    def get_active_profile_status(self):
        summary = self.get_active_profile_summary()
        if not summary:
            return ""

        current_game = str(summary.get("gameextrainfo", "") or "").strip()
        if current_game:
            return f"Playing {current_game}"

        status_labels = {
            0: "Offline",
            1: "Online",
            2: "Busy",
            3: "Away",
            4: "Snooze",
            5: "Looking to trade",
            6: "Looking to play",
        }
        try:
            return status_labels.get(int(summary.get("personastate", 0) or 0), "")
        except (TypeError, ValueError):
            return ""

    def fetch_owned_app_ids_from_api(self, api_key, steamid64, timeout=3):
        api_key = self.normalize_steam_web_api_key(api_key)
        steamid64 = str(steamid64 or "").strip()
        if not api_key or not steamid64:
            raise ValueError("Missing Steam API credentials")

        url = (
            "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
            f"?key={api_key}&steamid={steamid64}&include_played_free_games=1&include_appinfo=0"
        )
        response = self._http_get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        data = json.loads(response.data.decode("utf-8"))
        games = data.get("response", {}).get("games", [])
        if not isinstance(games, list):
            return set(), {}

        owned_app_ids = set()
        owned_game_playtimes = {}
        for game_data in games:
            app_id = str(game_data.get("appid", "")).strip()
            if app_id:
                owned_app_ids.add(app_id)
                try:
                    owned_game_playtimes[app_id] = int(game_data.get("playtime_forever", 0) or 0)
                except (TypeError, ValueError):
                    owned_game_playtimes[app_id] = 0
        return owned_app_ids, owned_game_playtimes

    def get_active_steam_avatar_icon(self):
        source_path = self.get_active_steam_avatar_path()
        if not source_path:
            return self.DEFAULT_ICON

        frame_path = self.get_active_steam_avatar_frame_path()
        if not frame_path:
            return str(source_path)

        composite_path = self.avatar_cache_dir / f"avatar_{source_path.stem}_framed.png"
        try:
            if (
                composite_path.exists()
                and composite_path.stat().st_mtime >= source_path.stat().st_mtime
                and composite_path.stat().st_mtime >= frame_path.stat().st_mtime
            ):
                return str(composite_path)
        except OSError:
            return str(source_path)

        if self.create_framed_avatar_icon(source_path, frame_path, composite_path):
            return str(composite_path)
        return str(source_path)

    def get_active_steam_avatar_path(self):
        if not self.steam_path:
            return None

        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return None

        avatar_path = self.steam_path / "config" / "avatarcache" / f"{steamid64}.png"
        if avatar_path.exists():
            return avatar_path
        return None

    def load_avatar_frame_cache(self):
        if not self.avatar_frame_cache_file.exists():
            return {}
        try:
            with open(self.avatar_frame_cache_file, "r", encoding="utf-8") as file_obj:
                cache_data = json.load(file_obj)
            return cache_data if isinstance(cache_data, dict) else {}
        except Exception:
            self.log_exception("Failed to load avatar frame cache")
            return {}

    def save_avatar_frame_cache(self, cache_data):
        try:
            with open(self.avatar_frame_cache_file, "w", encoding="utf-8") as file_obj:
                json.dump(cache_data, file_obj)
        except Exception:
            self.log_exception("Failed to save avatar frame cache")

    def get_active_steam_avatar_frame_path(self):
        if not self.has_owned_api_key() or not self.is_owned_api_key_bound_to_active_user():
            return None

        steamid64 = self.get_active_steam_user_steamid64()
        if not steamid64:
            return None

        cache_data = self.load_avatar_frame_cache()
        cached_steamid64 = str(cache_data.get("steamid64", "") or "")
        cache_age_seconds = time.time() - float(cache_data.get("timestamp", 0) or 0)
        cached_image_name = str(cache_data.get("image_name", "") or "")
        cached_frame_path = self.avatar_cache_dir / cached_image_name if cached_image_name else None

        if (
            cached_steamid64 == steamid64
            and cache_age_seconds < 24 * 60 * 60
            and cached_frame_path
            and cached_frame_path.exists()
        ):
            return cached_frame_path
        if cached_steamid64 == steamid64 and cache_age_seconds < 24 * 60 * 60 and cache_data.get("no_frame"):
            return None

        frame_data = self.fetch_active_avatar_frame_data(steamid64)
        if not frame_data:
            self.save_avatar_frame_cache(
                {
                    "steamid64": steamid64,
                    "timestamp": time.time(),
                    "no_frame": True,
                }
            )
            return None

        frame_name = f"avatar_frame_{frame_data['communityitemid']}.png"
        frame_path = self.avatar_cache_dir / frame_name
        if not frame_path.exists() and not self.download_avatar_frame_image(frame_data["image_url"], frame_path):
            return None

        self.save_avatar_frame_cache(
            {
                "steamid64": steamid64,
                "timestamp": time.time(),
                "communityitemid": frame_data["communityitemid"],
                "image_name": frame_name,
                "image_url": frame_data["image_url"],
                "frame_name": frame_data.get("name"),
            }
        )
        return frame_path if frame_path.exists() else None

    def fetch_active_avatar_frame_data(self, steamid64):
        api_key = self.get_owned_api_key()
        if not api_key or not steamid64:
            return None

        try:
            api_url = f"https://api.steampowered.com/IPlayerService/GetAvatarFrame/v1/?key={api_key}&steamid={steamid64}"
            response = self._http_get(api_url, timeout=1.2, headers={"User-Agent": "Mozilla/5.0"})
            data = json.loads(response.data.decode("utf-8"))
            frame_data = data.get("response", {}).get("avatar_frame") or {}
            communityitemid = str(frame_data.get("communityitemid", "")).strip()
            image_path = str(frame_data.get("image_small") or frame_data.get("image_large") or "").strip()
            if not communityitemid or not image_path:
                return None
            image_url = image_path
            if not image_url.startswith("http://") and not image_url.startswith("https://"):
                image_url = f"https://shared.fastly.steamstatic.com/community_assets/images/{image_url.lstrip('/')}"
            return {
                "communityitemid": communityitemid,
                "image_url": image_url,
                "name": frame_data.get("name") or frame_data.get("item_title"),
            }
        except Exception:
            self.log_exception("Failed to fetch active Steam avatar frame")
            return None

    def download_avatar_frame_image(self, image_url, save_path):
        try:
            response = self._http_get(image_url, timeout=2, headers={"User-Agent": "Mozilla/5.0"})
            with open(save_path, "wb") as out_file:
                out_file.write(response.data)
            return True
        except Exception:
            self.log_exception(f"Failed to download avatar frame: {image_url}")
            return False

    def create_framed_avatar_icon(self, avatar_path, frame_path, output_path):
        if Image is None:
            return False
        try:
            with Image.open(avatar_path) as avatar_image, Image.open(frame_path) as frame_image:
                avatar_rgba = avatar_image.convert("RGBA")
                frame_rgba = frame_image.convert("RGBA").resize(avatar_rgba.size, Image.Resampling.LANCZOS)
                composed = avatar_rgba.copy()
                composed.alpha_composite(frame_rgba)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                composed.save(output_path, format="PNG")
            return output_path.exists()
        except Exception:
            self.log_exception(f"Failed to compose framed avatar icon from {avatar_path}")
            return False

    def owned_games_cache_is_fresh(self):
        if not self.is_owned_api_key_bound_to_active_user():
            return False
        with self.state_lock:
            if not self.owned_games_cache_loaded:
                return False
            if not self.owned_games_last_sync:
                return False
            if self.owned_games_steamid64 != self.get_active_steam_user_steamid64():
                return False
            return (time.time() - self.owned_games_last_sync) < self.OWNED_GAMES_CACHE_TTL_SECONDS

    def schedule_owned_games_refresh(self, force=False):
        if not self.should_detect_owned_games() or not self.is_owned_api_key_bound_to_active_user():
            return

        with self.state_lock:
            if self.pending_owned_games_refresh:
                return
            if not force and (time.time() - self.owned_games_last_attempt) < self.OWNED_GAMES_RETRY_DELAY_SECONDS:
                return
            if not force and self.owned_games_cache_is_fresh():
                return
            self.pending_owned_games_refresh = True
            self.owned_games_last_attempt = time.time()

        threading.Thread(target=self._refresh_owned_games_worker, daemon=True).start()

    def _refresh_owned_games_worker(self):
        try:
            self.refresh_owned_games_cache()
        finally:
            with self.state_lock:
                self.pending_owned_games_refresh = False

    def refresh_owned_games_cache(self):
        if not self.should_detect_owned_games() or not self.is_owned_api_key_bound_to_active_user():
            return

        steamid64 = self.get_active_steam_user_steamid64()
        api_key = self.get_owned_api_key()
        if not steamid64:
            self.clear_owned_games_cache()
            return
        if not api_key:
            return

        start_time = time.perf_counter()
        fetch_succeeded = False
        owned_app_ids = set()
        owned_game_playtimes = {}
        try:
            owned_app_ids, owned_game_playtimes = self.fetch_owned_app_ids_from_api(api_key, steamid64, timeout=3)
            fetch_succeeded = True
        except Exception as error:
            if not isinstance(
                error,
                (
                    self.urllib3.exceptions.TimeoutError,
                    self.urllib3.exceptions.HTTPError,
                    json.JSONDecodeError,
                ),
            ):
                self.log_exception("Failed to refresh owned Steam games")

        if fetch_succeeded:
            with self.state_lock:
                self.owned_games_last_sync = time.time()
                self.owned_games_public_profile = True
                self.owned_games_steamid64 = steamid64
                self.owned_app_ids = owned_app_ids
                self.owned_game_playtimes = owned_game_playtimes
                self.owned_games_cache_loaded = True
            self.save_owned_games_cache()
        else:
            with self.state_lock:
                if self.owned_games_steamid64 != steamid64:
                    self.owned_games_steamid64 = steamid64

        self.log_slow_call(
            "refresh_owned_games_cache",
            (time.perf_counter() - start_time) * 1000,
            f"steamid64={steamid64} count={len(owned_app_ids)} success={fetch_succeeded}",
        )

    def is_owned_app(self, app_id):
        if not self.should_detect_owned_games() or not app_id or not self.is_owned_api_key_bound_to_active_user():
            return False

        app_id = str(app_id)
        with self.state_lock:
            if self.owned_games_steamid64 == self.get_active_steam_user_steamid64() and app_id in self.owned_app_ids:
                return True

        if not self.owned_games_cache_is_fresh():
            self.schedule_owned_games_refresh()
        return False

    def get_active_account_ownership_state(self, app_id):
        if not self.should_detect_owned_games() or not app_id or not self.is_owned_api_key_bound_to_active_user():
            return "unknown"

        app_id = str(app_id)
        active_steamid64 = self.get_active_steam_user_steamid64()
        with self.state_lock:
            if self.owned_games_steamid64 == active_steamid64 and app_id in self.owned_app_ids:
                return "owned"

        if self.owned_games_cache_is_fresh():
            return "not_owned"

        self.schedule_owned_games_refresh()
        return "unknown"
