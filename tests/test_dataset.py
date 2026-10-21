"""Dataset tests use generated, solid-color images, never game screenshots."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from PIL import Image

from lootlizard.dataset import (
    DatasetError, evaluate_predictions, inventory, load_dataset,
    load_predictions, sha256_file, validate_files,
)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "captures").mkdir()
        self.image = self.root / "captures" / "synthetic.png"
        Image.new("RGB", (100, 100), "#263442").save(self.image)

    def record(self, status="unannotated", truth=None):
        return {"id": "capture-1", "file": "captures/synthetic.png",
                "sha256": sha256_file(self.image), "split": "test",
                "annotation_status": status, "ground_truth": truth or {}}

    def write_manifest(self, *records):
        (self.root / "manifest.json").write_text(json.dumps({
            "schema_version": 1, "dataset_id": "synthetic-only", "captures": list(records),
        }), encoding="utf-8")
        return load_dataset(self.root)

    def positive_truth(self):
        return {"map_id": "test-map", "map_visible": True,
                "map_viewport": {"bounds": [10, 10, 90, 90], "anchors": [
                    {"id": "landmark", "map": [.5, .4], "image": [50, 40]},
                ]},
                "player_count": 2, "team_size": 4,
                "own_marker": [24, 25], "own_marker_visible": True,
                "zoomed": True, "panned": False,
                "poi_visibility": [{"id": "offscreen", "visible": False, "image": None}]}

    def test_unannotated_metadata_is_never_scored_as_a_pass(self):
        truth = self.positive_truth()
        dataset = self.write_manifest(self.record(truth=truth))
        predictions = {"capture-1": dict(truth)}
        result = evaluate_predictions(dataset, predictions)
        self.assertEqual(result["unannotated_captures_excluded"], 1)
        self.assertEqual(result["classification"]["map_visible"]["eligible"], 0)
        self.assertIsNone(result["classification"]["map_visible"]["accuracy"])
        self.assertEqual(inventory(dataset)["annotation_counts"]["unannotated"], 1)
        self.assertIn("No fully annotated captures", inventory(dataset)["coverage_gaps"])
        self.assertEqual(validate_files(dataset), [])

    def test_fully_annotated_negative_scene_allows_unknown_map_and_zero_markers(self):
        truth = {"map_visible": False, "map_id": None, "map_viewport": None,
                 "player_count": 0, "own_marker_visible": False, "own_marker": None,
                 "zoomed": None, "panned": None, "team_size": None}
        dataset = self.write_manifest(self.record("annotated", truth))
        result = evaluate_predictions(dataset, {"capture-1": {
            "map_visible": False, "player_count": 0, "own_marker_visible": False}})
        self.assertEqual(result["classification"]["map_visible"]["correct"], 1)
        self.assertEqual(result["classification"]["player_count"]["accuracy"], 1)
        self.assertEqual(result["classification"]["map_id"]["eligible"], 0)
        self.assertEqual(result["position"]["own_marker"]["eligible"], 0)
        self.assertEqual(inventory(dataset)["map_visibility_counts"]["hidden"], 1)

    def test_partial_scene_scores_known_map_facts_without_inventing_player_identity(self):
        truth = self.positive_truth()
        truth.update(own_marker=None, own_marker_visible=None, player_count=None)
        original = copy.deepcopy(truth)
        dataset = self.write_manifest(self.record("partial", truth))
        result = evaluate_predictions(dataset, {"capture-1": {"map_visible": True}})
        self.assertEqual(result["classification"]["map_visible"]["correct"], 1)
        self.assertEqual(result["classification"]["own_marker_visible"]["eligible"], 0)
        self.assertEqual(result["position"]["own_marker"]["eligible"], 0)
        self.assertEqual(dataset.captures[0].ground_truth, original)

    def test_missing_predictions_are_unknown_with_zero_coverage_not_passes(self):
        dataset = self.write_manifest(self.record("annotated", self.positive_truth()))
        result = evaluate_predictions(dataset, {})
        metric = result["classification"]["map_visible"]
        self.assertEqual(metric["eligible"], 1)
        self.assertEqual(metric["unknown_prediction"], 1)
        self.assertEqual(metric["correct"], 0)
        self.assertIsNone(metric["accuracy"])
        self.assertEqual(metric["coverage"], 0)
        self.assertEqual(metric["success_rate"], 0)
        self.assertIsNone(result["position"]["own_marker"]["mean_error_px"])

    def test_hidden_poi_projections_may_be_offscreen_without_becoming_position_labels(self):
        truth = self.positive_truth()
        truth["poi_visibility"] = [
            {"id": "above-map", "visible": False, "image": [50, -183.86]},
            {"id": "past-right-edge", "visible": False, "image": [150, 50]},
        ]
        dataset = self.write_manifest(self.record("annotated", truth))
        self.assertEqual(validate_files(dataset), [])
        result = evaluate_predictions(dataset, {"capture-1": {
            "poi_positions": [{"id": "landmark", "image": [50, 40]},
                              {"id": "above-map", "image": None},
                              {"id": "past-right-edge", "image": None}],
            "poi_visibility": [{"id": "above-map", "visible": False},
                               {"id": "past-right-edge", "visible": False}],
        }})
        visibility = result["classification"]["poi_visibility"]
        self.assertEqual(visibility["eligible"], 2)
        self.assertEqual(visibility["correct"], 2)
        self.assertEqual(visibility["unknown_prediction"], 0)
        positions = result["position"]["poi_positions"]
        self.assertEqual(positions["eligible"], 1)  # The visible landmark only.
        self.assertEqual(positions["compared"], 1)
        self.assertEqual(positions["unknown_prediction"], 0)
        self.assertEqual(result["unknown_capture_ids_in_predictions"], [])

    def test_visible_poi_cannot_use_negative_or_out_of_image_coordinates(self):
        truth = self.positive_truth()
        truth["poi_visibility"] = [{"id": "visible", "visible": True, "image": [50, -1]}]
        with self.assertRaises(DatasetError):
            self.write_manifest(self.record("annotated", truth))
        truth["poi_visibility"][0]["image"] = [150, 50]
        dataset = self.write_manifest(self.record("annotated", truth))
        self.assertIn("point_outside_image", {issue["code"] for issue in validate_files(dataset)})

    def test_manual_marker_and_anchor_errors_are_scored_in_screenshot_pixels(self):
        dataset = self.write_manifest(self.record("annotated", self.positive_truth()))
        prediction_path = self.root / "predictions.json"
        prediction_path.write_text(json.dumps({"schema_version": 1, "predictions": [{
            "capture_id": "capture-1", "map_visible": True, "map_id": "wrong-map",
            "player_count": 2, "own_marker_visible": True, "own_marker": [27, 29],
            "poi_positions": [{"id": "landmark", "image": [55, 40]}],
            "poi_visibility": [{"id": "offscreen", "visible": True}],
        }]}), encoding="utf-8")
        result = evaluate_predictions(dataset, load_predictions(prediction_path), tolerance_px=5)
        self.assertEqual(result["position"]["own_marker"]["mean_error_px"], 5)
        self.assertEqual(result["position"]["poi_positions"]["mean_error_px"], 5)
        self.assertEqual(result["position"]["own_marker"]["within_tolerance"], 1)
        self.assertEqual(result["classification"]["map_id"]["incorrect"], 1)
        self.assertEqual(result["classification"]["poi_visibility"]["incorrect"], 1)

    def test_incomplete_positive_scene_requires_partial_status(self):
        truth = self.positive_truth()
        truth["own_marker_visible"] = None
        with self.assertRaises(DatasetError):
            self.write_manifest(self.record("annotated", truth))
        self.write_manifest(self.record("partial", truth))

    def test_relative_paths_cannot_escape_or_address_windows_drives_and_streams(self):
        for filename in ("../outside.png", "/outside.png", "C:/outside.png",
                         "captures\\synthetic.png", "captures/synthetic.png:stream"):
            with self.subTest(file=filename):
                record = self.record()
                record["file"] = filename
                with self.assertRaises(DatasetError):
                    self.write_manifest(record)
        with self.assertRaises(DatasetError):
            load_dataset(self.root, "../manifest.json")

    def test_symlink_to_an_external_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            target = Path(external) / "outside.png"
            Image.new("RGB", (10, 10)).save(target)
            link = self.root / "captures" / "linked.png"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("Creating symlinks is unavailable on this host")
            record = self.record()
            record["file"] = "captures/linked.png"
            with self.assertRaises(DatasetError):
                self.write_manifest(record)

    def test_hash_mismatch_and_out_of_image_annotations_are_reported(self):
        truth = self.positive_truth()
        truth["map_viewport"]["bounds"] = [10, 10, 150, 150]
        truth["own_marker"] = [140, 25]
        dataset = self.write_manifest(self.record("annotated", truth))
        Image.new("RGB", (100, 100), "#405060").save(self.image)
        codes = {issue["code"] for issue in validate_files(dataset)}
        self.assertEqual(codes, {"hash_mismatch", "bounds_outside_image", "point_outside_image"})

    def test_duplicate_content_across_splits_is_a_coverage_warning(self):
        duplicate = self.root / "captures" / "duplicate.png"
        duplicate.write_bytes(self.image.read_bytes())
        first, second = self.record(), self.record()
        second.update(id="capture-2", file="captures/duplicate.png", split="train")
        report = inventory(self.write_manifest(first, second))
        self.assertEqual(report["cross_split_duplicate_capture_ids"], [["capture-1", "capture-2"]])
        self.assertTrue(any("leakage" in gap for gap in report["coverage_gaps"]))

    def test_boolean_labels_cannot_be_satisfied_by_integer_predictions(self):
        dataset = self.write_manifest(self.record("annotated", self.positive_truth()))
        with self.assertRaises(DatasetError):
            evaluate_predictions(dataset, {"capture-1": {"map_visible": 1}})
        for version in (True, 1):
            with self.subTest(schema_version=version):
                path = self.root / "predictions.json"
                path.write_text(json.dumps({"schema_version": version, "predictions": [
                    {"capture_id": "capture-1", "map_visible": 1}]}), encoding="utf-8")
                with self.assertRaises(DatasetError):
                    load_predictions(path)

    def test_inventory_cli_never_claims_accuracy_without_predictions(self):
        self.write_manifest(self.record())
        script = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_screenshots.py"
        result = subprocess.run([sys.executable, "-B", str(script), str(self.root)],
                                capture_output=True, text=True, check=False, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIsNone(report["evaluation"])
        self.assertIn("has not been evaluated", report["evaluation_status"])
        self.assertEqual(report["validation"]["issues"], [])
        self.assertTrue(report["inventory"]["coverage_gaps"])


if __name__ == "__main__":
    unittest.main()
