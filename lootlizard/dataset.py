"""Local, manually annotated screenshot datasets and offline evaluation.

The manifest never contains recognizer-generated ground truth. Unknown facts
are JSON null; unannotated scenes are not scored. Partial scenes contribute
only their explicitly known fields. No screenshots ship with the application.

Schema version 1 has ``dataset_id`` and a ``captures`` list. Each capture has
``id``, a root-relative ``file``, lowercase ``sha256``, ``split`` (train,
validation, test), ``annotation_status`` (unannotated, partial, annotated), and
``ground_truth``. Ground truth fields are:

* map_id, map_visible, zoomed, panned: string/bool or null as applicable.
* player_count: visible allied map markers, INCLUDING own marker, 0 through 4.
* team_size: optional known team size, 1 through 4 or null.
* own_marker_visible and own_marker: bool/null and screenshot [x, y]/null.
* map_viewport: null or {bounds: [left, top, right, bottom], anchors: [...]}.
  Each anchor is {id: optional string, map: [normalized_x, normalized_y],
  image: [screenshot_x, screenshot_y]}. Stable ids are recommended; an omitted
  id is addressed as anchor-1, anchor-2, etc. in prediction files.
* poi_visibility: optional list of {id, visible: bool/null, image: [x, y]/null}.
  For visible=false, image may optionally retain a known offscreen projection,
  including negative coordinates. It is not scored as a visible image point.

Bounds are screenshot pixels with exclusive right/bottom edges; points are
full screenshot pixels, never crop-relative. Anchor map points refer to the
entire map, even when its screenshot is zoomed or panned. Additional metadata
is permitted. A fully annotated negative scene has map_visible=false,
player_count=0, own_marker_visible=false, own_marker=null; its map id,
viewport, zoom and pan may all be null.

Optional prediction files use {schema_version: 1, predictions: [{capture_id,
map_id, map_visible, player_count, own_marker_visible, own_marker, zoomed,
panned, poi_positions: [{id, image}], poi_visibility: [{id, visible}]}]}.
Missing/null predictions remain unknown. This module has no detector adapter.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
from typing import Any


SCHEMA_VERSION = 1
STATUSES = ("unannotated", "partial", "annotated")
SPLITS = ("train", "validation", "test")
_MAX_MANIFEST_BYTES = 5_000_000


class DatasetError(ValueError):
    """An invalid manifest, annotation, or dataset-relative path."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise DatasetError(message)


def _text(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()) and len(value) <= 200,
             f"{label} must be a nonempty string of at most 200 characters")
    return value


def _number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _point(value: Any, label: str, *, normalized=False, allow_offscreen=False) -> None:
    _require(isinstance(value, list) and len(value) == 2
             and all(_number(n) for n in value),
             f"{label} must contain two finite coordinates")
    if not allow_offscreen:
        _require(all(n >= 0 for n in value), f"{label} must contain nonnegative coordinates")
    if normalized:
        _require(all(n <= 1 for n in value), f"{label} must use normalized map coordinates")


def _relative_path(root: Path, name: Any) -> Path:
    _require(isinstance(name, str) and bool(name), "A dataset file needs a relative path")
    _require(not any(ord(character) < 32 for character in name), "File paths cannot contain control characters")
    _require("\\" not in name and ":" not in name, "Use a relative path with forward slashes")
    candidate = Path(name)
    _require(not candidate.is_absolute() and not PureWindowsPath(name).drive
             and ".." not in candidate.parts, "Dataset paths must stay inside the dataset root")
    resolved = (root / candidate).resolve()
    _require(resolved != root and resolved.is_relative_to(root),
             "Dataset paths and symlinks must stay inside the dataset root")
    return resolved


def _read_json(path: Path) -> Any:
    _require(path.stat().st_size <= _MAX_MANIFEST_BYTES, "JSON exceeds the 5 MB limit")
    with path.open(encoding="utf-8-sig") as stream:
        try:
            return json.load(stream)
        except (ValueError, RecursionError) as error:
            raise DatasetError(f"Invalid JSON: {error}") from error


def _annotation(ground_truth: Any, status: str) -> None:
    _require(isinstance(ground_truth, dict), "ground_truth must be an object")
    truth = ground_truth
    if truth.get("map_id") is not None:
        _text(truth["map_id"], "map_id")
    for name in ("map_visible", "own_marker_visible", "zoomed", "panned"):
        _require(truth.get(name) is None or type(truth[name]) is bool,
                 f"{name} must be a boolean or null")
    count = truth.get("player_count")
    _require(count is None or type(count) is int and 0 <= count <= 4,
             "player_count must be 0 through 4 visible allied markers, or null")
    team = truth.get("team_size")
    _require(team is None or type(team) is int and 1 <= team <= 4,
             "team_size must be 1 through 4 or null")
    _require(count is None or team is None or count <= team,
             "Visible allied markers cannot exceed team_size")
    own = truth.get("own_marker")
    if own is not None:
        _point(own, "own_marker")
    _require(not (truth.get("own_marker_visible") is False and own is not None),
             "An invisible own marker must not have a visible image point")
    _require(not (truth.get("own_marker_visible") is True and count == 0),
             "A visible own marker must be included in player_count")
    viewport = truth.get("map_viewport")
    if viewport is not None:
        _require(isinstance(viewport, dict), "map_viewport must be an object or null")
        bounds = viewport.get("bounds")
        _require(isinstance(bounds, list) and len(bounds) == 4
                 and all(type(n) is int and n >= 0 for n in bounds),
                 "map_viewport.bounds must contain four nonnegative integer pixels")
        left, top, right, bottom = bounds
        _require(left < right and top < bottom, "Map viewport bounds must have positive dimensions")
        if truth.get("own_marker_visible") is True and own is not None:
            _require(left <= own[0] < right and top <= own[1] < bottom,
                     "The visible own marker must be inside map_viewport.bounds")
        anchors = viewport.get("anchors", [])
        _require(isinstance(anchors, list), "anchors must be a list")
        ids = set()
        for index, anchor in enumerate(anchors, 1):
            _require(isinstance(anchor, dict), "Each anchor must be an object")
            identifier = _text(anchor.get("id", f"anchor-{index}"), "anchor id")
            _require(identifier not in ids, "Anchor ids must be unique")
            ids.add(identifier)
            _point(anchor.get("map"), "anchor.map", normalized=True)
            _point(anchor.get("image"), "anchor.image")
            x, y = anchor["image"]
            _require(left <= x < right and top <= y < bottom,
                     "Visible anchors must be inside map_viewport.bounds")
    _require(not (truth.get("map_visible") is False and viewport is not None),
             "A hidden map must not have a visible map_viewport")
    pois = truth.get("poi_visibility", [])
    _require(isinstance(pois, list), "poi_visibility must be a list")
    ids = set()
    for poi in pois:
        _require(isinstance(poi, dict), "Each POI visibility annotation must be an object")
        identifier = _text(poi.get("id"), "POI id")
        _require(identifier not in ids, "POI ids must be unique")
        ids.add(identifier)
        _require(poi.get("visible") is None or type(poi["visible"]) is bool,
                 "POI visible must be a boolean or null")
        if poi.get("image") is not None:
            _point(poi["image"], "POI image", allow_offscreen=poi.get("visible") is False)
    if status != "annotated":
        return
    _require(type(truth.get("map_visible")) is bool, "An annotated scene needs map_visible")
    _require(count is not None, "An annotated scene needs player_count")
    _require(type(truth.get("own_marker_visible")) is bool,
             "An annotated scene needs own_marker_visible")
    if truth["map_visible"]:
        _require(bool(truth.get("map_id")) and viewport is not None,
                 "An annotated visible map needs map_id and map_viewport.bounds")
        _require(type(truth.get("zoomed")) is bool and type(truth.get("panned")) is bool,
                 "An annotated visible map needs zoomed and panned flags")
        _require(not truth["own_marker_visible"] or own is not None,
                 "An annotated visible own marker needs its image point")
    else:
        _require(count == 0 and truth["own_marker_visible"] is False and own is None,
                 "An annotated hidden map needs zero markers and no own marker")


@dataclass(frozen=True)
class Capture:
    id: str
    file: str
    sha256: str
    split: str
    annotation_status: str
    ground_truth: dict


@dataclass(frozen=True)
class Dataset:
    root: Path
    dataset_id: str
    captures: tuple[Capture, ...]

    def capture_path(self, capture: Capture) -> Path:
        return _relative_path(self.root, capture.file)


def load_dataset(root: str | Path, manifest: str = "manifest.json") -> Dataset:
    """Read a manifest without modifying annotations or calling a recognizer."""
    directory = Path(root).resolve()
    _require(directory.is_dir(), "Dataset root must be an existing directory")
    document = _read_json(_relative_path(directory, manifest))
    _require(isinstance(document, dict) and type(document.get("schema_version")) is int
             and document["schema_version"] == SCHEMA_VERSION, "Unsupported dataset schema_version")
    identifier = _text(document.get("dataset_id"), "dataset_id")
    records = document.get("captures")
    _require(isinstance(records, list) and len(records) <= 10000, "captures must be a list of at most 10000 records")
    ids, files, captures = set(), set(), []
    for record in records:
        _require(isinstance(record, dict), "Each capture must be an object")
        capture_id = _text(record.get("id"), "capture id")
        _require(capture_id not in ids, f"Duplicate capture id: {capture_id}")
        filename = record.get("file")
        path = _relative_path(directory, filename)
        _require(path not in files, "One image file cannot be listed as multiple captures")
        digest = record.get("sha256")
        _require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                 f"{capture_id}: sha256 must be 64 lowercase hex digits")
        split, status = record.get("split"), record.get("annotation_status")
        _require(split in SPLITS, f"{capture_id}: invalid split")
        _require(status in STATUSES, f"{capture_id}: invalid annotation_status")
        truth = record.get("ground_truth", {})
        try:
            _annotation(truth, status)
        except DatasetError as error:
            raise DatasetError(f"{capture_id}: {error}") from error
        captures.append(Capture(capture_id, filename, digest, split, status, truth))
        ids.add(capture_id)
        files.add(path)
    return Dataset(directory, identifier, tuple(captures))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_files(dataset: Dataset, *, verify_hashes=True) -> list[dict]:
    """Return actionable file/coordinate errors; unknown labels are not errors."""
    from PIL import Image

    issues = []
    for capture in dataset.captures:
        def issue(code, message):
            issues.append({"capture_id": capture.id, "code": code, "message": message})
        try:
            path = dataset.capture_path(capture)
            if verify_hashes and sha256_file(path) != capture.sha256:
                issue("hash_mismatch", "Image content differs from the manifest sha256")
            with Image.open(path) as image:
                width, height = image.size
                image.verify()
            truth = capture.ground_truth
            viewport = truth.get("map_viewport")
            if viewport is not None:
                if viewport["bounds"][2] > width or viewport["bounds"][3] > height:
                    issue("bounds_outside_image", "Map viewport extends outside the image")
            points = [truth.get("own_marker")]
            points.extend(a["image"] for a in (viewport or {}).get("anchors", []))
            points.extend(p.get("image") for p in truth.get("poi_visibility", [])
                          if p.get("visible") is not False)
            if any(point is not None and not (0 <= point[0] < width and 0 <= point[1] < height)
                   for point in points):
                issue("point_outside_image", "An annotated marker, anchor or POI is outside the image")
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            issue("unreadable_image", str(error))
    return issues


def inventory(dataset: Dataset) -> dict:
    """Describe annotation coverage; a coverage gap never counts as a pass."""
    captures = dataset.captures
    labeled = [capture for capture in captures if capture.annotation_status != "unannotated"]
    complete = [capture for capture in captures if capture.annotation_status == "annotated"]
    visible = [capture for capture in labeled if capture.ground_truth.get("map_visible") is True]
    counts = Counter(capture.ground_truth.get("player_count") for capture in visible)
    maps = sorted({capture.ground_truth["map_id"] for capture in visible
                   if capture.ground_truth.get("map_id") is not None})
    gaps = []
    if not complete:
        gaps.append("No fully annotated captures")
    for count in range(1, 5):
        if not counts[count]:
            gaps.append(f"No annotated visible-map case with {count} allied markers")
    if not any(c.ground_truth.get("map_visible") is False for c in labeled):
        gaps.append("No annotated map-hidden negative scene")
    for flag in ("zoomed", "panned"):
        if not any(c.ground_truth.get(flag) is True for c in visible):
            gaps.append(f"No annotated {flag} map")
    if len(maps) < 2:
        gaps.append("Fewer than two annotated map ids; cross-map behavior is not covered")
    if not any((c.ground_truth.get("map_viewport") or {}).get("anchors") for c in labeled):
        gaps.append("No manually annotated map-to-image anchors")
    for split in ("validation", "test"):
        if not any(c.split == split for c in labeled):
            gaps.append(f"No annotated {split} captures")
    hashes = {}
    for capture in captures:
        hashes.setdefault(capture.sha256, []).append(capture)
    duplicated = [[c.id for c in group] for group in hashes.values()
                  if len({c.split for c in group}) > 1]
    if duplicated:
        gaps.append("Identical image hashes occur in different splits; avoid evaluation leakage")
    return {"dataset_id": dataset.dataset_id, "capture_count": len(captures),
            "annotation_counts": {status: sum(c.annotation_status == status for c in captures) for status in STATUSES},
            "split_counts": {split: sum(c.split == split for c in captures) for split in SPLITS},
            "annotated_map_ids": maps,
            "map_visibility_counts": {
                "visible": sum(c.ground_truth.get("map_visible") is True for c in labeled),
                "hidden": sum(c.ground_truth.get("map_visible") is False for c in labeled),
                "unknown": sum(c.ground_truth.get("map_visible") is None for c in labeled)},
            "view_variants": {flag: {
                "true": sum(c.ground_truth.get(flag) is True for c in visible),
                "false": sum(c.ground_truth.get(flag) is False for c in visible),
                "unknown": sum(c.ground_truth.get(flag) is None for c in visible)}
                for flag in ("zoomed", "panned")},
            "annotated_anchor_count": sum(len((c.ground_truth.get("map_viewport") or {}).get("anchors", []))
                                          for c in labeled),
            "visible_allied_marker_counts": {str(n): counts[n] for n in range(5)},
            "visible_allied_marker_count_unknown": counts[None],
            "cross_split_duplicate_capture_ids": duplicated, "coverage_gaps": gaps}


def load_predictions(path: str | Path) -> dict[str, dict]:
    document = _read_json(Path(path))
    _require(isinstance(document, dict) and type(document.get("schema_version")) is int
             and document["schema_version"] == SCHEMA_VERSION,
             "Unsupported predictions schema_version")
    rows = document.get("predictions")
    _require(isinstance(rows, list), "predictions must be a list")
    predictions = {}
    for row in rows:
        _require(isinstance(row, dict), "Each prediction must be an object")
        identifier = _text(row.get("capture_id"), "prediction capture_id")
        _require(identifier not in predictions, "Prediction capture ids must be unique")
        for name in ("map_visible", "own_marker_visible", "zoomed", "panned"):
            _require(row.get(name) is None or type(row[name]) is bool,
                     f"Prediction {name} must be a boolean or null")
        if row.get("map_id") is not None:
            _text(row["map_id"], "predicted map_id")
        if row.get("player_count") is not None:
            _require(type(row["player_count"]) is int and 0 <= row["player_count"] <= 4,
                     "Predicted player_count must be 0 through 4 or null")
        if row.get("own_marker") is not None:
            _point(row["own_marker"], "predicted own_marker")
        for name in ("poi_positions", "poi_visibility"):
            values = row.get(name, [])
            _require(isinstance(values, list), f"Prediction {name} must be a list")
            ids = set()
            for value in values:
                _require(isinstance(value, dict), f"Each {name} prediction must be an object")
                key = _text(value.get("id"), "predicted POI id")
                _require(key not in ids, f"Prediction {name} ids must be unique")
                ids.add(key)
                if name == "poi_positions" and value.get("image") is not None:
                    _point(value["image"], "predicted POI image")
                if name == "poi_visibility":
                    _require(value.get("visible") is None or type(value["visible"]) is bool,
                             "Predicted POI visible must be a boolean or null")
        predictions[identifier] = row
    return predictions


def evaluate_predictions(dataset: Dataset, predictions: dict[str, dict], *, tolerance_px=8.0) -> dict:
    """Score explicit manual facts only, showing missing predictions separately.

    Accuracy is conditional on a known prediction and is always accompanied by
    coverage. Success rate includes every eligible manual label, so unknown
    predictions cannot appear as passes or silently inflate overall success.
    """
    _require(_number(tolerance_px) and tolerance_px >= 0, "tolerance_px must be finite and nonnegative")
    fields = ("map_visible", "map_id", "player_count", "own_marker_visible", "zoomed", "panned", "poi_visibility")
    metrics = {field: {"eligible": 0, "compared": 0, "correct": 0, "incorrect": 0,
                       "unknown_prediction": 0} for field in fields}
    errors = {field: {"eligible": 0, "errors_px": []} for field in ("own_marker", "poi_positions")}

    def compare(field, actual, predicted):
        if actual is None:
            return
        metric = metrics[field]
        metric["eligible"] += 1
        if predicted is None:
            metric["unknown_prediction"] += 1
        else:
            _require(type(predicted) is type(actual), f"Prediction {field} has the wrong value type")
            metric["compared"] += 1
            metric["correct" if actual == predicted else "incorrect"] += 1

    def compare_point(field, actual, predicted):
        metric = errors[field]
        metric["eligible"] += 1
        if predicted is not None:
            _point(predicted, f"prediction {field}")
            metric["errors_px"].append(math.hypot(actual[0] - predicted[0], actual[1] - predicted[1]))

    for capture in dataset.captures:
        if capture.annotation_status == "unannotated":
            continue
        truth, predicted = capture.ground_truth, predictions.get(capture.id, {})
        for field in fields[:-1]:
            compare(field, truth.get(field), predicted.get(field))
        if truth.get("own_marker_visible") is True and truth.get("own_marker") is not None:
            compare_point("own_marker", truth["own_marker"], predicted.get("own_marker"))
        actual_points = {anchor.get("id", f"anchor-{i}"): anchor["image"]
                         for i, anchor in enumerate((truth.get("map_viewport") or {}).get("anchors", []), 1)}
        predicted_points = {point["id"]: point.get("image") for point in predicted.get("poi_positions", [])}
        predicted_visibility = {point["id"]: point.get("visible") for point in predicted.get("poi_visibility", [])}
        for poi in truth.get("poi_visibility", []):
            compare("poi_visibility", poi.get("visible"), predicted_visibility.get(poi["id"]))
            if poi.get("visible") is True and poi.get("image") is not None:
                actual_points.setdefault(poi["id"], poi["image"])
        for identifier, point in actual_points.items():
            compare_point("poi_positions", point, predicted_points.get(identifier))
    for metric in metrics.values():
        metric["accuracy"] = metric["correct"] / metric["compared"] if metric["compared"] else None
        metric["coverage"] = metric["compared"] / metric["eligible"] if metric["eligible"] else None
        metric["success_rate"] = metric["correct"] / metric["eligible"] if metric["eligible"] else None
    for metric in errors.values():
        values = metric.pop("errors_px")
        compared = len(values)
        metric.update(compared=compared, unknown_prediction=metric["eligible"] - compared,
                      mean_error_px=sum(values) / compared if compared else None,
                      max_error_px=max(values) if values else None, tolerance_px=tolerance_px,
                      within_tolerance=sum(error <= tolerance_px for error in values),
                      coverage=compared / metric["eligible"] if metric["eligible"] else None,
                      success_rate=(sum(error <= tolerance_px for error in values) / metric["eligible"]
                                    if metric["eligible"] else None))
    return {"capture_count": len(dataset.captures),
            "unannotated_captures_excluded": sum(c.annotation_status == "unannotated" for c in dataset.captures),
            "unknown_capture_ids_in_predictions": sorted(set(predictions) - {c.id for c in dataset.captures}),
            "classification": metrics, "position": errors}
