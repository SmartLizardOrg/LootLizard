"""No real network: exercise requests, transactional catalogs and persistence."""
import copy
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

from lootlizard import map_updates as updates


def map_record(map_id="erangel", x=.4):
    return dict(id=map_id, name=map_id.title(), size_m=8000,
                source={"url": "https://example.org/source", "license": "CC0", "notes": "original"},
                points=[dict(id=map_id+"-01", name="Room 1", x=x, y=.5)])


def catalog(*, revision="a"*40, maps=None):
    return dict(schema_version=1, revision=revision, maps=[map_record()] if maps is None else maps)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class Response(io.BytesIO):
    def __init__(self, value=b"", *, code=200, headers=None):
        super().__init__(encoded(value) if isinstance(value, dict) else value)
        self.code = code
        self.headers = Message()
        for key, entry in (headers or {}).items():
            self.headers[key] = entry
        self.read_calls = 0
        self.delivered_bytes = 0

    def getcode(self): return self.code

    def read1(self, size=-1):
        self.read_calls += 1
        result = super().read(size)
        self.delivered_bytes += len(result)
        return result


class MapUpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested/maps-cache.json"
        self.client = updates.MapUpdateClient(self.path)
        self.opener = mock.patch.object(updates, "_open_feed").start()
        self.addCleanup(mock.patch.stopall)
        self.clock = [1000.]
        mock.patch.object(updates.time, "monotonic", side_effect=lambda: self.clock[0]).start()

    def respond(self, value=None, *, code=200, headers=None, force=True):
        response = Response(catalog() if value is None and code == 200 else value or b"", code=code, headers=headers)
        self.opener.return_value = response
        return self.client.check(force=force), response

    def seed(self):
        result, _ = self.respond(headers={"ETag": '"seed-tag"'})
        self.assertTrue(result.changed)
        self.assertEqual(result.status, "updated")
        return result

    def test_fixed_https_request_and_complete_snapshot_are_persisted(self):
        result, response = self.respond(catalog(maps=[map_record("taego"), map_record()]), headers={"ETag": '"v1"'})
        self.assertEqual([item.id for item in result.snapshot.maps], ["erangel", "taego"])
        self.assertEqual(result.next_check_seconds, 60)
        request, timeout = self.opener.call_args.args
        self.assertEqual(request.full_url, updates.FEED_URL)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(timeout, 8)
        self.assertIsNone(request.get_header("Authorization"))
        self.assertTrue(response.closed)
        fresh = updates.MapUpdateClient(self.path)
        self.assertEqual(fresh.load_cached(), result.snapshot)

    def test_empty_snapshot_removes_the_complete_previous_feed_catalog(self):
        self.seed()
        result, _ = self.respond(catalog(revision="b"*40, maps=[]))
        self.assertTrue(result.changed)
        self.assertEqual(result.snapshot.maps, ())
        self.assertEqual(updates.MapUpdateClient(self.path).load_cached().maps, ())

    def test_304_reuses_verified_cache_without_reading_or_writing_body(self):
        first = self.seed()
        old_bytes = self.path.read_bytes()
        result, response = self.respond(b"unused", code=304)
        self.assertEqual(result.status, "unchanged")
        self.assertFalse(result.changed)
        self.assertEqual(result.snapshot, first.snapshot)
        self.assertEqual(response.read_calls, 0)
        self.assertEqual(self.path.read_bytes(), old_bytes)
        request = self.opener.call_args.args[0]
        self.assertEqual(request.get_header("If-none-match"), '"seed-tag"')

    def test_urllib_http_error_304_has_the_same_cache_semantics(self):
        first = self.seed()
        self.opener.side_effect = urllib.error.HTTPError(updates.FEED_URL, 304, "Not modified", Message(), io.BytesIO())
        result = self.client.check(force=True)
        self.assertFalse(result.changed)
        self.assertEqual(result.snapshot, first.snapshot)
        self.assertEqual(result.status, "unchanged")

    def test_304_without_verified_cache_is_an_error(self):
        result, _ = self.respond(code=304)
        self.assertEqual(result.status, "error")
        self.assertIsNone(result.snapshot)
        self.assertFalse(self.path.exists())

    def test_startup_cache_is_fast_offline_and_etag_survives_restart(self):
        first = self.seed()
        self.client = updates.MapUpdateClient(self.path)
        before_calls = self.opener.call_count
        self.assertEqual(self.client.load_cached(), first.snapshot)
        self.assertEqual(self.opener.call_count, before_calls)
        self.opener.side_effect = urllib.error.URLError("offline")
        result = self.client.check()
        self.assertEqual(result.status, "offline")
        self.assertEqual(result.snapshot, first.snapshot)
        self.assertFalse(result.changed)
        self.assertEqual(self.opener.call_args.args[0].get_header("If-none-match"), '"seed-tag"')

    def test_first_offline_start_returns_no_snapshot_and_does_not_make_a_cache(self):
        self.opener.side_effect = TimeoutError("timeout")
        result = self.client.check()
        self.assertEqual(result.status, "offline")
        self.assertIsNone(result.snapshot)
        self.assertEqual(result.next_check_seconds, 60)
        self.assertFalse(self.path.exists())

    def test_http_error_keeps_previous_disk_and_in_memory_snapshot(self):
        first = self.seed()
        old = self.path.read_bytes()
        result, _ = self.respond(code=404)
        self.assertEqual(result.status, "error")
        self.assertEqual(result.snapshot, first.snapshot)
        self.assertEqual(self.path.read_bytes(), old)

    def test_a_bad_second_map_cannot_partially_replace_the_catalog(self):
        first = self.seed()
        old = self.path.read_bytes()
        invalid = map_record("taego", x=1.2)
        result, _ = self.respond(catalog(revision="b"*40, maps=[map_record(x=.7), invalid]))
        self.assertEqual(result.status, "error")
        self.assertFalse(result.changed)
        self.assertEqual(result.snapshot, first.snapshot)
        self.assertEqual(self.path.read_bytes(), old)

    def test_invalid_catalog_variants_preserve_the_last_good_snapshot(self):
        first = self.seed()
        variants = []
        for key, value in (("schema_version", True), ("schema_version", 2), ("maps", None),
                           ("maps", [map_record("map"+str(i)) for i in range(33)]),
                           ("revision", ""), ("revision", "x"*161), ("revision", "a\nb")):
            item = catalog(revision="b"*40)
            item[key] = value
            variants.append(item)
        variants.extend([catalog(maps=[map_record("../path")]), catalog(maps=[map_record("Bad/ID")]),
                         catalog(maps=[map_record(), map_record()]),
                         catalog(maps=[{**map_record(), "source": []}]),
                         catalog(maps=[{**map_record(), "points": []}])])
        for item in variants:
            with self.subTest(item=item):
                result, _ = self.respond(item)
                self.assertEqual(result.status, "error")
                self.assertEqual(result.snapshot, first.snapshot)

    def test_duplicate_keys_nonfinite_numbers_and_overflow_are_rejected(self):
        first = self.seed()
        raw = encoded(catalog())
        variants = [b'{"schema_version":1,'+raw[1:], raw.replace(b'"x":0.4', b'"x":NaN'),
                    raw.replace(b'"x":0.4', b'"x":1e9999'),
                    raw.replace(b'"size_m":8000', b'"size_m":'+b'9'*500), b'<html>error</html>']
        for value in variants:
            with self.subTest(value=value[:80]):
                result, _ = self.respond(value)
                self.assertEqual(result.status, "error")
                self.assertEqual(result.snapshot, first.snapshot)

    def test_oversized_declared_response_is_rejected_before_body_read(self):
        result, response = self.respond(b"{}", headers={"Content-Length": str(updates.MAX_FEED_BYTES+1)})
        self.assertEqual(result.status, "error")
        self.assertEqual(response.read_calls, 0)
        self.assertFalse(self.path.exists())

    def test_streaming_body_limit_is_enforced_even_without_content_length(self):
        result, response = self.respond(b" "*(updates.MAX_FEED_BYTES+2000))
        self.assertEqual(result.status, "error")
        self.assertEqual(response.delivered_bytes, updates.MAX_FEED_BYTES+1)
        self.assertTrue(response.closed)
        self.assertFalse(self.path.exists())

    def test_compressed_response_is_not_decompressed_or_cached(self):
        result, response = self.respond(b"fake gzip", headers={"Content-Encoding": "gzip"})
        self.assertEqual(result.status, "error")
        self.assertEqual(response.read_calls, 0)

    def test_same_maps_new_revision_and_formatting_do_not_invalidate_app_positions(self):
        first = self.seed()
        result, _ = self.respond(json.dumps(catalog(revision="b"*40), indent=4).encode())
        self.assertEqual(result.status, "unchanged")
        self.assertFalse(result.changed)
        self.assertEqual(result.snapshot.content_sha256, first.snapshot.content_sha256)
        self.assertEqual(result.snapshot.revision, "b"*40)
        self.assertEqual(updates.MapUpdateClient(self.path).load_cached().revision, "b"*40)

    def test_same_revision_different_content_is_rejected(self):
        first = self.seed()
        old = self.path.read_bytes()
        result, _ = self.respond(catalog(maps=[map_record(x=.6)]))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.snapshot, first.snapshot)
        self.assertEqual(self.path.read_bytes(), old)

    def test_cache_corruption_is_not_a_verified_startup_snapshot(self):
        self.seed()
        value = json.loads(self.path.read_text(encoding="utf-8"))
        value["snapshot"]["maps"][0]["points"][0]["x"] = .8
        self.path.write_bytes(encoded(value))
        self.client = updates.MapUpdateClient(self.path)
        self.assertIsNone(self.client.load_cached())
        self.respond()
        self.assertIsNone(self.opener.call_args.args[0].get_header("If-none-match"))

    def test_failed_atomic_replace_keeps_old_cache_and_old_runtime_catalog(self):
        first = self.seed()
        old = self.path.read_bytes()
        with mock.patch.object(updates.os, "replace", side_effect=OSError("locked")):
            result, _ = self.respond(catalog(revision="b"*40, maps=[map_record(x=.6)]))
        self.assertEqual(result.status, "error")
        self.assertEqual(result.snapshot, first.snapshot)
        self.assertEqual(self.path.read_bytes(), old)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_rate_limit_caps_retry_after_and_manual_force_honors_it(self):
        first = self.seed()
        result, _ = self.respond(code=429, headers={"Retry-After": "999999"})
        self.assertEqual(result.status, "throttled")
        self.assertEqual(result.snapshot, first.snapshot)
        self.assertEqual(result.next_check_seconds, 900)
        calls = self.opener.call_count
        deferred = self.client.check(force=True)
        self.assertEqual(deferred.status, "deferred")
        self.assertEqual(self.opener.call_count, calls)
        self.clock[0] += 901
        result, _ = self.respond(code=304)
        self.assertEqual(result.status, "unchanged")

    def test_503_http_date_retry_after_is_bounded_and_used(self):
        date = format_datetime(datetime.now(timezone.utc)+timedelta(seconds=300), usegmt=True)
        result, _ = self.respond(code=503, headers={"Retry-After": date})
        self.assertEqual(result.status, "throttled")
        self.assertGreaterEqual(result.next_check_seconds, 298)
        self.assertLessEqual(result.next_check_seconds, 301)

    def test_offline_backoff_grows_and_stops_at_fifteen_minutes(self):
        self.opener.side_effect = urllib.error.URLError("offline")
        delays = [self.client.check(force=True).next_check_seconds for _ in range(7)]
        self.assertEqual(delays, [60, 120, 240, 480, 900, 900, 900])

    def test_normal_due_gate_is_efficient_but_manual_force_can_check_now(self):
        self.seed()
        calls = self.opener.call_count
        deferred = self.client.check()
        self.assertEqual(deferred.status, "deferred")
        self.assertEqual(self.opener.call_count, calls)
        self.respond(code=304)
        self.assertEqual(self.opener.call_count, calls+1)

    def test_deadline_stops_reading_partial_slow_response(self):
        response = Response(encoded(catalog()))
        original = response.read1
        def slow_read(size):
            self.clock[0] += 9
            return original(min(size, 3))
        response.read1 = slow_read
        self.opener.return_value = response
        result = self.client.check()
        self.assertEqual(result.status, "offline")
        self.assertEqual(response.read_calls, 1)
        self.assertFalse(self.path.exists())

    def test_a_concurrent_check_is_deferred_without_duplicate_request(self):
        entered, release = threading.Event(), threading.Event()
        results = []
        def blocked(*args):
            entered.set()
            self.assertTrue(release.wait(3))
            return Response(catalog())
        self.opener.side_effect = blocked
        thread = threading.Thread(target=lambda: results.append(self.client.check()))
        thread.start()
        self.assertTrue(entered.wait(2))
        try:
            result = self.client.check(force=True)
            self.assertEqual(result.status, "deferred")
            self.assertEqual(self.opener.call_count, 1)
        finally:
            release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(results[0].status, "updated")

    def test_returned_mutable_source_metadata_cannot_corrupt_last_good_state(self):
        first = self.seed()
        first.snapshot.maps[0].source["notes"] = "changed by caller"
        self.opener.side_effect = urllib.error.URLError("offline")
        result = self.client.check(force=True)
        self.assertEqual(result.snapshot.maps[0].source["notes"], "original")

    def test_bad_etag_is_never_sent_as_a_request_header(self):
        self.respond(headers={"ETag": '"bad\r\nheader"'})
        self.respond(code=304)
        self.assertIsNone(self.opener.call_args.args[0].get_header("If-none-match"))

    def test_redirect_handler_rejects_redirect_before_another_origin_is_contacted(self):
        request = urllib.request.Request(updates.FEED_URL)
        for target in ("https://attacker.invalid/maps.json", "http://raw.githubusercontent.com/maps.json", updates.FEED_URL):
            with self.subTest(target=target):
                with self.assertRaises(urllib.error.HTTPError):
                    updates._NoRedirects().redirect_request(request, io.BytesIO(), 302, "redirect", Message(), target)

    def test_publisher_parser_accepts_descriptive_seed_and_shares_feed_validation(self):
        snapshot = updates.parse_snapshot(encoded(catalog(revision="bundled-seed-0.7.0")))
        self.assertEqual(snapshot.revision, "bundled-seed-0.7.0")
        for raw in (b"{}", b"NaN", b" "*(updates.MAX_FEED_BYTES+1), encoded(catalog(maps=[map_record("../bad")]))):
            with self.subTest(raw=raw[:20]):
                with self.assertRaises(ValueError):
                    updates.parse_snapshot(raw)

    def test_timeout_and_poll_interval_cannot_be_unbounded_or_invalid(self):
        for timeout in (True, 0, 31, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                updates.MapUpdateClient(self.path, timeout_seconds=timeout)
        for interval in (True, 0, 901, float("nan")):
            with self.assertRaises(ValueError):
                updates.MapUpdateClient(self.path, check_interval_seconds=interval)


if __name__ == "__main__":
    unittest.main()
