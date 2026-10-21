"""Map metadata changes cooperate with existing geometry, ownership and workers."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import test_app_state as fixtures
from lootlizard.core import MapData, Point
from lootlizard.map_updates import MapSnapshot, SyncResult
from lootlizard.marker_pipeline import MarkerRecognition
from lootlizard.presentation import present


class AppUpdateTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AppStateTests()
        fixture.setUp()
        self.app, self.fixture = fixture.app, fixture
        app = self.app
        app._feed_map_ids, app._local_map_ids, app._local_map_files = set(app.map_data), set(), {}
        app.selected_point_id = "inside"
        app.position_method, app.position_score, app.view_heading_degrees = "view-cone", .94, 30.
        app.position, app.safe_zone = (.2, .2), fixture.zone
        app.map_data_revision = None
        app.map_update_token, app.map_update_next_at = 0, 0.
        app.map_updates_enabled = True
        app.map_update_stop = threading.Event()
        app.map_update_status, app.map_update_reason = "bundled", ""
        app.map_update_future = None
        app.smoke_test = False
        app._load_profile = Mock()
        app.map_update_client = SimpleNamespace(check=Mock())
        app.map_update_executor = fixtures._DeferredExecutor()
        app.map_update_executor.shutdown = Mock()
        app.root = SimpleNamespace(destroy=Mock(), after=Mock())
        app.hotkey = None
        self.registration = fixture._registered_view(matrix=((160.,0.,20.),(0.,160.,20.),(0.,0.,1.)))
        app.registration = self.registration

    def snapshot(self, *maps, revision="r2"):
        return MapSnapshot(revision, tuple(maps), "synthetic-digest")

    def replacement(self):
        return MapData(self.app.data.id, "Updated test map", 1000, {},
                       (Point("new", "New room", .3, .4),))

    def result(self, snapshot=None, status="updated"):
        return SyncResult(snapshot, snapshot is not None, status, "Synthetic sync result", 60.)

    def test_same_map_replaces_points_immediately_without_changing_player_or_circle(self):
        app = self.app
        position, zone, generation = app.position, app.safe_zone, app.recognition_id
        replacement = self.replacement()
        app._apply_map_snapshot(self.snapshot(replacement))
        self.assertIs(app.data, replacement)
        self.assertEqual((app.position, app.safe_zone, app.recognition_id), (position, zone, generation))
        self.assertIs(app.registration, self.registration)
        self.assertEqual(len(app.results.rows()), 1)
        self.assertIn("New room", app.results.rows()[0][0])
        self.assertNotEqual(app.results.rows()[0][-1], "—")
        self.assertIsNone(app.selected_point_id)
        self.assertIsNotNone(app._project_map_point(.3, .4))

    def test_removed_map_withholds_old_points_and_rechecks_old_worker(self):
        app = self.app
        ticket = app.recognition_id
        app._apply_map_snapshot(self.snapshot())
        self.assertEqual(app.map_data, {})
        self.assertIsNone(app.position)
        self.assertIsNone(app.safe_zone)
        self.assertIsNone(app._active_registration())
        self.assertIsNone(app._project_map_point(.3, .4))
        self.assertEqual(app.results.rows(), [])
        app._accept_registration(ticket, self.registration,
            MarkerRecognition((.2,.2), .95, "stale", True, "view-cone"))
        self.assertIsNone(app.position)
        self.assertEqual(app.results.rows(), [])

    def test_removed_legacy_map_has_no_stale_main_count_or_destination(self):
        app = self.app
        app.references, app.registration = (), None
        app._apply_map_snapshot(self.snapshot())
        summary = present(app)
        self.assertEqual(summary.title, "Map data unavailable")
        self.assertEqual(summary.rooms, "0 rooms")
        self.assertEqual(summary.selection_title, "Choose a destination")
        self.assertEqual(summary.circle, "Circle unknown")
    def test_pending_worker_uses_current_catalog_not_old_same_id_data(self):
        app = self.app
        ticket = app.recognition_id
        replacement = self.replacement()
        app._apply_map_snapshot(self.snapshot(replacement))
        app._accept_registration(ticket, self.registration,
            MarkerRecognition((.2,.2), .95, "fresh", True, "view-cone"))
        self.assertIs(app.data, replacement)
        self.assertEqual(len(app.results.rows()), 1)
        self.assertIn("New room", app.results.rows()[0][0])

    def test_old_selected_map_removal_does_not_discard_pending_new_supported_map(self):
        app = self.app
        app.registration = None  # A fresh capture is being identified.
        ticket = app.recognition_id
        other = MapData("other-map", "Other map", 8000, {}, (Point("other-1", "Other room", .3,.4),))
        app._apply_map_snapshot(self.snapshot(other))
        registration = type(self.registration)(other.id, self.registration.map_to_image,
                                               self.registration.viewport, "verified")
        app._accept_registration(ticket, registration,
            MarkerRecognition((.2,.2), .95, "fresh", True, "view-cone"))
        self.assertIs(app.data, other)
        self.assertEqual(app.position, (.2,.2))
        self.assertEqual(len(app.results.rows()), 1)
        self.assertIn("Other room", app.results.rows()[0][0])

    def test_local_override_survives_remote_replacement_and_removal(self):
        app = self.app
        local = app.data
        app._local_map_ids.add(local.id)
        app._apply_map_snapshot(self.snapshot(self.replacement()))
        self.assertIs(app.data, local)
        app._apply_map_snapshot(self.snapshot(revision="r3"))
        self.assertIs(app.map_data[local.id], local)
        self.assertIs(app.data, local)

    def test_persisted_local_file_is_reloaded_and_missing_file_blocks_feed_override(self):
        app = self.app
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"my-map.json"
            path.write_text(__import__("json").dumps(self.replacement().to_dict()), encoding="utf-8")
            app.settings["local_map_files"] = {app.data.id: str(path)}
            app._load_local_map_files()
            self.assertEqual(app.map_data[app.data.id].name, "Updated test map")
            path.unlink()
            app._load_local_map_files()
            app._apply_map_snapshot(self.snapshot(self.replacement()))
            self.assertNotIn(app.data.id, app.map_data)
            self.assertEqual(app.results.rows(), [])

    def test_offline_check_does_not_change_capture_status_geometry_or_data(self):
        app = self.app
        app._status(app.t("Ready"), level="success")
        before = (app.data, app.position, app.safe_zone, app.registration, app._status_message, app._status_level)
        app._accept_map_update(0, self.result(status="offline"))
        self.assertEqual((app.data, app.position, app.safe_zone, app.registration, app._status_message, app._status_level), before)
        self.assertEqual(app.map_update_status, "offline")

    def test_unchanged_digest_updates_revision_without_redraw_or_generation_reset(self):
        app = self.app
        app._apply_map_snapshot(self.snapshot(app.data))
        generation, data = app.recognition_id, app.data
        app.draw.reset_mock()
        app._accept_map_update(0, SyncResult(self.snapshot(data, revision="r3"), False,
                                            "unchanged", "Not modified", 60.))
        self.assertEqual(app.map_data_revision, "r3")
        self.assertEqual(app.recognition_id, generation)
        self.assertIs(app.data, data)
        app.draw.assert_not_called()

    def test_network_runs_on_separate_worker_and_applies_only_after_queue_dispatch(self):
        app = self.app
        app.map_update_executor = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(app.map_update_executor.shutdown, wait=True)
        main_thread = threading.get_ident()
        worker_threads = []
        replacement = self.replacement()
        original = app.data
        def check(**kwargs):
            worker_threads.append(threading.get_ident())
            return self.result(self.snapshot(replacement))
        app.map_update_client.check = check
        self.assertTrue(app._check_map_updates(force=True))
        app.map_update_future.result(timeout=3)
        self.assertNotEqual(worker_threads, [main_thread])
        self.assertIs(app.data, original)
        event, token, result = app.events.get()
        self.assertEqual(event, "map_update")
        app._accept_map_update(token, result)
        self.assertIs(app.data, replacement)

    def test_disabling_automatic_updates_rejects_inflight_result(self):
        app = self.app
        app.automatic_updates = SimpleNamespace(get=lambda: False)
        old = app.data
        app._automatic_updates_changed()
        app._accept_map_update(0, self.result(self.snapshot(self.replacement())))
        self.assertIs(app.data, old)
        self.assertFalse(app.map_updates_enabled)
        self.assertFalse(app._check_map_updates())

    def test_shutdown_cancels_queue_work_and_completed_network_cannot_post(self):
        app = self.app
        app.map_update_client.check.return_value = self.result(self.snapshot(self.replacement()))
        app._check_map_updates(force=True)
        work = app.map_update_executor.pending[0][1]
        app.executor = SimpleNamespace(shutdown=Mock())
        app.close()
        work()  # Simulate a request that was already running when Close was clicked.
        self.assertTrue(app.map_update_stop.is_set())
        self.assertTrue(app.events.empty())
        app.map_update_executor.shutdown.assert_called_once_with(wait=False, cancel_futures=True)
        app.root.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
