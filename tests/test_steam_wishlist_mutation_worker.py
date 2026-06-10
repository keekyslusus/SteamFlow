import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import steam_wishlist_mutation_worker


class SteamWishlistMutationWorkerTests(unittest.TestCase):
    def test_main_records_wishlist_success(self):
        with TemporaryDirectory() as temp_dir:
            args = ["worker", temp_dir, "76561198000000000", "570", "add"]
            with patch.object(sys, "argv", args):
                with patch.object(steam_wishlist_mutation_worker, "perform_wishlist_mutation"):
                    with patch.object(steam_wishlist_mutation_worker, "record_feature_success") as mocked_success:
                        result = steam_wishlist_mutation_worker.main()

        self.assertEqual(result, 0)
        self.assertEqual(
            [call.args[1] for call in mocked_success.call_args_list],
            ["steam_session_token", "steam_wishlist"],
        )

    def test_main_records_token_dependency_failure(self):
        with TemporaryDirectory() as temp_dir:
            args = ["worker", temp_dir, "76561198000000000", "570", "add"]
            error = RuntimeError("No matching Steam webapi_token found for 76561198000000000")
            with patch.object(sys, "argv", args):
                with patch.object(steam_wishlist_mutation_worker, "perform_wishlist_mutation", side_effect=error):
                    with patch.object(steam_wishlist_mutation_worker, "record_feature_failure") as mocked_failure:
                        result = steam_wishlist_mutation_worker.main()

        self.assertEqual(result, 1)
        self.assertEqual(
            [call.args[1] for call in mocked_failure.call_args_list],
            ["steam_session_token", "steam_wishlist"],
        )
        self.assertEqual(mocked_failure.call_args_list[0].kwargs["reason"], "token_not_found")
        self.assertEqual(mocked_failure.call_args_list[1].kwargs["reason"], "dependency_failed")

    def test_main_records_wishlist_specific_failure(self):
        with TemporaryDirectory() as temp_dir:
            args = ["worker", temp_dir, "76561198000000000", "570", "add"]
            error = RuntimeError("IWishlistService rejected request")
            with patch.object(sys, "argv", args):
                with patch.object(steam_wishlist_mutation_worker, "perform_wishlist_mutation", side_effect=error):
                    with patch.object(steam_wishlist_mutation_worker, "record_feature_failure") as mocked_failure:
                        result = steam_wishlist_mutation_worker.main()

        self.assertEqual(result, 1)
        self.assertEqual([call.args[1] for call in mocked_failure.call_args_list], ["steam_wishlist"])
        self.assertEqual(mocked_failure.call_args_list[0].kwargs["reason"], "wishlist_rejected")


if __name__ == "__main__":
    unittest.main()
