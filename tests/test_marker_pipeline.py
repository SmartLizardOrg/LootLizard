"""Map/marker contract tests; the cone geometry has separate pixel tests."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from lootlizard.marker_pipeline import map_search_bounds, recognize_registered_marker
from lootlizard.registration import Registration
from lootlizard.vision import Recognition
from lootlizard.core import Bounds


class MarkerPipelineTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (2560, 1440))
        self.registration = Registration("map-a", np.array(
            ((2160., 0., 200.), (0., 2160., -360.), (0., 0., 1.))),
            (0, 0, 2560, 1440), "verified")
        self.profile = SimpleNamespace(map_id="map-a", bounds=Bounds(560, 0, 2000, 1440))

    def cone(self, center=(831., 1025.), reason="unique cone", **values):
        return SimpleNamespace(center=center, radius_px=12., heading_degrees=45.,
                               score=.9, reason=reason, candidates=(), **values)

    def find(self, result):
        return patch("lootlizard.self_marker.find_self_marker", return_value=result, create=True)

    def test_unknown_map_cannot_authorize_a_player_marker(self):
        unknown = Registration(None, None, (0, 0, 2560, 1440), "unknown")
        with self.find(self.cone()) as find:
            result = recognize_registered_marker(self.image, unknown)
        self.assertIsNone(result.position)
        self.assertFalse(result.layout_verified)
        find.assert_not_called()

    def test_whole_map_search_excludes_outside_hud(self):
        full = Registration("map-a", np.array(
            ((1440., 0., 560.), (0., 1440., 0.), (0., 0., 1.))),
            (0, 0, 2560, 1440), "verified")
        self.assertEqual(map_search_bounds(full, self.image.size), (560, 0, 2000, 1440))
        self.assertEqual(map_search_bounds(self.registration, self.image.size), (200, 0, 2360, 1440))
        self.assertTrue(all(type(n) is int for n in map_search_bounds(self.registration, self.image.size)))

    def test_zoomed_marker_uses_inverse_map_transform_not_viewport_normalization(self):
        with self.find(self.cone()) as find:
            result = recognize_registered_marker(self.image, self.registration)
        np.testing.assert_allclose(result.position, ((831-200)/2160, (1025+360)/2160))
        self.assertEqual(result.method, "view-cone")
        self.assertEqual(result.heading_degrees, 45.)
        self.assertEqual(find.call_args.kwargs["viewport"], (200, 0, 2360, 1440))

    def test_replay_mode_disables_both_cone_and_trained_icon(self):
        with self.find(self.cone()) as find, patch("lootlizard.marker_pipeline.recognize") as trained:
            result = recognize_registered_marker(self.image, self.registration,
                self.profile, view_context="replay")
        self.assertIsNone(result.position)
        find.assert_not_called()
        trained.assert_not_called()

    def test_outside_map_candidate_is_rejected_even_with_a_broad_cone(self):
        with self.find(self.cone(center=(2400., 10.))):
            result = recognize_registered_marker(self.image, self.registration)
        self.assertIsNone(result.position)

    def test_conflicting_visual_sources_abstain_instead_of_picking_a_player(self):
        with self.find(self.cone()), patch("lootlizard.marker_pipeline.recognize",
                return_value=Recognition((.8, .8), .99, "trained", True)):
            result = recognize_registered_marker(self.image, self.registration, self.profile)
        self.assertIsNone(result.position)
        self.assertIn("disagree", result.reason)

    def test_missing_cone_can_use_existing_unique_trained_profile(self):
        with self.find(self.cone(center=None, reason="No broad cone")), patch(
                "lootlizard.marker_pipeline.recognize",
                return_value=Recognition((.4, .6), .93, "trained", True)):
            result = recognize_registered_marker(self.image, self.registration, self.profile)
        np.testing.assert_allclose(result.position, ((560+.4*1440-200)/2160, (.6*1440+360)/2160))
        self.assertEqual(result.method, "trained-icon")

    def test_competing_cones_block_profile_fallback(self):
        with self.find(self.cone(center=None, reason="Competing cones are ambiguous", ambiguous=True)), patch(
                "lootlizard.marker_pipeline.recognize",
                return_value=Recognition((.4, .6), .99, "trained", True)):
            result = recognize_registered_marker(self.image, self.registration, self.profile)
        self.assertIsNone(result.position)

    def test_cone_agreement_uses_actual_profile_pixel_not_profile_normalized_coordinates(self):
        expected = (831., 1025.)
        local = ((expected[0]-560)/1440, expected[1]/1440)
        with self.find(self.cone()), patch("lootlizard.marker_pipeline.recognize",
                return_value=Recognition(local, .99, "trained", True)):
            result = recognize_registered_marker(self.image, self.registration, self.profile)
        self.assertEqual(result.method, "view-cone")
        self.assertIsNotNone(result.position)


if __name__ == "__main__":
    unittest.main()
