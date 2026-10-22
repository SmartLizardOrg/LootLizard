"""Loopback HTTP checks do not launch a browser or handle private screenshots."""
from __future__ import annotations

from contextlib import contextmanager
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("serve_web_poc", ROOT / "scripts/serve_web_poc.py")
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class QuietHandler(server_module.StaticHandler):
    def log_message(self, *args):
        pass


class StaticServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name, contents in (("web/poc/index.html", "demo"), ("web/poc/main.mjs", "export default 1;"),
                               ("lootlizard/registration.py", "public source"), ("data/erangel.json", "{}"),
                               ("private-profile/reference.png", "private"), (".env", "private")):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)

    @contextmanager
    def server(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, root=self.root)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                yield server.server_address
            finally:
                server.shutdown()
                thread.join(timeout=3)

    def request(self, address, path, method="GET", body=None):
        connection = HTTPConnection(*address, timeout=3)
        try:
            connection.request(method, path, body=body)
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_loopback_public_sources_mime_and_no_store(self):
        with self.server() as address:
            for path in ("/web/poc/", "/lootlizard/registration.py", "/data/erangel.json"):
                with self.subTest(path=path):
                    status, headers, body = self.request(address, path)
                    self.assertEqual(status, 200)
                    self.assertTrue(body)
                    self.assertEqual(headers["Cache-Control"], "no-store")
            status, headers, body = self.request(address, "/web/poc/main.mjs", "HEAD")
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-type"], "application/javascript")
            self.assertEqual(body, b"")

    def test_root_redirects_without_directory_listing(self):
        with self.server() as address:
            status, headers, _ = self.request(address, "/")
            self.assertEqual(status, 307)
            self.assertEqual(headers["Location"], "/web/poc/")
            self.assertEqual(self.request(address, "/lootlizard/")[0], 404)

    def test_private_files_encoded_traversal_and_backslashes_are_denied(self):
        with self.server() as address:
            for path in ("/.env", "/scripts/serve_web_poc.py", "/private-profile/reference.png",
                         "/web/poc/../../.env", "/web/poc/%2e%2e/%2e%2e/.env",
                         "/web/poc/%5c..%5c..%5c.env", "/data/%2e%2e/.env", "/data/erangel.json%00"):
                with self.subTest(path=path):
                    self.assertEqual(self.request(address, path)[0], 404)

    def test_upload_and_mutation_methods_are_rejected(self):
        with self.server() as address:
            for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
                with self.subTest(method=method):
                    status, headers, _ = self.request(address, "/web/poc/", method, b"not an upload")
                    self.assertEqual(status, 405)
                    self.assertEqual(headers["Allow"], "GET, HEAD")

    def test_symlink_escape_is_denied_if_supported_by_host(self):
        link = self.root / "web/poc/private.png"
        try:
            link.symlink_to(self.root / "private-profile/reference.png")
        except OSError:
            self.skipTest("This account cannot create symlinks")
        self.assertIsNone(server_module.public_path("/web/poc/private.png", self.root))


if __name__ == "__main__":
    unittest.main()
