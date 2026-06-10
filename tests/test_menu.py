import sys
import threading
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.menu import get_game_context_menu_entries, get_refund_menu_copy
from steamflow.ui import SteamPluginUIMixin


ICON = "icon"


class UIContextMenuHarness(SteamPluginUIMixin):
    DEFAULT_ICON = ICON
    STEAMDB_ICON = ICON
    BUY_ICON = "buy"
    CSRIN_ICON = ICON
    GUIDES_ICON = ICON
    DISCUSSIONS_ICON = ICON
    SCREENSHOT_ICON = ICON
    REFUND_ICON = ICON
    PROPERTIES_ICON = ICON
    LOCATION_ICON = ICON
    DOWNLOAD_ICON = ICON
    TRASH_ICON = ICON
    WISHLIST_ADD_ICON = "wishlist-add"
    WISHLIST_REMOVE_ICON = "wishlist-remove"

    def __init__(self):
        self.state_lock = threading.RLock()
        self.context_menu_cache = {}
        self.settings = {}
        self.enabled_features = {
            "steam_cart": True,
            "steam_session_token": True,
            "steam_wishlist": True,
        }

    def build_action(self, method, *parameters):
        return {"method": method, "parameters": list(parameters)}

    def build_result(self, title, subtitle, icon_path=None, action=None, context_data=None, **extra_fields):
        result = {
            "Title": title,
            "SubTitle": subtitle,
            "IcoPath": icon_path,
            "action": action,
            "ContextData": context_data,
        }
        result.update(extra_fields)
        return result

    def build_context_data(self, **kwargs):
        return dict(kwargs)

    def feature_enabled(self, name):
        return self.enabled_features.get(str(name), True)

    def should_show_steamdb_context_menu(self):
        return self.settings.get("show_steamdb_context_menu", True)

    def should_show_csrin_context_menu(self):
        return self.settings.get("show_csrin_context_menu", True)


class MenuTests(unittest.TestCase):
    def test_refund_menu_copy_uses_likely_wording(self):
        title, subtitle = get_refund_menu_copy("likely", "NEEDY GIRL OVERDOSE")

        self.assertEqual(title, "Support: Open Refund Page")
        self.assertIn("Likely eligible", subtitle)
        self.assertIn("NEEDY GIRL OVERDOSE", subtitle)

    def test_refund_menu_copy_uses_unclear_wording(self):
        title, subtitle = get_refund_menu_copy("unclear", "NEEDY GIRL OVERDOSE")

        self.assertEqual(title, "Support: Check Refund Options")
        self.assertIn("Eligibility unclear", subtitle)

    def test_game_context_menu_includes_refund_only_for_local_games_with_refund_state(self):
        entries = get_game_context_menu_entries(
            app_id="1451940",
            name="NEEDY GIRL OVERDOSE",
            install_path="C:/Games/Needy",
            is_owned=False,
            refund_state="likely",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
        )

        titles = [entry["title"] for entry in entries]
        self.assertIn("Support: Open Refund Page", titles)
        self.assertIn("Community: Search in CS.RIN", titles)
        self.assertIn("Files: Uninstall Game", titles)

        self.assertLess(
            titles.index("Store: Open in SteamDB"),
            titles.index("Community: Search in CS.RIN"),
        )

    def test_game_context_menu_hides_steamdb_when_setting_is_disabled(self):
        entries = get_game_context_menu_entries(
            app_id="1451940",
            name="NEEDY GIRL OVERDOSE",
            install_path="C:/Games/Needy",
            is_owned=False,
            refund_state="likely",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
            show_steamdb=False,
        )

        titles = [entry["title"] for entry in entries]
        self.assertNotIn("Store: Open in SteamDB", titles)
        self.assertIn("Community: Search in CS.RIN", titles)

    def test_game_context_menu_hides_csrin_when_setting_is_disabled(self):
        entries = get_game_context_menu_entries(
            app_id="1451940",
            name="NEEDY GIRL OVERDOSE",
            install_path="C:/Games/Needy",
            is_owned=False,
            refund_state="likely",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
            show_csrin=False,
        )

        titles = [entry["title"] for entry in entries]
        self.assertIn("Store: Open in SteamDB", titles)
        self.assertNotIn("Community: Search in CS.RIN", titles)

    def test_game_context_menu_hides_refund_for_store_results(self):
        entries = get_game_context_menu_entries(
            app_id="1451940",
            name="NEEDY GIRL OVERDOSE",
            install_path=None,
            is_owned=False,
            refund_state="likely",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
        )

        titles = [entry["title"] for entry in entries]
        self.assertNotIn("Support: Open Refund Page", titles)
        self.assertNotIn("Community: Search in CS.RIN", titles)
        self.assertNotIn("Files: Uninstall Game", titles)

    def test_game_context_menu_includes_install_for_owned_store_results(self):
        entries = get_game_context_menu_entries(
            app_id="570",
            name="Dota 2",
            install_path=None,
            is_owned=True,
            refund_state="",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
        )

        titles = [entry["title"] for entry in entries]
        self.assertIn("Library: Install Game", titles)
        self.assertNotIn("Files: Uninstall Game", titles)

    def test_game_context_menu_includes_add_to_cart_for_store_games_below_steamdb(self):
        entries = get_game_context_menu_entries(
            app_id="1462040",
            name="FINAL FANTASY VII REMAKE INTERGRADE",
            install_path=None,
            is_owned=False,
            refund_state="",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon="buy",
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
            can_add_to_cart=True,
            steamid64="76561198000000000",
        )

        titles = [entry["title"] for entry in entries]
        self.assertIn("Store: Add to Steam Cart", titles)
        self.assertLess(
            titles.index("Store: Open in SteamDB"),
            titles.index("Store: Add to Steam Cart"),
        )
        add_entry = next(entry for entry in entries if entry["title"] == "Store: Add to Steam Cart")
        self.assertEqual(add_entry["icon"], "buy")
        self.assertEqual(add_entry["method"], "add_to_steam_cart")
        self.assertEqual(add_entry["parameters"], ["1462040", "76561198000000000"])

    def test_game_context_menu_hides_add_to_cart_without_store_gate(self):
        entries = get_game_context_menu_entries(
            app_id="1462040",
            name="FINAL FANTASY VII REMAKE INTERGRADE",
            install_path=None,
            is_owned=False,
            refund_state="",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
            can_add_to_cart=False,
        )

        titles = [entry["title"] for entry in entries]
        self.assertNotIn("Store: Add to Steam Cart", titles)

    def test_game_context_menu_includes_add_to_wishlist_for_eligible_store_game(self):
        entries = get_game_context_menu_entries(
            app_id="1462040",
            name="FINAL FANTASY VII REMAKE INTERGRADE",
            install_path=None,
            is_owned=False,
            refund_state="",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
            wishlist_add_icon="wishlist-add",
            can_add_to_wishlist=True,
        )

        add_entry = next(entry for entry in entries if entry["title"] == "Store: Add to Wishlist")
        self.assertEqual(add_entry["icon"], "wishlist-add")
        self.assertEqual(add_entry["method"], "add_to_steam_wishlist")
        self.assertEqual(add_entry["parameters"], ["1462040"])

        entries = get_game_context_menu_entries(
            app_id="1462040",
            name="FINAL FANTASY VII REMAKE INTERGRADE",
            install_path=None,
            is_owned=False,
            refund_state="",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
            wishlist_add_icon="wishlist-add",
            can_add_to_wishlist=True,
            steamid64="76561198000000000",
        )

        add_entry = next(entry for entry in entries if entry["title"] == "Store: Add to Wishlist")
        self.assertEqual(add_entry["parameters"], ["1462040", "76561198000000000"])

    def test_game_context_menu_includes_remove_from_wishlist(self):
        entries = get_game_context_menu_entries(
            app_id="1462040",
            name="FINAL FANTASY VII REMAKE INTERGRADE",
            install_path=None,
            is_owned=False,
            refund_state="",
            default_icon=ICON,
            steamdb_icon=ICON,
            buy_icon=ICON,
            csrin_icon=ICON,
            guides_icon=ICON,
            discussions_icon=ICON,
            screenshot_icon=ICON,
            refund_icon=ICON,
            properties_icon=ICON,
            location_icon=ICON,
            download_icon=ICON,
            trash_icon=ICON,
            wishlist_add_icon="wishlist-add",
            wishlist_remove_icon="wishlist-remove",
            can_remove_from_wishlist=True,
        )

        titles = [entry["title"] for entry in entries]
        self.assertIn("Store: Remove from Wishlist", titles)
        self.assertNotIn("Store: Add to Wishlist", titles)
        remove_entry = next(entry for entry in entries if entry["title"] == "Store: Remove from Wishlist")
        self.assertEqual(remove_entry["icon"], "wishlist-remove")

    def test_ui_context_menu_cache_tracks_feature_health_state(self):
        harness = UIContextMenuHarness()
        kwargs = {
            "app_id": "1462040",
            "name": "FINAL FANTASY VII REMAKE INTERGRADE",
            "install_path": None,
            "is_owned": False,
            "refund_state": "",
            "result_source": "store",
            "store_type": "game",
            "is_free": False,
            "is_wishlisted": False,
            "coming_soon": False,
            "steamid64": "76561198000000000",
        }

        enabled_items = harness.get_context_menu_items(**kwargs)
        harness.enabled_features["steam_cart"] = False
        disabled_items = harness.get_context_menu_items(**kwargs)
        harness.enabled_features["steam_cart"] = True
        restored_items = harness.get_context_menu_items(**kwargs)

        enabled_titles = [item["Title"] for item in enabled_items]
        disabled_titles = [item["Title"] for item in disabled_items]
        restored_titles = [item["Title"] for item in restored_items]
        self.assertIn("Store: Add to Steam Cart", enabled_titles)
        self.assertNotIn("Store: Add to Steam Cart", disabled_titles)
        self.assertIn("Store: Add to Steam Cart", restored_titles)

    def test_ui_context_menu_allows_wishlist_for_free_store_games(self):
        harness = UIContextMenuHarness()

        items = harness.get_context_menu_items(
            app_id="570",
            name="Dota 2",
            install_path=None,
            is_owned=False,
            result_source="store",
            store_type="game",
            is_free=True,
            is_wishlisted=False,
            coming_soon=False,
            steamid64="76561198000000000",
        )

        titles = [item["Title"] for item in items]
        self.assertIn("Store: Add to Wishlist", titles)
        self.assertNotIn("Store: Add to Steam Cart", titles)

    def test_ui_context_menu_allows_store_actions_for_collection_results(self):
        harness = UIContextMenuHarness()

        items = harness.get_context_menu_items(
            app_id="1462040",
            name="FINAL FANTASY VII REMAKE INTERGRADE",
            install_path=None,
            is_owned=False,
            result_source="specials",
            store_type="game",
            is_free=False,
            is_wishlisted=False,
            coming_soon=False,
            steamid64="76561198000000000",
        )

        titles = [item["Title"] for item in items]
        self.assertIn("Store: Add to Wishlist", titles)
        self.assertIn("Store: Add to Steam Cart", titles)

    def test_ui_context_menu_hides_wishlist_when_wishlist_feature_disabled(self):
        harness = UIContextMenuHarness()
        harness.enabled_features["steam_wishlist"] = False

        items = harness.get_context_menu_items(
            app_id="570",
            name="Dota 2",
            install_path=None,
            is_owned=False,
            result_source="store",
            store_type="game",
            is_free=True,
            is_wishlisted=False,
            coming_soon=False,
            steamid64="76561198000000000",
        )

        titles = [item["Title"] for item in items]
        self.assertNotIn("Store: Add to Wishlist", titles)

    def test_ui_context_menu_hides_wishlist_when_api_key_is_unavailable(self):
        harness = UIContextMenuHarness()

        items = harness.get_context_menu_items(
            app_id="1462040",
            name="FINAL FANTASY VII REMAKE INTERGRADE",
            install_path=None,
            is_owned=False,
            result_source="specials",
            store_type="game",
            is_free=False,
            is_wishlisted=False,
            coming_soon=False,
            steamid64="76561198000000000",
            wishlist_actions_enabled=False,
        )

        titles = [item["Title"] for item in items]
        self.assertNotIn("Store: Add to Wishlist", titles)
        self.assertIn("Store: Add to Steam Cart", titles)

    def test_ui_context_menu_cache_tracks_context_link_settings(self):
        harness = UIContextMenuHarness()
        kwargs = {
            "app_id": "1451940",
            "name": "NEEDY GIRL OVERDOSE",
            "install_path": "C:/Games/Needy",
            "is_owned": True,
            "refund_state": "",
            "result_source": "store",
            "store_type": "game",
        }

        enabled_items = harness.get_context_menu_items(**kwargs)
        harness.settings["show_steamdb_context_menu"] = False
        harness.settings["show_csrin_context_menu"] = False
        disabled_items = harness.get_context_menu_items(**kwargs)

        enabled_titles = [item["Title"] for item in enabled_items]
        disabled_titles = [item["Title"] for item in disabled_items]
        self.assertIn("Store: Open in SteamDB", enabled_titles)
        self.assertIn("Community: Search in CS.RIN", enabled_titles)
        self.assertNotIn("Store: Open in SteamDB", disabled_titles)
        self.assertNotIn("Community: Search in CS.RIN", disabled_titles)


if __name__ == "__main__":
    unittest.main()
