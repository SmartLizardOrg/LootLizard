"""Experimental, offline matching of a user-trained icon, not player identity.

A profile is valid only for the captured map layout, screen size, and icon
appearance. A matching icon may belong to somebody else in another match.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .core import Bounds

# Keep on-demand work on one CPU thread. OpenCL driver discovery can block
# inside constrained Windows sessions even when ORB is given a CPU array.
# This process never needs GPU acceleration for a single requested snapshot.
cv2.setNumThreads(1)
cv2.ocl.setUseOpenCL(False)


MAX_IMAGE_PIXELS = 40_000_000
MAX_REFERENCE_PIXELS = 4096 * 4096
COLOR_DISTANCE = 58
MIN_SHAPE_SCORE = .82


@dataclass(frozen=True)
class Recognition:
    position: tuple[float, float] | None
    score: float
    reason: str
    layout_verified: bool = False


def _integer(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _rgb(image: Image.Image) -> np.ndarray:
    if not isinstance(image, Image.Image):
        raise ValueError("A PIL image is required")
    width, height = image.size
    if min(width, height) < 1 or max(width, height) > 16384 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("Screenshot dimensions exceed the supported limit")
    return np.asarray(image.convert("RGB"), dtype=np.uint8).copy()


def _color_mask(image: np.ndarray, color: np.ndarray) -> np.ndarray:
    difference = image.astype(np.int32) - np.asarray(color, dtype=np.int32)
    matches = (np.sum(difference * difference, axis=2) <= COLOR_DISTANCE ** 2)
    return matches.astype(np.uint8) * 255


def _mask_quality(mask: np.ndarray) -> None:
    if mask.dtype != np.uint8 or mask.ndim != 2 or not all(7 <= n <= 90 for n in mask.shape):
        raise ValueError("The icon box must measure 7 to 90 pixels on each side")
    if not np.isin(mask, (0, 255)).all():
        raise ValueError("The icon mask must be binary")
    area = int(np.count_nonzero(mask))
    if area < 15 or area > mask.size * .75:
        raise ValueError("The selected icon is too small or mostly fills its box")
    if mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any():
        raise ValueError("The icon touches the box edge; include a small background margin")
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if count != 2 or min(stats[1, cv2.CC_STAT_WIDTH], stats[1, cv2.CC_STAT_HEIGHT]) < 4:
        raise ValueError("Select one connected, sufficiently detailed icon component")


@dataclass
class Profile:
    map_id: str
    image_size: tuple[int, int]
    bounds: Bounds
    mask: np.ndarray
    color: np.ndarray
    reference: np.ndarray

    @property
    def reference_map(self) -> np.ndarray:
        return self.reference

    def _validate(self) -> None:
        if not isinstance(self.map_id, str) or not self.map_id.strip() or len(self.map_id) > 160:
            raise ValueError("A short map id is required")
        if len(self.image_size) != 2 or not all(_integer(n) and 1 <= n <= 16384 for n in self.image_size):
            raise ValueError("Invalid profile screenshot dimensions")
        if self.image_size[0] * self.image_size[1] > MAX_IMAGE_PIXELS:
            raise ValueError("Profile screenshot is too large")
        if not isinstance(self.bounds, Bounds) or not all(_integer(n) for n in self.bounds.as_box()):
            raise ValueError("Profile map bounds must contain integer pixels")
        self.bounds.validate(*self.image_size)
        width = self.bounds.right - self.bounds.left
        height = self.bounds.bottom - self.bounds.top
        if min(width, height) < 128 or width * height > MAX_REFERENCE_PIXELS:
            raise ValueError("The reference map must be at least 128 pixels and at most 4096 squared pixels")
        if not isinstance(self.reference, np.ndarray) or self.reference.dtype != np.uint8 or self.reference.shape != (height, width, 3):
            raise ValueError("The RGB reference does not match the calibrated map bounds")
        if not isinstance(self.color, np.ndarray) or self.color.shape != (3,) or self.color.dtype != np.uint8:
            raise ValueError("The profile needs one RGB icon color")
        _mask_quality(self.mask)

    def save(self, directory: Path) -> None:
        """Explicitly persist the cropped reference map, silhouette, and metadata."""
        self._validate()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        Image.fromarray(self.reference).save(directory / "reference.png")
        Image.fromarray(self.mask).save(directory / "mask.png")
        data = {"version": 1, "map_id": self.map_id,
                "image_size": list(self.image_size), "bounds": list(self.bounds.as_box()),
                "color": self.color.tolist()}
        (directory / "profile.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, directory: Path) -> "Profile":
        directory = Path(directory)
        metadata_path = directory / "profile.json"
        if metadata_path.stat().st_size > 16_384:
            raise ValueError("Profile metadata exceeds the 16 KB limit")
        data = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("Unsupported profile format")
        size, bounds, color = (data.get(name) for name in ("image_size", "bounds", "color"))
        for values, length in ((size, 2), (bounds, 4), (color, 3)):
            if not isinstance(values, list) or len(values) != length or not all(_integer(n) for n in values):
                raise ValueError("Invalid profile dimensions, bounds, or color")
        if not all(0 <= n <= 255 for n in color):
            raise ValueError("Invalid RGB profile color")

        def read_png(name: str, mode: str, max_bytes: int, max_pixels: int) -> np.ndarray:
            path = directory / name
            if path.stat().st_size > max_bytes:
                raise ValueError(f"{name} exceeds its file-size limit")
            with Image.open(path) as source:
                if source.format != "PNG" or source.mode != mode or source.width * source.height > max_pixels:
                    raise ValueError(f"Invalid {name} format, mode, or dimensions")
                if name == "mask.png" and not all(7 <= n <= 90 for n in source.size):
                    raise ValueError("Invalid mask dimensions")
                return np.asarray(source, dtype=np.uint8).copy()

        profile = cls(data.get("map_id"), tuple(size), Bounds(*bounds),
                      read_png("mask.png", "L", 65_536, 8100), np.array(color, dtype=np.uint8),
                      read_png("reference.png", "RGB", 64_000_000, MAX_REFERENCE_PIXELS))
        profile._validate()
        return profile


def _map_identity(reference: np.ndarray, current: np.ndarray) -> tuple[bool, str]:
    """Require distributed map features and an affine transform near identity."""
    # OpenCL use is thread-local: the UI thread's setting does not cover the
    # recognition executor. Disable driver discovery in every calling thread.
    cv2.ocl.setUseOpenCL(False)
    scale = min(1., 800 / max(reference.shape[:2]))
    dimensions = (round(reference.shape[1] * scale), round(reference.shape[0] * scale))
    images = [cv2.cvtColor(cv2.resize(image, dimensions, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
              for image in (reference, current)]
    orb = cv2.ORB_create(nfeatures=1800, edgeThreshold=15, fastThreshold=10)
    keypoints_a, descriptors_a = orb.detectAndCompute(images[0], None)
    keypoints_b, descriptors_b = orb.detectAndCompute(images[1], None)
    if descriptors_a is None or descriptors_b is None or min(len(keypoints_a), len(keypoints_b)) < 40:
        return False, "Not enough map detail; the full map may be closed or obscured"
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(descriptors_a, descriptors_b, k=2)
    good = [pair[0] for pair in matches if len(pair) == 2 and pair[0].distance < .72 * pair[1].distance]
    # Several query descriptors must not vote for one train point.
    unique = {}
    for match in sorted(good, key=lambda match: match.distance):
        unique.setdefault(match.trainIdx, match)
    good = list(unique.values())
    if len(good) < 24:
        return False, "The selected map does not match the saved reference"
    source = np.float32([keypoints_a[match.queryIdx].pt for match in good])
    target = np.float32([keypoints_b[match.trainIdx].pt for match in good])
    affine, inliers = cv2.estimateAffinePartial2D(source, target, method=cv2.RANSAC,
                                               ransacReprojThreshold=2., maxIters=2000,
                                               confidence=.995, refineIters=10)
    if affine is None or inliers is None or not np.isfinite(affine).all():
        return False, "The map layout could not be verified"
    keep = inliers.ravel().astype(bool)
    if np.count_nonzero(keep) < 24 or np.mean(keep) < .55:
        return False, "Too few consistent map features"
    points = source[keep]
    quadrants = {(int(x >= dimensions[0] / 2), int(y >= dimensions[1] / 2)) for x, y in points}
    if len(quadrants) < 3 or np.ptp(points[:, 0]) < dimensions[0] * .45 or np.ptp(points[:, 1]) < dimensions[1] * .45:
        return False, "Map matches do not cover enough of the full map"
    if np.max(np.abs(affine[:, :2] - np.eye(2))) > .006 or np.max(np.abs(affine[:, 2])) / scale > 2.5:
        return False, "Map zoom, rotation, or position changed; use the saved full-map layout"
    return True, "Map layout verified"


def create_profile(image: Image.Image, bounds: Bounds,
                   marker_box: tuple[int, int, int, int], seed: tuple[int, int],
                   map_id: str) -> Profile:
    rgb = _rgb(image)
    if not isinstance(bounds, Bounds) or not all(_integer(n) for n in bounds.as_box()):
        raise ValueError("Integer map bounds are required")
    bounds.validate(image.width, image.height)
    if len(marker_box) != 4 or len(seed) != 2 or not all(_integer(n) for n in (*marker_box, *seed)):
        raise ValueError("The icon box and seed must contain integer screenshot pixels")
    left, top, right, bottom = marker_box
    if not (bounds.left <= left < right <= bounds.right and bounds.top <= top < bottom <= bounds.bottom):
        raise ValueError("The icon box must be inside the map")
    if not (left <= seed[0] < right and top <= seed[1] < bottom):
        raise ValueError("Click an opaque icon pixel inside its box")
    if not all(7 <= n <= 90 for n in (right - left, bottom - top)):
        raise ValueError("The icon box must measure 7 to 90 pixels on each side")
    if image.mode == "RGBA" and image.getpixel(seed)[3] < 230:
        raise ValueError("The icon seed must be opaque")
    patch = rgb[top:bottom, left:right]
    seed_color = rgb[seed[1], seed[0]]
    _, labels, _, _ = cv2.connectedComponentsWithStats(_color_mask(patch, seed_color), connectivity=8)
    label = labels[seed[1] - top, seed[0] - left]
    mask = (labels == label).astype(np.uint8) * 255
    _mask_quality(mask)
    color = np.median(patch[mask != 0], axis=0).astype(np.uint8)
    border = np.concatenate((patch[0], patch[-1], patch[:, 0], patch[:, -1]))
    if np.median(np.linalg.norm(border.astype(float) - color, axis=1)) < 45:
        raise ValueError("The icon color is not distinct enough from the surrounding background")
    reference = rgb[bounds.top:bounds.bottom, bounds.left:bounds.right].copy()
    profile = Profile(map_id, image.size, bounds, mask, color, reference)
    profile._validate()
    verified, reason = _map_identity(reference, reference)
    if not verified:
        raise ValueError("Reference map is unsuitable: " + reason)
    return profile


def _shape_variants(mask: np.ndarray) -> tuple[list[tuple[np.ndarray, np.ndarray]], int]:
    moments = cv2.moments(mask, binaryImage=True)
    center = np.array((moments["m10"] / moments["m00"], moments["m01"] / moments["m00"]))
    anchor = np.array(((mask.shape[1] - 1) / 2, (mask.shape[0] - 1) / 2))
    side = math.ceil(math.hypot(*mask.shape)) + 12
    middle = (side - 1) / 2
    variants = []
    for angle in range(0, 360, 5):
        affine = cv2.getRotationMatrix2D(tuple(center), angle, 1.)
        affine[:, 2] += middle - center
        rotated = cv2.warpAffine(mask, affine, (side, side), flags=cv2.INTER_NEAREST)
        variants.append((rotated != 0, affine[:, :2] @ (center - anchor)))
    return variants, side


def recognize(image: Image.Image, profile: Profile, map_id: str) -> Recognition:
    """Return only a fresh, unique trained-icon match; never reuse a position."""
    try:
        profile._validate()
        if map_id != profile.map_id:
            return Recognition(None, 0., "Selected map differs from the trained profile")
        if image.size != profile.image_size:
            return Recognition(None, 0., "Screenshot dimensions changed; create a new profile")
        rgb = _rgb(image)
        bounds = profile.bounds
        current = rgb[bounds.top:bounds.bottom, bounds.left:bounds.right]
        verified, reason = _map_identity(profile.reference, current)
        if not verified:
            return Recognition(None, 0., reason)
        color_mask = _color_mask(current, profile.color)
        count, labels, stats, centers = cv2.connectedComponentsWithStats(color_mask, connectivity=8)
        reference_area = np.count_nonzero(profile.mask)
        variants, side = _shape_variants(profile.mask)
        candidates = []
        for label in range(1, count):
            x, y, width, height, area = stats[label]
            if not (.65 * reference_area <= area <= 1.5 * reference_area):
                continue
            if min(width, height) < 4 or max(width, height) >= side - 4:
                continue
            if x == 0 or y == 0 or x + width >= current.shape[1] or y + height >= current.shape[0]:
                continue
            candidates.append((label, x, y, width, height))
        if len(candidates) > 100:
            return Recognition(None, 0., "Too many similar-color objects; the profile is not selective enough", True)
        results = []
        middle = (side - 1) / 2
        for label, x, y, width, height in candidates:
            component = (labels[y:y + height, x:x + width] == label).astype(np.uint8) * 255
            centroid = centers[label]
            affine = np.array(((1., 0., middle - (centroid[0] - x)),
                               (0., 1., middle - (centroid[1] - y))))
            aligned = cv2.warpAffine(component, affine, (side, side), flags=cv2.INTER_NEAREST) != 0
            best_score, offset = 0., np.zeros(2)
            for silhouette, variant_offset in variants:
                union = np.count_nonzero(aligned | silhouette)
                score = np.count_nonzero(aligned & silhouette) / union if union else 0.
                if score > best_score:
                    best_score, offset = score, variant_offset
            anchor = centroid - offset
            results.append((best_score, float(anchor[0]), float(anchor[1])))
        results.sort(reverse=True)
        if not results or results[0][0] < MIN_SHAPE_SCORE:
            return Recognition(None, results[0][0] if results else 0., "No confident trained-icon match", True)
        score, x, y = results[0]
        if len(results) > 1 and (results[1][0] >= .80 or score - results[1][0] < .10):
            return Recognition(None, score, "Ambiguous: multiple objects resemble the trained icon", True)
        position = bounds.normalized(x + bounds.left, y + bounds.top)
        return Recognition(position, score, "Unique trained-icon match; player identity is not verified", True)
    except (ValueError, TypeError, AttributeError, cv2.error) as error:
        return Recognition(None, 0., "Recognition unavailable: " + str(error))
