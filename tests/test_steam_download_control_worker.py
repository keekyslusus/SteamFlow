import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import steam_download_control_worker


class SteamDownloadControlWorkerTests(unittest.TestCase):
    def test_main_writes_hint_only_after_successful_download_control(self):
        with TemporaryDirectory() as temp_dir:
            args = ["worker", temp_dir, "76561198000000000", "1451940", "resume"]
            with patch.object(sys, "argv", args):
                with patch.object(steam_download_control_worker, "perform_download_control") as mocked_control:
                    with patch.object(steam_download_control_worker, "set_download_control_status_hint") as mocked_hint:
                        with patch.object(steam_download_control_worker, "record_feature_success") as mocked_success:
                            result = steam_download_control_worker.main()

        self.assertEqual(result, 0)
        mocked_control.assert_called_once()
        mocked_hint.assert_called_once_with(
            PROJECT_ROOT / "cache_download_progress.json",
            "1451940",
            "resume",
        )
        self.assertEqual(
            [call.args[1] for call in mocked_success.call_args_list],
            ["steam_session_token", "download_control"],
        )

    def test_main_does_not_write_hint_when_download_control_fails(self):
        with TemporaryDirectory() as temp_dir:
            args = ["worker", temp_dir, "76561198000000000", "1451940", "resume"]
            with patch.object(sys, "argv", args):
                with patch.object(steam_download_control_worker, "perform_download_control", side_effect=RuntimeError):
                    with patch.object(steam_download_control_worker, "set_download_control_status_hint") as mocked_hint:
                        with patch.object(steam_download_control_worker, "record_feature_failure") as mocked_failure:
                            result = steam_download_control_worker.main()

        self.assertEqual(result, 1)
        mocked_hint.assert_not_called()
        self.assertEqual(mocked_failure.call_args.args[1], "download_control")

    def test_main_records_token_failure_for_token_not_found(self):
        with TemporaryDirectory() as temp_dir:
            args = ["worker", temp_dir, "76561198000000000", "1451940", "resume"]
            error = RuntimeError("No matching Steam webapi_token found for 76561198000000000")
            with patch.object(sys, "argv", args):
                with patch.object(steam_download_control_worker, "perform_download_control", side_effect=error):
                    with patch.object(steam_download_control_worker, "record_feature_failure") as mocked_failure:
                        result = steam_download_control_worker.main()

        self.assertEqual(result, 1)
        self.assertEqual(
            [call.args[1] for call in mocked_failure.call_args_list],
            ["steam_session_token", "download_control"],
        )
        self.assertEqual(mocked_failure.call_args_list[0].kwargs["reason"], "token_not_found")
        self.assertEqual(mocked_failure.call_args_list[1].kwargs["reason"], "dependency_failed")


if __name__ == "__main__":
    unittest.main()
