import sys
from types import ModuleType


def install_pyflowlauncher_stub():
    sys.modules.pop("pyflowlauncher", None)
    sys.modules.pop("pyflowlauncher.api", None)

    pyflowlauncher_module = ModuleType("pyflowlauncher")
    api_module = ModuleType("pyflowlauncher.api")
    api_module.change_query = lambda query, requery=False: {
        "Method": "Flow.Launcher.ChangeQuery",
        "Parameters": [query, requery],
    }
    api_module.show_msg = lambda title, subtitle, icon="": {
        "Method": "Flow.Launcher.ShowMsg",
        "Parameters": [title, subtitle, icon],
    }

    class Plugin:
        def __init__(self):
            self._client = type("Client", (), {"recieve": lambda self: {}})()

    pyflowlauncher_module.Plugin = Plugin
    pyflowlauncher_module.api = api_module
    sys.modules["pyflowlauncher"] = pyflowlauncher_module
    sys.modules["pyflowlauncher.api"] = api_module
