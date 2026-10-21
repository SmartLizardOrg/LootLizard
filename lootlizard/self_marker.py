"""Conservative automatic view-cone estimates, never verified player identity.

``find_self_marker(image, viewport=..., view_context="live")`` scans the map
for bright colored round bodies and paired, fading, broad fan borders. It needs
no supplied center, radius, color, or candidate count. Coordinates are screenshot
pixels; heading is clockwise from screen-right (east=0, south=90). Scores express
geometric support, not calibrated probabilities. Competing candidates abstain
with ``ambiguous=True`` so an integration can also block fallback recognition.

Call only after map registration, retaining its map and stale-result checks.
There is no live/replay classifier: explicit replay and unknown context abstain,
and callers must supply independently known context. The legacy given-candidate
``assess_view_cone`` remains available for comparing the original experiment.

Synthetic checks establish geometry only. The small saved live development set
contains yellow Training/local bodies, an orange NPC and one older reference;
it does not establish real human teammate, slot/color/UI, or dropped-pin accuracy.
Darkened bodies, clipping, missing/occluded fans and textured terrain can abstain.
"""

from dataclasses import dataclass, field
import math

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ConeEvidence:
    supported: bool | None
    heading_degrees: float | None
    score: float
    reason: str
    identity_verified: bool = field(default=False, init=False)


@dataclass(frozen=True)
class MarkerCandidate:
    center: tuple[float, float]
    radius_px: float
    color: tuple[int, int, int]
    body_score: float
    cone: ConeEvidence


@dataclass(frozen=True)
class SelfMarkerDetection:
    center: tuple[float, float] | None
    radius_px: float | None
    color: tuple[int, int, int] | None
    heading_degrees: float | None
    score: float
    reason: str
    candidates: tuple[MarkerCandidate, ...] = ()
    ambiguous: bool = False
    identity_verified: bool = field(default=False, init=False)

    @property
    def radius(self) -> float | None:
        return self.radius_px


def _unknown(reason: str) -> ConeEvidence:
    return ConeEvidence(None, None, 0., reason)


def _round_body(rgb: np.ndarray, center: tuple[float, float], radius: float,
                color: np.ndarray) -> bool:
    delta = rgb.astype(np.int32) - color
    selected = (np.sum(delta * delta, axis=2) <= 58 ** 2).astype(np.uint8)
    # White slot numerals and thin outlines can split the colored body into
    # pieces. Close only a small fraction of the body diameter; this does not
    # merge nearby full-sized marker bodies or manufacture a broad view cone.
    gap = max(3, int(round(radius * .3)) | 1)
    selected = cv2.morphologyEx(selected, cv2.MORPH_CLOSE, np.ones((gap, gap), np.uint8))
    count, _, stats, centers = cv2.connectedComponentsWithStats(selected, connectivity=8)
    plausible = 0
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if (math.dist(centers[label], center) > radius * .65
                or not .4 * math.pi * radius ** 2 <= area <= 1.4 * math.pi * radius ** 2
                or min(width, height) < radius * 1.1
                or area / (width * height) < .62
                or max(width, height) / min(width, height) > 1.4):
            continue
        patch = (selected[y:y + height, x:x + width] != 0).astype(np.uint8)
        contours, _ = cv2.findContours(patch, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) != 1:
            continue
        perimeter = cv2.arcLength(contours[0], True)
        circularity = 4 * math.pi * cv2.contourArea(contours[0]) / perimeter ** 2 if perimeter else 0.
        if circularity >= .65:
            plausible += 1
    return plausible == 1


def _fan_geometry(rgb: np.ndarray, center: tuple[float, float], radius: float) -> ConeEvidence:
    yy, xx = np.indices(rgb.shape[:2])
    distance = np.hypot(xx - center[0], yy - center[1])
    low, high = rgb.min(axis=2), rgb.max(axis=2).astype(np.int16)
    pale = ((low >= 105) & (high - low <= 65)
            & (distance >= radius * 1.3) & (distance <= radius * 6)).astype(np.uint8) * 255
    edges = cv2.Canny(pale, 60, 120)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=max(12, round(radius * .9)),
                            minLineLength=radius * 1.7, maxLineGap=radius * .85)
    if lines is None:
        return ConeEvidence(False, None, 0., "No broad pale fan boundary is visible")
    rays = []
    for x1, y1, x2, y2 in sorted(lines[:, 0], key=lambda p: -math.hypot(p[2] - p[0], p[3] - p[1])):
        dx, dy = float(x2 - x1), float(y2 - y1)
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        ux, uy = dx / length, dy / length
        if abs(ux * (y1 - center[1]) - uy * (x1 - center[0])) > radius * 1.3:
            continue
        if max(math.dist((x1, y1), center), math.dist((x2, y2), center)) < radius * 2.6:
            continue
        if ux * ((x1 + x2) / 2 - center[0]) + uy * ((y1 + y2) / 2 - center[1]) < 0:
            ux, uy = -ux, -uy
        angle = math.degrees(math.atan2(uy, ux)) % 360
        if any(abs((angle - existing[0] + 180) % 360 - 180) < 8 for existing in rays):
            continue
        rays.append((angle, length))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    radii = np.linspace(radius * 2, radius * 4.8, 36)

    def sample(angle):
        theta = math.radians(angle)
        x = np.rint(center[0] + radii * math.cos(theta)).astype(int)
        y = np.rint(center[1] + radii * math.sin(theta)).astype(int)
        return gray[y, x].astype(float)

    candidates = []
    for first, length_a in rays:
        for second, length_b in rays:
            opening = (second - first) % 360
            if not 60 <= opening <= 110:
                continue
            # A fan lightens its interior on BOTH boundary sides. Two crossing
            # roads alone should not suffice, nor should a small arrow head.
            contrast = min(float(np.median(sample(first + 12) - sample(first - 12))),
                           float(np.median(sample(second - 12) - sample(second + 12))))
            if contrast < 8:
                continue
            score = (.45 * min(1., min(length_a, length_b) / (3 * radius))
                     + .45 * min(1., contrast / 40)
                     + .10 * (1 - abs(opening - 90) / 70))
            if score >= .65:
                candidates.append((score, (first + opening / 2) % 360))
    candidates.sort(reverse=True)
    if not candidates:
        return ConeEvidence(False, None, 0., "No sufficiently supported broad fan is visible")
    score, heading = candidates[0]
    if any(other_score >= score - .12
           and abs((other_heading - heading + 180) % 360 - 180) > 20
           for other_score, other_heading in candidates[1:]):
        return _unknown("Competing fan directions are ambiguous")
    return ConeEvidence(True, heading, score, "Broad view-cone-like geometry supports this candidate; identity remains unverified")


def assess_view_cone(image: Image.Image, center: tuple[float, float], radius_px: float,
                     *, marker_color, view_context="unknown", candidate_count=None,
                     viewport=None) -> ConeEvidence:
    """Return optional fan evidence; ``None`` means abstention, never success.

    Heading is clockwise from screen-right (east=0, south=90). Score is a
    geometric support value, not a calibrated probability. Explicit replay or
    unknown context, multiple/unknown eligible candidates, clipped neighborhoods, and
    unsuitable bodies abstain. A positive result never verifies player identity.

    candidate_count means eligible self candidates AFTER independent color/body
    filtering, not total allied markers. For example, one yellow local candidate
    and an independently identified orange NPC may use candidate_count=1. If
    two players remain eligible, the caller must pass 2 and this probe abstains.
    """
    if view_context != "live":
        return _unknown("Replay/observer camera is not live self identity" if view_context == "replay"
                        else "Live versus replay context is unknown")
    if type(candidate_count) is not int or candidate_count != 1:
        return _unknown("Own-marker candidate identity is ambiguous or unknown")
    try:
        if not isinstance(image, Image.Image) or image.width * image.height > 40_000_000:
            return _unknown("Unsupported image")
        if (len(center) != 2 or any(isinstance(n, bool) or not math.isfinite(n) for n in center)
                or isinstance(radius_px, bool) or not math.isfinite(radius_px) or not 4 <= radius_px <= 40):
            return _unknown("Invalid candidate center or radius")
        color = np.asarray(marker_color)
        if color.shape != (3,) or not np.issubdtype(color.dtype, np.integer) or np.any(color < 0) or np.any(color > 255):
            return _unknown("A known RGB marker-body color is required")
        bounds = viewport if viewport is not None else (0, 0, image.width, image.height)
        if (len(bounds) != 4 or any(type(n) is not int for n in bounds)
                or not 0 <= bounds[0] < bounds[2] <= image.width
                or not 0 <= bounds[1] < bounds[3] <= image.height):
            return _unknown("Invalid map viewport")
        reach = math.ceil(radius_px * 6) + 2
        left, top = math.floor(center[0]) - reach, math.floor(center[1]) - reach
        right, bottom = math.ceil(center[0]) + reach + 1, math.ceil(center[1]) + reach + 1
        if left < bounds[0] or top < bounds[1] or right > bounds[2] or bottom > bounds[3]:
            return _unknown("View-cone neighborhood is clipped by the map viewport")
        patch = image.crop((left, top, right, bottom))
        if "A" in patch.getbands() or "transparency" in patch.info:
            if np.any(np.asarray(patch.convert("RGBA"))[:, :, 3] < 230):
                return _unknown("Transparent pixels are not reliable cone evidence")
        rgb = np.asarray(patch.convert("RGB"))
        local_center = (center[0] - left, center[1] - top)
        cv2.ocl.setUseOpenCL(False)
        if not _round_body(rgb, local_center, radius_px, color.astype(np.int32)):
            return _unknown("No unique compact round marker body; arrows and pins are not self identity")
        return _fan_geometry(rgb, local_center, radius_px)
    except (ValueError, TypeError, OverflowError, cv2.error):
        return _unknown("Cone evidence could not be assessed safely")


def _body_candidates(rgb: np.ndarray) -> list[tuple]:
    """Find saturated, compact discs without assuming a team-slot color."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    selected = ((hsv[:, :, 1] >= 140) & (hsv[:, :, 2] >= 105)).astype(np.uint8)
    selected = cv2.morphologyEx(selected, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(selected, connectivity=8)
    found = []
    for label in range(1, count):
        x, y, width, height, area = stats[label]
        if (not 9 <= min(width, height) <= 84 or max(width, height) > 84
                or max(width, height) / min(width, height) > 1.45 or area < 55):
            continue
        component = (labels[y:y + height, x:x + width] == label).astype(np.uint8)
        contours, _ = cv2.findContours(component, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) != 1:
            continue
        hull = cv2.convexHull(contours[0])
        (cx, cy), radius = cv2.minEnclosingCircle(hull)
        if not 4 <= radius <= 40:
            continue
        fill = cv2.contourArea(hull) / (math.pi * radius * radius)
        if fill < .72:
            continue
        center = (float(cx + x), float(cy + y))
        # A numbered/dotted player body has a pale border. Texture-only colored
        # discs without that UI border are not eligible candidates.
        angles = np.linspace(0, 2 * math.pi, 72, endpoint=False)
        border = np.zeros(72, bool)
        for extra in (-4., -3., -2., -1., .0, 1., 2., 3., 4.):
            px = np.rint(center[0] + (radius + extra) * np.cos(angles)).astype(int)
            py = np.rint(center[1] + (radius + extra) * np.sin(angles)).astype(int)
            valid = (px >= 0) & (py >= 0) & (px < rgb.shape[1]) & (py < rgb.shape[0])
            pixels = rgb[np.clip(py, 0, rgb.shape[0] - 1), np.clip(px, 0, rgb.shape[1] - 1)].astype(int)
            border |= valid & (pixels.min(axis=1) >= 140) & (np.ptp(pixels, axis=1) <= 80)
        coverage = float(np.mean(border))
        if coverage < .22:
            continue
        pixels = rgb[y:y + height, x:x + width][component != 0]
        sat = hsv[y:y + height, x:x + width, 1][component != 0]
        pixels = pixels[sat >= 140]
        if not len(pixels):
            continue
        color = tuple(int(value) for value in np.median(pixels, axis=0))
        # Live squad/local bodies are bright UI glyphs. Dim all-player replay
        # labels and colored terrain can otherwise satisfy circle geometry.
        # Darkened/occluded bodies abstain rather than gain identity from a fan.
        if max(color) < 150:
            continue
        body_score = min(1., .6 * fill + .4 * coverage)
        found.append((center, float(radius + 1), color, body_score))
    return found


def _fading_fan(rgb: np.ndarray, center: tuple[float, float], radius: float) -> ConeEvidence:
    """Require two converging pale borders with outward-fading local contrast.

    Interior brightness is not required: the fan overlays dark water, brown
    terrain, or other markers. Constant-width/brightness roads and small arrows
    lack the paired, long, fading border pattern.
    """
    yy, xx = np.indices(rgb.shape[:2])
    distance = np.hypot(xx - center[0], yy - center[1])
    low = rgb.min(axis=2)
    neutral = np.ptp(rgb.astype(np.int16), axis=2) <= 80
    pale = ((low >= 105) & neutral & (distance >= radius * 1.25)
            & (distance <= radius * 6.2)).astype(np.uint8) * 255
    lines = cv2.HoughLinesP(cv2.Canny(pale, 60, 120), 1, np.pi / 180,
                            threshold=max(8, round(radius * .7)),
                            minLineLength=radius * 1.2, maxLineGap=radius * .4)
    if lines is None:
        return ConeEvidence(False, None, 0., "No broad pale fan borders")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(float)
    bright = np.where(neutral, gray, 0.)
    radii = np.linspace(radius * 1.35, radius * 6, 64)
    rays = []

    def sample(values, x, y):
        return values[np.clip(np.rint(y).astype(int), 0, values.shape[0] - 1),
                      np.clip(np.rint(x).astype(int), 0, values.shape[1] - 1)]

    for x1, y1, x2, y2 in lines[:, 0]:
        vector = np.array((float(x2 - x1), float(y2 - y1)))
        length = float(np.linalg.norm(vector))
        if length == 0:
            continue
        unit = vector / length
        if np.dot(unit, np.array(((x1 + x2) / 2 - center[0], (y1 + y2) / 2 - center[1]))) < 0:
            unit = -unit
        normal = np.array((-unit[1], unit[0]))
        offset = float(np.dot(np.array((x1 - center[0], y1 - center[1])), normal))
        if abs(offset) > radius * 1.3:
            continue
        if max(math.dist((x1, y1), center), math.dist((x2, y2), center)) < radius * 2.4:
            continue
        origin = np.asarray(center) + normal * offset
        positions = origin[:, None] + unit[:, None] * radii
        peak = np.max([sample(bright, positions[0] + normal[0] * shift,
                              positions[1] + normal[1] * shift) for shift in (-2, -1, 0, 1, 2)], axis=0)
        flank = max(3., radius * .5)
        background = (sample(gray, positions[0] + normal[0] * flank, positions[1] + normal[1] * flank)
                      + sample(gray, positions[0] - normal[0] * flank, positions[1] - normal[1] * flank)) / 2
        contrast = np.maximum(0., peak - background)
        support = contrast >= 10
        longest, run = 0, 0
        for present in support:
            run = run + 1 if present else 0
            longest = max(longest, run)
        strength = float(np.percentile(contrast, 80))
        fraction = float(np.mean(support))
        fade = float(np.mean(contrast[radii <= radius * 3]) - np.mean(contrast[radii >= radius * 4.5]))
        if strength < 16 or fraction < .25 or longest < 8 or fade < 6:
            continue
        score = (.35 * min(1., strength / 60) + .25 * min(1., fraction / .6)
                 + .25 * min(1., fade / 25) + .15 * min(1., longest / 24))
        angle = math.degrees(math.atan2(unit[1], unit[0])) % 360
        rays.append((score, angle, origin, unit))
    rays.sort(key=lambda ray: -ray[0])
    unique = []
    for ray in rays:
        if not any(abs((ray[1] - old[1] + 180) % 360 - 180) < 8
                   and math.dist(ray[2], old[2]) < radius * .5 for old in unique):
            unique.append(ray)
    pairs = []
    near_radii = np.linspace(radius * 1.4, radius * 2.5, 36)

    def near_interior(angle):
        theta = math.radians(angle)
        return sample(gray, center[0] + near_radii * math.cos(theta),
                      center[1] + near_radii * math.sin(theta))

    for score_a, angle_a, origin_a, unit_a in unique:
        for score_b, angle_b, origin_b, unit_b in unique:
            opening = (angle_b - angle_a) % 360
            if not 55 <= opening <= 120:
                continue
            try:
                parameters = np.linalg.solve(np.column_stack((unit_a, -unit_b)), origin_b - origin_a)
            except np.linalg.LinAlgError:
                continue
            apex = origin_a + unit_a * parameters[0]
            if math.dist(apex, center) > radius * 1.4:
                continue
            # A fan is a translucent area, not merely two pale lines. Near
            # the body, require its interior to be lighter across BOTH edges.
            # The short range tolerates outward fading over textured terrain.
            fill = min(float(np.median(near_interior(angle_a + 12) - near_interior(angle_a - 12))),
                       float(np.median(near_interior(angle_b - 12) - near_interior(angle_b + 12))))
            if fill < 4:
                continue
            score = .8 * min(score_a, score_b) + .2 * (1 - abs(opening - 90) / 70)
            if score >= .75:
                pairs.append((float(score), (angle_a + opening / 2) % 360))
    pairs.sort(reverse=True)
    if not pairs:
        return ConeEvidence(False, None, 0., "No paired fading view-cone borders")
    score, heading = pairs[0]
    if any(other_score >= score - .10 and abs((other_heading - heading + 180) % 360 - 180) > 25
           for other_score, other_heading in pairs[1:]):
        return _unknown("Competing fan directions are ambiguous")
    return ConeEvidence(True, heading, score, "Paired fading view-cone borders; identity remains unverified")


def find_self_marker(image: Image.Image, *, viewport=None,
                     view_context="unknown") -> SelfMarkerDetection:
    """Scan a map viewport for a unique colored body with a broad viewing fan.

    No caller-provided center, color, radius, or candidate count is used. Replay
    and unknown context abstain. The result is a VIEW CONE ESTIMATE, never
    verified own-player identity. Map registration/identity checks belong to the
    caller, as do stale-result tickets and live/replay workflow selection.
    """
    def abstain(reason, candidates=(), *, ambiguous=False):
        return SelfMarkerDetection(None, None, None, None, 0., reason, tuple(candidates), ambiguous)

    if view_context != "live":
        return abstain("Replay/observer context cannot establish live self identity" if view_context == "replay"
                       else "Live versus replay context is unknown")
    try:
        if (not isinstance(image, Image.Image) or image.width * image.height > 40_000_000
                or max(image.size) > 16384):
            return abstain("Unsupported screenshot dimensions")
        bounds = viewport if viewport is not None else (0, 0, image.width, image.height)
        if (len(bounds) != 4 or any(type(n) is not int for n in bounds)
                or not 0 <= bounds[0] < bounds[2] <= image.width
                or not 0 <= bounds[1] < bounds[3] <= image.height):
            return abstain("Invalid map viewport")
        cv2.ocl.setUseOpenCL(False)
        crop = image.crop(bounds)
        if "A" in crop.getbands() or "transparency" in crop.info:
            if np.any(np.asarray(crop.convert("RGBA"))[:, :, 3] < 230):
                return abstain("Transparent pixels are not reliable self-marker evidence")
        rgb = np.asarray(crop.convert("RGB"))
        bodies = _body_candidates(rgb)
        if len(bodies) > 64:
            return abstain("Too many plausible colored marker bodies", ambiguous=True)
        candidates = []
        for center, radius, color, body_score in bodies:
            reach = math.ceil(radius * 6.5) + 3
            left, top = math.floor(center[0]) - reach, math.floor(center[1]) - reach
            right, bottom = math.ceil(center[0]) + reach + 1, math.ceil(center[1]) + reach + 1
            if left < 0 or top < 0 or right > rgb.shape[1] or bottom > rgb.shape[0]:
                cone = _unknown("View-cone neighborhood is clipped")
            else:
                cone = _fading_fan(rgb[top:bottom, left:right],
                                   (center[0] - left, center[1] - top), radius)
            candidates.append(MarkerCandidate((center[0] + bounds[0], center[1] + bounds[1]),
                                               radius, color, body_score, cone))
        accepted = [candidate for candidate in candidates if candidate.cone.supported is True]
        if len(accepted) != 1:
            return abstain("Multiple view-cone candidates are ambiguous" if len(accepted) > 1
                           else "No unique supported view-cone marker", candidates,
                           ambiguous=len(accepted) > 1 or any(candidate.cone.supported is None
                                                            and "Competing" in candidate.cone.reason
                                                            for candidate in candidates))
        if any(candidate.cone.supported is None for candidate in candidates):
            return abstain("Unresolved competing marker neighborhoods", candidates, ambiguous=True)
        chosen = accepted[0]
        return SelfMarkerDetection(chosen.center, chosen.radius_px, chosen.color,
                                   chosen.cone.heading_degrees, chosen.cone.score,
                                   "VIEW CONE ESTIMATE; player identity is not verified", tuple(candidates))
    except (ValueError, TypeError, OverflowError, cv2.error):
        return abstain("Automatic view-cone detection is unavailable")
