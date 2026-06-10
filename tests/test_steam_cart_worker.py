import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import steam_cart_worker


class SteamCartWorkerTests(unittest.TestCase):
    def test_main_records_cart_success_before_opening_cart(self):
        with TemporaryDirectory() as temp_dir:
            args = ["worker", temp_dir, "76561198000000000", "1462040"]
            with patch.object(sys, "argv", args):
                with patch.object(steam_cart_worker, "perform_add_to_cart", return_value={"packageid": 123}):
                    with patch.object(steam_cart_worker, "open_steam_cart") as mocked_open:
                        with patch.object(steam_cart_worker, "record_feature_success") as mocked_success:
                            result = steam_cart_worker.main()

        self.assertEqual(result, 0)
        mocked_open.assert_called_once()
        self.assertEqual(
            [call.args[1] for call in mocked_success.call_args_list],
            ["steam_session_token", "steam_cart"],
        )

    def test_main_records_token_dependency_failure(self):
        with TemporaryDirectory() as temp_dir:
            args = ["worker", temp_dir, "76561198000000000", "1462040"]
            error = RuntimeError("No matching Steam webapi_token found for 76561198000000000")
            with patch.object(sys, "argv", args):
                with patch.object(steam_cart_worker, "perform_add_to_cart", side_effect=error):
                    with patch.object(steam_cart_worker, "record_feature_failure") as mocked_failure:
                        result = steam_cart_worker.main()

        self.assertEqual(result, 1)
        self.assertEqual(
            [call.args[1] for call in mocked_failure.call_args_list],
            ["steam_session_token", "steam_cart"],
        )
        self.assertEqual(mocked_failure.call_args_list[0].kwargs["reason"], "token_not_found")
        self.assertEqual(mocked_failure.call_args_list[1].kwargs["reason"], "dependency_failed")


if __name__ == "__main__":
    unittest.main()
