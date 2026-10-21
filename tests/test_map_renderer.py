"""Canvas behavior contracts, independent of a desktop display or game images."""
from types import SimpleNamespace
from unittest import TestCase, mock
import math

import numpy as np
from PIL import Image

from lootlizard.core import Bounds, MapData, Point, SafeZone, nearest
from lootlizard.registration import Registration
from lootlizard import map_renderer as renderer


class RecordingCanvas:
    def __init__(self, width=900, height=700, dpi=96):
        self.width, self.height, self.dpi = width, height, dpi
        self.items, self.bindings, self.options = {}, {}, {}
        self.next_id = 0

    def winfo_width(self): return self.width
    def winfo_height(self): return self.height
    def winfo_fpixels(self, value): return self.dpi
    def delete(self, value): self.items.clear()
    def configure(self, **values): self.options.update(values)

    def _create(self, kind, coordinates, options):
        self.next_id += 1
        self.items[self.next_id] = dict(kind=kind, coordinates=list(coordinates), **options)
        return self.next_id

    def create_text(self, *coordinates, **options): return self._create("text", coordinates, options)
    def create_rectangle(self, *coordinates, **options): return self._create("rectangle", coordinates, options)
    def create_image(self, *coordinates, **options): return self._create("image", coordinates, options)
    def create_oval(self, *coordinates, **options): return self._create("oval", coordinates, options)
    def create_polygon(self, *coordinates, **options): return self._create("polygon", coordinates, options)
    def create_line(self, *coordinates, **options): return self._create("line", coordinates, options)
    def itemconfigure(self, item, **options): self.items[item].update(options)
    def tag_lower(self, *args): pass

    def coords(self, item, *coordinates):
        if coordinates: self.items[item]["coordinates"] = list(coordinates)
        return self.items[item]["coordinates"]

    def bbox(self, item):
        record = self.items[item]
        x, y = record["coordinates"][:2]
        height = abs(record.get("font", ("", 14))[1])
        width = max(1, len(str(record.get("text", "")))) * height * .6
        return x-width/2, y-height/2, x+width/2, y+height/2

    def bind(self, event, callback, add=None):
        if add and event in self.bindings:
            raise AssertionError("Interactions must not be bound twice")
        self.bindings[event] = callback

    def tagged(self, tag):
        return [item for item in self.items.values() if tag in item.get("tags", ())]


def app_fixture(*, count=7, canvas_size=(900, 700), crop=(200, 40, 1000, 840), registration=None):
    points = tuple(Point(f"point-{number}", f"Room {number}", .12 + (number % 4)*.22,
                         .2 + (number//4)*.42) for number in range(1, count+1))
    data = MapData("test", "Test", 8000, {}, points)
    app = SimpleNamespace(canvas=RecordingCanvas(*canvas_size), image=Image.new("RGB", (1200, 900), "#52604F"),
                          data=data, bounds=Bounds(*crop), references=() if registration is None else ("catalog",),
                          mode="position", first_corner=None, marker_box=None, position=(.5, .62),
                          safe_zone=None, selected_point_id=None, marker_size="large", language="en",
                          transform=None, manual_clicks=[], selected=[])
    app._active_registration = lambda: registration
    app._view_box = lambda: crop
    app._project_map_point = (lambda x, y: registration.project_poi(x, y)) if registration is not None else (
        lambda x, y: (crop[0]+x*(crop[2]-crop[0]), crop[1]+y*(crop[3]-crop[1])))
    app._ordered_targets = lambda: (nearest(data, app.position, count=len(points), zone=app.safe_zone)
                                    if app.position is not None else [(point, None) for point in points])
    app._zone_state = lambda point: "UNKNOWN" if app.safe_zone is None else ("IN" if app.safe_zone.contains(point.x, point.y) else "OUT")
    app.t = lambda message: "TE" if message == "YOU" and app.language == "hu" else message
    app._click = lambda event: app.manual_clicks.append((event.x, event.y, app.mode))
    app._select_point = lambda point_id: app.selected.append(point_id)
    app.draw = lambda: renderer.draw_map(app)
    return app


class MapRendererTests(TestCase):
    def setUp(self):
        self.photo = mock.patch.object(renderer.ImageTk, "PhotoImage", return_value=object())
        self.photo.start()
        self.addCleanup(self.photo.stop)

    def test_every_visible_point_is_numbered_with_a_compact_offset_badge(self):
        app = app_fixture()
        renderer.draw_map(app)
        bodies = app.canvas.tagged("basement")
        self.assertEqual(len(bodies), len(app.data.points))
        numbers = {item["tags"][1]: item["text"] for item in app.canvas.tagged("poi_number")}
        expected = {point.id: str(index) for index, (point, _) in enumerate(app._ordered_targets(), 1)}
        self.assertEqual(numbers, expected)
        for body in bodies:
            coordinates = body["coordinates"]
            self.assertAlmostEqual(max(coordinates[::2])-min(coordinates[::2]), 24)
            self.assertNotIn(body["fill"], ("white", "#a7b6c4", "#ffffff"))
            point_id = body["tags"][1]
            anchor_x, anchor_y, _ = app._map_pin_hits[point_id]
            self.assertFalse(min(coordinates[::2]) <= anchor_x <= max(coordinates[::2])
                             and min(coordinates[1::2]) <= anchor_y <= max(coordinates[1::2]))
        self.assertEqual(set(app._map_badge_hits), set(app._map_pin_hits))

    def test_inside_round_outside_amber_diamond_without_unknown_word_repetition(self):
        app = app_fixture()
        app.safe_zone = SafeZone(.5, .5, .34)
        renderer.draw_map(app)
        for point in app.data.points:
            body = next(item for item in app.canvas.tagged("basement") if point.id in item["tags"])
            self.assertEqual(body["kind"], "oval" if app.safe_zone.contains(point.x, point.y) else "polygon")
        text = [item["text"] for item in app.canvas.items.values() if item["kind"] == "text"]
        self.assertFalse(any("UNKNOWN" in item for item in text))
        self.assertEqual(len(app.canvas.tagged("safe_zone")), 2)

    def test_crop_transform_roundtrips_native_pixels_and_clips_offview_pois(self):
        matrix = np.array(((1400., 0, -350), (0, 1400, -300), (0, 0, 1)))
        registration = Registration("test", matrix, (100, 50, 1100, 850), "fixture")
        app = app_fixture(registration=registration, crop=(100, 50, 1100, 850))
        renderer.draw_map(app)
        ox, oy, sx, sy = app.transform
        visible_ids = set()
        for point in app.data.points:
            pixel = registration.project_poi(point.x, point.y)
            if pixel is None:
                self.assertNotIn(point.id, app._map_pin_hits)
                continue
            visible_ids.add(point.id)
            x, y, _ = app._map_pin_hits[point.id]
            native = ((x-ox)/sx+100, (y-oy)/sy+50)
            self.assertLess(math.dist(pixel, native), 1e-8)
        self.assertEqual(set(app._map_pin_hits), visible_ids)
        self.assertLess(len(visible_ids), len(app.data.points))

    def test_marker_setup_keeps_sample_pixels_unobscured_and_native_box_transform(self):
        app = app_fixture()
        app.mode, app.marker_box = "marker_seed", (480, 360, 510, 390)
        renderer.draw_map(app)
        self.assertFalse(app.canvas.tagged("basement"))
        self.assertFalse(app.canvas.tagged("player"))
        box = app.canvas.tagged("setup_marker")[0]["coordinates"]
        ox, oy, sx, sy = app.transform
        self.assertEqual(box, [ox+(480-200)*sx, oy+(360-40)*sy, ox+(510-200)*sx, oy+(390-40)*sy])

    def test_calibration_keeps_full_image_transform_and_hides_pois(self):
        app = app_fixture(crop=(0, 0, 1200, 900))
        app.mode, app.first_corner = "calibrate", (170, 130)
        renderer.draw_map(app)
        self.assertFalse(app.canvas.tagged("basement"))
        self.assertFalse(app._map_pin_hits)
        lines = [item for item in app.canvas.items.values() if item["kind"] == "line"]
        self.assertEqual(len(lines), 2)
        ox, oy, sx, sy = app.transform
        self.assertAlmostEqual((lines[0]["coordinates"][0]+lines[0]["coordinates"][2])/2, ox+170*sx)
        self.assertAlmostEqual(lines[0]["coordinates"][1], oy+130*sy)

    def test_player_is_cyan_and_you_label_translates_without_changing_position(self):
        app = app_fixture()
        app.language = "hu"
        before = app.position
        renderer.draw_map(app)
        labels = [item for item in app.canvas.tagged("player_label") if item["kind"] == "text"]
        self.assertEqual([item["text"] for item in labels], ["TE"])
        self.assertEqual(labels[0]["fill"], renderer.CYAN)
        self.assertEqual(app.position, before)
        filled_bodies = [item for item in app.canvas.tagged("player") if item.get("fill") == renderer.CYAN and item["kind"] == "oval"]
        self.assertEqual(len(filled_bodies), 1)
        self.assertLessEqual(filled_bodies[0]["coordinates"][2]-filled_bodies[0]["coordinates"][0], 6)

    def test_top_three_and_selected_only_get_compact_distance_labels(self):
        app = app_fixture()
        app.selected_point_id = app._ordered_targets()[-1][0].id
        renderer.draw_map(app)
        labels = [item for item in app.canvas.tagged("poi_distance") if item["kind"] == "text"]
        self.assertEqual(len(labels), 4)
        self.assertTrue(all(len(item["text"]) < 12 for item in labels))
        self.assertEqual(len(app.canvas.tagged("target_guide")), 2)

    def test_medium_is_smaller_and_high_dpi_does_not_make_giant_badges(self):
        app = app_fixture()
        renderer.draw_map(app)
        large = next(iter(app._map_badge_hits.values()))[2]
        app.marker_size = "medium"
        renderer.draw_map(app)
        self.assertLess(next(iter(app._map_badge_hits.values()))[2], large)
        app.marker_size, app.canvas.dpi = "large", 192
        renderer.draw_map(app)
        for body in app.canvas.tagged("basement"):
            self.assertLessEqual(max(body["coordinates"][::2])-min(body["coordinates"][::2]), 30)
        for guide in app.canvas.tagged("target_guide"):
            self.assertTrue(all(type(value) is int for value in guide["dash"]))

    def test_clipped_affine_circle_lines_stay_within_displayed_image(self):
        angle = math.radians(7)
        c, s = math.cos(angle)*900, math.sin(angle)*900
        registration = Registration("test", np.array(((c, -s, 80), (s, c, -80), (0, 0, 1))),
                                    (100, 50, 950, 760), "fixture")
        app = app_fixture(registration=registration, crop=registration.viewport)
        app.safe_zone = SafeZone(.5, .5, .65)
        renderer.draw_map(app)
        lines = app.canvas.tagged("safe_zone")
        self.assertTrue(lines)
        ox, oy, sx, sy = app.transform
        for line in lines:
            for x, y in zip(line["coordinates"][::2], line["coordinates"][1::2]):
                self.assertGreaterEqual(x, ox-1e-8)
                self.assertLessEqual(x, ox+850*sx+1e-8)
                self.assertGreaterEqual(y, oy-1e-8)
                self.assertLessEqual(y, oy+710*sy+1e-8)

    def test_pin_selection_and_setup_clicks_have_distinct_single_dispatch(self):
        app = app_fixture()
        renderer.draw_map(app)
        renderer.bind_interactions(app)
        renderer.bind_interactions(app)
        self.assertEqual(len(app.canvas.bindings), 3)
        point_id, (x, y, _) = next(iter(app._map_pin_hits.items()))
        event = SimpleNamespace(x=x, y=y)
        self.assertEqual(app.canvas.bindings["<Button-1>"](event), "break")
        self.assertEqual(app.selected, [point_id])
        self.assertFalse(app.manual_clicks)
        bx, by, _ = app._map_badge_hits[point_id]
        app.canvas.bindings["<Button-1>"](SimpleNamespace(x=bx, y=by))
        self.assertEqual(app.selected, [point_id, point_id])
        self.assertFalse(app.manual_clicks)
        app.mode = "marker_box"
        app.canvas.bindings["<Button-1>"](event)
        self.assertEqual(app.manual_clicks, [(x, y, "marker_box")])
        app.mode = "position"
        app.canvas.bindings["<Button-1>"](SimpleNamespace(x=1, y=1))
        self.assertEqual(len(app.manual_clicks), 2)

    def test_refresh_removes_previous_map_pin_hit_targets(self):
        app = app_fixture()
        renderer.draw_map(app)
        self.assertTrue(app._map_pin_hits)
        app.image = None
        renderer.draw_map(app)
        self.assertFalse(app._map_pin_hits)
        self.assertFalse(app._map_badge_hits)
        self.assertFalse(app.canvas.tagged("basement"))

    def test_precise_anchor_dot_remains_exact_and_is_drawn_above_badges(self):
        app = app_fixture()
        renderer.draw_map(app)
        ox, oy, sx, sy = app.transform
        for point in app.data.points:
            native = app._project_map_point(point.x, point.y)
            expected = (ox+(native[0]-200)*sx, oy+(native[1]-40)*sy)
            dot = next(item for item in app.canvas.tagged("poi_anchor")
                       if point.id in item["tags"] and item["kind"] == "oval")
            x0, y0, x1, y1 = dot["coordinates"]
            self.assertEqual(((x0+x1)/2, (y0+y1)/2), expected)
            self.assertLessEqual(x1-x0, 4)
            self.assertEqual(app._map_pin_hits[point.id][:2], expected)
        ids = list(app.canvas.items)
        last_badge = max(item_id for item_id in ids if "basement" in app.canvas.items[item_id].get("tags", ()))
        first_anchor = min(item_id for item_id in ids if "poi_anchor" in app.canvas.items[item_id].get("tags", ()))
        self.assertGreater(first_anchor, last_badge)

    def test_edge_anchor_stays_at_projection_while_badge_is_kept_on_canvas(self):
        app = app_fixture(count=1)
        point = Point("edge", "Edge room", .001, .001)
        app.data = MapData("test", "Test", 8000, {}, (point,))
        app._ordered_targets = lambda: [(point, 100)]
        renderer.draw_map(app)
        ox, oy, sx, sy = app.transform
        x, y, _ = app._map_pin_hits[point.id]
        self.assertAlmostEqual(x, ox+.001*800*sx)
        self.assertAlmostEqual(y, oy+.001*800*sy)
        bx, by, radius = app._map_badge_hits[point.id]
        self.assertGreaterEqual(bx-radius, 0)
        self.assertGreaterEqual(by-radius, 0)
        self.assertLessEqual(bx+radius, app.canvas.width)
        self.assertLessEqual(by+radius, app.canvas.height)
