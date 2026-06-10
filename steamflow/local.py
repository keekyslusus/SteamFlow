import time
import vdf

from .local_library import SteamPluginLocalLibraryMixin
from .local_presence import SteamPluginLocalPresenceMixin
from .local_stats import SteamPluginLocalStatsMixin


class SteamPluginLocalMixin(
    SteamPluginLocalStatsMixin,
    SteamPluginLocalLibraryMixin,
    SteamPluginLocalPresenceMixin,
):
    REQUIRED_PLUGIN_ATTRS = (
        "state_lock",
        "steam_path",
    )
    REQUIRED_PLUGIN_METHODS = (
        "log_exception",
    )
