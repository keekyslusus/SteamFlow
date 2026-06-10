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

from steamflow.tasks import BackgroundTaskManager, finish_flagged_refresh, get_background_task_manager, start_flagged_refresh


class ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self.target = target
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True
        if callable(self.target):
            self.target()


class TaskHarness:
    def __init__(self, manager=None):
        self.state_lock = threading.RLock()
        self.pending_refresh = False
        self.pending_keys = set()
        if manager is not None:
            self.background_task_manager = manager


class BackgroundTaskManagerTests(unittest.TestCase):
    def test_start_runs_target_with_args_and_returns_thread(self):
        calls = []
        manager = BackgroundTaskManager(thread_factory=ImmediateThread)

        thread = manager.start(lambda alpha, beta=None: calls.append((alpha, beta)), "a", beta="b")

        self.assertTrue(thread.started)
        self.assertTrue(thread.daemon)
        self.assertEqual(calls, [("a", "b")])

    def test_start_delayed_sleeps_before_running_target(self):
        calls = []
        manager = BackgroundTaskManager(
            thread_factory=ImmediateThread,
            sleeper=lambda seconds: calls.append(("sleep", seconds)),
        )

        manager.start_delayed(2, lambda: calls.append(("run", None)))

        self.assertEqual(calls, [("sleep", 2), ("run", None)])

    def test_start_flagged_refresh_sets_pending_and_deduplicates(self):
        calls = []
        manager = BackgroundTaskManager(thread_factory=ImmediateThread)
        harness = TaskHarness(manager)

        started = manager.start_flagged_refresh(harness, "pending_refresh", lambda: calls.append("refresh"))
        duplicate = manager.start_flagged_refresh(harness, "pending_refresh", lambda: calls.append("duplicate"))

        self.assertTrue(started)
        self.assertFalse(duplicate)
        self.assertEqual(calls, ["refresh"])
        self.assertTrue(harness.pending_refresh)

        manager.finish_flagged_refresh(harness, "pending_refresh")

        self.assertFalse(harness.pending_refresh)

    def test_start_keyed_refresh_sets_pending_key_and_deduplicates(self):
        calls = []
        manager = BackgroundTaskManager(thread_factory=ImmediateThread)
        harness = TaskHarness(manager)

        started = manager.start_keyed_refresh(harness, "pending_keys", "570", lambda key: calls.append(key))
        duplicate = manager.start_keyed_refresh(harness, "pending_keys", "570", lambda key: calls.append(f"again:{key}"))

        self.assertTrue(started)
        self.assertFalse(duplicate)
        self.assertEqual(calls, ["570"])
        self.assertEqual(harness.pending_keys, {"570"})

        manager.finish_keyed_refresh(harness, "pending_keys", "570")

        self.assertEqual(harness.pending_keys, set())

    def test_get_background_task_manager_prefers_plugin_manager(self):
        manager = BackgroundTaskManager(thread_factory=ImmediateThread)
        harness = TaskHarness(manager)

        self.assertIs(get_background_task_manager(harness), manager)

    def test_legacy_flagged_refresh_facade_uses_plugin_manager(self):
        calls = []
        manager = BackgroundTaskManager(thread_factory=ImmediateThread)
        harness = TaskHarness(manager)

        self.assertTrue(start_flagged_refresh(harness, "pending_refresh", lambda: calls.append("refresh")))
        self.assertEqual(calls, ["refresh"])
        self.assertTrue(harness.pending_refresh)

        finish_flagged_refresh(harness, "pending_refresh")

        self.assertFalse(harness.pending_refresh)


if __name__ == "__main__":
    unittest.main()
