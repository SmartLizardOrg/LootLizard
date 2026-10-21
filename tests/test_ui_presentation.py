"""Cross-surface redesign regressions without native windows or game input.

The real app selection/state handlers, presenter and canvas renderer cooperate
against lightweight recording widgets. Recognition and map data are unchanged.
"""

from concurrent.futures import Future
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

import test_app_state as state_fixtures
import test_map_renderer as renderer_fixtures
from lootlizard.app import Companion
from lootlizard.core import MapData, Point
from lootlizard import map_renderer as renderer
from lootlizard.marker_pipeline import MarkerRecognition
from lootlizard.presentation import present
from lootlizard.registration import Registration
from lootlizard.storage import read_preferences
from lootlizard.zone_vision import ZoneDetection


class _Widget:
    def __init__(self):
        self.options = {}
    def configure(self, **values): self.options.update(values)
    def winfo_exists(self): return True


class _Choice(_Widget):
    def __init__(self):
        super().__init__()
        self.index, self.value = 0, "English"
    def current(self, index=None):
        if index is not None: self.index = index
        return self.index
    def set(self, value): self.value = value
    def get(self): return self.value


class _Settings:
    def __init__(self): self.visible, self.caption = False, ""
    def title(self, value): self.caption = value
    def deiconify(self): self.visible = True
    def lift(self): pass
    def withdraw(self): self.visible = False


class _Results(state_fixtures._Results):
    def __init__(self):
        super().__init__()
        self.chosen, self.headings = (), {}
    def selection(self): return self.chosen
    def selection_set(self, item):
        if item not in self.items: raise AssertionError("Selected a missing row")
        self.chosen = (item,)
    def see(self, item):
        if item not in self.items: raise AssertionError("Scrolled to a missing row")
    def delete(self, item):
        super().delete(item)
        if item in self.chosen: self.chosen = ()
    def heading(self, key, **values): self.headings[key] = values


class UiPresentationTests(unittest.TestCase):
    def setUp(self):
        fixture = state_fixtures.AppStateTests()
        fixture.setUp()
        self.app, self.fixture = fixture.app, fixture
        app = self.app
        app.selected_point_id, app.marker_size = None, "large"
        app.position_method, app.position_score = None, 0.
        app.view_heading_degrees, app.map_text_result = None, None
        app.capture_busy = False
        app.hotkey_registration = "ready"
        app.results, app.settings_window = _Results(), _Settings()
        app.tabs = SimpleNamespace(tab=Mock())
        app.language_choice, app.marker_size_choice = _Choice(), _Choice()
        app.capture_choice, app.output_choice = _Choice(), _Choice()
        app.capture_index, app.target_index = 0, 0
        app.displays = [SimpleNamespace(width=1920, height=1080, primary=True)]
        for name in ("status_label", "hint", "zone_label", "map_label", "data_label",
                     "reference_label", "main_status_label", "main_detail_label",
                     "summary_map_label", "room_count_label", "freshness_label",
                     "circle_badge_label", "selection_title_label", "selection_detail_label"):
            setattr(app, name, _Widget())
        app._update_age, app._update_hotkey_feedback = Mock(), Mock()
        app.canvas = renderer_fixtures.RecordingCanvas()
        app.draw = lambda: renderer.draw_map(app)
        photo = patch.object(renderer.ImageTk, "PhotoImage", return_value=object())
        photo.start()
        self.addCleanup(photo.stop)
        self.registration = fixture._registered_view(matrix=(
            (160., 0., 20.), (0., 160., 20.), (0., 0., 1.)))
        self._accept_verified()

    def _accept_verified(self):
        self.app._accept_registration(self.app.recognition_id, self.registration,
            MarkerRecognition((.2, .2), .94, "synthetic cone", True, "view-cone", 45.),
            ZoneDetection(self.fixture.zone, .95, "synthetic circle"))

    def _row_for(self, point_id):
        return next(row for row, key in self.app._row_point_ids.items() if key == point_id)

    def _evidence(self):
        app = self.app
        return (app.position, app.safe_zone, app.recognition_id, app.data.to_dict(),
                app.registration.map_to_image.copy())

    def _assert_same_evidence(self, before):
        app = self.app
        self.assertEqual((app.position, app.safe_zone, app.recognition_id, app.data.to_dict()), before[:4])
        np.testing.assert_array_equal(app.registration.map_to_image, before[4])

    def test_pin_click_and_table_selection_share_card_highlight_and_geometry(self):
        app = self.app
        before = self._evidence()
        app._click = Mock()
        renderer.bind_interactions(app)
        x, y, _ = app._map_pin_hits["inside"]
        app.canvas.bindings["<Button-1>"](SimpleNamespace(x=x, y=y))
        self.assertEqual(app.selected_point_id, "inside")
        self.assertEqual(app.results.selection(), (self._row_for("inside"),))
        self.assertEqual(app.selection_title_label.options["text"], "Inside circle")
        self.assertEqual(app._map_pin_items["inside"][1], renderer.AMBER_LIGHT)
        app._click.assert_not_called()
        app.results.selection_set(self._row_for("other"))
        app._table_selected()
        self.assertEqual(app.selected_point_id, "other")
        self.assertEqual(app.selection_title_label.options["text"], "Other outside")
        self.assertEqual(app._map_pin_items["other"][1], renderer.AMBER_LIGHT)
        self._assert_same_evidence(before)

    def test_all_points_and_circle_order_match_list_numbers_and_canvas(self):
        app = self.app
        expected = [point.id for point, _ in app._ordered_targets()]
        self.assertEqual(list(app._row_point_ids.values()), expected)
        self.assertEqual(set(app._map_pin_hits), {point.id for point in app.data.points})
        numbers = {item["tags"][1]: item["text"] for item in app.canvas.tagged("poi_number")}
        self.assertEqual(numbers, {key: str(index) for index, key in enumerate(expected, 1)})
        self.assertEqual(expected[:2], ["inside", "inside-2"])

    def test_exact_anchors_roundtrip_and_offset_badges_select_original_ids(self):
        app = self.app
        before = self._evidence()
        ox, oy, sx, sy = app.transform
        left, top, _, _ = app._view_box()
        expected_ids = set()
        for point in app.data.points:
            native = app._project_map_point(point.x, point.y)
            if native is None:
                continue
            expected_ids.add(point.id)
            x, y, _ = app._map_pin_hits[point.id]
            self.assertLess(np.linalg.norm(np.array(((x-ox)/sx+left, (y-oy)/sy+top))-native), 1e-7)
            badge_x, badge_y, _ = app._map_badge_hits[point.id]
            self.assertGreater(np.hypot(badge_x-x, badge_y-y), 5.)
            self.assertEqual(renderer._pin_at(app, x, y), point.id)
            self.assertEqual(renderer._pin_at(app, badge_x, badge_y), point.id)
            marks = [item for item in app.canvas.tagged("poi_anchor") if point.id in item["tags"]]
            self.assertTrue(marks)
            for mark in marks:
                values = mark["coordinates"]
                center = ((min(values[::2])+max(values[::2]))/2,
                          (min(values[1::2])+max(values[1::2]))/2)
                self.assertLess(np.hypot(center[0]-x, center[1]-y), 1e-7)
        self.assertEqual(set(app._map_pin_hits), expected_ids)
        self.assertEqual(set(app._map_badge_hits), expected_ids)
        self._assert_same_evidence(before)

    def test_offscreen_points_never_acquire_an_edge_anchor_or_badge(self):
        app = self.app
        zoomed = self.fixture._registered_view()
        app._accept_registration(app.recognition_id, zoomed)
        expected = {point.id for point in app.data.points
                    if zoomed.project_poi(point.x, point.y) is not None}
        self.assertNotIn("outside", expected)
        self.assertEqual(set(app._map_pin_hits), expected)
        self.assertEqual(set(app._map_badge_hits), expected)
        numbers = {item["tags"][1] for item in app.canvas.tagged("poi_number")}
        self.assertEqual(numbers, expected)

    def test_language_redraw_preserves_selection_geometry_and_complete_details(self):
        app = self.app
        app._select_point("inside")
        before = self._evidence()
        english = str(app.selection_detail_label.options["text"])
        app._apply_language("hu")
        self.assertEqual(app.selected_point_id, "inside")
        self.assertEqual(app.results.selection(), (self._row_for("inside"),))
        self.assertNotEqual(str(app.selection_detail_label.options["text"]), english)
        self.assertIn("m", str(app.selection_detail_label.options["text"]))
        self._assert_same_evidence(before)
        app._apply_language("en")
        self.assertEqual(app.selection_detail_label.options["text"], english)
        self._assert_same_evidence(before)

    def test_settings_and_persisted_marker_size_do_not_change_detection(self):
        app = self.app
        app._select_point("inside")
        before = self._evidence()
        self.assertFalse(app.settings_window.visible)
        app.open_settings()
        self.assertTrue(app.settings_window.visible)
        app.close_settings()
        self.assertFalse(app.settings_window.visible)
        with tempfile.TemporaryDirectory() as directory:
            app.settings_path, app.smoke_test = Path(directory)/"settings.json", False
            app._persist = Companion._persist.__get__(app, Companion)
            app.marker_size_choice.current(1)
            app._marker_size_changed()
            self.assertEqual(app.marker_size, "medium")
            self.assertEqual(read_preferences(app.settings_path)["marker_size"], "medium")
            app.language_choice.set("Magyar")
            app._language_changed()
            restored = read_preferences(app.settings_path)
            self.assertEqual((restored["marker_size"], restored["language"]), ("medium", "hu"))
        self.assertEqual(app.selected_point_id, "inside")
        self._assert_same_evidence(before)

    def test_pending_and_late_old_result_never_restore_selected_pins_or_distances(self):
        app = self.app
        app._select_point("inside")
        old_ticket = app.recognition_id
        app._clear_results(clear_zone=True)
        app.future = Future()
        app.draw()
        self.assertIsNone(app.selected_point_id)
        self.assertEqual(app.results.rows(), [])
        self.assertFalse(app._map_pin_hits)
        self.assertEqual(present(app).title, "Reading map…")
        app._accept_registration(old_ticket, self.registration,
            MarkerRecognition((.2,.2), .94, "old cone", True, "view-cone"))
        self.assertIsNone(app.position)
        self.assertFalse(app._map_pin_hits)
        self.assertEqual(app.results.rows(), [])
        self.assertFalse(app._select_point("inside"))

    def test_other_map_with_colliding_point_id_does_not_inherit_selection(self):
        app = self.app
        app._select_point("inside")
        app._clear_results(clear_zone=True)
        other = MapData("other-map", "Other map", 2000, {}, (Point("inside", "Different destination", .5, .5),))
        app.map_data[other.id] = other
        other_registration = Registration(other.id, self.registration.map_to_image,
                                           self.registration.viewport, "verified")
        app._accept_registration(app.recognition_id, other_registration)
        self.assertIs(app.data, other)
        self.assertIsNone(app.selected_point_id)
        self.assertEqual(app.results.selection(), ())
        self.assertEqual(present(app).selection_title, "Choose a destination")

    def test_empty_no_dataset_and_failed_shortcut_have_clear_safe_main_copy(self):
        app = self.app
        app._clear_image()
        self.assertEqual(present(app).rooms, "0 rooms")
        self.assertEqual(present(app).selection_title, "Choose a destination")
        # A known map without point support must not borrow the selected map's data.
        app.image = renderer_fixtures.Image.new("RGB", (200,200))
        unsupported = Registration("camp-jackal", self.registration.map_to_image,
                                   self.registration.viewport, "verified")
        app._accept_registration(app.recognition_id, unsupported)
        self.assertEqual(app.results.rows(), [])
        self.assertFalse(app._map_pin_hits)
        self.assertEqual(present(app).title, "No rooms for this map")
        app.hotkey_registration = "failed"
        summary = present(app)
        self.assertEqual(summary.title, "Shortcut unavailable")
        self.assertIn("Refresh map", summary.detail)

    def test_unknown_circle_is_one_clear_badge_without_raw_table_unknowns(self):
        app = self.app
        app.safe_zone = None
        app._render_results()
        self.assertEqual(present(app).circle, "Circle unknown")
        self.assertTrue(all(row[1] == "—" for row in app.results.rows()))
        self.assertFalse(any("UNKNOWN" in str(row) for row in app.results.rows()))


if __name__ == "__main__":
    unittest.main()
