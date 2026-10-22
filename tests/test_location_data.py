"""Audit imported positions against pinned native-pixel records, not map size."""

import json
from pathlib import Path
import unittest

from lootlizard.core import MapData
from scripts.build_map_catalog import build_catalog

ROOT = Path(__file__).resolve().parents[1]


class LocationDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads((ROOT / "data-sources/secret-locations.json").read_text(encoding="utf-8"))
        cls.haven_audit = json.loads((ROOT / "data-sources/haven-candidate-buildings.json").read_text(encoding="utf-8"))
        cls.entrance_audit = json.loads((ROOT / "data-sources/erangel-bunker-entrances.json").read_text(encoding="utf-8"))
        cls.maps = {m["id"]: m for m in build_catalog(ROOT / "data")["maps"]}

    def test_every_licensed_location_has_one_pinned_source_and_correct_axes(self):
        records = {(r["map_id"], r["id"]): r for r in self.audit["locations"]}
        self.assertEqual(len(records), len(self.audit["locations"]))
        observed = {p["id"] for p in self.entrance_audit["points"]}
        actual = {(map_id, p["id"]): p for map_id, m in self.maps.items() if map_id != "haven"
                  for p in m["points"] if not (map_id == "erangel" and p["id"] in observed)}
        self.assertEqual(set(records), set(actual))
        system = self.audit["coordinate_system"]
        self.assertEqual((system["width_px"], system["height_px"], system["origin"]), (8192, 8192, "top-left"))
        self.assertEqual((system["x_direction"], system["y_direction"]), ("right", "down"))
        for key, record in records.items():
            with self.subTest(location=key):
                source = self.audit["sources"][record["source"]]
                self.assertEqual(source["license"], "MIT")
                self.assertIn(source["commit"], source["url"])
                self.assertTrue(record["upstream_id"])
                expected = record.get("correction", {"x": record["x_px"] / 8192, "y": record["y_px"] / 8192})
                point = actual[key]
                self.assertAlmostEqual(point["x"], expected["x"], places=12)
                self.assertAlmostEqual(point["y"], expected["y"], places=12)
                self.assertEqual(point.get("kind", "secret_room"), record["kind"])

    def test_small_map_pixel_coordinates_are_not_divided_by_metres(self):
        karakin = self.maps["karakin"]
        self.assertEqual(karakin["size_m"], 2000)
        self.assertEqual((karakin["points"][0]["x"], karakin["points"][0]["y"]), (1827 / 8192, 3034 / 8192))
        paramo = self.maps["paramo"]
        self.assertEqual(paramo["size_m"], 3000)
        self.assertEqual((paramo["points"][0]["x"], paramo["points"][0]["y"]), (1050 / 8192, 5207 / 8192))

    def test_taego_additions_and_corrected_old_id_are_distinct(self):
        points = {p["id"]: p for p in self.maps["taego"]["points"]}
        expected = {"taego-01": (1405, 1192), "taego-13": (6070, 3887),
                    "taego-14": (3595, 1979), "taego-15": (1265, 2715)}
        self.assertEqual(len(points), 15)
        for point_id, (x, y) in expected.items():
            self.assertEqual((points[point_id]["x"], points[point_id]["y"]), (x / 8192, y / 8192))
        self.assertEqual(len({(p["x"], p["y"]) for p in points.values()}), 15)

    def test_only_reviewed_location_categories_are_packaged(self):
        kinds = {map_id: {p.get("kind", "secret_room") for p in m["points"]} for map_id, m in self.maps.items()}
        self.assertEqual(kinds["vikendi"], {"security_room", "bear_cave"})
        self.assertEqual(kinds["deston"], {"security_room"})
        self.assertEqual(kinds["karakin"], {"tunnel_entrance"})
        self.assertEqual(kinds["miramar"], {"secret_room", "tunnel_entrance"})
        self.assertEqual(kinds["erangel"], {"secret_room", "tunnel_entrance"})
        self.assertEqual(kinds["haven"], {"supply_cache"})
        for map_id in ("taego", "rondo", "paramo"):
            self.assertEqual(kinds[map_id], {"secret_room"})
        for map_id in ("sanhok", "training"):
            self.assertEqual(self.maps[map_id]["points"], [])
        for map_id, document in self.maps.items():
            parsed = MapData.from_dict(document)
            self.assertEqual(len({(p.x, p.y) for p in parsed.points}), len(parsed.points), map_id)

    def test_miramar_entrances_are_separate_from_the_fifteen_key_rooms(self):
        points = self.maps["miramar"]["points"]
        rooms = [p for p in points if p.get("kind", "secret_room") == "secret_room"]
        entrances = {p["id"]: p for p in points if p.get("kind") == "tunnel_entrance"}
        self.assertEqual([p["id"] for p in rooms], [f"miramar-{i:02}" for i in range(1, 16)])
        expected = {"miramar-entrance-01": (4910, 6255), "miramar-entrance-02": (5018, 6296),
                    "miramar-entrance-03": (5039, 6350)}
        self.assertEqual(set(entrances), set(expected))
        for point_id, (x, y) in expected.items():
            self.assertEqual((entrances[point_id]["x"], entrances[point_id]["y"]), (x / 8192, y / 8192))
        self.assertIn("not three additional key-locked rooms", self.maps["miramar"]["source"]["notes"])

    def test_erangel_observed_entrances_use_the_source_plane_and_keep_rooms_separate(self):
        points = self.maps["erangel"]["points"]
        rooms = [p for p in points if p.get("kind", "secret_room") == "secret_room"]
        entrances = {p["id"]: p for p in points if p.get("kind") == "tunnel_entrance"}
        self.assertEqual([p["id"] for p in rooms], [f"erangel-{i:02}" for i in range(1, 16)])
        audit = self.entrance_audit
        self.assertEqual(len(entrances), 7)
        self.assertEqual(set(entrances), {p["id"] for p in audit["points"]})
        self.assertEqual(audit["coordinate_system"], {"width_units": 1000, "height_units": 1000,
                         "origin": "top-left", "x_direction": "right", "y_direction": "down"})
        self.assertIn("No general source license", audit["source"]["license"])
        for field in ("bundle_sha256", "component_sha256"):
            self.assertRegex(audit["source"][field], r"^[a-f0-9]{64}$")
        for record in audit["points"]:
            point = entrances[record["id"]]
            self.assertAlmostEqual(point["x"], record["source_x"] / 1000, places=12)
            self.assertAlmostEqual(point["y"], record["source_y"] / 1000, places=12)
            self.assertEqual(point["kind"], "tunnel_entrance")
        self.assertEqual(sum(p["name"].startswith("Shelter entrance") for p in entrances.values()), 4)
        self.assertEqual(audit["excluded_points"][0]["id"], "erangel-entrance-04")
        self.assertNotIn("erangel-entrance-04", entrances)

    def test_haven_observed_candidate_buildings_use_the_recorded_image_transform(self):
        audit = self.haven_audit
        points = {p["id"]: p for p in self.maps["haven"]["points"]}
        self.assertEqual(len(points), 22)
        self.assertEqual({p["id"] for p in audit["points"]}, set(points))
        self.assertIn("2021-03-25", audit["source_image_revision_in_url"])
        self.assertIn("not exact doors", audit["normalization"])
        self.assertIn("not exact doors", self.maps["haven"]["source"]["notes"])
        matrix = audit["registration"]["matrix"]
        width, height = audit["registration"]["reference_size"]
        for record in audit["points"]:
            x, y = record["source_marker_x"], record["source_marker_y"]
            projected_x = (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / width
            projected_y = (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / height
            point = points[record["id"]]
            # The observation tool projects in float32 before rounding its JSON.
            self.assertAlmostEqual(point["x"], projected_x, delta=1e-7)
            self.assertAlmostEqual(point["y"], projected_y, delta=1e-7)
            self.assertEqual((point["x"], point["y"]), (record["x"], record["y"]))

    def test_rondo_outlier_correction_has_independent_provenance(self):
        point = next(p for p in self.maps["rondo"]["points"] if p["id"] == "rondo-08")
        self.assertEqual((point["x"], point["y"]), (0.69952, 0.74753))
        record = next(r for r in self.audit["locations"] if r["map_id"] == "rondo" and r["id"] == "rondo-08")
        self.assertEqual(record["upstream_id"], "S608")
        self.assertEqual((record["x_px"], record["y_px"]), (5615, 6109))
        self.assertEqual(len(record["correction"]["sources"]), 2)


if __name__ == "__main__":
    unittest.main()
