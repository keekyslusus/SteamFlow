import sys
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

from steamflow.account_service import (
    get_known_steam_accounts,
    get_loginusers_backup_path,
    get_loginusers_path,
    get_steam_account_label,
    get_steam_user_details,
    load_loginusers_file,
    normalize_loginusers_data,
    save_loginusers_file,
    select_last_known_steamid64,
    set_loginusers_autologin_account_data,
    steamid64_to_user_id,
    user_id_to_steamid64,
)


class AccountServiceTests(unittest.TestCase):
    def test_normalize_loginusers_data_guarantees_users_dict(self):
        self.assertEqual(normalize_loginusers_data(None), {"users": {}})
        self.assertEqual(normalize_loginusers_data({"users": []}), {"users": {}})

    def test_get_loginusers_paths(self):
        with TemporaryDirectory() as temp_dir:
            steam_path = Path(temp_dir) / "Steam"
            loginusers_path = steam_path / "config" / "loginusers.vdf"
            loginusers_path.parent.mkdir(parents=True)
            loginusers_path.write_text("", encoding="utf-8")

            self.assertEqual(get_loginusers_path(steam_path), loginusers_path)
            self.assertEqual(get_loginusers_backup_path(loginusers_path), loginusers_path.with_name("loginusers.vdf_last"))

    def test_load_loginusers_file_normalizes_loaded_vdf_data(self):
        with TemporaryDirectory() as temp_dir:
            loginusers_path = Path(temp_dir) / "loginusers.vdf"
            loginusers_path.write_text("", encoding="utf-8")

            loaded = load_loginusers_file(loginusers_path, vdf_loader=lambda _file_obj: {"users": []})

        self.assertEqual(loaded, {"users": {}})

    def test_save_loginusers_file_writes_temp_replaces_original_and_backs_up(self):
        dumped_payloads = []
        copied_paths = []

        with TemporaryDirectory() as temp_dir:
            loginusers_path = Path(temp_dir) / "loginusers.vdf"
            backup_path = Path(temp_dir) / "loginusers.vdf_last"
            loginusers_path.write_text("old", encoding="utf-8")

            def fake_dump(data, file_obj, pretty=True):
                dumped_payloads.append((data, pretty))
                file_obj.write("new")

            def fake_copy(source, destination):
                copied_paths.append((Path(source), Path(destination)))

            save_loginusers_file(
                loginusers_path,
                {"users": {}},
                backup_path=backup_path,
                vdf_dumper=fake_dump,
                copy_file=fake_copy,
            )

            saved_text = loginusers_path.read_text(encoding="utf-8")

        self.assertEqual(saved_text, "new")
        self.assertEqual(dumped_payloads, [({"users": {}}, True)])
        self.assertEqual(copied_paths, [(loginusers_path, backup_path)])

    def test_get_steam_account_label_prefers_persona_then_account_then_steamid(self):
        self.assertEqual(
            get_steam_account_label(
                {
                    "steamid64": "76561198000000000",
                    "account_name": "alpha",
                    "persona_name": "Alpha",
                }
            ),
            "Alpha",
        )
        self.assertEqual(get_steam_account_label({"account_name": "alpha"}), "alpha")
        self.assertEqual(get_steam_account_label({"steamid64": "76561198000000000"}), "76561198000000000")

    def test_get_known_steam_accounts_normalizes_and_sorts_accounts(self):
        loginusers_data = {
            "users": {
                "76561198000000000": {
                    "AccountName": "alpha",
                    "PersonaName": "Alpha",
                    "Timestamp": "10",
                    "MostRecent": "0",
                    "RememberPassword": "1",
                },
                "76561198000000001": {
                    "AccountName": "beta",
                    "PersonaName": "Beta",
                    "Timestamp": "1",
                    "MostRecent": "1",
                },
                "invalid": {"AccountName": "ignored"},
            }
        }

        accounts = get_known_steam_accounts(loginusers_data, avatar_path_resolver=lambda steamid64: f"{steamid64}.png")

        self.assertEqual([account["steamid64"] for account in accounts], ["76561198000000001", "76561198000000000"])
        self.assertEqual(accounts[0]["label"], "Beta")
        self.assertTrue(accounts[1]["remember_password"])
        self.assertEqual(accounts[1]["icon_path"], "76561198000000000.png")

    def test_set_loginusers_autologin_account_data_updates_target_flags(self):
        loginusers_data = {
            "users": {
                "1": {"MostRecent": "1", "AllowAutoLogin": "0"},
                "2": {"MostRecent": "0", "AccountName": "beta"},
            }
        }

        updated_user = set_loginusers_autologin_account_data(loginusers_data, "2")

        self.assertEqual(updated_user["AccountName"], "beta")
        self.assertEqual(loginusers_data["users"]["1"]["MostRecent"], "0")
        self.assertEqual(loginusers_data["users"]["2"]["MostRecent"], "1")
        self.assertEqual(loginusers_data["users"]["2"]["AllowAutoLogin"], "1")
        self.assertEqual(loginusers_data["users"]["2"]["RememberPassword"], "1")

    def test_get_steam_user_details_returns_compact_user_record(self):
        details = get_steam_user_details(
            {"users": {"76561198000000000": {"AccountName": "alpha", "PersonaName": "Alpha"}}},
            "76561198000000000",
        )

        self.assertEqual(
            details,
            {
                "steamid64": "76561198000000000",
                "account_name": "alpha",
                "persona_name": "Alpha",
            },
        )

    def test_select_last_known_steamid64_prefers_most_recent_then_timestamp(self):
        self.assertEqual(
            select_last_known_steamid64(
                {
                    "users": {
                        "76561198000000000": {"Timestamp": "100", "MostRecent": "0"},
                        "76561198000000001": {"Timestamp": "1", "MostRecent": "1"},
                    }
                }
            ),
            "76561198000000001",
        )
        self.assertEqual(
            select_last_known_steamid64(
                {
                    "users": {
                        "76561198000000000": {"Timestamp": "100"},
                        "76561198000000001": {"Timestamp": "1"},
                    }
                }
            ),
            "76561198000000000",
        )

    def test_steamid64_and_user_id_conversion_round_trip(self):
        self.assertEqual(steamid64_to_user_id("76561197960265729"), "1")
        self.assertEqual(user_id_to_steamid64("1"), "76561197960265729")


if __name__ == "__main__":
    unittest.main()
