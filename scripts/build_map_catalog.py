"""Validate local map records and atomically build a bundled release catalog.

This script needs only Python's standard library and LootLizard's pure model.
It never downloads images, changes data files or writes to GitHub.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lootlizard.core import MapData

MAX_CATALOG_BYTES = 2_000_000
MAX_MAPS = 32
SAFE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
CONTENT_REVISION = re.compile(r"content:[0-9a-f]{64}\Z")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Non-finite JSON constant: {value}")


def encode_catalog(catalog: dict) -> bytes:
    validate_catalog(catalog)
    payload = (json.dumps(catalog, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > MAX_CATALOG_BYTES:
        raise ValueError(f"Catalog exceeds {MAX_CATALOG_BYTES} UTF-8 bytes")
    return payload


def _validate_record(document: dict) -> MapData:
    data = MapData.from_dict(document)
    if not SAFE_ID.fullmatch(data.id):
        raise ValueError(f"Unsafe map id: {data.id}")
    for point in data.points:
        if not SAFE_ID.fullmatch(point.id):
            raise ValueError(f"Unsafe point id in {data.id}: {point.id}")
    for key in ("url", "license", "attribution"):
        value = data.source.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{data.id}: source.{key} is required")
    url = urlsplit(data.source["url"])
    if url.scheme not in ("https", "http") or not url.hostname or url.username or url.password:
        raise ValueError(f"{data.id}: source.url must be a public HTTP(S) source URL without credentials")
    return data


def validate_catalog(value: dict) -> dict:
    """Validate a local, complete catalog without any updater/network dependency."""
    if not isinstance(value, dict) or set(value) != {"schema_version", "revision", "maps"}:
        raise ValueError("Expected a versioned complete map catalog")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported map catalog schema")
    revision = value["revision"]
    if not isinstance(revision, str) or not (COMMIT.fullmatch(revision) or CONTENT_REVISION.fullmatch(revision)):
        raise ValueError("A source commit or deterministic content revision is required")
    if not isinstance(value["maps"], list) or len(value["maps"]) > MAX_MAPS:
        raise ValueError("A catalog may contain at most 32 maps")
    seen = set()
    for document in value["maps"]:
        data = _validate_record(document)
        if data.id in seen:
            raise ValueError(f"Duplicate map id: {data.id}")
        seen.add(data.id)
    return value


def build_catalog(data_dir: Path, revision: str | None = None) -> dict:
    """Build from local files; release commits label builds, local data hashes label previews."""
    if revision is not None and (not isinstance(revision, str) or not COMMIT.fullmatch(revision)):
        raise ValueError("revision must be the full lowercase 40-character main commit SHA")
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise ValueError("The point-data directory does not exist")
    paths = sorted(data_dir.glob("*.json"), key=lambda path: path.name)
    if len(paths) > MAX_MAPS:
        raise ValueError(f"A catalog may contain at most {MAX_MAPS} maps")
    maps, seen = [], set()
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Point data must be a regular, non-symlink file: {path.name}")
        if path.stat().st_size > MAX_CATALOG_BYTES:
            raise ValueError(f"Point file exceeds the byte limit: {path.name}")
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"),
                                  object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
            data = _validate_record(document)
        except (ValueError, TypeError, UnicodeError) as error:
            raise ValueError(f"{path.name}: {error}") from error
        if data.id in seen:
            raise ValueError(f"Duplicate map id: {data.id}")
        seen.add(data.id)
        maps.append(data.to_dict())
    if revision is None:
        content = json.dumps(maps, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        revision = "content:" + hashlib.sha256(content).hexdigest()
    catalog = {"schema_version": 1, "revision": revision, "maps": maps}
    encode_catalog(catalog)
    return catalog


def write_catalog(path: Path, catalog: dict) -> None:
    """Replace one complete static catalog only after successful validation/encoding."""
    payload = encode_catalog(catalog)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--revision", help="Full source commit SHA; previews otherwise use a deterministic data hash")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        catalog = build_catalog(args.data_dir, args.revision)
        write_catalog(args.output, catalog)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(2, f"Catalog validation failed: {error}\n")
    print(f"Validated {len(catalog['maps'])} map(s); wrote {args.output} ({len(encode_catalog(catalog))} bytes).")


if __name__ == "__main__":
    main()
