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

import urllib3

from .actions import SteamPluginActionsMixin
from .app_details import APP_DETAILS_CACHE_DIR_NAME
from .accounts import SteamPluginAccountsMixin
from .cart import SteamPluginCartMixin
from .constants import STEAMFLOW_CONFIG
from .core import SteamPluginCoreMixin
from .download_control import SteamPluginDownloadControlMixin
from .feature_health import SteamPluginFeatureHealthMixin
from .local import SteamPluginLocalMixin
from .mixin_contracts import validate_declared_mixin_contracts
from .profile import SteamPluginProfileMixin
from .providers import SteamPluginProviders
from .pyflow_compat import SteamFlowPluginBase
from .state import (
    STATE_ATTR_GROUPS,
    SteamPluginLifecycleState,
    SteamPluginLocalState,
    SteamPluginPathState,
    SteamPluginRuntimeState,
    build_state_attr_property,
)
from .storage import SteamPluginStorageMixin
from .store import SteamPluginStoreMixin
from .store_metrics import SteamPluginStoreMetricsMixin
from .tasks import BackgroundTaskManager
from .ui_commands import SteamPluginUICommandsMixin
from .ui import SteamPluginUIMixin
from .ui_query import SteamPluginUIQueryMixin
from .wishlist import SteamPluginWishlistMixin

try:
    import certifi

    _CA_CERTS_PATH = certifi.where()
except ImportError:
    _CA_CERTS_PATH = None


class SteamPluginRuntimeMixin(
    SteamPluginStoreMixin,
    SteamPluginStoreMetricsMixin,
    SteamPluginProfileMixin,
    SteamPluginAccountsMixin,
    SteamPluginDownloadControlMixin,
    SteamPluginCartMixin,
    SteamPluginFeatureHealthMixin,
    SteamPluginLocalMixin,
    SteamPluginStorageMixin,
    SteamPluginCoreMixin,
    SteamPluginActionsMixin,
):
    """Core Steam data, cache, network, and OS-integration behaviors."""


class SteamPluginExperienceMixin(
    SteamPluginUIQueryMixin,
    SteamPluginWishlistMixin,
    SteamPluginUICommandsMixin,
    SteamPluginUIMixin,
    SteamPluginRuntimeMixin,
):
    """User-facing query and UI behaviors layered on top of runtime services."""


class SteamPlugin(
    SteamPluginExperienceMixin,
    SteamFlowPluginBase,
):
    CONFIG = STEAMFLOW_CONFIG
    urllib3 = urllib3

    def __init__(self):
        super().__init__()
        object.__setattr__(self, "path_state", SteamPluginPathState())
        object.__setattr__(self, "lifecycle_state", SteamPluginLifecycleState())
        object.__setattr__(self, "local_state", SteamPluginLocalState())
        object.__setattr__(self, "runtime_state", SteamPluginRuntimeState())
        self.plugin_dir = PACKAGE_ROOT
        self.background_task_manager = BackgroundTaskManager()
        self.providers = SteamPluginProviders(self)
        self._initialize_paths()
        self._initialize_minimal_state()
        self._validate_mixin_contracts()

    @cached_property
    def logfile(self):
        return str(self.plugin_dir / "plugin_steamflow.log")

    def _initialize_paths(self):
        self.state_lock = threading.RLock()
        self.DEFAULT_ICON = str(self.plugin_dir / self.CONFIG.icons.default_icon)
        self.BROWSER_ICON = str(self.plugin_dir / self.CONFIG.icons.browser_icon)
        self.BUY_ICON = str(self.plugin_dir / self.CONFIG.icons.buy_icon)
        self.CLIPBOARD_ICON = str(self.plugin_dir / self.CONFIG.icons.clipboard_icon)
        self.COMMUNITY_ICON = str(self.plugin_dir / self.CONFIG.icons.community_icon)
        self.CSRIN_ICON = str(self.plugin_dir / self.CONFIG.icons.csrin_icon)
        self.DEALS_ICON = str(self.plugin_dir / self.CONFIG.icons.deals_icon)
        self.DOWNLOAD_ICON = str(self.plugin_dir / self.CONFIG.icons.download_icon)
        self.FEATURE_HEALTH_RESET_ICON = str(self.plugin_dir / self.CONFIG.icons.feature_health_reset_icon)
        self.DISCUSSIONS_ICON = str(self.plugin_dir / self.CONFIG.icons.discussions_icon)
        self.GUIDES_ICON = str(self.plugin_dir / self.CONFIG.icons.guides_icon)
        self.LOCATION_ICON = str(self.plugin_dir / self.CONFIG.icons.location_icon)
        self.OWNED_ICON = str(self.plugin_dir / self.CONFIG.icons.owned_icon)
        self.ONLINE_ICON = str(self.plugin_dir / self.CONFIG.icons.online_icon)
        self.OFFLINE_ICON = str(self.plugin_dir / self.CONFIG.icons.offline_icon)
        self.INVISIBLE_ICON = str(self.plugin_dir / self.CONFIG.icons.invisible_icon)
        self.PROPERTIES_ICON = str(self.plugin_dir / self.CONFIG.icons.properties_icon)
        self.REFUND_ICON = str(self.plugin_dir / self.CONFIG.icons.refund_icon)
        self.SCREENSHOT_ICON = str(self.plugin_dir / self.CONFIG.icons.screenshot_icon)
        self.SETTINGS_ICON = str(self.plugin_dir / self.CONFIG.icons.settings_icon)
        self.STEAMDB_ICON = str(self.plugin_dir / self.CONFIG.icons.steamdb_icon)
        self.TOP_SELLERS_ICON = str(self.plugin_dir / self.CONFIG.icons.top_sellers_icon)
        self.TRASH_ICON = str(self.plugin_dir / self.CONFIG.icons.trash_icon)
        self.WARNING_ICON = str(self.plugin_dir / self.CONFIG.icons.warning_icon)
        self.WISHLIST_ICON = str(self.plugin_dir / self.CONFIG.icons.wishlist_icon)
        self.WISHLIST_ADD_ICON = str(self.plugin_dir / self.CONFIG.icons.wishlist_add_icon)
        self.WISHLIST_REMOVE_ICON = str(self.plugin_dir / self.CONFIG.icons.wishlist_remove_icon)
        self.cache_dir = self.plugin_dir / "cache_img"
        self.country_cache_file = self.plugin_dir / "cache_country.json"
        self.download_progress_cache_file = self.plugin_dir / "cache_download_progress.json"
        self.feature_health_cache_file = self.plugin_dir / "cache_feature_health.json"
        self.app_details_cache_dir = self.plugin_dir / APP_DETAILS_CACHE_DIR_NAME
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
        object.__setattr__(self, "lifecycle_state", SteamPluginLifecycleState())
        object.__setattr__(self, "local_state", SteamPluginLocalState())
        object.__setattr__(self, "runtime_state", SteamPluginRuntimeState())

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
        self.store_collection_cache = {}
        self.store_user_preferences_cache = {}
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
        self.cleanup_app_details_cache_files()
        self.load_owned_api_key_metadata()
        self.load_owned_games_cache()
        self.load_wishlist_cache()
        self.runtime_initialized = True

    def _initialize_steam_state(self):
        self.steam_path = self.get_steam_path()
        self.country_code = self.load_cached_country_code() if self.providers.settings.should_show_prices() else "us"
        self.localconfig_path = self.get_localconfig_path()
        self.hidden_collections_path = self.get_hidden_collections_path()
        self.stats_cache_path = (self.steam_path / "appcache" / "stats") if self.steam_path else None
        self.localconfig_mtime = 0
        self.hidden_games_mtime = 0
        self.providers.runtime.update_installed_games()
        self.steam_icon_cache = (self.steam_path / "appcache" / "librarycache") if self.steam_path else None

    def _start_background_tasks(self):
        self.start_daemon_task(self._prewarm_connections)
        self.start_daemon_task(self.cleanup_image_cache)
        self.schedule_owned_games_refresh()
        self.schedule_active_profile_summary_refresh()

    def _validate_mixin_contracts(self):
        validate_declared_mixin_contracts(self)

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


def _attach_state_properties():
    for group_name, attr_names in STATE_ATTR_GROUPS.items():
        for attr_name in attr_names:
            setattr(SteamPlugin, attr_name, build_state_attr_property(group_name, attr_name))


_attach_state_properties()
