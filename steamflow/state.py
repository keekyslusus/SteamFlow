from dataclasses import dataclass, field


@dataclass
class SteamPluginPathState:
    cache_dir: object = None
    country_cache_file: object = None
    download_progress_cache_file: object = None
    feature_health_cache_file: object = None
    app_details_cache_dir: object = None
    metric_cache_file: object = None
    wishlist_worker_lock_file: object = None
    owned_games_cache_file: object = None
    wishlist_cache_file: object = None
    secure_settings_dir: object = None
    avatar_cache_dir: object = None
    avatar_frame_cache_file: object = None
    profile_cache_file: object = None
    owned_api_key_file: object = None
    owned_api_key_meta_file: object = None


@dataclass
class SteamPluginLifecycleState:
    startup_initialized: bool = False
    runtime_initialized: bool = False
    background_tasks_started: bool = False


@dataclass
class SteamPluginLocalState:
    loginusers_cache_path: object = None
    loginusers_cache_mtime: float = 0
    loginusers_cache_data: object = None
    library_folders_cache_path: object = None
    library_folders_cache_mtime: float = 0
    library_paths_cache: object = None
    appmanifest_cache: dict = field(default_factory=dict)
    app_download_progress_cache: dict = field(default_factory=dict)
    app_download_progress_cache_loaded: bool = False
    steam_path: object = None
    active_steam_user_id_snapshot: object = None
    country_code: str = "us"
    localconfig_path: object = None
    hidden_collections_path: object = None
    stats_cache_path: object = None
    localconfig_mtime: float = 0
    hidden_games_mtime: float = 0
    steam_icon_cache: object = None
    hidden_app_ids: set = field(default_factory=set)
    hidden_games_cache_loaded: bool = False
    localconfig_data_cache_path: object = None
    localconfig_data_cache_mtime: float = 0
    localconfig_data_cache: object = None
    localconfig_text_cache_path: object = None
    localconfig_text_cache_mtime: float = 0
    localconfig_text_cache: str = ""
    installed_games: dict = field(default_factory=dict)
    installed_game_paths: dict = field(default_factory=dict)
    installed_game_statuses: dict = field(default_factory=dict)
    playtime_minutes: dict = field(default_factory=dict)
    last_played_timestamps: dict = field(default_factory=dict)
    achievement_progress: dict = field(default_factory=dict)
    achievement_progress_signatures: dict = field(default_factory=dict)
    last_update: float = 0
    installed_games_update_in_progress: bool = False


@dataclass
class SteamPluginRuntimeState:
    http_pool: object = None
    last_cache_cleanup: float = 0
    last_metric_cache_save: float = 0
    metric_cache_dirty: bool = False
    search_cache: dict = field(default_factory=dict)
    store_collection_cache: dict = field(default_factory=dict)
    store_user_preferences_cache: dict = field(default_factory=dict)
    player_count_cache: dict = field(default_factory=dict)
    review_score_cache: dict = field(default_factory=dict)
    achievement_schema_cache: dict = field(default_factory=dict)
    achievement_progress_cache: dict = field(default_factory=dict)
    app_details_cache: dict = field(default_factory=dict)
    context_menu_cache: dict = field(default_factory=dict)
    owned_api_key_loaded: bool = False
    owned_api_key_value: object = None
    owned_api_key_bound_steamid64: object = None
    owned_api_key_persona_name: object = None
    owned_api_key_account_name: object = None
    owned_api_key_last4: object = None
    owned_games_cache_loaded: bool = False
    owned_games_last_attempt: float = 0
    owned_games_last_sync: float = 0
    owned_games_public_profile: object = None
    owned_games_steamid64: object = None
    owned_app_ids: set = field(default_factory=set)
    owned_game_playtimes: dict = field(default_factory=dict)
    pending_owned_games_refresh: bool = False
    active_profile_summary: dict = field(default_factory=dict)
    active_profile_summary_loaded: bool = False
    pending_profile_summary_refresh: bool = False
    pending_player_count_refresh: set = field(default_factory=set)
    pending_review_score_refresh: set = field(default_factory=set)
    pending_app_details_refresh: set = field(default_factory=set)
    wishlist_cache_loaded: bool = False
    wishlist_items: list = field(default_factory=list)
    wishlist_last_attempt: float = 0
    wishlist_last_sync: float = 0
    wishlist_steamid64: object = None
    pending_wishlist_refresh: bool = False


STATE_ATTR_GROUPS = {
    "path_state": (
        "cache_dir",
        "country_cache_file",
        "download_progress_cache_file",
        "feature_health_cache_file",
        "app_details_cache_dir",
        "metric_cache_file",
        "wishlist_worker_lock_file",
        "owned_games_cache_file",
        "wishlist_cache_file",
        "secure_settings_dir",
        "avatar_cache_dir",
        "avatar_frame_cache_file",
        "profile_cache_file",
        "owned_api_key_file",
        "owned_api_key_meta_file",
    ),
    "lifecycle_state": (
        "startup_initialized",
        "runtime_initialized",
        "background_tasks_started",
    ),
    "local_state": (
        "loginusers_cache_path",
        "loginusers_cache_mtime",
        "loginusers_cache_data",
        "library_folders_cache_path",
        "library_folders_cache_mtime",
        "library_paths_cache",
        "appmanifest_cache",
        "app_download_progress_cache",
        "app_download_progress_cache_loaded",
        "steam_path",
        "active_steam_user_id_snapshot",
        "country_code",
        "localconfig_path",
        "hidden_collections_path",
        "stats_cache_path",
        "localconfig_mtime",
        "hidden_games_mtime",
        "steam_icon_cache",
        "hidden_app_ids",
        "hidden_games_cache_loaded",
        "localconfig_data_cache_path",
        "localconfig_data_cache_mtime",
        "localconfig_data_cache",
        "localconfig_text_cache_path",
        "localconfig_text_cache_mtime",
        "localconfig_text_cache",
        "installed_games",
        "installed_game_paths",
        "installed_game_statuses",
        "playtime_minutes",
        "last_played_timestamps",
        "achievement_progress",
        "achievement_progress_signatures",
        "last_update",
        "installed_games_update_in_progress",
    ),
    "runtime_state": (
        "http_pool",
        "last_cache_cleanup",
        "last_metric_cache_save",
        "metric_cache_dirty",
        "search_cache",
        "store_collection_cache",
        "store_user_preferences_cache",
        "player_count_cache",
        "review_score_cache",
        "achievement_schema_cache",
        "achievement_progress_cache",
        "app_details_cache",
        "context_menu_cache",
        "owned_api_key_loaded",
        "owned_api_key_value",
        "owned_api_key_bound_steamid64",
        "owned_api_key_persona_name",
        "owned_api_key_account_name",
        "owned_api_key_last4",
        "owned_games_cache_loaded",
        "owned_games_last_attempt",
        "owned_games_last_sync",
        "owned_games_public_profile",
        "owned_games_steamid64",
        "owned_app_ids",
        "owned_game_playtimes",
        "pending_owned_games_refresh",
        "active_profile_summary",
        "active_profile_summary_loaded",
        "pending_profile_summary_refresh",
        "pending_player_count_refresh",
        "pending_review_score_refresh",
        "pending_app_details_refresh",
        "wishlist_cache_loaded",
        "wishlist_items",
        "wishlist_last_attempt",
        "wishlist_last_sync",
        "wishlist_steamid64",
        "pending_wishlist_refresh",
    ),
}

STATE_ATTR_TO_GROUP = {
    attr_name: group_name
    for group_name, attr_names in STATE_ATTR_GROUPS.items()
    for attr_name in attr_names
}


def build_state_attr_property(group_name, attr_name):
    def getter(plugin):
        return getattr(getattr(plugin, group_name), attr_name)

    def setter(plugin, value):
        setattr(getattr(plugin, group_name), attr_name, value)

    return property(getter, setter)
