import sys
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))
if "vdf" not in sys.modules:
    sys.modules["vdf"] = SimpleNamespace(load=lambda *_args, **_kwargs: {}, dump=lambda *_args, **_kwargs: None)

from steamflow.local_library_service import (
    build_installed_game_record,
    collect_installed_games_snapshot,
    cleanup_cache_keys,
    extract_localconfig_app_stats,
    load_steam_library_paths,
    normalize_appmanifest_state,
    parse_active_persona_state,
    parse_hidden_app_ids_data,
    parse_libraryfolders_steamapps_paths,
    parse_manifest_int,
    parse_state_flags,
    resolve_hidden_collections_path,
    resolve_localconfig_path,
)


class LocalLibraryServiceTests(unittest.TestCase):
    def test_parse_manifest_int_falls_back_for_invalid_values(self):
        self.assertEqual(parse_manifest_int("42"), 42)
        self.assertEqual(parse_manifest_int("nope", default=7), 7)

    def test_parse_state_flags_marks_paused_update_visible(self):
        parsed = parse_state_flags(512)

        self.assertTrue(parsed["is_visible"])
        self.assertTrue(parsed["is_update_paused"])
        self.assertEqual(parsed["label"], "Update Paused")

    def test_normalize_appmanifest_state_extracts_download_progress(self):
        manifest = normalize_appmanifest_state(
            {
                "appid": "1451940",
                "name": "NEEDY GIRL OVERDOSE",
                "installdir": "NEEDY GIRL OVERDOSE",
                "StateFlags": "4",
                "BytesToDownload": "100",
                "BytesDownloaded": "25",
            }
        )

        self.assertEqual(manifest["app_id"], "1451940")
        self.assertEqual(manifest["bytes_to_download"], 100)
        self.assertEqual(manifest["bytes_downloaded"], 25)
        self.assertTrue(manifest["state_flags"]["is_fully_installed"])

    def test_cleanup_cache_keys_removes_stale_entries(self):
        cache = {"keep": {"data": 1}, "drop": {"data": 2}}

        changed = cleanup_cache_keys(cache, {"keep"})

        self.assertTrue(changed)
        self.assertEqual(cache, {"keep": {"data": 1}})

    def test_parse_libraryfolders_steamapps_paths_adds_existing_alt_libraries(self):
        with TemporaryDirectory() as temp_dir:
            alt_steamapps = Path(temp_dir) / "SteamLibrary" / "steamapps"
            alt_steamapps.mkdir(parents=True)

            paths = parse_libraryfolders_steamapps_paths(
                {"libraryfolders": {"1": {"path": str(alt_steamapps.parent)}}},
                existing_paths=[],
            )

        self.assertEqual(paths, [alt_steamapps])

    def test_load_steam_library_paths_includes_main_and_libraryfolders_paths(self):
        with TemporaryDirectory() as temp_dir:
            steam_path = Path(temp_dir) / "Steam"
            main_steamapps = steam_path / "steamapps"
            alt_steamapps = Path(temp_dir) / "AltLibrary" / "steamapps"
            main_steamapps.mkdir(parents=True)
            alt_steamapps.mkdir(parents=True)
            (main_steamapps / "libraryfolders.vdf").write_text("", encoding="utf-8")

            paths = load_steam_library_paths(
                steam_path,
                vdf_loader=lambda _file_obj: {
                    "libraryfolders": {"1": {"path": str(alt_steamapps.parent)}}
                },
            )

        self.assertEqual(paths, [main_steamapps, alt_steamapps])

    def test_resolve_localconfig_path_prefers_active_user(self):
        with TemporaryDirectory() as temp_dir:
            steam_path = Path(temp_dir) / "Steam"
            active_path = steam_path / "userdata" / "111" / "config" / "localconfig.vdf"
            other_path = steam_path / "userdata" / "222" / "config" / "localconfig.vdf"
            active_path.parent.mkdir(parents=True)
            other_path.parent.mkdir(parents=True)
            active_path.write_text("", encoding="utf-8")
            other_path.write_text("", encoding="utf-8")

            selected = resolve_localconfig_path(steam_path, active_user_id="111")

        self.assertEqual(selected, active_path)

    def test_resolve_hidden_collections_path_prefers_localconfig_sibling(self):
        with TemporaryDirectory() as temp_dir:
            localconfig_path = Path(temp_dir) / "Steam" / "userdata" / "111" / "config" / "localconfig.vdf"
            hidden_path = localconfig_path.parent / "cloudstorage" / "cloud-storage-namespace-1.json"
            hidden_path.parent.mkdir(parents=True)
            localconfig_path.write_text("", encoding="utf-8")
            hidden_path.write_text("[]", encoding="utf-8")

            selected = resolve_hidden_collections_path(
                Path(temp_dir) / "Steam",
                active_user_id="111",
                localconfig_path=localconfig_path,
            )

        self.assertEqual(selected, hidden_path)

    def test_parse_active_persona_state_reads_friend_store_local_prefs(self):
        text = '"FriendStoreLocalPrefs_410190284"\t\t"{\\"ePersonaState\\":7,\\"x\\":1}"'

        self.assertEqual(parse_active_persona_state(text, "410190284"), 7)

    def test_parse_hidden_app_ids_data_applies_removed_filter(self):
        data = [
            [
                "user-collections.hidden",
                {"value": json.dumps({"added": [10, "20", 30], "removed": ["20"]})},
            ]
        ]

        self.assertEqual(parse_hidden_app_ids_data(data), {"10", "30"})

    def test_extract_localconfig_app_stats_reads_upper_and_lower_apps(self):
        playtimes, last_played = extract_localconfig_app_stats(
            {
                "Apps": {
                    "570": {"Playtime": "11290", "LastPlayed": "1776516641"},
                    "10": {"Playtime": "bad", "LastPlayed": "1"},
                }
            }
        )

        self.assertEqual(playtimes, {"570": 11290})
        self.assertEqual(last_played, {"570": 1776516641, "10": 1})

    def test_build_installed_game_record_filters_hidden_or_blacklisted_manifests(self):
        self.assertIsNone(
            build_installed_game_record(
                "C:/Steam/steamapps",
                {
                    "app_id": "10",
                    "name": "Counter-Strike",
                    "state_flags": {"is_visible": False},
                },
            )
        )
        self.assertIsNone(
            build_installed_game_record(
                "C:/Steam/steamapps",
                {
                    "app_id": "20",
                    "name": "Team Fortress Classic",
                    "state_flags": {"is_visible": True},
                },
                blacklist={"20"},
            )
        )

    def test_collect_installed_games_snapshot_builds_game_maps_and_manifest_keys(self):
        with TemporaryDirectory() as temp_dir:
            steamapps_path = Path(temp_dir) / "steamapps"
            steamapps_path.mkdir()
            manifest_path = steamapps_path / "appmanifest_1451940.acf"
            manifest_path.write_text("", encoding="utf-8")

            def load_manifest_data(_manifest_path):
                return {
                    "app_id": "1451940",
                    "name": "NEEDY GIRL OVERDOSE",
                    "install_dir": "NEEDY GIRL OVERDOSE",
                    "state_flags": {"is_visible": True},
                }

            snapshot = collect_installed_games_snapshot(
                [steamapps_path],
                load_manifest_data,
                lambda app_id, _state_flags, _manifest_data: f"status:{app_id}",
            )

        self.assertEqual(snapshot.installed_games, {"1451940": "NEEDY GIRL OVERDOSE"})
        self.assertEqual(snapshot.installed_game_statuses, {"1451940": "status:1451940"})
        self.assertIn("NEEDY GIRL OVERDOSE", snapshot.installed_game_paths["1451940"])
        self.assertEqual(snapshot.manifest_keys_in_use, {str(manifest_path)})


if __name__ == "__main__":
    unittest.main()
