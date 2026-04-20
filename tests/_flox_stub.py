import sys
from types import ModuleType


def install_flox_stub(include_clipboard=False):
    sys.modules.pop("flox", None)
    sys.modules.pop("flox.clipboard", None)

    flox_module = ModuleType("flox")
    flox_module.Flox = type("Flox", (), {})
    sys.modules["flox"] = flox_module

    if include_clipboard:
        flox_clipboard_module = ModuleType("flox.clipboard")
        flox_clipboard_module.get = lambda: ""
        sys.modules["flox.clipboard"] = flox_clipboard_module
