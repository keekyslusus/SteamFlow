import sys
import json
from pathlib import Path

plugindir = Path(__file__).parent.resolve()
if str(plugindir) not in sys.path:
    sys.path.insert(0, str(plugindir))
lib_path = plugindir / "lib"
if str(lib_path) not in sys.path:
    sys.path.insert(0, str(lib_path))


LIGHTWEIGHT_METHODS = {
    "context_menu",
    "open_steam_refund_page",
    "open_steam",
    "open_steam_discussions_page",
    "open_steam_friends",
    "open_steam_guides_page",
    "open_steam_library_game_details",
    "open_my_steam_wishlist",
    "open_steam_settings",
    "install_steam_game",
    "uninstall_steam_game",
    "open_local_files",
    "open_steam_game_properties_page",
    "open_steam_screenshots_page",
    "open_steam_store_page",
    "open_steamdb_page",
}


def get_request_method():
    if len(sys.argv) <= 1:
        return ""
    try:
        request = json.loads(sys.argv[1])
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    return str(request.get("method", ""))


def get_plugin_class():
    request_method = get_request_method()
    if request_method in LIGHTWEIGHT_METHODS:
        from steamflow.contextmenu import SteamContextMenuPlugin

        return SteamContextMenuPlugin

    from steamflow import SteamPlugin

    return SteamPlugin


if __name__ == "__main__":
    plugin = get_plugin_class()()
    run = getattr(plugin, "run", None)
    if callable(run):
        run()
