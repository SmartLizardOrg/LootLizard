"""Synthetic geometry/adversarial checks, not a claim of game-image accuracy."""

import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image

from lootlizard.core import Bounds
from lootlizard.zone_vision import detect_safe_zone


SIDE = 512
BOUNDS = Bounds(32, 24, 32 + SIDE, 24 + SIDE)
WHITE = (245, 245, 245)
BLUE = (25, 120, 250)
YELLOW = (250, 215, 30)


def scene(seed=37, roads=True):
    random = np.random.default_rng(seed)
    texture = random.integers(25, 140, (SIDE, SIDE, 3), dtype=np.uint8)
    texture = cv2.GaussianBlur(texture, (5, 5), 1.)
    if roads:
        for points in (((0, 90), (110, 100), (180, 200), (360, 180), (511, 60)),
                       ((60, 0), (145, 150), (100, 300), (200, 511)),
                       ((0, 410), (170, 350), (360, 390), (511, 480)),
                       ((440, 0), (400, 180), (440, 300), (350, 511))):
            cv2.polylines(texture, [np.array(points, np.int32)], False, (210, 210, 210),
                          2, cv2.LINE_AA)
        for word, origin in (("YASNAYA", (285, 110)), ("POCHINKI", (90, 280)),
                             ("ERANGEL", (280, 450))):
            cv2.putText(texture, word, origin, cv2.FONT_HERSHEY_SIMPLEX,
                        .55, WHITE, 1, cv2.LINE_AA)
    image = np.full((SIDE + 60, SIDE + 80, 3), 15, np.uint8)
    image[BOUNDS.top:BOUNDS.bottom, BOUNDS.left:BOUNDS.right] = texture
    return image


def ring(image, center, radius, color=WHITE, thickness=2, arc=None):
    result = image.copy()
    crop = result[BOUNDS.top:BOUNDS.bottom, BOUNDS.left:BOUNDS.right]
    if arc is None:
        cv2.circle(crop, center, radius, color, thickness, cv2.LINE_AA)
    else:
        cv2.ellipse(crop, center, (radius, radius), 0, arc[0], arc[1],
                    color, thickness, cv2.LINE_AA)
    return result


class ZoneVisionTests(unittest.TestCase):
    def assertCircle(self, result, center, radius, delta=.012):
        self.assertIsNotNone(result.zone, result.reason)
        self.assertAlmostEqual(result.zone.center_x, center[0] / SIDE, delta=delta)
        self.assertAlmostEqual(result.zone.center_y, center[1] / SIDE, delta=delta)
        self.assertAlmostEqual(result.zone.radius, radius / SIDE, delta=delta)
        self.assertGreaterEqual(result.score, .62)
        self.assertLessEqual(result.score, 1.)

    def test_white_ring_over_roads_text_and_texture(self):
        result = detect_safe_zone(Image.fromarray(ring(scene(), (275, 240), 158)), BOUNDS)
        self.assertCircle(result, (275, 240), 158)

    def test_thin_antialiased_white_ring(self):
        frame = ring(scene(), (275, 240), 158, thickness=1)
        self.assertCircle(detect_safe_zone(Image.fromarray(frame), BOUNDS), (275, 240), 158)

    def test_uhd_screenshot_is_normalized_without_changing_map_coordinates(self):
        small = ring(scene(), (275, 240), 158)
        crop = small[BOUNDS.top:BOUNDS.bottom, BOUNDS.left:BOUNDS.right]
        frame = np.full((2160, 3840, 3), 15, np.uint8)
        frame[40:2120, 880:2960] = cv2.resize(crop, (2080, 2080))
        result = detect_safe_zone(Image.fromarray(frame), Bounds(880, 40, 2960, 2120))
        self.assertCircle(result, (275, 240), 158)

    def test_clipped_large_ring(self):
        result = detect_safe_zone(Image.fromarray(ring(scene(), (125, 260), 300)), BOUNDS)
        self.assertCircle(result, (125, 260), 300)

    def test_slightly_imprecise_square_calibration_preserves_circle_geometry(self):
        frame = ring(scene(), (275, 240), 158)
        bounds = Bounds(BOUNDS.left, BOUNDS.top, BOUNDS.right + 9, BOUNDS.bottom)
        result = detect_safe_zone(Image.fromarray(frame), bounds)
        self.assertIsNotNone(result.zone, result.reason)
        self.assertAlmostEqual(result.zone.center_x, 275 / (SIDE + 9), delta=.012)
        self.assertAlmostEqual(result.zone.center_y, 240 / SIDE, delta=.012)

    def test_white_ring_with_blue_and_yellow_decoys(self):
        frame = ring(scene(), (250, 245), 145)
        frame = ring(frame, (275, 250), 230, BLUE, 4)
        frame = ring(frame, (80, 90), 40, YELLOW, 4)
        self.assertCircle(detect_safe_zone(Image.fromarray(frame), BOUNDS), (250, 245), 145)

    def test_only_blue_or_yellow_boundaries_never_produce_a_zone(self):
        for color in (BLUE, YELLOW, (195, 225, 255), (255, 244, 185)):
            with self.subTest(color=color):
                frame = ring(scene(), (260, 250), 170, color, 4)
                self.assertIsNone(detect_safe_zone(Image.fromarray(frame), BOUNDS).zone)

    def test_roads_text_and_random_white_noise_are_not_a_ring(self):
        frame = scene()
        random = np.random.default_rng(14)
        x, y = random.integers(3, SIDE - 3, (2, 1000))
        frame[y + BOUNDS.top, x + BOUNDS.left] = WHITE
        self.assertIsNone(detect_safe_zone(Image.fromarray(frame), BOUNDS).zone)

    def test_competing_and_concentric_white_rings_are_ambiguous(self):
        for centers, radii in ((((170, 210), (340, 295)), (95, 110)),
                               (((250, 250), (250, 250)), (120, 190))):
            with self.subTest(centers=centers):
                frame = ring(ring(scene(), centers[0], radii[0]), centers[1], radii[1])
                result = detect_safe_zone(Image.fromarray(frame), BOUNDS)
                self.assertIsNone(result.zone)
                self.assertIn("Ambiguous", result.reason)

    def test_short_arc_and_heavily_missing_circle_are_rejected(self):
        for arc in ((0, 70), (0, 180), (0, 240)):
            with self.subTest(arc=arc):
                frame = ring(scene(), (260, 250), 155, arc=arc)
                self.assertIsNone(detect_safe_zone(Image.fromarray(frame), BOUNDS).zone)

    def test_small_dotted_range_circle_is_not_a_safe_zone(self):
        for radius, arc_length in ((25, 3), (25, 8), (35, 8)):
            with self.subTest(radius=radius, arc_length=arc_length):
                frame = scene()
                crop = frame[BOUNDS.top:BOUNDS.bottom, BOUNDS.left:BOUNDS.right]
                for angle in range(0, 360, 20):
                    cv2.ellipse(crop, (85, 420), (radius, radius), 0,
                                angle, angle + arc_length, WHITE, 2, cv2.LINE_AA)
                self.assertIsNone(detect_safe_zone(Image.fromarray(frame), BOUNDS).zone)
                with_safe_zone = ring(frame, (275, 240), 158)
                self.assertCircle(detect_safe_zone(Image.fromarray(with_safe_zone), BOUNDS),
                                  (275, 240), 158)

    def test_filled_disc_and_nearly_uniform_white_image_are_rejected(self):
        frame = ring(scene(), (260, 250), 100, thickness=-1)
        self.assertIsNone(detect_safe_zone(Image.fromarray(frame), BOUNDS).zone)
        self.assertIsNone(detect_safe_zone(Image.new("RGB", (SIDE + 80, SIDE + 60), "white"), BOUNDS).zone)

    def test_circle_outside_calibrated_map_is_ignored(self):
        image = scene(roads=False)
        cv2.circle(image, (10, 12), 8, WHITE, 2)
        self.assertIsNone(detect_safe_zone(Image.fromarray(image), BOUNDS).zone)

    def test_transparent_white_ring_is_not_evidence(self):
        frame = ring(scene(roads=False), (260, 250), 170)
        rgba = np.dstack((frame, np.zeros(frame.shape[:2], np.uint8)))
        self.assertIsNone(detect_safe_zone(Image.fromarray(rgba), BOUNDS).zone)

    def test_invalid_bounds_and_image_are_rejected(self):
        for image, bounds in ((None, BOUNDS), (Image.fromarray(scene()), None),
                              (Image.fromarray(scene()), Bounds(-1, 0, 300, 301)),
                              (Image.new("RGB", (100, 100)), Bounds(0, 0, 90, 90))):
            with self.subTest(bounds=bounds):
                result = detect_safe_zone(image, bounds)
                self.assertIsNone(result.zone)
                self.assertEqual(result.score, 0.)

    def test_opencl_is_disabled_in_the_calling_thread(self):
        with patch("lootlizard.zone_vision.cv2.ocl.setUseOpenCL") as disable:
            detect_safe_zone(Image.fromarray(scene(roads=False)), BOUNDS)
        disable.assert_called_with(False)


if __name__ == "__main__":
    unittest.main()
