from dataclasses import dataclass, field
from types import MappingProxyType


@dataclass(frozen=True)
class SteamFlowIconConfig:
    default_icon: str = "icons/steam.png"
    browser_icon: str = "icons/browser.png"
    buy_icon: str = "icons/buy.png"
    clipboard_icon: str = "icons/clipboard.png"
    community_icon: str = "icons/community.png"
    csrin_icon: str = "icons/csrin.png"
    deals_icon: str = "icons/deals.png"
    download_icon: str = "icons/download.png"
    feature_health_reset_icon: str = "icons/feature_health_reset.png"
    discussions_icon: str = "icons/discussions.png"
    guides_icon: str = "icons/guides.png"
    location_icon: str = "icons/location.png"
    owned_icon: str = "icons/owned.png"
    online_icon: str = "icons/online.png"
    offline_icon: str = "icons/offline.png"
    invisible_icon: str = "icons/invisible.png"
    properties_icon: str = "icons/properties.png"
    refund_icon: str = "icons/refund.png"
    screenshot_icon: str = "icons/screenshot.png"
    settings_icon: str = "icons/settings.png"
    steamdb_icon: str = "icons/steamdb.png"
    top_sellers_icon: str = "icons/top_sellers.png"
    trash_icon: str = "icons/trash.png"
    warning_icon: str = "icons/warning.png"
    wishlist_icon: str = "icons/wishlist.png"
    wishlist_add_icon: str = "icons/wl_add.png"
    wishlist_remove_icon: str = "icons/wl_remove.png"


@dataclass(frozen=True)
class SteamFlowQueryConfig:
    max_results: int = 5
    max_store_collection_results: int = 10
    max_empty_query_results: int = 67
    max_wishlist_results: int = 15
    store_cold_metric_fetch_limit: int = 5
    wishlist_cold_detail_fetch_limit: int = 8


@dataclass(frozen=True)
class SteamFlowCacheConfig:
    owned_games_retry_delay_seconds: int = 10 * 60
    owned_games_cache_ttl_seconds: int = 24 * 60 * 60
    search_ttl_seconds: int = 30
    store_specials_ttl_seconds: int = 20 * 60
    store_top_sellers_ttl_seconds: int = 45 * 60
    store_collection_stale_ttl_seconds: int = 24 * 60 * 60
    store_collection_failure_ttl_seconds: int = 5 * 60
    store_user_preferences_ttl_seconds: int = 60 * 60
    player_count_ttl_seconds: int = 4 * 60
    review_score_ttl_seconds: int = 4 * 60 * 60
    achievement_progress_ttl_seconds: int = 12 * 60 * 60
    achievement_schema_ttl_seconds: int = 30 * 24 * 60 * 60
    app_details_ttl_seconds: int = 30 * 24 * 60 * 60
    app_details_failure_ttl_seconds: int = 6 * 60 * 60
    wishlist_ttl_seconds: int = 15 * 60
    cleanup_interval_seconds: int = 5 * 60
    metric_cache_save_interval_seconds: int = 10
    profile_summary_ttl_seconds: int = 30


@dataclass(frozen=True)
class SteamFlowPerformanceConfig:
    max_log_size_bytes: int = 10 * 1024
    query_log_threshold_ms: int = 250
    stage_log_threshold_ms: int = 100


@dataclass(frozen=True)
class SteamFlowDownloadConfig:
    status_updating: str = "Updating"
    status_update_paused: str = "Update Paused"
    status_update_queued: str = "Update Queued"
    status_update_required: str = "Update Required"
    state_flag_update_required: int = 2
    state_flag_fully_installed: int = 4
    state_flag_update_running: int = 256
    state_flag_update_paused: int = 512
    state_flag_update_started: int = 1024
    progress_stall_seconds: int = 6
    status_hint_seconds: int = 30


@dataclass(frozen=True)
class SteamFlowAvailabilityReasons:
    api_not_configured: str = "api_not_configured"
    api_bound_to_another_account: str = "api_bound_to_another_account"
    no_active_account: str = "no_active_account"


@dataclass(frozen=True)
class SteamFlowConfig:
    icons: SteamFlowIconConfig = field(default_factory=SteamFlowIconConfig)
    query: SteamFlowQueryConfig = field(default_factory=SteamFlowQueryConfig)
    cache: SteamFlowCacheConfig = field(default_factory=SteamFlowCacheConfig)
    performance: SteamFlowPerformanceConfig = field(default_factory=SteamFlowPerformanceConfig)
    download: SteamFlowDownloadConfig = field(default_factory=SteamFlowDownloadConfig)
    availability_reasons: SteamFlowAvailabilityReasons = field(default_factory=SteamFlowAvailabilityReasons)
    default_blacklisted_app_ids: frozenset = field(default_factory=lambda: frozenset({"228980"}))
    review_score_excluded_name_patterns: tuple = field(
        default_factory=lambda: (
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
    )
    platform_labels: MappingProxyType = field(
        default_factory=lambda: MappingProxyType(
            {
                "windows": "Win",
                "mac": "Mac",
                "linux": "Linux",
            }
        )
    )


STEAMFLOW_CONFIG = SteamFlowConfig()
