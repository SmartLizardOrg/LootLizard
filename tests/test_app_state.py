"""State regressions with synthetic images and a manually scheduled worker.

No Tk interpreter, native window, screen capture, or real detection is used.
The actual UI state handlers and result ordering run against small fake widgets.
"""

from concurrent.futures import Future
import queue
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import numpy as np

from lootlizard.app import Companion
from lootlizard.core import Bounds, MapData, Point, SafeZone
from lootlizard.vision import Recognition
from lootlizard.zone_vision import ZoneDetection
from lootlizard.registration import Registration
from lootlizard.marker_pipeline import MarkerRecognition
from lootlizard.map_text import MapTextEvidence


class _Widget:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class _Value:
    def set(self, value):
        self.value = value


class _Results:
    def __init__(self):
        self.items = {}
        self.next_id = 0

    def get_children(self):
        return tuple(self.items)

    def delete(self, item):
        del self.items[item]

    def insert(self, parent, index, **options):
        self.next_id += 1
        item = str(self.next_id)
        self.items[item] = options
        return item

    def rows(self):
        return [options["values"] for options in self.items.values()]


class _DeferredExecutor:
    """Hold work until the test chooses to finish it, without creating threads."""

    def __init__(self):
        self.pending = []

    def submit(self, operation):
        future = Future()
        self.pending.append((future, operation))
        return future

    def complete_next(self):
        while self.pending:
            future, operation = self.pending.pop(0)
            if not future.set_running_or_notify_cancel():
                continue
            try:
                future.set_result(operation())
            except BaseException as error:
                future.set_exception(error)
                raise
            return
        raise AssertionError("No recognition work remains to complete")


class AppStateTests(unittest.TestCase):
    def setUp(self):
        self.app = Companion.__new__(Companion)
        self.app.language = "en"
        self.app._localized_widgets = {}
        self.app._status_message = None
        self.app._status_level = "info"
        self.app.status = _Value()
        self.app.status_label = _Widget()
        self.app.hint = _Widget()
        self.app.zone_label = _Widget()
        self.app.map_label = _Widget()
        self.app.data_label = _Widget()
        self.app.reference_label = _Widget()
        self.app.results = _Results()
        self.app.data = MapData("test", "Test map", 1000, {}, (
            Point("outside", "Nearby outside", .15, .15),
            Point("inside", "Inside circle", .70, .70),
            Point("inside-2", "Also inside circle", .78, .72),
            Point("other", "Other outside", .35, .35),
        ))
        self.app.image = Image.new("RGB", (200, 200), "#263442")
        self.app.map_data = {self.app.data.id: self.app.data}
        self.app.references = ()
        self.app.reference_catalog = None
        self.app.registration = None
        self.app.smoke_test = True
        self.app.settings = {}
        self.app._persist = Mock()
        self.app.bounds = Bounds(20, 20, 180, 180)
        self.app.profile = SimpleNamespace(image_size=(200, 200), bounds=self.app.bounds)
        self.app.image_is_capture = False
        self.app.captured_at = None
        self.app.captured_monotonic = None
        self.app.position = None
        self.app.safe_zone = None
        self.app.zone_reason = "Safe zone has not been checked for this image."
        self.app.mode = "position"
        self.app.first_corner = None
        self.app.marker_box = None
        self.app.transform = (10, 20, .5, .5)
        self.app.recognition_id = 0
        self.app.closed = False
        self.app.events = queue.SimpleQueue()
        self.app.executor = _DeferredExecutor()
        self.app.future = None
        # Skip rendering native images while keeping real state/result handlers.
        self.app.draw = Mock()
        self.app._show_profile = Mock()
        self.zone = SafeZone(.75, .75, .15)

    def _accept(self, ticket, position, zone):
        self.app._accept_recognition(
            ticket, Recognition(position, .95, "Synthetic unique match", True),
            ZoneDetection(zone, .95, "Synthetic white ring"),
        )

    def test_old_worker_cannot_replace_the_current_circle_or_player(self):
        old_ticket = self.app.recognition_id
        self.app.set_image(Image.new("RGB", (200, 200), "#304050"))
        current_position = (.20, .20)
        self._accept(self.app.recognition_id, current_position, self.zone)
        current_rows = self.app.results.rows()

        self._accept(old_ticket, (.05, .05), SafeZone(.10, .10, .12))

        self.assertEqual(self.app.position, current_position)
        self.assertEqual(self.app.safe_zone, self.zone)
        self.assertEqual(self.app.results.rows(), current_rows)
        self.assertIn("Inside circle", current_rows[0][0])

    def test_new_image_has_no_previous_circle_player_or_distances_while_pending(self):
        old_ticket = self.app.recognition_id
        self._accept(old_ticket, (.20, .20), self.zone)
        self.assertTrue(any(row[-1] != "—" for row in self.app.results.rows()))

        self.app.set_image(Image.new("RGB", (200, 200), "#405060"))

        self.assertIsNone(self.app.position)
        self.assertIsNone(self.app.safe_zone)
        self.assertTrue(all(row[1] == "—" and row[-1] == "—"
                            for row in self.app.results.rows()))
        self.assertTrue(all(self.app._zone_state(point) == "UNKNOWN" for point in self.app.data.points))
        # A result already queued for the previous snapshot cannot restore it.
        self._accept(old_ticket, (.20, .20), self.zone)
        self.assertIsNone(self.app.position)
        self.assertIsNone(self.app.safe_zone)

    def test_manual_position_keeps_fresh_circle_detection_alive(self):
        self.app._start_recognition(zone_only=True, quiet=True)
        # Select (.25, .75) on the displayed map crop, with nonzero screen
        # offsets and a half-scale display transform.
        self.app._click(SimpleNamespace(x=30, y=80))
        self.assertEqual(self.app.position, (.25, .75))

        with patch("lootlizard.app.detect_safe_zone",
                   return_value=ZoneDetection(self.zone, .95, "Synthetic white ring")), \
                patch("lootlizard.app.recognize",
                      side_effect=AssertionError("Circle-only work must preserve manual player selection")):
            self.app.executor.complete_next()
        event = self.app.events.get_nowait()
        self.assertEqual(event[0], "recognized")
        self.app._accept_recognition(*event[1:])

        self.assertEqual(self.app.position, (.25, .75))
        self.assertEqual(self.app.safe_zone, self.zone)
        self.assertEqual(self.app.results.rows()[0][1], "IN")
        self.assertIn("Inside circle", self.app.results.rows()[0][0])

    def _registered_view(self, map_id="test", matrix=None):
        self.app.references = (object(),)
        if matrix is None:
            matrix = ((240., 0., -20.), (0., 240., -50.), (0., 0., 1.))
        return Registration(map_id, np.array(matrix), (0, 0, 200, 200), "Canonical map registered")

    def test_registered_zoom_projects_full_map_points_without_any_icon(self):
        registration = self._registered_view()
        self.app.profile = None

        self.app._accept_registration(self.app.recognition_id, registration)

        self.assertIs(self.app._active_registration(), registration)
        self.assertEqual(self.app._project_map_point(.25, .75), (40., 130.))
        self.assertIsNone(self.app._project_map_point(.15, .15))
        self.assertIsNone(self.app.position)
        self.assertEqual(len(self.app.results.rows()), len(self.app.data.points))
        self.assertTrue(all(row[-1] == "—" for row in self.app.results.rows()))
        self.assertIn("icon optional", self.app.status.value)

    def test_icon_layout_failure_does_not_remove_registered_basements(self):
        registration = self._registered_view()
        self.app.position = (.3, .3)
        self.app._accept_registration(self.app.recognition_id, registration,
                                     Recognition(None, 0., "Map zoom changed", False))

        self.assertIs(self.app._active_registration(), registration)
        self.assertIsNone(self.app.position)
        self.assertEqual(self.app._project_map_point(.25, .75), (40., 130.))
        self.assertIn("icon distances unavailable", self.app.status.value)

    def test_new_image_hides_old_projection_until_fresh_registration(self):
        old_ticket = self.app.recognition_id
        registration = self._registered_view()
        self.app._accept_registration(old_ticket, registration, None,
                                      ZoneDetection(self.zone, .95, "Old ring"))
        self.app.set_image(Image.new("RGB", (200, 200), "#304050"))

        self.assertIsNone(self.app._active_registration())
        self.assertIsNone(self.app._project_map_point(.25, .75))
        self.assertIsNone(self.app.safe_zone)
        self.assertEqual(self.app.results.rows(), [], "Pending catalog registration must not offer old-map targets")
        self.app._accept_registration(old_ticket, registration,
                                      Recognition((.25, .75), 1., "Old icon", True),
                                      ZoneDetection(self.zone, .95, "Old ring"))
        self.assertIsNone(self.app.registration)
        self.assertIsNone(self.app.position)
        self.assertIsNone(self.app.safe_zone)

    def test_unknown_or_unsupported_map_withholds_all_projection(self):
        for registration in (self._registered_view("unloaded-map"),
                             Registration(None, None, (0, 0, 200, 200), "No map matched")):
            with self.subTest(map_id=registration.map_id):
                self.app.position, self.app.safe_zone = (.3, .3), self.zone
                self.app._accept_registration(self.app.recognition_id, registration)
                self.assertIsNone(self.app._active_registration())
                self.assertIsNone(self.app._project_map_point(.25, .75))
                self.assertIsNone(self.app.position)
                self.assertIsNone(self.app.safe_zone)
                self.assertEqual(self.app.results.rows(), [], "Unknown or unsupported maps must offer no targets")

    def test_registered_map_selects_only_its_matching_point_data(self):
        other = MapData("other-map", "Other map", 2000, {}, (
            Point("other-only", "Other-map basement", .5, .5),
        ))
        self.app.map_data[other.id] = other
        registration = self._registered_view(other.id)
        self.app._accept_registration(self.app.recognition_id, registration)

        self.assertIs(self.app.data, other)
        self.assertEqual(len(self.app.results.rows()), 1)
        self.assertIn("Other-map basement", self.app.results.rows()[0][0])
        self.assertIs(self.app._active_registration(), registration)
        self.assertIsNone(self.app.profile)

    def test_registered_manual_position_uses_inverse_transform(self):
        registration = self._registered_view()
        self.app._accept_registration(self.app.recognition_id, registration, None,
                                      ZoneDetection(self.zone, .95, "Ring"))
        self.app._click(SimpleNamespace(x=30, y=85))
        self.assertTrue(np.allclose(self.app.position, (.25, .75)))

    def test_clipped_map_worker_never_normalizes_circle_to_viewport(self):
        registration = self._registered_view()
        self.app.profile = None
        self.app._start_recognition()
        with patch("lootlizard.app.register_map", return_value=registration), \
                patch("lootlizard.app.recognize") as icon, \
                patch("lootlizard.app.detect_safe_zone") as detect:
            self.app.executor.complete_next()
        event = self.app.events.get_nowait()
        self.assertEqual(event[0], "registered")
        self.app._accept_registration(*event[1:])
        icon.assert_not_called()
        detect.assert_not_called()
        self.assertIsNone(self.app.safe_zone)
        self.assertIn("clipped", self.app.zone_reason)

    def test_complete_registered_map_uses_full_map_bounds_for_circle(self):
        registration = self._registered_view(matrix=((160., 0., 20.), (0., 160., 20.), (0., 0., 1.)))
        self.app.profile = None
        self.app._start_recognition()
        with patch("lootlizard.app.register_map", return_value=registration), \
                patch("lootlizard.app.detect_safe_zone", return_value=ZoneDetection(self.zone, .95, "Ring")) as detect:
            self.app.executor.complete_next()
        detect.assert_called_once()
        self.assertEqual(detect.call_args.args[1], Bounds(20, 20, 180, 180))
        event = self.app.events.get_nowait()
        self.app._accept_registration(*event[1:])
        self.assertEqual(self.app.safe_zone, self.zone)

    def test_catalog_loading_is_explicit_and_persists_only_its_path(self):
        self.app.image = None
        reference = object()
        path = Path("local-map-references/catalog.json").resolve()
        with patch("lootlizard.app.load_reference_catalog", return_value=(reference,)) as load:
            self.assertTrue(self.app._load_map_catalog(path))
        load.assert_called_once_with(path)
        self.assertEqual(self.app.references, (reference,))
        self.assertEqual(self.app.settings, {"reference_catalog": str(path)})
        self.app._persist.assert_called_once()

    def test_empty_or_invalid_catalog_does_not_replace_loaded_references(self):
        old = object()
        self.app.references = (old,)
        for error_or_result in ((), ValueError("Invalid catalog")):
            options = ({"side_effect": error_or_result} if isinstance(error_or_result, Exception)
                       else {"return_value": error_or_result})
            with self.subTest(result=error_or_result), patch("lootlizard.app.load_reference_catalog", **options):
                self.assertFalse(self.app._load_map_catalog(Path("catalog.json")))
                self.assertEqual(self.app.references, (old,))

    def test_registered_cone_result_sets_estimate_and_fresh_distances(self):
        registration = self._registered_view()
        result = MarkerRecognition((.3, .4), .9, "cone", True, "view-cone", 45., (52., 46.))
        self.app._accept_registration(self.app.recognition_id, registration, result)
        self.assertEqual(self.app.position, (.3, .4))
        self.assertEqual(self.app.position_method, "view-cone")
        self.assertEqual(self.app.view_heading_degrees, 45.)
        self.assertIn("View cone estimate", self.app.status.value)
        self.assertTrue(all(row[-1] != "—" for row in self.app.results.rows()))

    def test_replay_context_change_clears_estimate_and_invalidates_old_worker(self):
        registration = self._registered_view()
        old_ticket = self.app.recognition_id
        result = MarkerRecognition((.3, .4), .9, "cone", True, "view-cone", 45., (52., 46.))
        self.app._accept_registration(old_ticket, registration, result)
        self.app.observer_image = SimpleNamespace(get=lambda: True)
        self.app._view_context_changed()
        self.assertEqual(self.app.view_context, "replay")
        self.assertTrue(self.app.settings["observer_image"])
        self.assertIsNone(self.app.position)
        self.assertIsNone(self.app.position_method)
        self.assertIsNone(self.app.view_heading_degrees)
        self.app._accept_registration(old_ticket, registration, result)
        self.assertIsNone(self.app.position)
        self.assertEqual(self.app.results.rows(), [])

    def test_registered_worker_searches_for_cone_without_a_trained_profile(self):
        registration = self._registered_view()
        self.app.profile = None
        self.app.view_context = "live"
        self.app._start_recognition()
        result = MarkerRecognition((.3, .4), .9, "cone", True, "view-cone")
        with patch("lootlizard.app.register_map", return_value=registration), patch(
                "lootlizard.app.recognize_registered_marker", return_value=result) as marker:
            self.app.executor.complete_next()
        marker.assert_called_once()
        self.assertEqual(marker.call_args.kwargs["view_context"], "live")
        self.assertIsNone(marker.call_args.args[2])
        event = self.app.events.get_nowait()
        self.app._accept_registration(*event[1:])
        self.assertEqual(self.app.position, (.3, .4))

    def test_registered_circle_only_work_does_not_replace_manual_position(self):
        registration = self._registered_view()
        self.app.position = (.3, .4)
        self.app._start_recognition(zone_only=True)
        with patch("lootlizard.app.register_map", return_value=registration), patch(
                "lootlizard.app.recognize_registered_marker") as marker:
            self.app.executor.complete_next()
        marker.assert_not_called()
        event = self.app.events.get_nowait()
        self.app._accept_registration(*event[1:])
        self.assertEqual(self.app.position, (.3, .4))
        self.assertEqual(self.app.position_method, "manual")

    def test_registered_circle_only_result_preserves_existing_cone_source_and_heading(self):
        registration = self._registered_view()
        self.app._accept_registration(self.app.recognition_id, registration,
            MarkerRecognition((.3, .4), .91, "cone", True, "view-cone", 45.))
        self.app._accept_registration(self.app.recognition_id, registration, None,
            ZoneDetection(self.zone, .95, "Ring"))
        self.assertEqual(self.app.position_method, "view-cone")
        self.assertEqual(self.app.view_heading_degrees, 45.)
        self.assertEqual(self.app.position_score, .91)
        self.assertIn("View cone estimate", self.app.status.value)

    def test_saving_a_profile_in_replay_mode_does_not_create_an_automatic_position(self):
        self.app.view_context = "replay"
        self.app.mode = "marker_seed"
        self.app.marker_box = (40, 40, 60, 60)
        self.app.root = SimpleNamespace(update_idletasks=lambda: None)
        profile = SimpleNamespace(bounds=self.app.bounds)
        with patch("lootlizard.app.create_profile", return_value=profile), patch(
                "lootlizard.app.recognize",
                return_value=Recognition((.4, .6), .99, "trained", True)):
            self.app._click(SimpleNamespace(x=25, y=35))
        self.assertIs(self.app.profile, profile)
        self.assertIsNone(self.app.position)
        self.assertIsNone(self.app.position_method)

    def test_ocr_hint_cannot_authorize_point_placement_or_player_estimate(self):
        self.app.references = (object(),)
        registration = Registration(None, None, (0, 0, 200, 200), "unknown")
        text = MapTextEvidence("test", ("City One", "City Two"), "labels", available=True)
        self.app._accept_registration(self.app.recognition_id, registration,
            MarkerRecognition((.3, .4), .9, "cone", True, "view-cone"), text_result=text)
        self.assertIsNone(self.app.position)
        self.assertEqual(self.app.results.rows(), [])
        self.assertIsNone(self.app._active_registration())
        self.assertIn("Text suggests Test map", self.app.status.value)
        self.assertEqual(self.app.map_label.options["text"], "Not verified")

    def test_old_ocr_hint_is_cleared_by_new_image_and_cannot_return_late(self):
        self.app.references = (object(),)
        self.app.profile = None
        old = self.app.recognition_id
        registration = Registration(None, None, (0, 0, 200, 200), "unknown")
        text = MapTextEvidence("test", ("City One", "City Two"), "labels", available=True)
        self.app._accept_registration(old, registration, text_result=text)
        self.app.set_image(Image.new("RGB", (200, 200)))
        self.assertIsNone(self.app.map_text_result)
        self.app._accept_registration(old, registration, text_result=text)
        self.assertIsNone(self.app.map_text_result)

    def test_geometry_success_restores_map_label_after_an_ocr_only_hint(self):
        self.app.references = (object(),)
        self.app._accept_registration(self.app.recognition_id,
            Registration(None, None, (0, 0, 200, 200), "unknown"),
            text_result=MapTextEvidence("test", ("City One", "City Two"), "labels", available=True))
        self.app._accept_registration(self.app.recognition_id, self._registered_view())
        self.assertEqual(self.app.map_label.options["text"], "Test map")
        self.assertEqual(len(self.app.results.rows()), len(self.app.data.points))


if __name__ == "__main__":
    unittest.main()
