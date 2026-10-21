import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, Mock, patch
import unittest

import cv2
import numpy as np
from PIL import Image

from lootlizard.registration import MapReference, load_reference_catalog, project_poi, register_map


VIEWPORT = (40, 30, 760, 610)  # Deliberately non-square, in full screenshot pixels.


def terrain(seed=47):
    random = np.random.default_rng(seed)
    image = random.integers(25, 170, (640, 640, 3), dtype=np.uint8)
    image = cv2.GaussianBlur(image, (5, 5), 1.)
    for _ in range(180):
        x, y = random.integers(6, 605, 2)
        width, height = random.integers(5, 27, 2)
        color = tuple(int(value) for value in random.integers(5, 240, 3))
        cv2.rectangle(image, (int(x), int(y)), (int(x+width), int(y+height)), color, 2)
    for _ in range(25):
        a, b = random.integers(0, 640, (2, 2))
        cv2.line(image, tuple(a.tolist()), tuple(b.tolist()), (210, 195, 160), 2)
    return image


def view(canonical, side=520, x=100, y=50, *, stretch=1., angle=0.):
    height, width = canonical.shape[:2]
    scale = side / width
    rotation = cv2.getRotationMatrix2D((0., 0.), angle, scale)
    rotation[1, :2] *= stretch
    rotation[:, 2] = (x, y)
    return cv2.warpAffine(canonical, rotation, (800, 640),
                          flags=cv2.INTER_LINEAR, borderValue=(8, 8, 8))


def shared_border_ui(canonical, *, shared_center=False):
    """Two unrelated maps can share the same grid labels and HUD symbols."""
    image = canonical.copy()
    image[:24] = image[-24:] = (18, 22, 26)
    image[:, :24] = image[:, -24:] = (18, 22, 26)
    for index, label in enumerate("ABCDEFGH"):
        cv2.putText(image, label, (45+index*76, 17), cv2.FONT_HERSHEY_SIMPLEX,
                    .5, (245, 245, 245), 1, cv2.LINE_AA)
    for index, label in enumerate("JKLMNOPQ"):
        cv2.putText(image, label, (5, 48+index*76), cv2.FONT_HERSHEY_SIMPLEX,
                    .5, (245, 245, 245), 1, cv2.LINE_AA)
    for index, label in enumerate(("PING", "FPS", "STATUS", "NET")):
        cv2.putText(image, label, (50+index*155, 632), cv2.FONT_HERSHEY_SIMPLEX,
                    .4, (245, 245, 245), 1, cv2.LINE_AA)
    for index in range(5):
        cv2.circle(image, (628, 70+index*110), 7, (245, 245, 245), 1)
        cv2.line(image, (621, 70+index*110), (635, 70+index*110), (245, 245, 245), 1)
    if shared_center:
        # A repeated marker/label patch is more detailed than an actual icon,
        # but still must not establish the geography outside that small patch.
        image[272:368, 272:368] = terrain(800)[272:368, 272:368]
    return image


class RegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = terrain()
        cls.b = terrain(103)
        cls.reference_a = MapReference("map-a", Image.fromarray(cls.a))
        cls.reference_b = MapReference("map-b", cls.b)

    def test_full_view_and_normalized_projection_with_image_offset(self):
        result = register_map(view(self.a), [self.reference_a], VIEWPORT)
        self.assertEqual(result.map_id, "map-a", result.diagnostics)
        for x, y in ((.2, .3), (.5, .5), (.8, .75)):
            actual = result.project_poi(x, y)
            self.assertIsNotNone(actual)
            np.testing.assert_allclose(actual, (100+x*520, 50+y*520), atol=2.)
            np.testing.assert_allclose(result.image_point_to_map(*actual), (x, y), atol=1e-6)
        self.assertGreaterEqual(result.diagnostics["inliers"], 24)
        self.assertGreaterEqual(result.diagnostics["coverage"], .12)
        self.assertLess(result.diagnostics["median_reprojection_error"], 2.)
        self.assertTrue(np.isfinite(result.diagnostics["max_reprojection_error"]))

    def test_zoom_pan_and_offscreen_poi_clipping(self):
        frame = view(self.a, side=1280, x=-380, y=-310)
        result = register_map(frame, [self.reference_a], VIEWPORT)
        self.assertEqual(result.map_id, "map-a", result.diagnostics)
        np.testing.assert_allclose(result.project_poi(.5, .5), (260, 330), atol=3.)
        self.assertIsNone(result.project_poi(.05, .05))
        np.testing.assert_allclose(project_poi(result, .05, .05, clip=False), (-316, -246), atol=3.)
        self.assertIsNone(result.image_point_to_map(0, 0))

    def test_automatic_map_id_with_multiple_references(self):
        result = register_map(view(self.b, side=1100, x=-200, y=-170),
                              [self.reference_a, self.reference_b], VIEWPORT)
        self.assertEqual(result.map_id, "map-b", result.diagnostics)

    def test_unknown_map_is_not_forced_to_a_loaded_id(self):
        result = register_map(view(terrain(999)), [self.reference_a, self.reference_b], VIEWPORT)
        self.assertIsNone(result.map_id)
        self.assertIsNone(result.map_to_image)
        self.assertIsNone(result.image_to_map)
        self.assertIsNone(result.project_poi(.5, .5))

    def test_indistinguishable_map_references_are_rejected(self):
        duplicate = MapReference("other-map", self.a)
        result = register_map(view(self.a), [self.reference_a, duplicate], VIEWPORT)
        self.assertIsNone(result.map_id)
        self.assertIn("Ambiguous", result.reason)

    def test_shared_border_labels_and_icons_do_not_establish_map_identity(self):
        a, b = shared_border_ui(self.a), shared_border_ui(self.b)
        wrong = MapReference("wrong-map", b)
        result = register_map(a, [wrong])
        self.assertIsNone(result.map_id, result.diagnostics)
        candidate = result.diagnostics["candidates"][0]
        self.assertEqual(candidate["reason"], "Map matches lack distributed interior support")
        self.assertLess(candidate["interior_inliers"], 24)

    def test_shared_border_ui_does_not_make_distinct_maps_ambiguous(self):
        a, b = shared_border_ui(self.a), shared_border_ui(self.b)
        result = register_map(a, [MapReference("correct-map", a), MapReference("wrong-map", b)])
        self.assertEqual(result.map_id, "correct-map", result.diagnostics)

    def test_shared_border_plus_small_interior_icon_patch_is_not_map_identity(self):
        a = shared_border_ui(self.a, shared_center=True)
        b = shared_border_ui(self.b, shared_center=True)
        result = register_map(a, [MapReference("wrong-map", b)])
        self.assertIsNone(result.map_id, result.diagnostics)
        candidate = result.diagnostics["candidates"][0]
        self.assertGreaterEqual(candidate["interior_inliers"], 24)
        self.assertLess(candidate["interior_coverage"], .12)

    def test_tiny_matching_patch_does_not_identify_a_map(self):
        frame = np.full((640, 800, 3), 8, np.uint8)
        frame[250:350, 300:450] = self.a[250:350, 300:450]
        result = register_map(frame, [self.reference_a], VIEWPORT)
        self.assertIsNone(result.map_id, result.diagnostics)

    def test_closed_blank_map_and_missing_reference_return_unknown(self):
        self.assertIsNone(register_map(Image.new("RGB", (800, 640)), [self.reference_a], VIEWPORT).map_id)
        self.assertIsNone(register_map(view(self.a), [], VIEWPORT).map_id)

    def test_small_reference_aspect_difference_is_tolerated(self):
        reference = MapReference("legacy", cv2.resize(self.a, (640, 652)))
        result = register_map(view(self.a), [reference], VIEWPORT)
        self.assertEqual(result.map_id, "legacy", result.diagnostics)
        np.testing.assert_allclose(result.project_poi(.5, .5), (360, 310), atol=3.)
        self.assertLessEqual(result.diagnostics["anisotropy"], 1.075)

    def test_excessive_stretch_and_rotation_are_rejected(self):
        for frame in (view(self.a, stretch=1.25), view(self.a, angle=15)):
            with self.subTest():
                result = register_map(frame, [self.reference_a], VIEWPORT)
                self.assertIsNone(result.map_id, result.diagnostics)

    def test_reflected_view_is_rejected(self):
        result = register_map(view(self.a[:, ::-1].copy()), [self.reference_a], VIEWPORT)
        self.assertIsNone(result.map_id, result.diagnostics)

    def test_one_to_four_overlay_icons_are_not_required_for_registration(self):
        for count in range(1, 5):
            frame = view(self.a)
            for index in range(count):
                x, y = 180+index*100, 170+index*60
                cv2.fillPoly(frame, [np.array(((x, y-10), (x+8, y+8), (x-8, y+8)))],
                             (245, 200-index*30, 30+index*40))
            result = register_map(frame, [self.reference_a], VIEWPORT)
            self.assertEqual(result.map_id, "map-a", result.diagnostics)

    def test_reference_and_viewport_validation(self):
        for image in (Image.new("RGB", (500, 500)), Image.new("RGB", (400, 700))):
            with self.subTest(size=image.size), self.assertRaises(ValueError):
                MapReference("invalid", image)
        for viewport in ((-1, 0, 700, 600), (0, 0, 90, 90), (True, 0, 700, 600), (0, 0, 900, 700)):
            with self.subTest(viewport=viewport):
                self.assertIsNone(register_map(view(self.a), [self.reference_a], viewport).map_id)
        duplicate_id = MapReference("map-a", self.b)
        self.assertIsNone(register_map(view(self.a), [self.reference_a, duplicate_id], VIEWPORT).map_id)

    def test_projection_rejects_invalid_points(self):
        result = register_map(view(self.a), [self.reference_a], VIEWPORT)
        for point in ((-.1, .5), (1.1, .5), (float("nan"), .5), (True, .5), ("x", .5)):
            with self.subTest(point=point):
                self.assertIsNone(result.project_poi(*point))


class ReferenceCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "maps").mkdir()
        self.image = self.root / "maps" / "synthetic.png"
        Image.fromarray(terrain()).save(self.image)
        self.catalog = self.root / "catalog.json"

    def write(self, records, version=1):
        self.catalog.write_text(json.dumps({"schema_version": version, "references": records}), encoding="utf-8")
        return self.catalog

    def record(self, **values):
        return {"map_id": "synthetic-map", "file": "maps/synthetic.png", **values}

    def test_nested_rgb_png_jpeg_and_optional_hash_load_without_file_copies(self):
        jpeg = self.root / "maps" / "synthetic.jpg"
        Image.fromarray(terrain(103)).save(jpeg)
        digest = hashlib.sha256(self.image.read_bytes()).hexdigest()
        path = self.write([self.record(sha256=digest),
                           {"map_id": "second-map", "file": "maps/synthetic.jpg"}])
        before = {item.relative_to(self.root): item.read_bytes()
                  for item in self.root.rglob("*") if item.is_file()}
        references = load_reference_catalog(path)
        self.assertIsInstance(references, tuple)
        self.assertEqual([reference.map_id for reference in references], ["synthetic-map", "second-map"])
        self.assertTrue(all(isinstance(reference, MapReference) for reference in references))
        self.assertEqual(references[0].image_size, (640, 640))
        after = {item.relative_to(self.root): item.read_bytes()
                 for item in self.root.rglob("*") if item.is_file()}
        self.assertEqual(before, after)

    def test_catalog_rejects_absolute_traversal_drive_and_stream_paths(self):
        for filename in ("../outside.png", "/outside.png", "C:/outside.png",
                         "C:relative.png", "maps/synthetic.png:stream", "maps\\..\\synthetic.png"):
            with self.subTest(file=filename), self.assertRaises(ValueError):
                load_reference_catalog(self.write([self.record(file=filename)]))

    def test_catalog_rejects_symlink_escape(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "external.png"
            target.write_bytes(self.image.read_bytes())
            link = self.root / "maps" / "linked.png"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("Creating symlinks is unavailable on this host")
            with self.assertRaises(ValueError):
                load_reference_catalog(self.write([self.record(file="maps/linked.png")]))

    def test_catalog_version_count_and_duplicate_map_ids_are_validated(self):
        for version in (True, 0, 2):
            with self.subTest(version=version), self.assertRaises(ValueError):
                load_reference_catalog(self.write([], version))
        with self.assertRaises(ValueError):
            load_reference_catalog(self.write([self.record(), self.record()]))
        with self.assertRaises(ValueError):
            load_reference_catalog(self.write([self.record(map_id=str(i)) for i in range(33)]))
        self.assertEqual(load_reference_catalog(self.write([])), ())

    def test_hash_mismatch_and_malformed_hash_are_rejected(self):
        for digest in ("0" * 64, "bad-hash", 123):
            with self.subTest(sha256=digest), self.assertRaises(ValueError):
                load_reference_catalog(self.write([self.record(sha256=digest)]))

    def test_catalog_size_limit_is_enforced(self):
        self.catalog.write_text(" " * (128 * 1024 + 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "128 KiB"):
            load_reference_catalog(self.catalog)

    def test_header_dimensions_are_checked_before_decoding_pixels(self):
        path = self.write([self.record()])
        for dimensions in ((8193, 128), (8192, 8192)):
            with self.subTest(size=dimensions):
                image = Mock(size=dimensions, mode="RGB", format="PNG")
                opened = MagicMock()
                opened.__enter__.return_value = image
                with patch("PIL.Image.open", return_value=opened), self.assertRaises(ValueError):
                    load_reference_catalog(path)
                image.load.assert_not_called()

    def test_non_rgb_reference_is_rejected(self):
        Image.new("RGBA", (640, 640)).save(self.image)
        with self.assertRaisesRegex(ValueError, "RGB PNG or JPEG"):
            load_reference_catalog(self.write([self.record()]))


if __name__ == "__main__":
    unittest.main()
