import sys
import threading
from functools import cached_property
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
LIB_PATH = PACKAGE_ROOT / "lib"

if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from flox import Flox
import urllib3

from .actions import SteamPluginActionsMixin
from .accounts import SteamPluginAccountsMixin
from .core import SteamPluginCoreMixin
from .local import SteamPluginLocalMixin
from .profile import SteamPluginProfileMixin
from .storage import SteamPluginStorageMixin
from .store import SteamPluginStoreMixin
from .store_metrics import SteamPluginStoreMetricsMixin
from .ui_commands import SteamPluginUICommandsMixin
from .ui import SteamPluginUIMixin
from .ui_query import SteamPluginUIQueryMixin
from .wishlist import SteamPluginWishlistMixin

try:
    import certifi

    _CA_CERTS_PATH = certifi.where()
except ImportError:
    _CA_CERTS_PATH = None


class SteamPlugin(
    SteamPluginUIQueryMixin,
    SteamPluginWishlistMixin,
    SteamPluginUICommandsMixin,
    SteamPluginUIMixin,
    SteamPluginStoreMixin,
    SteamPluginStoreMetricsMixin,
    SteamPluginProfileMixin,
    SteamPluginAccountsMixin,
    SteamPluginLocalMixin,
    SteamPluginStorageMixin,
    SteamPluginCoreMixin,
    SteamPluginActionsMixin,
    Flox,
):
    DEFAULT_ICON = "icons/steam.png"
    BROWSER_ICON = "icons/browser.png"
    CLIPBOARD_ICON = "icons/clipboard.png"
    COMMUNITY_ICON = "icons/community.png"
    DOWNLOAD_ICON = "icons/download.png"
    DISCUSSIONS_ICON = "icons/discussions.png"
    GUIDES_ICON = "icons/guides.png"
    LOCATION_ICON = "icons/location.png"
    OWNED_ICON = "icons/owned.png"
    ONLINE_ICON = "icons/online.png"
    OFFLINE_ICON = "icons/offline.png"
    INVISIBLE_ICON = "icons/invisible.png"
    PROPERTIES_ICON = "icons/properties.png"
    REFUND_ICON = "icons/refund.png"
    SCREENSHOT_ICON = "icons/screenshot.png"
    SETTINGS_ICON = "icons/settings.png"
    STEAMDB_ICON = "icons/steamdb.png"
    TRASH_ICON = "icons/trash.png"
    WARNING_ICON = "icons/warning.png"
    WISHLIST_ICON = "icons/wishlist.png"
    OWNED_GAMES_RETRY_DELAY_SECONDS = 10 * 60
    OWNED_GAMES_CACHE_TTL_SECONDS = 24 * 60 * 60
    MAX_LOG_SIZE_BYTES = 10 * 1024
    MAX_QUERY_RESULTS = 5
    MAX_EMPTY_QUERY_RESULTS = 67
    SEARCH_CACHE_TTL_SECONDS = 30
    PLAYER_COUNT_CACHE_TTL_SECONDS = 4 * 60
    REVIEW_SCORE_CACHE_TTL_SECONDS = 4 * 60 * 60
    ACHIEVEMENT_PROGRESS_CACHE_TTL_SECONDS = 12 * 60 * 60
    ACHIEVEMENT_SCHEMA_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
    APP_DETAILS_CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
    APP_DETAILS_FAILURE_CACHE_TTL_SECONDS = 6 * 60 * 60
    WISHLIST_CACHE_TTL_SECONDS = 15 * 60
    CACHE_CLEANUP_INTERVAL_SECONDS = 5 * 60
    METRIC_CACHE_SAVE_INTERVAL_SECONDS = 10
    STORE_COLD_METRIC_FETCH_LIMIT = 3
    WISHLIST_COLD_DETAIL_FETCH_LIMIT = 8
    MAX_WISHLIST_RESULTS = 15
    PERF_QUERY_LOG_THRESHOLD_MS = 250
    PERF_STAGE_LOG_THRESHOLD_MS = 100
    PROFILE_SUMMARY_CACHE_TTL_SECONDS = 30
    DEFAULT_BLACKLISTED_APP_IDS = {"228980"}
    STATE_FLAG_UPDATE_REQUIRED = 2
    STATE_FLAG_FULLY_INSTALLED = 4
    STATE_FLAG_UPDATE_RUNNING = 256
    STATE_FLAG_UPDATE_PAUSED = 512
    STATE_FLAG_UPDATE_STARTED = 1024
    REVIEW_SCORE_EXCLUDED_NAME_PATTERNS = (
        "soundtrack",
        "demo",
        "dlc",
        "art book",
        "artbook",
        "digital artbook",
        "digital art book",
        "supporter pack",
        "starter pack",
        "upgrade pack",
        "season pass",
        "expansion pass",
        "character creator",
        "cosmetic pack",
    )
    PLATFORM_LABELS = {
        "windows": "Win",
        "mac": "Mac",
        "linux": "Linux",
    }

    urllib3 = urllib3

    def __init__(self):
        super().__init__()
        self.plugin_dir = PACKAGE_ROOT
        self._initialize_paths()
        self._initialize_minimal_state()

    @cached_property
    def logfile(self):
        return str(self.plugin_dir / "plugin_steamflow.log")

    def _initialize_paths(self):
        self.state_lock = threading.RLock()
        self.DEFAULT_ICON = str(self.plugin_dir / "icons" / "steam.png")
        self.BROWSER_ICON = str(self.plugin_dir / "icons" / "browser.png")
        self.CLIPBOARD_ICON = str(self.plugin_dir / "icons" / "clipboard.png")
        self.COMMUNITY_ICON = str(self.plugin_dir / "icons" / "community.png")
        self.DOWNLOAD_ICON = str(self.plugin_dir / "icons" / "download.png")
        self.DISCUSSIONS_ICON = str(self.plugin_dir / "icons" / "discussions.png")
        self.GUIDES_ICON = str(self.plugin_dir / "icons" / "guides.png")
        self.LOCATION_ICON = str(self.plugin_dir / "icons" / "location.png")
        self.OWNED_ICON = str(self.plugin_dir / "icons" / "owned.png")
        self.ONLINE_ICON = str(self.plugin_dir / "icons" / "online.png")
        self.OFFLINE_ICON = str(self.plugin_dir / "icons" / "offline.png")
        self.INVISIBLE_ICON = str(self.plugin_dir / "icons" / "invisible.png")
        self.PROPERTIES_ICON = str(self.plugin_dir / "icons" / "properties.png")
        self.REFUND_ICON = str(self.plugin_dir / "icons" / "refund.png")
        self.SCREENSHOT_ICON = str(self.plugin_dir / "icons" / "screenshot.png")
        self.SETTINGS_ICON = str(self.plugin_dir / "icons" / "settings.png")
        self.STEAMDB_ICON = str(self.plugin_dir / "icons" / "steamdb.png")
        self.TRASH_ICON = str(self.plugin_dir / "icons" / "trash.png")
        self.WARNING_ICON = str(self.plugin_dir / "icons" / "warning.png")
        self.WISHLIST_ICON = str(self.plugin_dir / "icons" / "wishlist.png")
        self.cache_dir = self.plugin_dir / "cache_img"
        self.country_cache_file = self.plugin_dir / "cache_country.json"
        self.metric_cache_file = self.plugin_dir / "cache_metric.json"
        self.wishlist_worker_lock_file = self.plugin_dir / "steam_wishlist_worker.lock"
        self.owned_games_cache_file = self.plugin_dir / "cache_owned_games.json"
        self.wishlist_cache_file = self.plugin_dir / "cache_wishlist.json"
        self.secure_settings_dir = Path(self.settings_path).parent
        self.avatar_cache_dir = self.secure_settings_dir / "cache_avatar"
        self.avatar_frame_cache_file = self.secure_settings_dir / "cache_avatar_frame.json"
        self.profile_cache_file = self.secure_settings_dir / "cache_profile.json"
        self.owned_api_key_file = self.secure_settings_dir / "owned_api_key.bin"
        self.owned_api_key_meta_file = self.secure_settings_dir / "owned_api_key.meta.json"
        self.secure_settings_dir.mkdir(parents=True, exist_ok=True)
        self.avatar_cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)

    def _initialize_minimal_state(self):
        self.context_menu_cache = {}
        self.startup_initialized = False
        self.runtime_initialized = False
        self.background_tasks_started = False
        self.loginusers_cache_path = None
        self.loginusers_cache_mtime = 0
        self.loginusers_cache_data = None
        self.library_folders_cache_path = None
        self.library_folders_cache_mtime = 0
        self.library_paths_cache = None
        self.appmanifest_cache = {}
        self.steam_path = None
        self.active_steam_user_id_snapshot = None
        self.country_code = "us"
        self.localconfig_path = None
        self.hidden_collections_path = None
        self.stats_cache_path = None
        self.localconfig_mtime = 0
        self.hidden_games_mtime = 0
        self.steam_icon_cache = None
        self.wishlist_cache_loaded = False
        self.wishlist_items = []
        self.wishlist_last_attempt = 0
        self.wishlist_last_sync = 0
        self.wishlist_steamid64 = None
        self.pending_wishlist_refresh = False

    def _initialize_runtime_state(self):
        if self.runtime_initialized:
            return
        self.http_pool = urllib3.PoolManager(maxsize=8, retries=False, ca_certs=_CA_CERTS_PATH)
        self.installed_games = {}
        self.installed_game_paths = {}
        self.installed_game_statuses = {}
        self.playtime_minutes = {}
        self.last_played_timestamps = {}
        self.achievement_progress = {}
        self.achievement_progress_signatures = {}
        self.last_update = 0
        self.installed_games_update_in_progress = False
        self.last_cache_cleanup = 0
        self.last_metric_cache_save = 0
        self.metric_cache_dirty = False
        self.search_cache = {}
        self.player_count_cache = {}
        self.review_score_cache = {}
        self.achievement_schema_cache = {}
        self.achievement_progress_cache = {}
        self.app_details_cache = {}
        self.context_menu_cache = {}
        self.owned_api_key_loaded = False
        self.owned_api_key_value = None
        self.owned_api_key_bound_steamid64 = None
        self.owned_api_key_persona_name = None
        self.owned_api_key_account_name = None
        self.owned_api_key_last4 = None
        self.owned_games_cache_loaded = False
        self.owned_games_last_attempt = 0
        self.owned_games_last_sync = 0
        self.owned_games_public_profile = None
        self.owned_games_steamid64 = None
        self.owned_app_ids = set()
        self.owned_game_playtimes = {}
        self.pending_owned_games_refresh = False
        self.active_profile_summary = {}
        self.active_profile_summary_loaded = False
        self.pending_profile_summary_refresh = False
        self.hidden_app_ids = set()
        self.hidden_games_cache_loaded = False
        self.pending_player_count_refresh = set()
        self.pending_review_score_refresh = set()
        self.pending_app_details_refresh = set()
        self.load_metric_caches()
        self.load_owned_api_key_metadata()
        self.load_owned_games_cache()
        self.load_wishlist_cache()
        self.runtime_initialized = True

    def _initialize_steam_state(self):
        self.steam_path = self.get_steam_path()
        self.country_code = self.load_cached_country_code() if self.should_show_prices() else "us"
        self.localconfig_path = self.get_localconfig_path()
        self.hidden_collections_path = self.get_hidden_collections_path()
        self.stats_cache_path = (self.steam_path / "appcache" / "stats") if self.steam_path else None
        self.localconfig_mtime = 0
        self.hidden_games_mtime = 0
        self.update_installed_games()
        self.steam_icon_cache = (self.steam_path / "appcache" / "librarycache") if self.steam_path else None

    def _start_background_tasks(self):
        threading.Thread(target=self._prewarm_connections, daemon=True).start()
        threading.Thread(target=self.cleanup_image_cache, daemon=True).start()
        self.schedule_owned_games_refresh()
        self.schedule_active_profile_summary_refresh()

    def ensure_startup_initialized(self):
        with self.state_lock:
            if self.startup_initialized:
                return
            self._initialize_runtime_state()
            self.configure_logger()
            self._initialize_steam_state()
            self.startup_initialized = True
            if not self.background_tasks_started:
                self._start_background_tasks()
                self.background_tasks_started = True
