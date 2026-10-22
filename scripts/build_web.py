"""Build only public browser assets for Cloudflare Pages or another static host.

No package installation, network access or game imagery collection is performed.
The generated directory contains no desktop code, tests, captures or profiles.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_map_catalog import build_catalog, encode_catalog

PYTHON_MODULES = (
    "__init__.py", "core.py", "registration.py", "marker_pipeline.py",
    "self_marker.py", "vision.py", "zone_vision.py",
)
STATIC_SUFFIXES = frozenset((
    ".html", ".css", ".js", ".mjs", ".json", ".svg", ".png",
    ".jpg", ".jpeg", ".webp", ".ico", ".woff2", ".txt",
))
MAX_FILE_BYTES = 24_000_000
BUILD_INFO = "build-info.json"
REFERENCE_MANIFEST = "app/map-assets/manifest.json"
HEADERS = """/*
  Cache-Control: public, max-age=0, must-revalidate
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()

/app/*.py
  Content-Type: text/x-python; charset=utf-8

/cv/*.py
  Content-Type: text/x-python; charset=utf-8
"""
REDIRECTS = """/app /app/ 308
/web/poc /app/ 308
/web/poc/ /app/ 308
"""


def _relative_name(name: str) -> str:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or "\\" in name or ":" in name
            or any(ord(character) < 32 for character in name)
            or any(part in (".", "..") or part.startswith(".") for part in path.parts)
            or name != path.as_posix()):
        raise ValueError(f"Unsafe public asset path: {name!r}")
    return name


def _read(path: Path, *, within: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(within.resolve()):
        raise ValueError(f"Public inputs must be regular files inside their source directory: {path}")
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Public asset exceeds the static hosting size limit: {path.name}")
    return data


def _static_tree(directory: Path, prefix: str = "") -> dict[str, bytes]:
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"Missing public source directory: {directory}")
    assets = {}
    for path in sorted(directory.rglob("*")):
        # Local Python/compileall checks may leave bytecode next to the bridge.
        # It is a generated cache, never an application asset.
        if "__pycache__" in path.relative_to(directory).parts:
            continue
        if path.is_symlink():
            raise ValueError(f"Public source directories must not contain symlinks: {path}")
        if path.is_dir():
            continue
        relative = path.relative_to(directory).as_posix()
        name = _relative_name(prefix + relative)
        if path.suffix.lower() not in STATIC_SUFFIXES and not (prefix == "app/" and relative == "python_bridge.py"):
            raise ValueError(f"Unexpected file in public source directory: {relative}")
        assets[name] = _read(path, within=directory)
    return assets


def _version(root: Path) -> str:
    tree = ast.parse((root / "lootlizard/__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            version = ast.literal_eval(node.value)
            if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+(?:[-.][a-zA-Z0-9.]+)?", version):
                return version
    raise ValueError("A semantic application version is required")


def release_key(tag: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)-web\.([1-9]\d*)", tag)
    if not match:
        raise ValueError("Web releases use vMAJOR.MINOR.PATCH-web.NUMBER tags")
    return tuple(int(part) for part in match.groups())


def _validate_references(assets: dict[str, bytes], map_ids: set[str]) -> None:
    """Check all official bundled PNGs before any public output is replaced."""
    try:
        manifest = json.loads(assets[REFERENCE_MANIFEST])
        if manifest["schema_version"] != 1 or not re.fullmatch(r"[0-9a-f]{40}", manifest["source"]["commit"]):
            raise ValueError("Invalid bundled reference source")
        records = manifest["references"]
        if not isinstance(records, list) or not 1 <= len(records) <= 32:
            raise ValueError("Provide one to 32 bundled reference images")
        seen, expected = set(), {"manifest.json", "NOTICE.txt"}
        for record in records:
            map_id, name = record["mapId"], record["file"]
            if not isinstance(map_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", map_id) or map_id in seen:
                raise ValueError("Bundled reference map ids must be safe and unique")
            if name != f"{map_id}.png":
                raise ValueError("Bundled reference filenames must match their map ids")
            prefix = f'https://raw.githubusercontent.com/pubg/api-assets/{manifest["source"]["commit"]}/Assets/Maps/'
            if not isinstance(record["source_url"], str) or not record["source_url"].startswith(prefix) or not re.fullmatch(r"[A-Za-z0-9_]+\.png", record["source_url"][len(prefix):]):
                raise ValueError("Bundled reference source must be the pinned official PUBG repository")
            data = assets[f"app/map-assets/{name}"]
            if len(data) != record["bytes"] or not 1 <= len(data) <= 2_000_000:
                raise ValueError("Bundled reference byte size does not match its manifest")
            if not isinstance(record["sha256"], str) or hashlib.sha256(data).hexdigest() != record["sha256"]:
                raise ValueError("Bundled reference checksum mismatch")
            if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR" or struct.unpack(">I", data[8:12])[0] != 13:
                raise ValueError("Bundled reference must contain a PNG image")
            width, height = struct.unpack(">II", data[16:24])
            if width != record["width"] or height != record["height"] or width != height or not 128 <= width <= 2400:
                raise ValueError("Bundled reference must be a complete square map with verified dimensions")
            seen.add(map_id); expected.add(name)
        actual = {name.removeprefix("app/map-assets/") for name in assets if name.startswith("app/map-assets/")}
        if actual != expected or seen != map_ids:
            raise ValueError("Bundled map assets and local catalog must match exactly")
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Missing or malformed bundled map reference manifest") from error


def collect_assets(root: Path = ROOT, *, revision: str | None = None, tag: str | None = None) -> dict[str, bytes]:
    root = Path(root).resolve()
    if revision is not None and not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("revision must be a full lowercase commit SHA")
    version = _version(root)
    if tag is not None:
        release_key(tag)
        if not tag.startswith(f"v{version}-web."):
            raise ValueError("Web release tag does not match the application version")
    assets = _static_tree(root / "web/landing")
    if "index.html" not in assets:
        raise ValueError("The landing page requires web/landing/index.html")
    app = _static_tree(root / "web/app", "app/")
    if "app/index.html" not in app or "app/python_bridge.py" not in app:
        raise ValueError("The browser application and Python bridge are required")
    if set(assets) & set(app):
        raise ValueError("Landing assets must not overwrite the application")
    assets.update(app)
    for filename in PYTHON_MODULES:
        assets[f"cv/{filename}"] = _read(root / "lootlizard" / filename, within=root / "lootlizard")
    catalog = build_catalog(root / "data", revision)
    for record in catalog["maps"]:
        assets[f'data/{record["id"]}.json'] = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    assets["data/maps.json"] = encode_catalog(catalog)
    _validate_references(assets, {record["id"] for record in catalog["maps"]})
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        assets[filename] = _read(root / filename, within=root)
    assets["_headers"] = HEADERS.encode("utf-8")
    assets["_redirects"] = REDIRECTS.encode("utf-8")
    assets.setdefault("404.html", b'<!doctype html><html lang="en"><meta charset="utf-8"><title>Not found - LootLizard</title><h1>Page not found</h1><p><a href="/">Back to LootLizard</a></p></html>\n')
    info = {
        "schema_version": 1,
        "version": version,
        "revision": revision,
        "tag": tag,
        "assets": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(assets.items())},
    }
    assets[BUILD_INFO] = (json.dumps(info, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return assets


def write_assets(output: Path, assets: dict[str, bytes]) -> None:
    """Replace only a verified previous build; never recursively delete a folder."""
    output = Path(output).absolute()
    if output.is_symlink() or (output.exists() and not output.is_dir()):
        raise ValueError("The output must be a regular directory")
    resolved_output = output.resolve()
    previous = set()
    if output.exists():
        existing = set()
        for path in output.rglob("*"):
            if path.is_symlink() or not path.resolve().is_relative_to(resolved_output):
                raise ValueError("The output contains a link outside the build directory")
            if path.is_file():
                existing.add(path.relative_to(output).as_posix())
        if existing:
            try:
                info = json.loads((output / BUILD_INFO).read_text(encoding="utf-8"))
                if info["schema_version"] != 1 or not isinstance(info["assets"], dict):
                    raise ValueError("Invalid build manifest")
                previous = {_relative_name(name) for name in info["assets"]} | {BUILD_INFO}
            except (OSError, KeyError, TypeError, ValueError) as error:
                raise ValueError("Refusing to replace a nonempty directory without a valid LootLizard build manifest") from error
            if existing - previous:
                raise ValueError("The output contains files not listed in its previous build manifest")
    for name in assets:
        _relative_name(name)
    output.mkdir(parents=True, exist_ok=True)
    for name in sorted(previous - assets.keys()):
        target = output.joinpath(*PurePosixPath(name).parts)
        if not target.resolve().is_relative_to(resolved_output):
            raise ValueError("A previous build path escaped its output directory")
        target.unlink(missing_ok=True)
    for name, data in sorted(assets.items()):
        target = output.joinpath(*PurePosixPath(name).parts)
        if not target.resolve().is_relative_to(resolved_output):
            raise ValueError("A public asset path escaped its output directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def build(output: Path, *, root: Path = ROOT, revision: str | None = None, tag: str | None = None) -> dict[str, bytes]:
    assets = collect_assets(root, revision=revision, tag=tag)
    write_assets(output, assets)
    return assets


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--revision", default=os.environ.get("CF_PAGES_COMMIT_SHA") or os.environ.get("GITHUB_SHA"))
    parser.add_argument("--tag", help="Published web release tag, e.g. v0.9.0-web.1")
    args = parser.parse_args(argv)
    try:
        assets = build(args.output, revision=args.revision, tag=args.tag)
    except (OSError, ValueError, SyntaxError) as error:
        parser.exit(2, f"Web build failed: {error}\n")
    print(f"Built {len(assets)} public assets ({sum(map(len, assets.values())):,} bytes) in {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
