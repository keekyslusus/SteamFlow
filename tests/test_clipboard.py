import ctypes
import sys
import unittest
from ctypes import wintypes
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.clipboard import get_clipboard_text


class FakeFunction:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class ClipboardTests(unittest.TestCase):
    def test_reads_unicode_text_with_pointer_sized_winapi_results(self):
        text_buffer = ctypes.create_unicode_buffer("steam-api-key")

        class User32:
            OpenClipboard = FakeFunction(True)
            CloseClipboard = FakeFunction(True)
            GetClipboardData = FakeFunction(123)

        class Kernel32:
            GlobalLock = FakeFunction(ctypes.addressof(text_buffer))
            GlobalUnlock = FakeFunction(True)

        self.assertEqual(get_clipboard_text(User32, Kernel32), "steam-api-key")
        self.assertIs(User32.GetClipboardData.restype, wintypes.HANDLE)
        self.assertIs(Kernel32.GlobalLock.restype, wintypes.LPVOID)
        self.assertEqual(Kernel32.GlobalUnlock.calls, [(123,)])
        self.assertEqual(User32.CloseClipboard.calls, [()])


if __name__ == "__main__":
    unittest.main()
