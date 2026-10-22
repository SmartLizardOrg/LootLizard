"""Register a visible map against local, complete canonical map references.

No game/player identity, assets, downloads, or application state are involved.
Reference crops represent the entire normalized map. Their correct identity and
outer bounds must be established when collecting them; matching cannot repair a
mislabeled or incorrectly cropped reference. Small reference aspect differences
are tolerated, with bounded affine correction explicitly reported in diagnostics.
"""

from dataclasses import dataclass, field
import math
from typing import Sequence

import cv2
import numpy as np
from PIL import Image


cv2.setNumThreads(1)
cv2.ocl.setUseOpenCL(False)

Viewport = tuple[int, int, int, int]
WORK_SIDE = 1400
MIN_FEATURES = 40
MIN_INLIERS = 24
INTERIOR_MARGIN = .05
MAX_ANISOTROPY = 1.075
MAX_IMAGE_PIXELS = 40_000_000


def _rgb(image: Image.Image | np.ndarray) -> np.ndarray:
    if isinstance(image, Image.Image):
        width, height = image.size
        if max(width, height) > 16384 or width * height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds the supported dimensions")
        array = np.asarray(image.convert("RGB"), dtype=np.uint8)
    elif isinstance(image, np.ndarray) and image.dtype == np.uint8 and image.ndim == 3 and image.shape[2] == 3:
        array = image
    else:
        raise ValueError("An RGB uint8 array or PIL image is required")
    if min(array.shape[:2]) < 1 or max(array.shape[:2]) > 16384 or array.shape[0] * array.shape[1] > MAX_IMAGE_PIXELS:
        raise ValueError("Image exceeds the supported dimensions")
    return np.ascontiguousarray(array).copy()


def _viewport(value, width: int, height: int) -> Viewport:
    if value is None:
        value = (0, 0, width, height)
    if not isinstance(value, (tuple, list)) or len(value) != 4 or not all(
            isinstance(item, int) and not isinstance(item, bool) for item in value):
        raise ValueError("Viewport must contain four integer image coordinates")
    left, top, right, bottom = value
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("Viewport must be inside the screenshot")
    if min(right - left, bottom - top) < 128:
        raise ValueError("Viewport must be at least 128 pixels on each side")
    return tuple(value)


def _features(image: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    # OpenCL selection is thread-local; disable it in the calling worker too.
    cv2.ocl.setUseOpenCL(False)
    scale = min(1., WORK_SIDE / max(image.shape[:2]))
    size = (max(1, round(image.shape[1] * scale)), max(1, round(image.shape[0] * scale)))
    gray = cv2.cvtColor(cv2.resize(image, size, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    detector = cv2.SIFT_create(nfeatures=4500, contrastThreshold=.025, edgeThreshold=12)
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    if not keypoints or descriptors is None:
        return np.empty((0, 2), np.float32), None
    # Store native image coordinates, independent of the work-image size.
    factors = np.array((image.shape[1] / size[0], image.shape[0] / size[1]))
    points = np.float32([point.pt for point in keypoints]) * factors
    return points.astype(np.float32), descriptors


def _coverage(points: np.ndarray, width: int, height: int) -> tuple[float, float, float]:
    if len(points) < 3:
        return 0., 0., 0.
    area = float(cv2.contourArea(cv2.convexHull(points.astype(np.float32))))
    return area / (width * height), float(np.ptp(points[:, 0]) / width), float(np.ptp(points[:, 1]) / height)


@dataclass(frozen=True)
class MapReference:
    map_id: str
    image: Image.Image | np.ndarray = field(repr=False, compare=False)
    _points: np.ndarray = field(init=False, repr=False, compare=False)
    _descriptors: np.ndarray = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.map_id, str) or not self.map_id.strip() or len(self.map_id) > 160:
            raise ValueError("A short canonical map id is required")
        image = _rgb(self.image)
        height, width = image.shape[:2]
        if min(width, height) < 128 or max(width, height) > 8192:
            raise ValueError("A full-map reference must measure 128 to 8192 pixels")
        if max(width, height) / min(width, height) > MAX_ANISOTROPY:
            raise ValueError("A canonical full-map reference must be approximately square")
        points, descriptors = _features(image)
        coverage, span_x, span_y = _coverage(points, width, height)
        if descriptors is None or len(points) < MIN_FEATURES or coverage < .15 or min(span_x, span_y) < .4:
            raise ValueError("The reference needs distributed detail across the full map")
        image.setflags(write=False)
        points.setflags(write=False)
        descriptors.setflags(write=False)
        object.__setattr__(self, "image", image)
        object.__setattr__(self, "_points", points)
        object.__setattr__(self, "_descriptors", descriptors)

    @property
    def image_size(self) -> tuple[int, int]:
        return self.image.shape[1], self.image.shape[0]


def _point(matrix: np.ndarray, x: float, y: float) -> tuple[float, float] | None:
    if isinstance(x, bool) or isinstance(y, bool):
        return None
    try:
        result = matrix @ np.array((float(x), float(y), 1.))
    except (TypeError, ValueError):
        return None
    if not np.isfinite(result).all() or abs(result[2]) < 1e-12:
        return None
    return float(result[0] / result[2]), float(result[1] / result[2])


@dataclass(frozen=True)
class Registration:
    map_id: str | None
    map_to_image: np.ndarray | None
    viewport: Viewport
    reason: str
    diagnostics: dict = field(default_factory=dict)

    @property
    def image_to_map(self) -> np.ndarray | None:
        if self.map_to_image is None:
            return None
        try:
            return np.linalg.inv(self.map_to_image)
        except np.linalg.LinAlgError:
            return None

    def project_poi(self, x: float, y: float, *, clip: bool = True) -> tuple[float, float] | None:
        """Normalized full-map point to full screenshot pixels; off-view is None."""
        if self.map_id is None or self.map_to_image is None:
            return None
        try:
            if not (0 <= x <= 1 and 0 <= y <= 1):
                return None
        except TypeError:
            return None
        point = _point(self.map_to_image, x, y)
        if point is not None and clip:
            left, top, right, bottom = self.viewport
            if not (left <= point[0] < right and top <= point[1] < bottom):
                return None
        return point

    def image_point_to_map(self, x: float, y: float, *, clip: bool = True) -> tuple[float, float] | None:
        inverse = self.image_to_map
        if inverse is None or self.map_id is None:
            return None
        try:
            left, top, right, bottom = self.viewport
            if clip and not (left <= x < right and top <= y < bottom):
                return None
        except TypeError:
            return None
        point = _point(inverse, x, y)
        if point is not None and clip and not (0 <= point[0] <= 1 and 0 <= point[1] <= 1):
            return None
        return point


def project_poi(registration: Registration, x: float, y: float, *, clip: bool = True):
    return registration.project_poi(x, y, clip=clip)


def _assess(matrix, inliers, source, target, reference, viewport, tolerance, model):
    diagnostics = {"model": model, "matches": len(source), "inliers": 0}
    if matrix is None or inliers is None or not np.isfinite(matrix).all():
        return None, diagnostics, "No consistent map transform"
    keep = inliers.ravel().astype(bool)
    count = int(np.count_nonzero(keep))
    diagnostics.update(inliers=count, inlier_ratio=float(np.mean(keep)))
    if count < MIN_INLIERS or np.mean(keep) < .45:
        return None, diagnostics, "Too few consistent map matches"
    linear = matrix[:, :2]
    determinant = float(np.linalg.det(linear))
    if determinant <= 0:
        return None, diagnostics, "Reflected map transforms are unsupported"
    u, singular, vt = np.linalg.svd(linear)
    rotation = u @ vt
    angle = math.degrees(math.atan2(rotation[1, 0], rotation[0, 0]))
    anisotropy = float(singular[0] / singular[-1]) if singular[-1] > 1e-12 else math.inf
    scale = math.sqrt(determinant)
    diagnostics.update(scale=scale, anisotropy=anisotropy, rotation_degrees=angle)
    if not .05 <= scale <= 32 or anisotropy > MAX_ANISOTROPY or abs(angle) > 3:
        return None, diagnostics, "Map scale, distortion, or rotation is unsupported"
    shear = abs(float(np.dot(linear[:, 0], linear[:, 1]))) / (np.linalg.norm(linear[:, 0]) * np.linalg.norm(linear[:, 1]))
    if shear > .04:
        return None, diagnostics, "Map shear is unsupported"
    left, top, right, bottom = viewport
    width, height = right - left, bottom - top
    reference_width, reference_height = reference.image_size
    normalized_source = source / np.array((reference_width, reference_height))
    interior = keep & np.all((normalized_source >= INTERIOR_MARGIN)
                             & (normalized_source <= 1.-INTERIOR_MARGIN), axis=1)
    interior_count = int(np.count_nonzero(interior))
    interior_coverage, interior_span_x, interior_span_y = _coverage(target[interior], width, height)
    diagnostics.update(interior_inliers=interior_count, interior_coverage=interior_coverage,
                       interior_span_x=interior_span_x, interior_span_y=interior_span_y)
    # Shared grid letters and HUD symbols can sit along every edge, yielding
    # a large convex hull and a precise transform even on a different map.
    # Require independently distributed support inside the canonical map;
    # neither border labels nor one repeated interior icon patch establish it.
    if interior_count < MIN_INLIERS or interior_coverage < .12 or min(interior_span_x, interior_span_y) < .35:
        return None, diagnostics, "Map matches lack distributed interior support"
    coverage, span_x, span_y = _coverage(target[keep], width, height)
    # target points are crop-local, so these ratios measure viewport coverage.
    diagnostics.update(coverage=coverage, span_x=span_x, span_y=span_y)
    if coverage < .12 or min(span_x, span_y) < .35:
        return None, diagnostics, "Matches cover too little of the map viewport"
    projected = source[keep] @ linear.T + matrix[:, 2]
    errors = np.linalg.norm(projected - target[keep], axis=1)
    median_error, max_error = float(np.median(errors)), float(np.max(errors))
    diagnostics.update(median_reprojection_error=median_error, max_reprojection_error=max_error)
    if median_error > tolerance * .75 or max_error > tolerance * 1.5:
        return None, diagnostics, "Map reprojection error is too large"
    pixel_to_view = np.vstack((matrix, (0., 0., 1.)))
    crop_to_image = np.array(((1., 0., left), (0., 1., top), (0., 0., 1.)))
    normalized_to_reference = np.diag((float(reference_width), float(reference_height), 1.))
    normalized_to_image = crop_to_image @ pixel_to_view @ normalized_to_reference
    canonical_singular = np.linalg.svd(normalized_to_image[:2, :2], compute_uv=False)
    canonical_anisotropy = float(canonical_singular[0] / canonical_singular[-1])
    map_side = math.sqrt(float(np.linalg.det(normalized_to_image[:2, :2])))
    diagnostics.update(canonical_anisotropy=canonical_anisotropy, map_side_pixels=map_side,
                       reference_size=list(reference.image_size))
    if canonical_anisotropy > MAX_ANISOTROPY:
        return None, diagnostics, "Canonical map geometry is too distorted"
    if map_side < min(width, height) * .55:
        return None, diagnostics, "Map is too small; a minimap or label patch is not enough"
    return normalized_to_image, diagnostics, "Map transform verified"


def _match_reference(reference: MapReference, points, descriptors, viewport):
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    pairs = matcher.knnMatch(reference._descriptors, descriptors, k=2)
    good = [pair[0] for pair in pairs if len(pair) == 2 and pair[0].distance < .72 * pair[1].distance]
    unique = {}
    for match in sorted(good, key=lambda match: match.distance):
        unique.setdefault(match.trainIdx, match)
    good = list(unique.values())
    diagnostics = {"map_id": reference.map_id, "matches": len(good), "inliers": 0}
    if len(good) < MIN_INLIERS:
        return None, diagnostics, "Not enough distinctive matches for this map"
    source = np.float32([reference._points[match.queryIdx] for match in good])
    target = np.float32([points[match.trainIdx] for match in good])
    tolerance = max(3., max(viewport[2]-viewport[0], viewport[3]-viewport[1]) * .002)
    arguments = dict(method=cv2.RANSAC, ransacReprojThreshold=tolerance,
                     maxIters=3000, confidence=.995, refineIters=10)
    matrix, inliers = cv2.estimateAffinePartial2D(source, target, **arguments)
    result, partial, reason = _assess(matrix, inliers, source, target, reference, viewport, tolerance, "similarity")
    # A bounded affine correction handles small aspect/calibration differences,
    # but never admits a free perspective warp or a substantially stretched map.
    affine, affine_inliers = cv2.estimateAffine2D(source, target, **arguments)
    alternative, complete, affine_reason = _assess(
        affine, affine_inliers, source, target, reference, viewport, tolerance, "bounded_affine")
    prefer_affine = alternative is not None and (result is None
        or complete["inliers"] > partial["inliers"] * 1.15
        or (partial.get("median_reprojection_error", 0.) > 1.25
            and complete["median_reprojection_error"] < partial["median_reprojection_error"] * .6))
    if prefer_affine:
        result, diagnostics, reason = alternative, complete, affine_reason
    else:
        diagnostics = partial
    diagnostics["map_id"] = reference.map_id
    return result, diagnostics, reason


def register_map(image: Image.Image | np.ndarray, references: Sequence[MapReference],
                 viewport: Viewport | None = None) -> Registration:
    """Identify a unique referenced map and register its current zoom/pan.

    ``viewport`` is a rectangular map search region in full screenshot pixels;
    it does not need to be square or show the entire map. No player icon is
    required. Unknown, weak, ambiguous, or unsupported views return no matrix.
    """
    checked_viewport = (0, 0, 0, 0)
    try:
        rgb = _rgb(image)
        checked_viewport = _viewport(viewport, rgb.shape[1], rgb.shape[0])
        references = tuple(references)
        if not references:
            return Registration(None, None, checked_viewport, "No canonical map references are loaded")
        if len(references) > 32 or not all(isinstance(reference, MapReference) for reference in references):
            raise ValueError("Provide at most 32 canonical MapReference objects")
        if len({reference.map_id for reference in references}) != len(references):
            raise ValueError("Each canonical map id must be unique")
        left, top, right, bottom = checked_viewport
        points, descriptors = _features(rgb[top:bottom, left:right])
        if descriptors is None or len(points) < MIN_FEATURES:
            return Registration(None, None, checked_viewport, "Not enough visible map detail")
        accepted, candidates = [], []
        for reference in references:
            matrix, diagnostics, reason = _match_reference(reference, points, descriptors, checked_viewport)
            diagnostics["reason"] = reason
            diagnostics["accepted"] = matrix is not None
            candidates.append(diagnostics)
            if matrix is not None:
                accepted.append((reference.map_id, matrix, diagnostics))
        if not accepted:
            return Registration(None, None, checked_viewport,
                                "No canonical map passed registration checks", {"candidates": candidates})
        if len(accepted) != 1:
            return Registration(None, None, checked_viewport,
                                "Ambiguous map: multiple canonical references match", {"candidates": candidates})
        map_id, matrix, diagnostics = accepted[0]
        matrix.setflags(write=False)
        return Registration(map_id, matrix, checked_viewport, "Canonical map registered",
                            {**diagnostics, "candidates": candidates})
    except (ValueError, TypeError, cv2.error, np.linalg.LinAlgError) as error:
        return Registration(None, None, checked_viewport, "Registration unavailable: " + str(error))


from pathlib import Path


def load_reference_catalog(path: Path) -> tuple[MapReference, ...]:
    """Load an explicitly selected local catalog without copying image files.

    Version 1 is ``{schema_version: 1, references: [{map_id, file, sha256?}]}``.
    Image paths are relative to the catalog's directory; subdirectories are
    supported, while absolute paths, traversal, streams, and symlink escapes
    are rejected. A catalog has at most 32 unique map ids. It must not exceed
    128 KiB, and each RGB PNG/JPEG is limited to 64 MiB, 8192 pixels per side,
    and 40 million pixels before decoding. MapReference then verifies geometry
    and distributed map detail. Extra provenance fields are retained on disk.

    Raises ValueError or OSError for malformed or unavailable input. No assets
    are downloaded, generated, saved, or copied by this function.
    """
    import hashlib
    import json
    from pathlib import PureWindowsPath
    import re

    catalog = Path(path).resolve(strict=True)
    if catalog.stat().st_size > 128 * 1024:
        raise ValueError("Reference catalog exceeds the 128 KiB limit")
    with catalog.open(encoding="utf-8-sig") as stream:
        document = json.load(stream)
    if (not isinstance(document, dict) or type(document.get("schema_version")) is not int
            or document["schema_version"] != 1):
        raise ValueError("Unsupported reference catalog schema_version")
    records = document.get("references")
    if not isinstance(records, list) or len(records) > 32:
        raise ValueError("A catalog must contain at most 32 map references")
    root, checked, seen = catalog.parent, [], set()
    # Check every record before decoding any image, so an invalid catalog never
    # leaves the caller with a silently accepted subset of map identities.
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each reference entry must be an object")
        map_id, filename = record.get("map_id"), record.get("file")
        if not isinstance(map_id, str) or not map_id.strip() or len(map_id) > 160:
            raise ValueError("A short canonical map id is required")
        if map_id in seen:
            raise ValueError("Each canonical map id must be unique")
        seen.add(map_id)
        if (not isinstance(filename, str) or not filename
                or any(ord(character) < 32 for character in filename)
                or ":" in filename or PureWindowsPath(filename).drive):
            raise ValueError("Reference image paths must be relative to the catalog directory")
        relative = Path(filename.replace("\\", "/"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Reference image paths must stay inside the catalog directory")
        image_path = (root / relative).resolve()
        if image_path == root or not image_path.is_relative_to(root):
            raise ValueError("Reference image symlinks must stay inside the catalog directory")
        if image_path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Reference image exceeds the 64 MiB limit")
        digest = record.get("sha256")
        if digest is not None and (not isinstance(digest, str)
                                   or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None):
            raise ValueError("Reference sha256 must contain 64 hexadecimal digits")
        checked.append((map_id, image_path, digest))
    references = []
    for map_id, image_path, expected_hash in checked:
        if expected_hash is not None:
            digest = hashlib.sha256()
            with image_path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected_hash.lower():
                raise ValueError("Reference image sha256 does not match the catalog")
        try:
            with Image.open(image_path) as image:
                width, height = image.size
                if image.format not in ("PNG", "JPEG") or image.mode != "RGB":
                    raise ValueError("Reference images must be RGB PNG or JPEG files")
                if (min(width, height) < 128 or max(width, height) > 8192
                        or width * height > MAX_IMAGE_PIXELS):
                    raise ValueError("Reference image exceeds the supported dimensions")
                image.load()
                references.append(MapReference(map_id, image))
        except Image.DecompressionBombError as error:
            raise ValueError("Reference image exceeds the supported dimensions") from error
    return tuple(references)
