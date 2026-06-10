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

from steamflow.secure_storage import (
    build_data_blob,
    delete_secure_files,
    read_protected_text,
    write_protected_text,
)


class SecureStorageTests(unittest.TestCase):
    def test_build_data_blob_handles_empty_bytes(self):
        blob, buffer = build_data_blob(b"")

        self.assertEqual(blob.cbData, 0)
        self.assertFalse(blob.pbData)
        self.assertIsNone(buffer)

    def test_read_and_write_protected_text_use_injected_crypto(self):
        calls = []

        def protect_bytes(raw_bytes, entropy):
            calls.append(("protect", raw_bytes, entropy))
            return b"protected:" + raw_bytes[::-1]

        def unprotect_bytes(protected_bytes, entropy):
            calls.append(("unprotect", protected_bytes, entropy))
            self.assertTrue(protected_bytes.startswith(b"protected:"))
            return protected_bytes.removeprefix(b"protected:")[::-1]

        with TemporaryDirectory() as temp_dir:
            secret_path = Path(temp_dir) / "secrets" / "token.bin"

            write_protected_text(secret_path, " secret-token ", b"entropy", protect_bytes=protect_bytes)
            value = read_protected_text(secret_path, b"entropy", unprotect_bytes=unprotect_bytes)

        self.assertEqual(value, "secret-token")
        self.assertEqual(calls[0], ("protect", b" secret-token ", b"entropy"))
        self.assertEqual(calls[1][0], "unprotect")

    def test_delete_secure_files_ignores_missing_paths(self):
        with TemporaryDirectory() as temp_dir:
            existing_path = Path(temp_dir) / "secret.bin"
            missing_path = Path(temp_dir) / "missing.bin"
            existing_path.write_bytes(b"secret")

            delete_secure_files(existing_path, missing_path)

            self.assertFalse(existing_path.exists())


if __name__ == "__main__":
    unittest.main()
