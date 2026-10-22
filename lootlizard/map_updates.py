"""Bounded, atomic map metadata updates from the project's fixed GitHub feed.

The caller owns its executor and schedules the next call using SyncResult's
``next_check_seconds``. This module never sleeps, starts threads, touches Tk,
captures a display, downloads executable content, or uses credentials. A normal
poll is due every 60 seconds; GitHub's CDN may make publication visible later.
All redirects are rejected, so a feed cannot redirect requests to another host.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request

from .core import MapData

FEED_URL = "https://raw.githubusercontent.com/molnard-labs/LootLizard/metadata/maps.json"
MAX_FEED_BYTES = 2_000_000
MAX_MAPS = 32
MAX_RETRY_SECONDS = 900.
DEFAULT_CHECK_SECONDS = 60.
_MAX_CACHE_BYTES = MAX_FEED_BYTES + 4096
_MAP_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z", re.ASCII)


@dataclass(frozen=True)
class MapSnapshot:
    revision: str
    maps: tuple[MapData, ...]
    content_sha256: str


@dataclass(frozen=True)
class SyncResult:
    snapshot: MapSnapshot | None
    changed: bool
    status: str
    reason: str
    next_check_seconds: float


class _InvalidSnapshot(ValueError):
    pass


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise urllib.error.HTTPError(request.full_url, code, "Map update redirects are disabled", headers, fp)


def _open_feed(request, timeout):
    return urllib.request.build_opener(_NoRedirects()).open(request, timeout=timeout)


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidSnapshot("Duplicate JSON object key")
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise _InvalidSnapshot("Non-finite JSON numbers are not allowed")
    return number


def _bad_constant(value):
    raise _InvalidSnapshot("Non-finite JSON numbers are not allowed")


def _decode(raw):
    return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_object,
                      parse_float=_finite_float, parse_constant=_bad_constant)


def _validate_catalog(value):
    if not isinstance(value, dict) or set(value) != {"schema_version", "revision", "maps"}:
        raise _InvalidSnapshot("Expected a versioned complete map catalog")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise _InvalidSnapshot("Unsupported map catalog schema")
    revision = value["revision"]
    if (not isinstance(revision, str) or not 1 <= len(revision) <= 160 or revision != revision.strip()
            or any(ord(character) < 32 or ord(character) > 126 for character in revision)):
        raise _InvalidSnapshot("A short printable source revision is required")
    records = value["maps"]
    if not isinstance(records, list) or len(records) > MAX_MAPS:
        raise _InvalidSnapshot("Map catalog must contain at most 32 maps")
    maps, seen = [], set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not _MAP_ID.fullmatch(record["id"]):
            raise _InvalidSnapshot("Map ids must be short, safe lowercase identifiers")
        if record["id"] in seen:
            raise _InvalidSnapshot("Map ids must be unique")
        seen.add(record["id"])
        maps.append(MapData.from_dict(record))
    # Map ordering and object-key ordering do not change catalog content. The
    # revision is tracked separately, so a documentation-only commit need not
    # clear an application's current map/position when its maps are identical.
    maps.sort(key=lambda item: item.id)
    normalized = {"schema_version": 1, "revision": revision, "maps": [item.to_dict() for item in maps]}
    encoded = _json_bytes(normalized)
    if len(encoded) > MAX_FEED_BYTES:
        raise _InvalidSnapshot("Map catalog exceeds the 2 MB limit")
    content_hash = hashlib.sha256(_json_bytes(normalized["maps"])).hexdigest()
    return MapSnapshot(revision, tuple(maps), content_hash), normalized


def parse_snapshot(raw: bytes) -> MapSnapshot:
    """Pure publisher/client validation of one bounded UTF-8 feed snapshot.

    Raises ValueError for invalid input. This permits the metadata publisher to
    check the same snapshot contract as the desktop client before publication.
    """
    if not isinstance(raw, bytes) or len(raw) > MAX_FEED_BYTES:
        raise _InvalidSnapshot("Map catalog must be bounded UTF-8 JSON bytes")
    try:
        return _validate_catalog(_decode(raw))[0]
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as error:
        raise _InvalidSnapshot(str(error)) from error


def _etag(value):
    return (value if isinstance(value, str) and 1 <= len(value) <= 512
            and all(32 <= ord(character) <= 126 for character in value) else None)


def _retry_after(value):
    if not isinstance(value, str) or len(value) > 128:
        return None
    try:
        if value.strip().isdigit():
            seconds = float(int(value.strip()))
        else:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            seconds = (date - datetime.now(timezone.utc)).total_seconds()
        return max(0., min(MAX_RETRY_SECONDS, seconds))
    except (ValueError, TypeError, OverflowError):
        return None


def _read_response(response, deadline):
    headers = response.headers
    encoding = headers.get("Content-Encoding", "identity").strip().lower()
    if encoding not in ("", "identity"):
        raise _InvalidSnapshot("Compressed metadata responses are not accepted")
    length = headers.get("Content-Length")
    if length is not None:
        try:
            if not 0 <= int(length) <= MAX_FEED_BYTES:
                raise _InvalidSnapshot("Map catalog exceeds the 2 MB limit")
        except (ValueError, TypeError) as error:
            raise _InvalidSnapshot("Invalid metadata response length") from error
    result = bytearray()
    reader = getattr(response, "read1", response.read)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Map metadata response exceeded its deadline")
        # HTTPResponse.read1 performs at most one underlying read. Limit its
        # socket wait to the remaining total request budget when available.
        transport = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
        if transport is not None:
            transport.settimeout(remaining)
        chunk = reader(min(65536, MAX_FEED_BYTES + 1 - len(result)))
        if not isinstance(chunk, bytes):
            raise _InvalidSnapshot("A binary JSON metadata response is required")
        if not chunk:
            break
        result.extend(chunk)
        if len(result) > MAX_FEED_BYTES:
            raise _InvalidSnapshot("Map catalog exceeds the 2 MB limit")
    return bytes(result)


class MapUpdateClient:
    """One fixed-origin metadata client, safe for a caller-owned worker.

    ``load_cached`` performs disk I/O only. ``check(force=True)`` bypasses the
    normal due time but still respects explicit 429/503 Retry-After. Failed
    validation, network requests and cache replacement retain the last good
    snapshot. No synchronous retry or sleeping extends a worker's request.
    """
    def __init__(self, cache_path: Path, *, timeout_seconds=8., check_interval_seconds=DEFAULT_CHECK_SECONDS):
        if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
                or not math.isfinite(timeout_seconds) or not .1 <= timeout_seconds <= 30):
            raise ValueError("Map update timeout must be between 0.1 and 30 seconds")
        if (isinstance(check_interval_seconds, bool) or not isinstance(check_interval_seconds, (int, float))
                or not math.isfinite(check_interval_seconds) or not 10 <= check_interval_seconds <= MAX_RETRY_SECONDS):
            raise ValueError("Map update interval must be between 10 and 900 seconds")
        self.cache_path = Path(cache_path)
        self.timeout_seconds = float(timeout_seconds)
        self.check_interval_seconds = float(check_interval_seconds)
        self._snapshot = None
        self._payload = None
        self._etag = None
        self._loaded = False
        self._due = 0.
        self._retry_until = 0.
        self._failures = 0
        self._lock = threading.RLock()

    def _result(self, changed, status, reason, delay=None):
        if delay is None:
            delay = max(0., self._due-time.monotonic())
        return SyncResult(copy.deepcopy(self._snapshot), changed, status, reason, max(0., float(delay)))

    def load_cached(self):
        """Return a verified cached catalog, or None; never perform a request."""
        with self._lock:
            self._loaded = True
            try:
                with self.cache_path.open("rb") as stream:
                    raw = stream.read(_MAX_CACHE_BYTES+1)
                if len(raw) > _MAX_CACHE_BYTES:
                    raise _InvalidSnapshot("Map cache exceeds its limit")
                envelope = _decode(raw)
                if (not isinstance(envelope, dict) or type(envelope.get("cache_schema_version")) is not int
                        or envelope["cache_schema_version"] != 1):
                    raise _InvalidSnapshot("Unsupported map cache")
                snapshot, payload = _validate_catalog(envelope.get("snapshot"))
                if envelope.get("content_sha256") != snapshot.content_sha256:
                    raise _InvalidSnapshot("Map cache content hash does not match")
                self._snapshot, self._payload = snapshot, payload
                self._etag = _etag(envelope.get("etag"))
            except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
                pass
            return copy.deepcopy(self._snapshot)

    def _save(self, snapshot, payload, etag):
        raw = _json_bytes({"cache_schema_version": 1, "etag": etag,
                           "content_sha256": snapshot.content_sha256, "snapshot": payload})
        if len(raw) > _MAX_CACHE_BYTES:
            raise _InvalidSnapshot("Map cache exceeds its limit")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=self.cache_path.parent,
                                             prefix="."+self.cache_path.name+".", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.cache_path)
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def _failure(self, status, reason, *, retry_after=None):
        self._failures += 1
        delay = min(MAX_RETRY_SECONDS, self.check_interval_seconds*2**min(self._failures-1, 10))
        if retry_after is not None:
            delay = max(delay, retry_after)
            self._retry_until = time.monotonic()+retry_after
        self._due = time.monotonic()+delay
        return self._result(False, status, reason, delay)

    def _http_status(self, code, headers):
        if code == 304:
            if self._snapshot is None:
                self._etag = None
                return self._failure("error", "The update server returned no data without a verified cache.")
            self._failures = 0
            self._due = time.monotonic()+self.check_interval_seconds
            return self._result(False, "unchanged", "Map catalog is unchanged.", self.check_interval_seconds)
        if code in (429, 503):
            return self._failure("throttled", "The map update server requested a retry; keeping saved map data.",
                                 retry_after=_retry_after(headers.get("Retry-After")))
        return self._failure("error", f"Map update server returned HTTP {code}; keeping saved map data.")

    def check(self, *, force=False):
        if not self._lock.acquire(blocking=False):
            return self._result(False, "deferred", "A map update check is already running.", 1.)
        response = None
        try:
            if not self._loaded:
                self.load_cached()
            now = time.monotonic()
            if now < self._retry_until or (not force and now < self._due):
                return self._result(False, "deferred", "The next map update check is not due yet.")
            headers = {"Accept": "application/json", "User-Agent": "LootLizard map metadata client"}
            if self._snapshot is not None and self._etag is not None:
                headers["If-None-Match"] = self._etag
            request = urllib.request.Request(FEED_URL, headers=headers, method="GET")
            deadline = time.monotonic()+self.timeout_seconds
            response = _open_feed(request, self.timeout_seconds)
            code = response.getcode()
            if code != 200:
                return self._http_status(code, response.headers)
            raw = _read_response(response, deadline)
            snapshot, payload = _validate_catalog(_decode(raw))
            if (self._snapshot is not None and snapshot.revision == self._snapshot.revision
                    and snapshot.content_sha256 != self._snapshot.content_sha256):
                raise _InvalidSnapshot("A source revision changed its map content")
            changed = self._snapshot is None or snapshot.content_sha256 != self._snapshot.content_sha256
            etag = _etag(response.headers.get("ETag"))
            self._save(snapshot, payload, etag)
            self._snapshot, self._payload, self._etag = snapshot, payload, etag
            self._failures, self._retry_until = 0, 0.
            self._due = time.monotonic()+self.check_interval_seconds
            return self._result(changed, "updated" if changed else "unchanged",
                                "Map catalog updated." if changed else "Map catalog is unchanged.", self.check_interval_seconds)
        except urllib.error.HTTPError as error:
            try:
                return self._http_status(error.code, error.headers or {})
            finally:
                error.close()
        except (TimeoutError, urllib.error.URLError, http.client.HTTPException) as error:
            return self._failure("offline", "Could not reach the map update feed; keeping saved map data.")
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as error:
            return self._failure("error", "Map metadata rejected: "+str(error))
        except OSError:
            return self._failure("error", "Map update or cache could not be saved; keeping saved map data.")
        finally:
            if response is not None:
                response.close()
            self._lock.release()
