"""Real synthetic-image CV integration; not evidence of PUBG accuracy."""
import importlib.util
import json
from pathlib import Path
import unittest

import cv2
import numpy as np
from PIL import Image, ImageDraw


SOURCE = Path(__file__).resolve().parents[1] / "web/poc/python_bridge.py"
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
