import hashlib
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from steamflow.smokeapi_payload_service import (
    SmokeAPIPayloadFile,
    download_smokeapi_payload,
    inspect_smokeapi_payload,
)


class SmokeAPIPayloadServiceTests(unittest.TestCase):
    def make_specs(self):
        payloads = {
            "memory://steam_api.dll": b"smoke-32",
            "memory://steam_api64.dll": b"smoke-64",
        }
        specs = tuple(
            SmokeAPIPayloadFile(
                filename=url.rsplit("/", 1)[-1],
                url=url,
                sha256=hashlib.sha256(payload).hexdigest(),
                max_bytes=1024,
            )
            for url, payload in payloads.items()
        )
        return payloads, specs

    def test_inspection_reports_missing_invalid_and_ready_files(self):
        with TemporaryDirectory() as temp_dir:
            payloads, specs = self.make_specs()
            payload_dir = Path(temp_dir)

            missing = inspect_smokeapi_payload(payload_dir, specs)
            self.assertEqual(
                missing.missing_files,
                ("steam_api.dll", "steam_api64.dll"),
            )

            (payload_dir / "steam_api.dll").write_bytes(b"wrong")
            (payload_dir / "steam_api64.dll").write_bytes(
                payloads["memory://steam_api64.dll"]
            )
            mixed = inspect_smokeapi_payload(payload_dir, specs)
            self.assertEqual(mixed.missing_files, ())
            self.assertEqual(mixed.invalid_files, ("steam_api.dll",))

    def test_download_writes_verified_payload_files(self):
        with TemporaryDirectory() as temp_dir:
            payloads, specs = self.make_specs()

            def open_url(url, timeout):
                self.assertEqual(timeout, 7)
                return io.BytesIO(payloads[url])

            result = download_smokeapi_payload(
                temp_dir,
                payload_files=specs,
                open_url=open_url,
                timeout_seconds=7,
            )

            self.assertTrue(result.success)
            self.assertEqual(
                set(result.downloaded_files),
                {"steam_api.dll", "steam_api64.dll"},
            )
            self.assertTrue(inspect_smokeapi_payload(temp_dir, specs).ready)

    def test_hash_mismatch_leaves_existing_payload_untouched(self):
        with TemporaryDirectory() as temp_dir:
            _payloads, specs = self.make_specs()
            payload_dir = Path(temp_dir)
            existing = payload_dir / "steam_api.dll"
            existing.write_bytes(b"existing-invalid")

            result = download_smokeapi_payload(
                payload_dir,
                payload_files=specs,
                open_url=lambda _url, timeout: io.BytesIO(b"wrong"),
            )

            self.assertFalse(result.success)
            self.assertIn("payload_hash_mismatch", result.errors[0])
            self.assertEqual(existing.read_bytes(), b"existing-invalid")
            self.assertFalse((payload_dir / "steam_api64.dll").exists())

    def test_network_error_leaves_no_partial_files(self):
        with TemporaryDirectory() as temp_dir:
            _payloads, specs = self.make_specs()

            def fail(_url, timeout):
                raise OSError("offline")

            result = download_smokeapi_payload(
                temp_dir,
                payload_files=specs,
                open_url=fail,
            )

            self.assertFalse(result.success)
            self.assertIn("offline", result.errors[0])
            self.assertFalse((Path(temp_dir) / "steam_api.dll").exists())
            self.assertFalse((Path(temp_dir) / "steam_api64.dll").exists())

    def test_oversized_payload_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            _payloads, specs = self.make_specs()
            tiny_limit_spec = SmokeAPIPayloadFile(
                filename=specs[0].filename,
                url=specs[0].url,
                sha256=specs[0].sha256,
                max_bytes=2,
            )

            result = download_smokeapi_payload(
                temp_dir,
                payload_files=(tiny_limit_spec,),
                open_url=lambda _url, timeout: io.BytesIO(b"too large"),
            )

            self.assertFalse(result.success)
            self.assertIn("payload_too_large", result.errors[0])
            self.assertFalse((Path(temp_dir) / tiny_limit_spec.filename).exists())


if __name__ == "__main__":
    unittest.main()
