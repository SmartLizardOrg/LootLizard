"""Conservative, offline detection of a white safe-zone ring in a map crop.

This detects visible geometry, not game state. A similarly drawn non-zone white
circle cannot be distinguished from a safe-zone ring by pixels alone. Weak,
small, heavily obscured, or competing rings therefore return no zone.
"""

from dataclasses import dataclass
import math

import cv2
import numpy as np
from PIL import Image

from .core import Bounds, SafeZone


@dataclass(frozen=True)
class ZoneDetection:
    zone: SafeZone | None
    score: float
    reason: str


MAX_IMAGE_PIXELS = 40_000_000
WORK_SIDE = 1024
MIN_SUPPORT = .72
MIN_RIDGE_SUPPORT = .62
MIN_RAW_WHITE_SUPPORT = .75


def _white_mask(image: Image.Image, bounds: Bounds) -> np.ndarray:
    """Keep bright, nearly neutral strokes; blue/yellow rings are excluded."""
    crop = image.crop(bounds.as_box()).convert("RGBA")
    side = min(WORK_SIDE, max(crop.size))
    # Preserve pixel aspect ratio: a slightly imprecise map calibration must not
    # turn a real circular stroke into an ellipse before circle fitting.
    scale = side / max(crop.size)
    size = (round(crop.width * scale), round(crop.height * scale))
    rgba = np.asarray(crop.resize(size, Image.Resampling.LANCZOS))
    rgb = rgba[:, :, :3].astype(np.int16)
    minimum, maximum = rgb.min(axis=2), rgb.max(axis=2)
    neutral = (minimum >= 175) & (maximum - minimum <= 30)
    mask = (neutral & (rgba[:, :, 3] >= 230)).astype(np.uint8) * 255
    # A map frame must not contribute circle support at its clipping boundary.
    mask[:2] = mask[-2:] = 0
    mask[:, :2] = mask[:, -2:] = 0
    return mask


def _fit_circle(points: np.ndarray) -> np.ndarray | None:
    if len(points) < 12:
        return None
    origin = points.mean(axis=0)
    centered = points - origin
    matrix = np.column_stack((2 * centered, np.ones(len(points))))
    solution, _, rank, _ = np.linalg.lstsq(matrix, np.sum(centered ** 2, axis=1), rcond=None)
    if rank < 3:
        return None
    radius_squared = solution[2] + np.sum(solution[:2] ** 2)
    if radius_squared <= 0:
        return None
    return np.array((*tuple(solution[:2] + origin), math.sqrt(radius_squared)))


def _valid_circles(circles: np.ndarray, shape: tuple[int, int], minimum: float) -> np.ndarray:
    circles = np.asarray(circles, dtype=np.float64).reshape((-1, 3))
    height, width = shape
    keep = (np.isfinite(circles).all(axis=1)
            & (circles[:, 0] >= 0) & (circles[:, 0] < width)
            & (circles[:, 1] >= 0) & (circles[:, 1] < height)
            & (circles[:, 2] >= minimum) & (circles[:, 2] <= max(shape) * 1.2))
    return circles[keep]


def _candidates(mask: np.ndarray, minimum: float) -> np.ndarray:
    """Hough plus deterministic three-point proposals, including clipped arcs."""
    side = max(mask.shape)
    proposals = []
    hough = cv2.HoughCircles(mask, cv2.HOUGH_GRADIENT, dp=1.4,
                             minDist=max(10, side * .025), param1=100, param2=28,
                             minRadius=int(minimum), maxRadius=int(side * 1.2))
    if hough is not None:
        proposals.extend(hough[0, :80])
    contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    for contour in sorted(contours, key=len, reverse=True)[:60]:
        if len(contour) >= max(40, minimum * 2):
            fitted = _fit_circle(contour[:, 0].astype(float))
            if fitted is not None:
                proposals.append(fitted)
    ys, xs = np.nonzero(cv2.Canny(mask, 80, 160))
    if len(xs) >= 30:
        random = np.random.default_rng(2917)
        points = np.column_stack((xs, ys)).astype(float)
        if len(points) > 12000:
            points = points[random.choice(len(points), 12000, replace=False)]
        triples = points[random.integers(0, len(points), (4500, 3))]
        a, b, c = (triples[:, index] for index in range(3))
        determinant = 2 * (a[:, 0] * (b[:, 1] - c[:, 1])
                           + b[:, 0] * (c[:, 1] - a[:, 1])
                           + c[:, 0] * (a[:, 1] - b[:, 1]))
        usable = np.abs(determinant) > 20
        a, b, c, determinant = a[usable], b[usable], c[usable], determinant[usable]
        aa, bb, cc = (np.sum(point ** 2, axis=1) for point in (a, b, c))
        x = (aa * (b[:, 1] - c[:, 1]) + bb * (c[:, 1] - a[:, 1])
             + cc * (a[:, 1] - b[:, 1])) / determinant
        y = (aa * (c[:, 0] - b[:, 0]) + bb * (a[:, 0] - c[:, 0])
             + cc * (b[:, 0] - a[:, 0])) / determinant
        radii = np.hypot(x - a[:, 0], y - a[:, 1])
        proposals.extend(np.column_stack((x, y, radii)))
    return _valid_circles(proposals, mask.shape, minimum)


def _angular_samples(circles: np.ndarray, distance: np.ndarray,
                     count: int, tolerance: float) -> tuple[np.ndarray, np.ndarray]:
    angles = np.arange(count) * (2 * math.pi / count)
    x = circles[:, 0, None] + circles[:, 2, None] * np.cos(angles)
    y = circles[:, 1, None] + circles[:, 2, None] * np.sin(angles)
    height, width = distance.shape
    visible = (x >= 3) & (x < width - 3) & (y >= 3) & (y < height - 3)
    ix = np.clip(np.rint(x).astype(int), 0, width - 1)
    iy = np.clip(np.rint(y).astype(int), 0, height - 1)
    supported = visible & (distance[iy, ix] <= tolerance)
    return visible, supported


def _same_circle(a: np.ndarray, b: np.ndarray, tolerance: float = 4.) -> bool:
    tolerance = max(tolerance, min(a[2], b[2]) * .012)
    return np.linalg.norm(a[:2] - b[:2]) <= tolerance and abs(a[2] - b[2]) <= tolerance


def _refine(circle: np.ndarray, points: np.ndarray) -> np.ndarray | None:
    current = circle.copy()
    change = math.inf
    for band in (5., 4., 3.5, 3., 3., 3., 3., 3., 3., 3.):
        distances = np.abs(np.hypot(points[:, 0] - current[0],
                                    points[:, 1] - current[1]) - current[2])
        nearby = points[distances <= band]
        if len(nearby) < 40:
            return None
        fitted = _fit_circle(nearby)
        if fitted is None:
            return None
        change = max(np.linalg.norm(fitted[:2] - current[:2]), abs(fitted[2] - current[2]))
        current = fitted
        if band == 3. and change < .05:
            break
    # A still-moving fit on a clipped arc has not constrained the circle enough.
    return current if change <= .20 else None


def _evidence(circle: np.ndarray, distance: np.ndarray) -> tuple[bool, float]:
    """Require a thin white ridge over most of the circumference visible in-map."""
    count = 720
    visible, support = _angular_samples(circle[None], distance, count, 1.8)
    visible, support = visible[0], support[0]
    expected = int(np.count_nonzero(visible))
    if expected < 120:  # Less than 60 degrees in view is poorly constrained.
        return False, 0.
    support_fraction = np.count_nonzero(support) / expected
    # A distance tolerance must not turn closely spaced dots into a solid ring.
    # Require actual white pixels on the fitted centerline as well as proximity.
    _, raw_support = _angular_samples(circle[None], distance, count, 0.)
    raw_support = raw_support[0]
    raw_fraction = np.count_nonzero(raw_support) / expected
    longest = current_run = 0
    for present in np.concatenate((raw_support, raw_support)):
        current_run = current_run + 1 if present else 0
        longest = max(longest, current_run)
    continuous_degrees = min(longest, count) * 360 / count
    flanks = np.repeat(circle[None], 2, axis=0)
    flanks[:, 2] += (-5., 5.)
    flank_visible, flank_support = _angular_samples(flanks, distance, count, 1.)
    comparable = visible & flank_visible.all(axis=0)
    if np.count_nonzero(comparable) < 100:
        return False, 0.
    ridge = support & ~flank_support.any(axis=0)
    ridge_fraction = np.count_nonzero(ridge & comparable) / np.count_nonzero(comparable)
    # Do not let one short arc or a cluster of town labels dominate a fit.
    expected_bins = visible.reshape(24, -1).sum(axis=1)
    supported_bins = support.reshape(24, -1).sum(axis=1)
    relevant = expected_bins >= 5
    well_supported = supported_bins >= expected_bins * .55
    spread = np.count_nonzero(well_supported & relevant) / max(1, np.count_nonzero(relevant))
    angles = np.flatnonzero(support) * (2 * math.pi / count)
    if len(angles) < 100:
        return False, 0.
    positions = np.column_stack((np.cos(angles), np.sin(angles)))
    eigenvalues = np.linalg.eigvalsh(np.cov(positions, rowvar=False))
    conditioned = eigenvalues[0] / max(eigenvalues[1], 1e-9) >= .035
    score = float(min(support_fraction, raw_fraction, ridge_fraction, spread))
    accepted = (support_fraction >= MIN_SUPPORT and ridge_fraction >= MIN_RIDGE_SUPPORT
                and raw_fraction >= MIN_RAW_WHITE_SUPPORT and continuous_degrees >= 20
                and spread >= .80 and conditioned)
    return accepted, score


def detect_safe_zone(image: Image.Image, bounds: Bounds) -> ZoneDetection:
    """Return a unique supported white ring, or explicitly return no zone.

    Coordinates and radius are normalized to the whole calibrated map. Detection
    deliberately abstains on rings smaller than about 24 working-image pixels in
    diameter and on severely clipped/obscured or ambiguous circles.
    """
    cv2.ocl.setUseOpenCL(False)  # OpenCL state is local to the calling thread.
    try:
        if not isinstance(image, Image.Image) or not isinstance(bounds, Bounds):
            raise ValueError("A PIL image and calibrated map bounds are required")
        if image.width * image.height > MAX_IMAGE_PIXELS or max(image.size) > 16384:
            raise ValueError("Screenshot dimensions exceed the supported limit")
        if not all(isinstance(value, int) and not isinstance(value, bool) for value in bounds.as_box()):
            raise ValueError("Map bounds must contain integer screenshot pixels")
        bounds.validate(*image.size)
        if min(bounds.right - bounds.left, bounds.bottom - bounds.top) < 128:
            raise ValueError("The calibrated map is too small for zone detection")
        mask = _white_mask(image, bounds)
        white_count = int(np.count_nonzero(mask))
        if white_count < 60 or white_count > mask.size * .20:
            return ZoneDetection(None, 0., "No sufficiently isolated white safe-zone ring")
        side = max(mask.shape)
        minimum = max(12., side * .012)
        proposals = _candidates(mask, minimum)
        if not len(proposals):
            return ZoneDetection(None, 0., "No white safe-zone circle candidate")
        distance = cv2.distanceTransform(255 - mask, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        visible, supported = _angular_samples(proposals, distance, 144, 3.)
        expected = visible.sum(axis=1)
        hits = supported.sum(axis=1)
        fractions = hits / np.maximum(expected, 1)
        order = np.argsort(-fractions, kind="stable")
        selected = []
        for index in order:
            if expected[index] < 24 or hits[index] < 20 or fractions[index] < .52:
                continue
            candidate = proposals[index]
            if not any(_same_circle(candidate, other) for other in selected):
                selected.append(candidate)
            if len(selected) >= 80:
                break
        ys, xs = np.nonzero(mask)
        white_points = np.column_stack((xs, ys)).astype(float)
        accepted = []
        best_score = 0.
        for candidate in selected:
            refined = _refine(candidate, white_points)
            if refined is None or not len(_valid_circles(refined, mask.shape, minimum)):
                continue
            matches, score = _evidence(refined, distance)
            best_score = max(best_score, score)
            if matches and not any(_same_circle(refined, other[0]) for other in accepted):
                accepted.append((refined, score))
        if len(accepted) > 1:
            return ZoneDetection(None, max(score for _, score in accepted),
                                 "Ambiguous: multiple supported white circles")
        if not accepted:
            return ZoneDetection(None, best_score, "White circle evidence is incomplete or uncertain")
        circle, score = accepted[0]
        height, width = mask.shape
        zone = SafeZone(center_x=float(circle[0] / width), center_y=float(circle[1] / height),
                        radius=float(circle[2] * .5 * (1 / width + 1 / height)))
        return ZoneDetection(zone, score, "Unique supported white safe-zone ring")
    except (ValueError, TypeError, AttributeError, cv2.error, np.linalg.LinAlgError) as error:
        return ZoneDetection(None, 0., "Safe-zone detection unavailable: " + str(error))
