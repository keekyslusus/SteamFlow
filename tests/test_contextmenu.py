import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from tests._flox_stub import install_flox_stub

install_flox_stub()

from steamflow.contextmenu import SteamContextMenuPlugin


class ContextMenuHarness(SteamContextMenuPlugin):
    def __init__(self, plugin_dir):
        self.plugin_dir = Path(plugin_dir)
        self._steam_path = None
        self.default_icon = "default"
        self.community_icon = "community"
        self.download_icon = "download"
        self.discussions_icon = "discussions"
        self.guides_icon = "guides"
        self.location_icon = "location"
        self.properties_icon = "properties"
        self.refund_icon = "refund"
        self.screenshot_icon = "screenshot"
        self.settings_icon = "settings"
        self.steamdb_icon = "steamdb"
        self.fetch_calls = []

    def fetch_app_details_metadata(self, app_id):
        self.fetch_calls.append(str(app_id))
        return {"type": "game", "is_free": False}


class ContextMenuRefundTests(unittest.TestCase):
    def test_existing_refund_state_short_circuits_everything(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {"app_id": "1451940", "install_path": "C:/Games/Needy", "refund_state": "likely"}
            )

            self.assertEqual(refund_state, "likely")
            self.assertEqual(plugin.fetch_calls, [])

    def test_store_result_never_fetches_refund_metadata(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state({"app_id": "1451940", "playtime_minutes": 54})

            self.assertEqual(refund_state, "")
            self.assertEqual(plugin.fetch_calls, [])

    def test_games_over_two_hours_never_fetch_refund_metadata(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {"app_id": "1451940", "install_path": "C:/Games/Needy", "playtime_minutes": 200}
            )

            self.assertEqual(refund_state, "")
            self.assertEqual(plugin.fetch_calls, [])

    def test_missing_current_account_data_blocks_refund_derivation(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {
                    "app_id": "1451940",
                    "install_path": "C:/Games/Needy",
                    "playtime_minutes": 54,
                    "has_current_account_local_data": False,
                }
            )

            self.assertEqual(refund_state, "")
            self.assertEqual(plugin.fetch_calls, [])

    def test_local_game_uses_cached_app_details_without_network(self):
        with TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "cache_metric.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "app_details_cache": {
                            "1451940": {
                                "timestamp": 1,
                                "success": True,
                                "metadata": {"type": "game", "is_free": False},
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {"app_id": "1451940", "install_path": "C:/Games/Needy", "playtime_minutes": 54}
            )

            self.assertEqual(refund_state, "likely")
            self.assertEqual(plugin.fetch_calls, [])

    def test_local_game_fetches_and_persists_app_details_on_cache_miss(self):
        with TemporaryDirectory() as temp_dir:
            plugin = ContextMenuHarness(temp_dir)

            refund_state = plugin.derive_refund_state(
                {"app_id": "1451940", "install_path": "C:/Games/Needy", "playtime_minutes": 54}
            )

            self.assertEqual(refund_state, "likely")
            self.assertEqual(plugin.fetch_calls, ["1451940"])
            cache_data = json.loads((Path(temp_dir) / "cache_metric.json").read_text(encoding="utf-8"))
            self.assertTrue(cache_data["app_details_cache"]["1451940"]["success"])


if __name__ == "__main__":
    unittest.main()
