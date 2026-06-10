import os
import subprocess
import sys
import webbrowser
from pathlib import Path

try:
    import winreg
except ImportError:
    try:
        import _winreg as winreg
    except ImportError:
        winreg = None


STEAM_GAMES_URI = "steam://nav/games"
STEAM_SETTINGS_URI = "steam://open/settings"
STEAM_FRIENDS_URI = "steam://open/friends"
STEAM_STORE_SPECIALS_URL = "https://store.steampowered.com/search/?os=win&specials=1&ndl=1"
STEAM_STORE_TOP_SELLERS_URL = "https://store.steampowered.com/search/?filter=topsellers&os=win"
STEAM_FRIENDS_STATUS_URIS = {
    "online": "steam://friends/status/online",
    "offline": "steam://friends/status/offline",
    "invisible": "steam://friends/status/invisible",
}
STEAM_INSTALL_REGISTRY_PATHS = (
    (lambda registry: registry.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
    (lambda registry: registry.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    (lambda registry: registry.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
)


def open_uri(uri, startfile=None):
    (startfile or os.startfile)(str(uri))


def open_web_url(url, browser_open=None):
    return (browser_open or webbrowser.open)(str(url))


def open_uri_with_web_fallback(uri, fallback_url, startfile=None, browser_open=None):
    try:
        open_uri(uri, startfile=startfile)
        return "uri"
    except Exception:
        open_web_url(fallback_url, browser_open=browser_open)
        return "web"


def run_shell_start_uri(uri, runner=subprocess.run):
    return runner(["start", str(uri)], shell=True)


def run_executable(executable_path, runner=subprocess.run):
    return runner([str(executable_path)])


def build_steam_store_uri(app_id):
    return f"steam://store/{app_id}"


def build_steam_store_url(app_id):
    return f"https://store.steampowered.com/app/{app_id}/"


def build_steam_openurl_uri(url):
    return f"steam://openurl/{url}"


def build_steam_guides_uri(app_id):
    return build_steam_openurl_uri(f"https://steamcommunity.com/app/{app_id}/guides/")


def build_steam_discussions_uri(app_id):
    return build_steam_openurl_uri(f"https://steamcommunity.com/app/{app_id}/discussions/")


def build_steam_refund_uri(app_id):
    return build_steam_openurl_uri(
        f"https://help.steampowered.com/en/wizard/HelpWithGameIssue/?appid={app_id}&issueid=108"
    )


def build_steam_wishlist_uri():
    return build_steam_openurl_uri("https://steamcommunity.com/my/wishlist/")


def build_steam_wishlist_url():
    return "https://steamcommunity.com/my/wishlist/"


def build_steam_store_specials_uri():
    return build_steam_openurl_uri(STEAM_STORE_SPECIALS_URL)


def build_steam_store_top_sellers_uri():
    return build_steam_openurl_uri(STEAM_STORE_TOP_SELLERS_URL)


def build_steam_library_details_uri(app_id):
    return f"steam://nav/games/details/{app_id}"


def build_steam_game_properties_uri(app_id):
    return f"steam://gameproperties/{app_id}"


def build_steam_screenshots_uri(app_id):
    return f"steam://open/screenshots/{app_id}"


def build_steam_install_uri(app_id):
    return f"steam://install/{app_id}"


def build_steam_uninstall_uri(app_id):
    return f"steam://uninstall/{app_id}"


def build_steam_run_game_uri(app_id):
    return f"steam://launch/{app_id}/dialog"


def resolve_steam_install_path_from_registry(registry=winreg):
    if registry is None:
        return None

    for hkey_getter, path in STEAM_INSTALL_REGISTRY_PATHS:
        try:
            with registry.OpenKey(hkey_getter(registry), path) as key:
                steam_path, _ = registry.QueryValueEx(key, "InstallPath")
            steam_path = Path(steam_path)
            if steam_path.exists():
                return steam_path
        except Exception:
            continue
    return None


def build_hidden_process_kwargs(platform=sys.platform, subprocess_module=subprocess):
    startupinfo = None
    creationflags = 0
    if platform == "win32":
        startupinfo = subprocess_module.STARTUPINFO()
        startupinfo.dwFlags |= subprocess_module.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess_module.SW_HIDE
        creationflags = (
            subprocess_module.CREATE_NO_WINDOW
            | subprocess_module.DETACHED_PROCESS
            | getattr(subprocess_module, "CREATE_NEW_PROCESS_GROUP", 0)
        )
    return startupinfo, creationflags


def build_hidden_run_kwargs(platform=sys.platform, subprocess_module=subprocess):
    if platform != "win32":
        return {}
    return {
        "creationflags": getattr(subprocess_module, "CREATE_NO_WINDOW", 0),
    }


def start_hidden_process(
    command,
    *,
    cwd=None,
    stdout=None,
    stderr=None,
    popen=None,
    platform=sys.platform,
    subprocess_module=subprocess,
):
    startupinfo, creationflags = build_hidden_process_kwargs(
        platform=platform,
        subprocess_module=subprocess_module,
    )
    popen = popen or subprocess_module.Popen
    kwargs = {
        "startupinfo": startupinfo,
        "creationflags": creationflags,
        "start_new_session": True,
        "stdout": stdout if stdout is not None else subprocess_module.DEVNULL,
        "stderr": stderr if stderr is not None else subprocess_module.DEVNULL,
        "stdin": subprocess_module.DEVNULL,
    }
    if cwd is not None:
        kwargs["cwd"] = str(cwd)
    return popen(list(command), **kwargs)
