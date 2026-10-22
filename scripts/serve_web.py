"""Serve an already built LootLizard static site on loopback only.

Build first with ``python scripts/build_web.py``. This development server has no
upload endpoint, application backend, directory listing or network proxy.
"""
from __future__ import annotations

import argparse
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import urllib.parse

ROOT = Path(__file__).resolve().parents[1] / "dist"
PUBLIC_SUFFIXES = frozenset((".html", ".css", ".js", ".mjs", ".json", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff2", ".txt", ".md"))
PYTHON_MODULES = frozenset(("__init__.py", "core.py", "registration.py", "marker_pipeline.py", "self_marker.py", "vision.py", "zone_vision.py"))


def public_path(request_target: str, root: Path = ROOT) -> Path | None:
    try:
        path = urllib.parse.unquote(urllib.parse.urlsplit(request_target).path, encoding="utf-8", errors="strict")
    except (UnicodeError, ValueError):
        return None
    if not path.startswith("/") or "\\" in path or any(ord(character) < 32 for character in path):
        return None
    parts = path.strip("/").split("/") if path.strip("/") else []
    if any(part in (".", "..") or part.startswith(".") or part == "__pycache__" for part in parts):
        return None
    root = root.resolve()
    resolved = root.joinpath(*parts).resolve()
    if not resolved.is_relative_to(root):
        return None
    if resolved.is_dir():
        resolved = (resolved / "index.html").resolve()
        if not resolved.is_relative_to(root):
            return None
    relative = resolved.relative_to(root).as_posix()
    if resolved.suffix == ".py":
        if relative != "app/python_bridge.py" and not (relative.startswith("cv/") and relative[3:] in PYTHON_MODULES):
            return None
    elif resolved.suffix.lower() not in PUBLIC_SUFFIXES and relative != "LICENSE":
        return None
    return resolved if resolved.is_file() else None


class StaticHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".js": "application/javascript", ".mjs": "application/javascript",
                      ".json": "application/json", ".wasm": "application/wasm", ".py": "text/x-python"}

    def __init__(self, *args, root: Path = ROOT, **kwargs):
        self.public_root = root.resolve()
        super().__init__(*args, directory=str(self.public_root), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        super().end_headers()

    def send_head(self):
        try:
            request_path = urllib.parse.urlsplit(self.path).path
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND, "No public asset at this path")
            return None
        redirects = {"/app": "/app/", "/web/poc": "/app/", "/web/poc/": "/app/"}
        if request_path in redirects:
            self.send_response(HTTPStatus.PERMANENT_REDIRECT)
            self.send_header("Location", redirects[request_path])
            self.send_header("Content-Length", "0")
            self.end_headers()
            return None
        if public_path(self.path, self.public_root) is None:
            self.send_error(HTTPStatus.NOT_FOUND, "No public asset at this path")
            return None
        return super().send_head()

    def translate_path(self, path):
        return str(public_path(path, self.public_root) or self.public_root / ".not-a-public-route")

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
    if not (root / "index.html").is_file() or not (root / "app/index.html").is_file():
        raise ValueError("Build the static site first: python scripts/build_web.py")
    return ThreadingHTTPServer(("127.0.0.1", port), partial(StaticHandler, root=root))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--directory", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")
    try:
        server = create_server(args.port, root=args.directory)
    except (OSError, ValueError) as error:
        parser.exit(2, f"Could not start the local static server: {error}\n")
    with server:
        print(f"LootLizard: http://127.0.0.1:{args.port}/ (app: /app/)", flush=True)
        print("Static GET/HEAD only. Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
