import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))
if "vdf" not in sys.modules:
    sys.modules["vdf"] = SimpleNamespace(load=lambda *_args, **_kwargs: {}, dump=lambda *_args, **_kwargs: None)

import steam_switch_worker


class SteamSwitchWorkerLaunchTests(unittest.TestCase):
    def test_launch_steam_client_prefers_games_uri(self):
        with patch.object(steam_switch_worker.os, "startfile", return_value=None) as mocked_startfile, patch.object(
            steam_switch_worker.subprocess, "Popen"
        ) as mocked_popen:
            steam_switch_worker.launch_steam_client(Path("C:/Steam"))

        mocked_startfile.assert_called_once_with(steam_switch_worker.STEAM_GAMES_URI)
        mocked_popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
