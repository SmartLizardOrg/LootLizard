"""Synthetic geometry checks do not establish real PUBG identity accuracy."""

import unittest
import math

from PIL import Image, ImageDraw

from lootlizard.self_marker import assess_view_cone, find_self_marker


COLOR = (200, 188, 35)
CENTER = (160, 160)
RADIUS = 12


def scene(*, fan=True, arrow=False, competing=False):
    image = Image.new("RGB", (330, 330), (35, 35, 35))
    draw = ImageDraw.Draw(image)
    if fan:
        draw.pieslice((94, 94, 226, 226), 180, 270, fill=(110, 110, 110))
        draw.line((94, 160, 160, 160, 160, 94), fill=(225, 225, 225), width=2)
    if competing:
        draw.pieslice((94, 94, 226, 226), 0, 90, fill=(110, 110, 110))
        draw.line((226, 160, 160, 160, 160, 226), fill=(225, 225, 225), width=2)
    if arrow:
        draw.polygon(((160, 148), (172, 172), (148, 172)), fill=COLOR, outline="white")
    else:
        draw.ellipse((148, 148, 172, 172), fill=COLOR, outline="white", width=2)
        draw.ellipse((159, 159, 161, 161), fill="white")
    return image


class ConeEvidenceTests(unittest.TestCase):
    def assess(self, image, **values):
        arguments = dict(marker_color=COLOR, view_context="live", candidate_count=1)
        arguments.update(values)
        return assess_view_cone(image, CENTER, RADIUS, **arguments)

    def test_round_body_and_broad_fan_are_supporting_evidence_only(self):
        result = self.assess(scene())
        self.assertIs(result.supported, True, result.reason)
        self.assertLess(abs(result.heading_degrees - 225), 12)
        self.assertFalse(result.identity_verified)

    def test_small_directional_arrow_does_not_establish_self_identity(self):
        result = self.assess(scene(arrow=True))
        self.assertIsNone(result.supported)
        self.assertFalse(result.identity_verified)

    def test_fan_evidence_is_not_tied_to_one_screen_direction(self):
        for rotation in (90, 180, 270):
            with self.subTest(rotation=rotation):
                result = self.assess(scene().rotate(rotation, center=CENTER))
                self.assertIs(result.supported, True, result.reason)
                expected = (225 - rotation) % 360
                self.assertLess(abs((result.heading_degrees - expected + 180) % 360 - 180), 12)

    def test_round_dropped_marker_without_fan_is_not_positive_evidence(self):
        result = self.assess(scene(fan=False))
        self.assertIs(result.supported, False)
        self.assertIsNone(result.heading_degrees)
        self.assertFalse(result.identity_verified)

    def test_replay_and_unknown_context_abstain_even_with_a_fan(self):
        for context in ("replay", "unknown"):
            with self.subTest(context=context):
                self.assertIsNone(self.assess(scene(), view_context=context).supported)

    def test_multiple_or_unknown_eligible_candidates_abstain(self):
        for count in (None, 0, 2, 3, 4, True):
            with self.subTest(candidate_count=count):
                self.assertIsNone(self.assess(scene(), candidate_count=count).supported)

    def test_white_slot_glyph_does_not_split_a_round_marker_into_false_candidates(self):
        image = scene()
        draw = ImageDraw.Draw(image)
        draw.line((160, 150, 160, 170), fill="white", width=3)
        result = self.assess(image)
        self.assertIs(result.supported, True, result.reason)
        self.assertFalse(result.identity_verified)

    def test_a_distinctly_colored_nearby_ally_is_not_an_extra_eligible_self_candidate(self):
        image = scene()
        draw = ImageDraw.Draw(image)
        draw.ellipse((184, 148, 208, 172), fill=(185, 105, 30), outline="white", width=2)
        result = self.assess(image, candidate_count=1)
        self.assertIs(result.supported, True, result.reason)
        self.assertFalse(result.identity_verified)

    def test_competing_cones_abstain(self):
        result = self.assess(scene(competing=True))
        self.assertIsNone(result.supported, result.reason)

    def test_clipped_and_transparent_evidence_abstain(self):
        self.assertIsNone(self.assess(scene(), viewport=(140, 0, 330, 330)).supported)
        transparent = scene().convert("RGBA")
        transparent.putalpha(100)
        self.assertIsNone(self.assess(transparent).supported)
        palette = scene().convert("P")
        palette.info["transparency"] = 0
        self.assertIsNone(self.assess(palette).supported)


class AutomaticFinderTests(unittest.TestCase):
    def find(self, image, **options):
        return find_self_marker(image, view_context="live", **options)

    def assert_center(self, result, expected, tolerance=3):
        self.assertIsNotNone(result.center, result.reason)
        self.assertLess(math.dist(result.center, expected), tolerance)
        self.assertFalse(result.identity_verified)

    def test_finds_center_without_caller_candidate_and_retains_diagnostics(self):
        result = self.find(scene())
        self.assert_center(result, CENTER)
        self.assertLess(abs(result.heading_degrees - 225), 8)
        self.assertGreater(result.radius_px, 6)
        self.assertEqual(result.radius, result.radius_px)
        self.assertEqual(len(result.candidates), 1)
        self.assertFalse(result.ambiguous)

    def test_viewport_results_use_original_screenshot_coordinates(self):
        image = Image.new("RGB", (600, 550), (20, 20, 20))
        image.paste(scene(), (100, 80))
        self.assert_center(self.find(image, viewport=(100, 80, 430, 410)), (260, 240))

    def test_headings_and_scale_do_not_require_a_fixed_pixel_center(self):
        for scale in (.6, .8, 1., 1.5):
            for rotation in (0, 45, 90, 180, 270):
                with self.subTest(scale=scale, rotation=rotation):
                    image = scene().rotate(rotation, center=CENTER)
                    image = image.resize((round(330 * scale), round(330 * scale)), Image.Resampling.BICUBIC)
                    result = self.find(image)
                    self.assert_center(result, (160 * scale, 160 * scale), 3)
                    self.assertLess(abs((result.heading_degrees - (225 - rotation) + 180) % 360 - 180), 12)

    def test_color_is_inferred_for_different_bright_team_body_colors(self):
        for color in ((185, 105, 30), (35, 170, 200), (60, 80, 210), (210, 70, 100)):
            with self.subTest(color=color):
                image = scene()
                draw = ImageDraw.Draw(image)
                draw.ellipse((148, 148, 172, 172), fill=color, outline="white", width=2)
                draw.text((157, 154), "2", fill="white")
                self.assert_center(self.find(image), CENTER)

    def test_nearby_nonfan_ally_does_not_block_a_single_supported_candidate(self):
        image = scene()
        draw = ImageDraw.Draw(image)
        draw.ellipse((184, 148, 208, 172), fill=(185, 105, 30), outline="white", width=2)
        self.assert_center(self.find(image), CENTER)

    def test_two_distinct_fan_bodies_abstain_and_expose_ambiguity(self):
        image = Image.new("RGB", (700, 370), (35, 35, 35))
        image.paste(scene(), (10, 20))
        image.paste(scene().rotate(180, center=CENTER), (360, 20))
        result = self.find(image)
        self.assertIsNone(result.center)
        self.assertTrue(result.ambiguous)
        self.assertGreaterEqual(len(result.candidates), 2)

    def test_single_body_with_competing_fans_abstains(self):
        result = self.find(scene(competing=True))
        self.assertIsNone(result.center)
        self.assertTrue(result.ambiguous)

    def test_arrow_and_dropped_pin_and_disc_without_fan_are_not_own_estimates(self):
        pin = scene()
        draw = ImageDraw.Draw(pin)
        draw.polygon(((148, 164), (172, 164), (160, 193)), fill=COLOR, outline="white")
        for image in (scene(arrow=True), scene(fan=False), pin):
            with self.subTest(image=image):
                self.assertIsNone(self.find(image).center)

    def test_dark_terrain_and_partial_fan_occlusion(self):
        image = scene()
        pixels = image.load()
        for y in range(image.height):
            for x in range(image.width):
                if pixels[x, y] == (35, 35, 35):
                    pixels[x, y] = (25 + x % 9, 33 + y % 9, 12)
        ImageDraw.Draw(image).line((110, 145, 150, 105), fill=(20, 30, 10), width=4)
        self.assert_center(self.find(image), CENTER)

    def test_crossing_constant_brightness_roads_do_not_replace_a_fan(self):
        image = scene(fan=False)
        draw = ImageDraw.Draw(image)
        draw.line((5, 160, 325, 160), fill=(220, 220, 220), width=2)
        draw.line((160, 5, 160, 325), fill=(220, 220, 220), width=2)
        draw.ellipse((148, 148, 172, 172), fill=COLOR, outline="white", width=2)
        self.assertIsNone(self.find(image).center)

    def test_replay_unknown_transparency_and_clipping_abstain(self):
        for context in ("replay", "observer", "unknown"):
            self.assertIsNone(find_self_marker(scene(), view_context=context).center)
        rgba = scene().convert("RGBA")
        rgba.putalpha(100)
        self.assertIsNone(self.find(rgba).center)
        self.assertIsNone(self.find(scene(), viewport=(140, 0, 330, 330)).center)
        self.assertIsNone(self.find(scene(), viewport=(-1, 0, 330, 330)).center)

    def test_dim_observer_style_body_cannot_gain_identity_from_a_fan(self):
        image = scene()
        draw = ImageDraw.Draw(image)
        draw.ellipse((148, 148, 172, 172), fill=(118, 58, 45), outline="white", width=2)
        draw.text((157, 154), "6", fill="white")
        self.assertIsNone(self.find(image).center)


if __name__ == "__main__":
    unittest.main()
