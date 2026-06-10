import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.http_client import (
    build_form_body,
    build_headers,
    build_url_with_query,
    decode_json_bytes,
    http_get_json,
    http_pool_get,
    http_pool_request,
    urllib_form_request,
    urllib_json_request,
)


class ResponseContext:
    def __init__(self, raw_data, content_type="application/json"):
        self.raw_data = raw_data
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.raw_data


class HttpClientTests(unittest.TestCase):
    def test_build_headers_adds_user_agent_and_preserves_overrides(self):
        self.assertEqual(
            build_headers({"Accept": "application/json"}),
            {"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )

    def test_decode_json_bytes_and_http_get_json(self):
        calls = []

        def http_get(url, **kwargs):
            calls.append((url, kwargs))
            return SimpleNamespace(data=json.dumps({"ok": True}).encode("utf-8"))

        self.assertEqual(decode_json_bytes(b'{"alpha": 1}'), {"alpha": 1})
        self.assertEqual(http_get_json(http_get, "https://example.test", timeout=3), {"ok": True})
        self.assertEqual(calls[0][1]["headers"]["User-Agent"], "Mozilla/5.0")

    def test_http_pool_get_raises_http_error_for_bad_status(self):
        class HTTPError(Exception):
            pass

        calls = []
        http_pool = SimpleNamespace(
            request=lambda *args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(status=500)
        )
        urllib3_module = SimpleNamespace(exceptions=SimpleNamespace(HTTPError=HTTPError))

        with self.assertRaisesRegex(HTTPError, "HTTP 500"):
            http_pool_get(http_pool, urllib3_module, "https://example.test", timeout=2)

        self.assertEqual(calls[0][0][0], "GET")
        self.assertFalse(calls[0][1]["retries"])

    def test_http_pool_request_supports_head_requests(self):
        calls = []
        http_pool = SimpleNamespace(
            request=lambda *args, **kwargs: calls.append((args, kwargs)) or SimpleNamespace(status=204)
        )
        urllib3_module = SimpleNamespace(exceptions=SimpleNamespace(HTTPError=RuntimeError))

        response = http_pool_request(http_pool, urllib3_module, "HEAD", "https://example.test", timeout=2)

        self.assertEqual(response.status, 204)
        self.assertEqual(calls[0][0][0], "HEAD")

    def test_urllib_json_request_builds_get_query(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return ResponseContext(b'{"ok": true}')

        payload = urllib_json_request(
            "https://example.test/api",
            fields={"a": "1", "b": ["2", "3"]},
            timeout=5,
            opener=opener,
        )

        self.assertEqual(payload, {"ok": True})
        self.assertIn("a=1", requests[0][0].full_url)
        self.assertIn("b=2", requests[0][0].full_url)
        self.assertEqual(requests[0][1], 5)

    def test_urllib_form_request_posts_form_fields_and_falls_back_for_non_json(self):
        requests = []

        def opener(request, timeout):
            requests.append((request, timeout))
            return ResponseContext(b"raw", content_type="text/plain")

        payload, raw_data = urllib_form_request(
            "https://example.test/form",
            fields={"alpha": "1"},
            origin="https://store.steampowered.com",
            referer="https://store.steampowered.com/",
            opener=opener,
        )

        self.assertEqual(payload, {})
        self.assertEqual(raw_data, b"raw")
        request = requests[0][0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.data, b"alpha=1")
        self.assertEqual(request.headers["Origin"], "https://store.steampowered.com")

    def test_build_form_body_and_url_query_support_doseq(self):
        self.assertEqual(build_form_body({"a": ["1", "2"]}), b"a=1&a=2")
        self.assertEqual(build_url_with_query("https://example.test?a=1", {"b": "2"}), "https://example.test?a=1&b=2")


if __name__ == "__main__":
    unittest.main()
