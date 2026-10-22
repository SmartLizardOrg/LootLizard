import json
from pathlib import Path
import tempfile
import unittest

from lootlizard.core import Bounds, MapData, SafeZone, nearest

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return {"id": "test", "name": "Test map", "size_m": 8000,
            "source": {"license": "MIT"},
            "points": [{"id": "center", "name": "Center", "x": .5, "y": .5},
                       {"id": "east", "name": "East", "x": .6, "y": .5},
                       {"id": "south", "name": "South", "x": .5, "y": .7},
                       {"id": "corner", "name": "Corner", "x": 0, "y": 0}]}


class GeometryTests(unittest.TestCase):
    def test_zone_prioritizes_inside_before_closer_outside(self):
        data = MapData.from_dict(fixture())
        zone = SafeZone(.5, .7, .03)
        result = nearest(data, (.5, .5), 4, zone=zone)
        self.assertEqual([point.id for point, _ in result], ["south", "center", "east", "corner"])
        self.assertAlmostEqual(result[0][1], 1600)

    def test_no_inside_points_falls_back_to_distance(self):
        data = MapData.from_dict(fixture())
        zone = SafeZone(.95, .95, .01)
        self.assertEqual(nearest(data, (.5, .5), zone=zone), nearest(data, (.5, .5)))

    def test_zone_contains_boundary_and_rejects_invalid_geometry(self):
        zone = SafeZone(.5, .5, .2)
        self.assertTrue(zone.contains(.7, .5))
        self.assertFalse(zone.contains(.701, .5))
        for geometry in [(0, 0, 0), (0, 0, -1), (0, 0, float("nan")),
                         (0, 0, True), (-.1, .5, .2), (.5, 1.1, .2)]:
            with self.subTest(geometry=geometry), self.assertRaises(ValueError):
                SafeZone(*geometry)

    def test_nearest_has_expected_order_and_meters(self):
        results = nearest(MapData.from_dict(fixture()), (.5, .5))
        self.assertEqual([p.id for p, _ in results], ["center", "east", "south"])
        for (_, actual), expected in zip(results, [0, 800, 1600]):
            self.assertAlmostEqual(actual, expected)

    def test_diagonal_is_horizontal_euclidean_distance(self):
        data = MapData.from_dict(fixture())
        result = dict((p.id, distance) for p, distance in nearest(data, (0, 0), 4))
        self.assertAlmostEqual(result["center"], (2 ** .5) * 4000)

    def test_top_left_origin(self):
        bounds = Bounds(100, 50, 800, 750).validate(1000, 800)
        self.assertEqual(bounds.normalized(100, 50), (0, 0))
        self.assertEqual(bounds.normalized(800, 750), (1, 1))
        self.assertEqual(bounds.normalized(450, 400), (.5, .5))

    def test_outside_or_reversed_calibration_rejected(self):
        for values in [(-1, 0, 99, 100), (0, 0, 1100, 1100), (100, 100, 0, 0), (0, 0, 100, 200), (0, 0, 10, 10)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                Bounds(*values).validate(1000, 1000)

    def test_outside_player_rejected(self):
        for position in [(-.1, 0), (0, 1.1), (float("nan"), 0), (True, 0)]:
            with self.subTest(position=position), self.assertRaises(ValueError):
                nearest(MapData.from_dict(fixture()), position)

    def test_deterministic_ties_and_limit(self):
        data = MapData.from_dict(fixture())
        self.assertEqual(len(nearest(data, (0, 0), 100)), 4)
        self.assertEqual(nearest(data, (0, 0), 0), [])
        with self.assertRaises(ValueError):
            nearest(data, (0, 0), -1)


class DataTests(unittest.TestCase):
    def test_round_trip_retains_attribution(self):
        original = fixture()
        self.assertEqual(MapData.from_dict(original).to_dict(), original)

    def test_location_kinds_survive_packaging_and_legacy_rooms_keep_their_default(self):
        original = fixture()
        self.assertEqual(MapData.from_dict(original).points[0].kind, "secret_room")
        for kind in ("security_room", "bear_cave", "tunnel_entrance", "supply_cache"):
            with self.subTest(kind=kind):
                original["points"][0]["kind"] = kind
                parsed = MapData.from_dict(original)
                self.assertEqual(parsed.points[0].kind, kind)
                self.assertEqual(parsed.to_dict(), original)
        for kind in (None, True, {}, "vehicle", "__proto__"):
            original["points"][0]["kind"] = kind
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                MapData.from_dict(original)

    def test_bad_coordinate_types_are_rejected(self):
        for value in [None, True, "0.5", -1, 1.1, float("nan"), float("inf")]:
            data = fixture()
            data["points"][0]["x"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                MapData.from_dict(data)

    def test_duplicate_or_missing_point_ids_are_rejected(self):
        for value in [None, "", "east"]:
            data = fixture()
            data["points"][0]["id"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                MapData.from_dict(data)

    def test_missing_names_invalid_sizes_and_non_list_points(self):
        for key, value in [("name", ""), ("size_m", 0), ("size_m", True), ("size_m", float("inf")), ("points", None), ("points", {}), ("source", [])]:
            data = fixture()
            data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                MapData.from_dict(data)

    def test_reference_only_map_retains_identity_without_inventing_locations(self):
        original = fixture()
        original["points"] = []
        data = MapData.from_dict(original)
        self.assertEqual(data.to_dict(), original)
        self.assertEqual(nearest(data, (.5, .5)), [])

    def test_oversized_file_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.json"
            path.write_text(" " * 2_000_001)
            with self.assertRaises(ValueError):
                MapData.load(path)

    def test_bundled_data_is_normalized_and_attributed(self):
        for map_id, expected_count in [("erangel", 15), ("taego", 15)]:
            with self.subTest(map_id=map_id):
                data = MapData.load(ROOT / "data" / f"{map_id}.json")
                self.assertEqual(data.id, map_id)
                self.assertEqual(len(data.points), expected_count)
                self.assertEqual(data.size_m, 8000)
                self.assertTrue(all(point.id.startswith(f"{map_id}-") for point in data.points))
                self.assertTrue(data.source["url"].startswith("https://github.com/"))
                self.assertEqual(data.source["license"], "MIT")
                self.assertIn("Aleksei Reuk", data.source["attribution"])

    def test_utf8_bom_json_load(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8-sig")
            self.assertEqual(MapData.load(path).id, "test")


if __name__ == "__main__":
    unittest.main()
