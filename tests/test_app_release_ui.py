"""Application updates stay off the image worker and apply only after cleanup."""

from concurrent.futures import Future, ThreadPoolExecutor
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_app_state as fixtures
from lootlizard.app_updates import AppUpdateResult


class ReleaseUpdateUiTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.AppStateTests()
        fixture.setUp()
        app = self.app = fixture.app
        app.smoke_test = False
        app.app_updates_enabled = True
        app.app_update_client = SimpleNamespace(installed=True, has_pending=False,
            check_and_download=Mock(return_value=AppUpdateResult("current", "0.8.0")), apply_on_exit=Mock(return_value=True))
        app.app_update_status, app.app_update_version, app.app_update_reason = "idle", None, ""
        app.app_update_ready = False
        app.app_update_token, app.app_update_next_at = 0, 0.
        app.app_update_stop = threading.Event()
        app.app_update_future = None
        app.app_update_executor = fixtures._DeferredExecutor()
        app.app_update_executor.shutdown = Mock()
        app.executor.shutdown = Mock()
        app.root = SimpleNamespace(destroy=Mock(), after=Mock())
        app.hotkey = None
        for name in ("app_update_label", "app_update_check_button", "app_restart_button", "app_update_diagnostic_label"):
            setattr(app, name, fixtures._Widget())

    def complete(self):
        self.app.app_update_executor.complete_next()
        kind, token, result = self.app.events.get()
        self.assertEqual(kind, "app_update")
        self.app._accept_app_update(token, result)

    def test_startup_check_and_six_hour_interval_do_not_touch_geometry(self):
        app = self.app
        before = (app.position, app.safe_zone, app.bounds, app.recognition_id, app.data)
        with patch("lootlizard.app.time.monotonic", return_value=100.):
            self.assertTrue(app._check_app_updates())
            self.assertFalse(app._check_app_updates())  # Single flight.
            self.complete()
            self.assertEqual(app.app_update_next_at, 21700.)
            self.assertFalse(app._check_app_updates())
        with patch("lootlizard.app.time.monotonic", return_value=21701.):
            self.assertTrue(app._check_app_updates())
        self.assertEqual((app.position, app.safe_zone, app.bounds, app.recognition_id, app.data), before)

    def test_manual_check_works_with_automatic_updates_disabled(self):
        app = self.app
        app.app_updates_enabled, app.app_update_next_at = False, float("inf")
        self.assertFalse(app._check_app_updates())
        self.assertTrue(app._check_app_updates(force=True))
        self.complete()
        self.assertEqual(app.app_update_status, "current")
        self.assertFalse(app._check_app_updates())

    def test_ready_result_only_enables_restart_never_closes_or_applies_in_background(self):
        app = self.app
        app._accept_app_update(0, AppUpdateResult("ready", "0.9.0"))
        self.assertTrue(app.app_update_ready)
        self.assertEqual(app.app_restart_button.options["state"], "normal")
        self.assertIn("0.9.0", app.app_update_label.options["text"])
        app.root.destroy.assert_not_called()
        app.app_update_client.apply_on_exit.assert_not_called()
        self.assertFalse(app._check_app_updates(force=True))

    def test_normal_close_applies_after_all_cleanup_without_restart(self):
        app = self.app
        order = []
        app.app_update_ready = True
        app.app_update_executor.shutdown = lambda **kwargs: order.append("app-worker")
        app.map_update_executor = SimpleNamespace(shutdown=lambda **kwargs: order.append("map-worker"))
        app.hotkey = SimpleNamespace(close=lambda: order.append("hotkey"))
        app.executor.shutdown = lambda **kwargs: order.append("recognition-worker")
        app.root.destroy = lambda: order.append("destroy")
        app.app_update_client.apply_on_exit = lambda restart=False: order.append(("apply", restart))
        app.close()
        self.assertEqual(order, ["app-worker", "map-worker", "hotkey", "recognition-worker", "destroy", ("apply", False)])
        self.assertTrue(app.app_update_stop.is_set())

    def test_disabled_automatic_updates_do_not_apply_on_normal_close(self):
        app = self.app
        app.app_updates_enabled, app.app_update_ready = False, True
        app.close()
        app.app_update_client.apply_on_exit.assert_not_called()

    def test_explicit_restart_applies_after_close_even_when_automatic_updates_off(self):
        app = self.app
        app.app_updates_enabled, app.app_update_ready = False, True
        self.assertTrue(app._restart_for_app_update())
        app.root.destroy.assert_called_once()
        app.app_update_client.apply_on_exit.assert_called_once_with(restart=True)
        self.assertFalse(app._restart_for_app_update())

    def test_restart_action_without_ready_package_is_noop(self):
        app = self.app
        self.assertFalse(app._restart_for_app_update())
        self.assertFalse(app.closed)
        app.root.destroy.assert_not_called()
        app.app_update_client.apply_on_exit.assert_not_called()

    def test_restart_waits_for_worker_with_one_poll_then_closes_and_applies(self):
        app = self.app
        app.app_update_ready = True
        app.future = Future()
        app.future.set_running_or_notify_cancel()
        self.assertFalse(app._restart_for_app_update())
        self.assertFalse(app._restart_for_app_update())
        app.root.after.assert_called_once()
        delay, callback = app.root.after.call_args.args
        self.assertEqual(delay, 200)
        self.assertIn("Finishing", app.app_update_label.options["text"])
        app.root.destroy.assert_not_called()
        app.future.set_result(None)
        callback()
        app.root.destroy.assert_called_once()
        app.app_update_client.apply_on_exit.assert_called_once_with(restart=True)

    def test_old_unfinished_recognition_is_not_hidden_by_replacement_future(self):
        app = self.app
        app.app_update_ready = True
        older = Future()
        older.set_running_or_notify_cancel()
        app._remember_recognition_work(older)
        app.future = Future()
        app.future.set_result(None)
        app._remember_recognition_work(app.future)
        app.close()
        app.root.destroy.assert_called_once()
        app.app_update_client.apply_on_exit.assert_not_called()
        self.assertTrue(app._background_tasks_busy())

    def test_normal_close_defers_apply_while_map_or_app_worker_runs(self):
        for name in ("map_update_future", "app_update_future"):
            with self.subTest(worker=name):
                self.setUp()
                app = self.app
                app.app_update_ready = True
                future = Future()
                future.set_running_or_notify_cancel()
                setattr(app, name, future)
                app.close()
                app.root.destroy.assert_called_once()
                app.app_update_client.apply_on_exit.assert_not_called()

    def test_close_during_download_never_applies_late_pending_package(self):
        app = self.app
        def download():
            app.app_update_client.has_pending = True
            return AppUpdateResult("ready", "0.9.0")
        app.app_update_client.check_and_download.side_effect = download
        app._check_app_updates(force=True)
        work = app.app_update_executor.pending[0][1]
        app.close()
        work()  # An already-running SDK request returns after Close.
        self.assertTrue(app.app_update_client.has_pending)
        self.assertTrue(app.events.empty())
        self.assertFalse(app.app_update_ready)
        app.app_update_client.apply_on_exit.assert_not_called()

    def test_disabling_updates_persists_and_rejects_old_queued_result(self):
        app = self.app
        app.automatic_app_updates = SimpleNamespace(get=lambda: False)
        app._automatic_app_updates_changed()
        self.assertIs(app.settings["automatic_app_updates"], False)
        app._persist.assert_called_once()
        app._accept_app_update(0, AppUpdateResult("ready", "0.9.0"))
        self.assertFalse(app.app_update_ready)
        self.assertFalse(app._check_app_updates())

    def test_source_or_portable_has_actionable_unavailable_state_without_check(self):
        app = self.app
        client = SimpleNamespace(installed=False, reason="portable build", check_and_download=Mock())
        with patch("lootlizard.app_updates.AppUpdateClient", return_value=client):
            app._initialize_app_updates()
        self.assertFalse(app._check_app_updates(force=True))
        client.check_and_download.assert_not_called()
        self.assertEqual(app.app_update_check_button.options["state"], "disabled")
        self.assertIn("Install LootLizard", app.app_update_label.options["text"])
        self.assertIn("portable build", app.app_update_diagnostic_label.options["text"])

    def test_error_is_confined_to_update_feedback_and_language_preserves_ready_state(self):
        app = self.app
        app._status(app.t("Ready"), level="success")
        before = (app._status_message, app._status_level, app.position, app.safe_zone, app.recognition_id)
        app._accept_app_update(0, AppUpdateResult("error", reason="network unavailable"))
        self.assertEqual((app._status_message, app._status_level, app.position, app.safe_zone, app.recognition_id), before)
        self.assertNotIn("network unavailable", app.app_update_label.options["text"])
        self.assertIn("network unavailable", app.app_update_diagnostic_label.options["text"])
        app._accept_app_update(0, AppUpdateResult("ready", "0.9.0"))
        app.language = "hu"
        app._update_app_feedback()
        self.assertIn("készen", app.app_update_label.options["text"])
        self.assertEqual(app.app_update_version, "0.9.0")
        self.assertTrue(app.app_update_ready)
        self.assertEqual(app.recognition_id, before[-1])

    def test_update_check_runs_on_dedicated_thread_and_result_waits_for_ui_dispatch(self):
        app = self.app
        app.app_update_executor = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(app.app_update_executor.shutdown, wait=True)
        threads = []
        def check():
            threads.append(threading.get_ident())
            return AppUpdateResult("ready", "0.9.0")
        app.app_update_client.check_and_download.side_effect = check
        app._check_app_updates(force=True)
        app.app_update_future.result(timeout=3)
        self.assertNotEqual(threads, [threading.get_ident()])
        self.assertFalse(app.app_update_ready)
        kind, token, result = app.events.get()
        self.assertEqual(kind, "app_update")
        app._accept_app_update(token, result)
        self.assertTrue(app.app_update_ready)
        app.root.destroy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
