"""Validation and deterministic packaging of bundled release map catalogs."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_map_catalog as builder


SHA = "a" * 40


def record(map_id="test-map"):
    return {"id": map_id, "name": "Test map", "size_m": 8000,
            "source": {"url": "https://example.org/source", "license": "MIT",
                       "attribution": "Test contributors", "notes": "Incomplete; unverified."},
            "points": [{"id": f"{map_id}-01", "name": "Room 01", "x": .25, "y": .75}]}


class MapCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.data = self.root / "data"
        self.data.mkdir()

    def save(self, document, name="map.json"):
        path = self.data / name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_bundled_feed_preserves_provenance_and_known_counts(self):
        catalog = builder.build_catalog(builder.ROOT / "data", SHA)
        self.assertEqual(set(catalog), {"schema_version", "revision", "maps"})
        self.assertEqual(catalog["revision"], SHA)
        self.assertEqual(len(catalog["maps"]), 11)
        self.assertEqual({m["id"]: len(m["points"]) for m in catalog["maps"] if m["points"]},
                         {"erangel": 15, "taego": 15, "miramar": 15, "deston": 39,
                          "rondo": 15, "vikendi": 20, "paramo": 8, "karakin": 22, "haven": 22})
        self.assertEqual(next(m for m in catalog["maps"] if m["id"] == "erangel")["source"]["license"], "MIT")
        self.assertIn("15 rooms", next(m for m in catalog["maps"] if m["id"] == "taego")["source"]["notes"])
        vikendi = next(m for m in catalog["maps"] if m["id"] == "vikendi")
        self.assertEqual({p["kind"] for p in vikendi["points"]}, {"security_room", "bear_cave"})

    def test_deterministic_whole_snapshot_and_valid_empty_removal(self):
        self.save(record("map-b"), "z.json")
        self.save(record("map-a"), "a.json")
        first = builder.build_catalog(self.data, SHA)
        self.assertEqual([m["id"] for m in first["maps"]], ["map-a", "map-b"])
        self.assertEqual(builder.encode_catalog(first), builder.encode_catalog(builder.build_catalog(self.data, SHA)))
        for path in self.data.glob("*.json"): path.unlink()
        self.assertEqual(builder.build_catalog(self.data, SHA)["maps"], [])

    def test_published_bytes_roundtrip_through_the_real_client_parser(self):
        self.save(record())
        catalog = builder.build_catalog(self.data, SHA)
        snapshot = builder.validate_catalog(json.loads(builder.encode_catalog(catalog)))
        self.assertEqual(snapshot["revision"], SHA)
        self.assertEqual(snapshot["maps"], catalog["maps"])

    def test_reference_only_maps_can_have_no_points_without_dummy_targets(self):
        document = record(); document["points"] = []
        self.save(document)
        self.assertEqual(builder.build_catalog(self.data, SHA)["maps"][0]["points"], [])
        local = builder.build_catalog(self.data)
        self.assertRegex(local["revision"], r"^content:[a-f0-9]{64}$")
        self.assertEqual(local, builder.build_catalog(self.data))

    def test_missing_directory_and_non_commit_revision_are_rejected(self):
        for revision in ("main", "a"*39, "A"*40, "../metadata", "a"*161):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                builder.build_catalog(self.data, revision)
        with self.assertRaises(ValueError): builder.build_catalog(self.root / "missing", SHA)

    def test_unsafe_ids_and_duplicate_maps_or_points_are_rejected(self):
        for key in ("map", "point"):
            for value in ("../escape", "Uppercase", "a/b", "a"*65):
                document = record()
                if key == "map": document["id"] = value
                else: document["points"][0]["id"] = value
                self.save(document)
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    builder.build_catalog(self.data, SHA)
        document = record(); document["points"].append(copy.deepcopy(document["points"][0]))
        self.save(document)
        with self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)
        self.save(record()); self.save(record(), "duplicate.json")
        with self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)

    def test_coordinates_and_credits_are_validated_before_publication(self):
        for value in (-.01, 1.01, True, "0.5", None):
            document = record(); document["points"][0]["x"] = value
            self.save(document)
            with self.subTest(value=value), self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)
        for key in ("url", "license", "attribution"):
            document = record(); del document["source"][key]
            self.save(document)
            with self.subTest(key=key), self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)
        document = record(); document["source"]["url"] = "https://user:secret@example.org/data"
        self.save(document)
        with self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)

    def test_duplicate_json_keys_and_nonfinite_constants_are_rejected(self):
        path = self.data / "map.json"
        path.write_text('{"id":"first","id":"second"}', encoding="utf-8")
        with self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)
        text = json.dumps(record()).replace('"x": 0.25', '"x": NaN')
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)

    def test_count_and_total_encoded_bytes_are_bounded(self):
        for number in range(33): self.save(record(f"map-{number}"), f"{number:02}.json")
        with self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)
        for path in self.data.glob("*.json"): path.unlink()
        for number in range(2):
            document = record(f"map-{number}"); document["source"]["notes"] = "x" * 1_100_000
            self.save(document, f"{number}.json")
        with self.assertRaises(ValueError): builder.build_catalog(self.data, SHA)

    def test_atomic_output_replaces_whole_feed_and_failure_keeps_old_file(self):
        self.save(record())
        catalog = builder.build_catalog(self.data, SHA)
        output = self.root / "maps.json"
        output.write_bytes(b"previous valid snapshot")
        with patch.object(builder.os, "replace", side_effect=OSError("synthetic replace failure")):
            with self.assertRaises(OSError): builder.write_catalog(output, catalog)
        self.assertEqual(output.read_bytes(), b"previous valid snapshot")
        self.assertEqual(list(self.root.glob(".maps.json.*.tmp")), [])
        builder.write_catalog(output, catalog)
        self.assertEqual(json.loads(output.read_bytes()), catalog)
        self.assertTrue(output.read_bytes().endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
