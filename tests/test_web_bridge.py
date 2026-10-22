"""Real synthetic-image CV integration; not evidence of PUBG accuracy."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageDraw


SOURCE = Path(__file__).resolve().parents[1] / "web/app/python_bridge.py"
SPEC = importlib.util.spec_from_file_location("browser_python_bridge", SOURCE)
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


def terrain(seed=47):
    random = np.random.default_rng(seed)
    image = random.integers(25, 170, (640, 640, 3), dtype=np.uint8)
    image = cv2.GaussianBlur(image, (5, 5), 1.)
    for _ in range(180):
        x, y = random.integers(6, 605, 2)
        w, h = random.integers(5, 27, 2)
        color = tuple(int(v) for v in random.integers(5, 240, 3))
        cv2.rectangle(image, (int(x), int(y)), (int(x+w), int(y+h)), color, 2)
    for _ in range(25):
        a, b = random.integers(0, 640, (2, 2))
        cv2.line(image, tuple(a.tolist()), tuple(b.tolist()), (210, 195, 160), 2)
    return image


def frame(canonical, *, side=520, x=100, y=50):
    return cv2.warpAffine(canonical, np.float32(((side/640, 0, x), (0, side/640, y))),
                          (800, 640), flags=cv2.INTER_LINEAR, borderValue=(8, 8, 8))


def rgba(image):
    image = Image.fromarray(image) if isinstance(image, np.ndarray) else image
    return image.convert("RGBA").tobytes()


def data(map_id):
    return dict(id=map_id, name=map_id, size_m=8000, source={}, points=[
        dict(id="center", name="Center", x=.5, y=.5),
        dict(id="edge", name="Edge", x=.05, y=.05)])


def icon_patch():
    image = Image.new("RGB", (330, 330), (35, 35, 35))
    draw = ImageDraw.Draw(image)
    draw.pieslice((94, 94, 226, 226), 180, 270, fill=(110, 110, 110))
    draw.line((94, 160, 160, 160, 160, 94), fill=(225, 225, 225), width=2)
    draw.ellipse((148, 148, 172, 172), fill=(200, 188, 35), outline="white", width=2)
    draw.ellipse((159, 159, 161, 161), fill="white")
    return image


class WebBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = terrain(), terrain(103)

    def engine(self, records=None):
        result = bridge.BrowserVisionEngine([data("map-a"), data("map-b")])
        result.set_references(records or [self.reference("map-a", self.a)])
        return result

    def reference(self, map_id, image):
        h, w = image.shape[:2]
        return dict(mapId=map_id, rgba=rgba(image), width=w, height=h)

    def analyze(self, engine, image, **options):
        h, w = image.shape[:2]
        return engine.analyze_rgba(memoryview(rgba(image)), w, h, **options)

    def test_runtime_probe_executes_sift_and_affine(self):
        result = bridge.capabilities()
        self.assertTrue(result["sift"])
        self.assertTrue(result["affine"])
        self.assertEqual(result["referenceSide"], 1800)
        self.assertEqual(result["maxReferences"], 32)

    def test_identifies_map_and_projects_into_supplied_frame_pixels(self):
        engine = self.engine([self.reference("map-a", self.a), self.reference("map-b", self.b)])
        result = self.analyze(engine, frame(self.b), context="replay", ticket=19)
        self.assertEqual(result["ticket"], 19)
        self.assertEqual(result["registration"]["mapId"], "map-b")
        matrix = np.asarray(result["registration"]["matrix"])
        np.testing.assert_allclose(matrix @ (.5, .5, 1), (360, 310, 1), atol=2.)
        center = result["points"][0]
        self.assertTrue(center["visible"])
        np.testing.assert_allclose((center["imageX"], center["imageY"]), (360, 310), atol=2.)
        json.dumps(result, allow_nan=False)

    def test_unknown_fresh_frame_never_reuses_geometry_or_points(self):
        engine = self.engine()
        known = self.analyze(engine, frame(self.a), context="replay")
        self.assertIsNotNone(known["registration"])
        unknown = self.analyze(engine, frame(terrain(999)), context="replay", ticket=20)
        self.assertIsNone(unknown["registration"])
        self.assertIsNone(unknown["position"])
        self.assertIsNone(unknown["zone"])
        self.assertEqual(unknown["points"], [])

    def test_match_map_lock_rechecks_one_reference_and_reset_restores_full_search(self):
        engine = self.engine([self.reference("map-a", self.a), self.reference("map-b", self.b)])
        with patch.object(bridge, "register_map", wraps=bridge.register_map) as register:
            locked = self.analyze(engine, frame(self.a), context="map-only", map_id="map-a")
            self.assertEqual(locked["registration"]["mapId"], "map-a")
            self.assertEqual([ref.map_id for ref in register.call_args.args[1]], ["map-a"])
            unknown = self.analyze(engine, frame(self.b), context="map-only", map_id="map-a")
            self.assertIsNone(unknown["registration"], "A different map cannot replace the current match")
            self.assertEqual(unknown["points"], [])
            reset = self.analyze(engine, frame(self.b), context="map-only")
            self.assertEqual(reset["registration"]["mapId"], "map-b")
            self.assertEqual(len(register.call_args.args[1]), 2)
        for hint, context in [("missing", "map-only"), (1, "map-only"), ("map-a", "live")]:
            with self.subTest(hint=hint, context=context), self.assertRaises(ValueError):
                self.analyze(engine, frame(self.a), context=context, map_id=hint)

    def test_ambiguous_references_withhold_all_geometry(self):
        engine = self.engine([self.reference("map-a", self.a), self.reference("map-b", self.a)])
        result = self.analyze(engine, frame(self.a))
        self.assertIsNone(result["registration"])
        self.assertIn("Ambiguous", result["reason"])
        self.assertEqual(result["points"], [])

    def test_zoom_pan_clips_points_and_does_not_normalize_partial_map_as_zone(self):
        result = self.analyze(self.engine(), frame(self.a, side=1280, x=-380, y=-310), context="replay")
        self.assertEqual(result["registration"]["mapId"], "map-a")
        np.testing.assert_allclose((result["points"][0]["imageX"], result["points"][0]["imageY"]),
                                   (260, 330), atol=3.)
        self.assertFalse(result["points"][1]["visible"])
        self.assertIsNone(result["points"][1]["imageX"])
        self.assertIsNone(result["zone"])
        self.assertIn("clipped", result["zoneReason"])

    def test_actual_automatic_cone_pipeline_returns_normalized_estimate(self):
        canonical = Image.fromarray(self.a)
        canonical.paste(icon_patch(), (160, 160))
        result = self.analyze(self.engine(), frame(np.asarray(canonical)))
        self.assertEqual(result["registration"]["mapId"], "map-a")
        self.assertIsNotNone(result["position"], result["markerReason"])
        np.testing.assert_allclose((result["position"]["x"], result["position"]["y"]), (.5, .5), atol=.009)
        self.assertEqual(result["position"]["method"], "view-cone")
        self.assertFalse(result["position"]["identityVerified"])

    def test_replay_with_an_actual_cone_keeps_map_but_never_player_estimate(self):
        canonical = Image.fromarray(self.a)
        canonical.paste(icon_patch(), (160, 160))
        result = self.analyze(self.engine(), frame(np.asarray(canonical)), context="replay")
        self.assertIsNotNone(result["registration"])
        self.assertIsNone(result["position"])
        self.assertIn("Replay", result["markerReason"])

    def test_actual_white_ring_returns_canonical_geometry(self):
        canonical = self.a.copy()
        cv2.circle(canonical, (275, 245), 158, (245, 245, 245), 2, cv2.LINE_AA)
        result = self.analyze(self.engine(), frame(canonical), context="replay")
        self.assertIsNotNone(result["zone"], result["zoneReason"])
        self.assertAlmostEqual(result["zone"]["centerX"], 275/640, delta=.012)
        self.assertAlmostEqual(result["zone"]["centerY"], 245/640, delta=.012)
        self.assertAlmostEqual(result["zone"]["radius"], 158/640, delta=.012)

    def test_map_only_registers_and_projects_without_running_marker_or_circle_detection(self):
        canonical = Image.fromarray(self.a)
        canonical.paste(icon_patch(), (160, 160))
        pixels = np.asarray(canonical).copy()
        cv2.circle(pixels, (275, 245), 158, (245, 245, 245), 2, cv2.LINE_AA)
        engine = self.engine()
        with patch.object(bridge, "recognize_registered_marker") as marker, \
                patch.object(bridge, "detect_safe_zone") as circle, \
                patch.object(bridge, "_full_map_bounds") as bounds:
            result = self.analyze(engine, frame(pixels), context="map-only", ticket={"epoch": 4, "sequence": 2})
        marker.assert_not_called()
        circle.assert_not_called()
        bounds.assert_not_called()
        self.assertEqual(result["registration"]["mapId"], "map-a")
        self.assertEqual(result["ticket"], {"epoch": 4, "sequence": 2})
        self.assertEqual(len(result["points"]), 2)
        center = next(point for point in result["points"] if point["id"] == "center")
        np.testing.assert_allclose((center["imageX"], center["imageY"]), (360, 310), atol=2.)
        self.assertIsNone(result["position"])
        self.assertIsNone(result["zone"])
        self.assertIn("disabled in map-only", result["markerReason"])
        self.assertIn("disabled in map-only", result["zoneReason"])
        self.assertEqual(result["timings"]["markerMs"], 0.)
        self.assertEqual(result["timings"]["zoneMs"], 0.)
        self.assertGreater(result["timings"]["registrationMs"], 0.)
        json.dumps(result, allow_nan=False)

    def test_unknown_and_empty_reference_map_only_never_run_optional_detectors(self):
        engines = (self.engine(), bridge.BrowserVisionEngine([data("map-a")]))
        with patch.object(bridge, "recognize_registered_marker") as marker, \
                patch.object(bridge, "detect_safe_zone") as circle:
            for engine in engines:
                with self.subTest(reference_count=len(engine.references)):
                    result = self.analyze(engine, frame(terrain(999)), context="map-only")
                    self.assertIsNone(result["registration"])
                    self.assertIsNone(result["position"])
                    self.assertIsNone(result["zone"])
                    self.assertEqual(result["points"], [])
                    self.assertEqual(result["timings"]["markerMs"], 0.)
                    self.assertEqual(result["timings"]["zoneMs"], 0.)
        marker.assert_not_called()
        circle.assert_not_called()

    def test_reference_capacity_accepts_a_complete_32_map_catalog_and_rejects_33_atomically(self):
        maps = [data(f"map-{i}") for i in range(32)]
        engine = bridge.BrowserVisionEngine(maps)
        records = [self.reference(record["id"], self.a[:128, :128]) for record in maps]
        # Capacity/transaction coverage does not need 32 SIFT feature builds;
        # real reference construction and registration are exercised separately.
        with patch.object(bridge, "MapReference", side_effect=lambda map_id, image:
                          SimpleNamespace(map_id=map_id, image_size=image.size)) as construct:
            result = engine.set_references(records)
            self.assertEqual(result["count"], 32)
            self.assertEqual(construct.call_count, 32)
            previous = engine.references
            with self.assertRaisesRegex(ValueError, "at most 32"):
                engine.set_references(records + records[:1])
            self.assertIs(engine.references, previous)
            self.assertEqual(construct.call_count, 32, "Reject over-capacity input before decoding/building references")

    def test_reference_transaction_failure_preserves_previous_catalog(self):
        engine = self.engine()
        invalid = self.reference("map-a", np.zeros((640, 640, 3), np.uint8))
        with self.assertRaises(ValueError):
            engine.set_references([self.reference("map-b", self.b), invalid])
        result = self.analyze(engine, frame(self.a), context="replay")
        self.assertEqual(result["registration"]["mapId"], "map-a")
        self.assertEqual(len(engine.references), 1)

    def test_reference_resize_bounds_cache_without_changing_normalized_map(self):
        large = cv2.resize(self.a, (2200, 2200))
        engine = self.engine([self.reference("map-a", large)])
        self.assertEqual(engine.references[0].image_size, (1800, 1800))
        result = self.analyze(engine, frame(self.a), context="replay")
        np.testing.assert_allclose((result["points"][0]["imageX"], result["points"][0]["imageY"]),
                                   (360, 310), atol=2.)

    def test_clear_removes_references_and_previous_outputs(self):
        engine = self.engine()
        self.assertEqual(engine.clear()["count"], 0)
        result = self.analyze(engine, frame(self.a), context="replay")
        self.assertIsNone(result["registration"])
        self.assertEqual(result["points"], [])
        self.assertIn("No canonical", result["reason"])

    def test_no_references_validate_without_decoding_or_registering(self):
        engine = bridge.BrowserVisionEngine([data("map-a")])
        pixels = memoryview(bytes((12, 34, 56, 255, 78, 90, 12, 255)))
        ticket = {"epoch": 7, "sequence": 3}
        with patch.object(bridge, "_rgba_image") as decode, \
                patch.object(bridge, "register_map") as register, \
                patch.object(bridge.time, "perf_counter", side_effect=(10., 10.004)):
            result = engine.analyze_rgba(pixels, 2, 1, context="replay", ticket=ticket)
        decode.assert_not_called()
        register.assert_not_called()
        timings = result.pop("timings")
        self.assertEqual(result, dict(ticket=ticket, width=2, height=1, registration=None,
            position=None, zone=None, points=[], reason="No canonical map references are loaded",
            markerReason="Map layout is not verified; player position is unknown.",
            zoneReason="Map layout is not verified; safe zone is unknown."))
        self.assertEqual({key: value for key, value in timings.items() if key != "totalMs"},
                         dict(decodeMs=0., registrationMs=0., markerMs=0., zoneMs=0.))
        self.assertAlmostEqual(timings["totalMs"], 4.)
        json.dumps(result, allow_nan=False)

    def test_no_references_still_reject_invalid_input(self):
        engine = bridge.BrowserVisionEngine([])
        opaque = bytes((12, 34, 56, 255))
        cases = (
            (opaque, 1, 1, "unknown"),
            (opaque, True, 1, "live"),
            (opaque, 1., 1, "live"),
            (opaque, 0, 1, "live"),
            (opaque, 1, -1, "live"),
            (b"", 2401, 1, "live"),
            (b"", 2400, 2400, "live"),
            (object(), 1, 1, "live"),
            (opaque[:-1], 1, 1, "live"),
            (opaque + opaque, 1, 1, "live"),
            (memoryview(bytearray(8))[::2], 1, 1, "live"),
            (memoryview(np.array((1, 2), dtype=np.uint16)), 1, 1, "live"),
            (bytes((12, 34, 56, 254)), 1, 1, "live"),
        )
        with patch.object(bridge, "_rgba_image") as decode, \
                patch.object(bridge, "register_map") as register:
            for pixels, width, height, context in cases:
                with self.subTest(size=(width, height), context=context, buffer_type=type(pixels)), \
                        self.assertRaises(ValueError):
                    engine.analyze_rgba(pixels, width, height, context=context)
        decode.assert_not_called()
        register.assert_not_called()

    def test_bad_buffers_context_and_catalog_are_rejected(self):
        engine = self.engine()
        for buffer, w, h in ((b"bad", 640, 640), (b"", 2401, 1), (b"", True, 2), (b"", 2400, 2400)):
            with self.subTest(size=(w, h)), self.assertRaises(ValueError):
                engine.analyze_rgba(buffer, w, h)
        with self.assertRaises(ValueError):
            self.analyze(engine, frame(self.a), context="unknown")
        with self.assertRaises(ValueError):
            bridge.BrowserVisionEngine([data("map-a"), data("map-a")])
        with self.assertRaises(ValueError):
            engine.set_references([self.reference("missing-map", self.a)])
        with self.assertRaises(ValueError):
            engine.set_references([self.reference("map-a", self.a)] * 9)
        transparent = bytearray(rgba(frame(self.a)))
        transparent[3] = 0
        with self.assertRaises(ValueError):
            engine.analyze_rgba(transparent, 800, 640)


if __name__ == "__main__":
    unittest.main()
