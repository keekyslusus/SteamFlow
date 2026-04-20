__all__ = ["SteamPlugin"]


def __getattr__(name):
    if name == "SteamPlugin":
        from .plugin import SteamPlugin

        return SteamPlugin
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
