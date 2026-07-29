import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.worker_feedback import start_worker_feedback_monitor, wait_for_worker_result


class ImmediateThread:
    def __init__(self, target, daemon):
        self.target = target
        self.daemon = daemon

    def start(self):
        self.target()


class FakeProcess:
    def __init__(self, return_code):
        self.return_code = return_code

    def wait(self):
        return self.return_code


class FeedbackHarness:
    def __init__(self):
        self.messages = []
        self.logged_exceptions = []

    def show_msg(self, title, subtitle, icon=""):
        self.messages.append((title, subtitle, icon))

    def log_exception(self, message):
        self.logged_exceptions.append(message)


class WorkerFeedbackTests(unittest.TestCase):
    def test_wait_for_worker_result_uses_exit_code(self):
        self.assertTrue(wait_for_worker_result(FakeProcess(0)))
        self.assertFalse(wait_for_worker_result(FakeProcess(1)))

    def test_monitor_reports_success_and_uses_non_daemon_thread(self):
        harness = FeedbackHarness()
        outcomes = []

        thread = start_worker_feedback_monitor(
            harness,
            FakeProcess(0),
            outcomes.append,
            thread_factory=ImmediateThread,
        )

        self.assertEqual(outcomes, [True])
        self.assertFalse(thread.daemon)

    def test_monitor_reports_failure_when_wait_raises(self):
        harness = FeedbackHarness()
        outcomes = []

        class BrokenProcess:
            def wait(self):
                raise OSError("wait failed")

        start_worker_feedback_monitor(
            harness,
            BrokenProcess(),
            outcomes.append,
            thread_factory=ImmediateThread,
        )

        self.assertEqual(outcomes, [False])


if __name__ == "__main__":
    unittest.main()
