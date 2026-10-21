import json
from pathlib import Path
import tempfile
import unittest

import cv2
import numpy as np
from PIL import Image

from lootlizard.core import Bounds
from lootlizard.vision import Profile, create_profile, recognize


BOUNDS = Bounds(40, 40, 440, 440)
COLOR = (245, 30, 210)


def terrain(seed=19):
    random = np.random.default_rng(seed)
    texture = random.integers(15, 165, (400, 400, 3), dtype=np.uint8)
    texture = cv2.GaussianBlur(texture, (3, 3), .6)
    # Distinctive map features spread over all quadrants.
    for _ in range(90):
        x, y = random.integers(5, 375, 2)
        cv2.rectangle(texture, (int(x), int(y)), (int(x + 8), int(y + 13)), (20, 25, 35), 2)
    image = np.full((480, 480, 3), 8, dtype=np.uint8)
    image[40:440, 40:440] = texture
    return image


def icon_mask():
    mask = np.zeros((35, 35), np.uint8)
    polygon = np.array(((17, 4), (29, 23), (21, 20), (21, 29),
                        (13, 29), (13, 20), (5, 23)), np.int32)
    cv2.fillPoly(mask, [polygon], 255)
    return mask


def place(image, center, angle=0, color=COLOR):
    image = image.copy()
    mask = cv2.warpAffine(icon_mask(), cv2.getRotationMatrix2D((17, 17), angle, 1),
                          (35, 35), flags=cv2.INTER_NEAREST)
    x, y = center
    patch = image[y - 17:y + 18, x - 17:x + 18]
    patch[mask != 0] = color
    return image


class VisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.background = terrain()
        cls.initial = place(cls.background, (150, 170))
        cls.profile = create_profile(Image.fromarray(cls.initial), BOUNDS,
                                     (133, 153, 168, 188), (150, 170), "test")

    def test_changed_background_position_and_rotation(self):
        for angle in (0, 37, 90, 143, 270):
            with self.subTest(angle=angle):
                frame = place(self.background, (340, 305), angle)
                result = recognize(Image.fromarray(frame), self.profile, "test")
                self.assertIsNotNone(result.position, result.reason)
                self.assertAlmostEqual(result.position[0], .75, delta=.01)
                self.assertAlmostEqual(result.position[1], .6625, delta=.01)
                self.assertGreaterEqual(result.score, .82)

    def test_two_similar_icons_are_ambiguous(self):
        frame = place(place(self.background, (130, 140)), (340, 305), 37)
        result = recognize(Image.fromarray(frame), self.profile, "test")
        self.assertIsNone(result.position)
        self.assertIn("Ambiguous", result.reason)

    def test_marker_absent_never_reuses_old_location(self):
        found = recognize(Image.fromarray(self.initial), self.profile, "test")
        self.assertIsNotNone(found.position, found.reason)
        self.assertTrue(found.layout_verified)
        missing = recognize(Image.fromarray(self.background), self.profile, "test")
        self.assertIsNone(missing.position)
        self.assertTrue(missing.layout_verified, "A missing icon must not hide a verified map's circle")

    def test_same_color_different_shape_and_different_color_same_shape(self):
        frame = place(self.background, (340, 305), 37)
        frame = place(frame, (150, 300), 0, (20, 240, 210))
        cv2.circle(frame, (300, 140), 10, COLOR, -1)
        result = recognize(Image.fromarray(frame), self.profile, "test")
        self.assertIsNotNone(result.position, result.reason)
        self.assertAlmostEqual(result.position[0], .75, delta=.01)

    def test_uniform_color_extent_does_not_match_foreground_only(self):
        frame = self.background.copy()
        cv2.rectangle(frame, (230, 230), (290, 290), COLOR, -1)
        self.assertIsNone(recognize(Image.fromarray(frame), self.profile, "test").position)

    def test_wrong_map_id_size_layout_zoom_and_closed_map_reject(self):
        frames = []
        changed = self.initial.copy()
        changed[40:440, 40:440] = cv2.warpAffine(
            changed[40:440, 40:440], np.float32(((1, 0, 14), (0, 1, 0))), (400, 400))
        frames.append(changed)
        zoomed = self.initial.copy()
        zoomed[40:440, 40:440] = cv2.warpAffine(
            zoomed[40:440, 40:440], cv2.getRotationMatrix2D((200, 200), 0, 1.06), (400, 400))
        frames += [zoomed, terrain(43), np.zeros_like(self.initial)]
        for index, frame in enumerate(frames):
            with self.subTest(frame=index):
                result = recognize(Image.fromarray(frame), self.profile, "test")
                self.assertIsNone(result.position)
                self.assertFalse(result.layout_verified, "Wrong map layout must not enable circle classification")
        self.assertIsNone(recognize(Image.fromarray(self.initial), self.profile, "other").position)
        self.assertIsNone(recognize(Image.new("RGB", (481, 480)), self.profile, "test").position)

    def test_uniform_or_edge_connected_training_patch_rejected(self):
        frame = self.background.copy()
        frame[153:188, 133:168] = COLOR
        with self.assertRaises(ValueError):
            create_profile(Image.fromarray(frame), BOUNDS, (133, 153, 168, 188), (150, 170), "test")
        # Selecting a background pixel connects to the patch's surrounding border.
        with self.assertRaises(ValueError):
            create_profile(Image.fromarray(self.initial), BOUNDS, (133, 153, 168, 188), (134, 154), "test")

    def test_blank_map_cannot_create_a_profile(self):
        frame = place(np.zeros_like(self.initial), (150, 170))
        with self.assertRaises(ValueError):
            create_profile(Image.fromarray(frame), BOUNDS, (133, 153, 168, 188), (150, 170), "test")

    def test_profile_roundtrip_preserves_result(self):
        with tempfile.TemporaryDirectory() as folder:
            self.profile.save(Path(folder))
            loaded = Profile.load(Path(folder))
            self.assertEqual(loaded.image_size, (480, 480))
            self.assertEqual(loaded.bounds, BOUNDS)
            np.testing.assert_array_equal(loaded.mask, self.profile.mask)
            np.testing.assert_array_equal(loaded.reference, self.profile.reference)
            frame = Image.fromarray(place(self.background, (340, 305), 37))
            self.assertIsNotNone(recognize(frame, loaded, "test").position)
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()),
                             ["mask.png", "profile.json", "reference.png"])

    def test_profile_limits_and_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            self.profile.save(path)
            data = json.loads((path / "profile.json").read_text())
            data["image_size"] = [True, 480]
            (path / "profile.json").write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                Profile.load(path)
            (path / "profile.json").write_text(" " * 16_385)
            with self.assertRaises(ValueError):
                Profile.load(path)


if __name__ == "__main__":
    unittest.main()
