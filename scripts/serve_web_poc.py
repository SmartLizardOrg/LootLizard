"""Serve the browser experiment and public source/data on loopback only.

No uploads, directory listings, network proxy or application execution. Run
from any working directory; paths are rooted at this script's source checkout.
"""
from __future__ import annotations

import argparse
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]


def public_path(request_target: str, root: Path = ROOT) -> Path | None:
    """Resolve only explicit public roots, including after percent decoding."""
    try:
        path = urllib.parse.unquote(urllib.parse.urlsplit(request_target).path,
                                   encoding="utf-8", errors="strict")
    except (UnicodeError, ValueError):
        return None
    if not path.startswith("/") or "\\" in path or any(ord(character) < 32 for character in path):
        return None
    parts = path.strip("/").split("/")
    if any(part in (".", "..") or part.startswith(".") or part == "__pycache__" for part in parts):
        return None
    if parts[:2] == ["web", "poc"]:
        allowed = root / "web" / "poc"
    elif (len(parts) == 2 and parts[0] == "lootlizard"
          and parts[1].endswith(".py")):
        allowed = root / "lootlizard"
    elif len(parts) == 2 and parts[0] == "data" and parts[1].endswith(".json"):
        allowed = root / "data"
    else:
        return None
    root = root.resolve()
    if not allowed.resolve().is_relative_to(root):
        return None
    resolved = root.joinpath(*parts).resolve()
    # Deny symlinks/junctions into other directories, even within this checkout.
    if not resolved.is_relative_to(allowed.resolve()):
        return None
    if resolved.is_dir():
        resolved = (resolved / "index.html").resolve()
        if not resolved.is_relative_to(allowed.resolve()):
            return None
    return resolved if resolved.is_file() else None


class StaticHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".js": "application/javascript", ".mjs": "application/javascript",
                      ".json": "application/json", ".wasm": "application/wasm",
                      ".py": "text/x-python"}

    def __init__(self, *args, root: Path = ROOT, **kwargs):
        self.public_root = root.resolve()
        super().__init__(*args, directory=str(self.public_root), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()

    def send_head(self):
        try:
            request_path = urllib.parse.urlsplit(self.path).path
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND, "No public asset at this path")
            return None
        if request_path in ("/", "/web/poc"):
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", "/web/poc/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        path = public_path(self.path, self.public_root)
        if path is None:
            self.send_error(HTTPStatus.NOT_FOUND, "No public asset at this path")
            return None
        # SimpleHTTPRequestHandler uses translate_path only after this check.
        return super().send_head()

    def translate_path(self, path):
        result = public_path(path, self.public_root)
        # send_head already rejects invalid requests. Keep the fallback outside
        # any actual file rather than exposing the checkout through this API.
        return str(result or self.public_root / ".not-a-public-route")

    def list_directory(self, path):
        self.send_error(HTTPStatus.NOT_FOUND, "Directory listing is unavailable")
        return None

    def reject_write(self):
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.close_connection = True

    do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = reject_write


def create_server(port: int = 8765, *, root: Path = ROOT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), partial(StaticHandler, root=root))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    with create_server(args.port) as server:
        print(f"LootLizard browser experiment: http://127.0.0.1:{args.port}/web/poc/", flush=True)
        print("Static GET/HEAD only. Press Ctrl+C to stop. No browser is opened automatically.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
