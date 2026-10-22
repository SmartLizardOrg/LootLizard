"""Browser-only adapter around the unchanged desktop geometry/CV modules.

RGBA buffers and reference images exist only in this worker's memory. No GUI,
screen capture, filesystem persistence, OCR subprocess, or network client is
imported. A result always describes the supplied frame, never an earlier one.
"""
from dataclasses import asdict, is_dataclass
import json
import math
import re
import sys
import time

import cv2
import numpy as np
from PIL import Image, __version__ as pillow_version

from lootlizard.core import Bounds, MapData
from lootlizard.marker_pipeline import recognize_registered_marker
from lootlizard.registration import MapReference, register_map
from lootlizard.zone_vision import detect_safe_zone


MAX_REFERENCES = 8
REFERENCE_SIDE = 1800
MAX_INPUT_SIDE = 2400
MAX_FRAME_PIXELS = 4_000_000
MAX_REFERENCE_PIXELS = MAX_INPUT_SIDE ** 2
MAX_MAP_BYTES = 2_000_000
MAP_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def _json_safe(value):
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _rgba_view(rgba, width, height, *, reference=False):
    """Validate a borrowed byte view without allocating an RGB image."""
    if (type(width) is not int or type(height) is not int or min(width, height) < 1
            or max(width, height) > MAX_INPUT_SIDE
            or width * height > (MAX_REFERENCE_PIXELS if reference else MAX_FRAME_PIXELS)):
        raise ValueError("Image dimensions exceed the browser proof-of-concept limit.")
    try:
        view = memoryview(rgba)
    except TypeError as error:
        raise ValueError("An RGBA byte buffer is required.") from error
    if view.nbytes != width * height * 4 or not view.c_contiguous or view.itemsize != 1:
        raise ValueError("RGBA buffer length does not match the image dimensions.")
    if np.any(np.frombuffer(view, dtype=np.uint8)[3::4] != 255):
        raise ValueError("Use a fully opaque screenshot or reference image.")
    return view


def _rgba_image(rgba, width, height, *, reference=False):
    view = _rgba_view(rgba, width, height, reference=reference)
    # frombytes owns a copy; a transferred JavaScript buffer may then be freed.
    return Image.frombytes("RGBA", (width, height), view.tobytes()).convert("RGB")


def _full_map_bounds(registration, size):
    """Keep the desktop circle detector's complete/upright-map safety gate."""
    matrix = registration.map_to_image
    if matrix is None:
        return None
    width, height = size
    horizontal, vertical = float(matrix[0, 0]), float(matrix[1, 1])
    scale = max(abs(horizontal), abs(vertical))
    if (min(horizontal, vertical) <= 0 or abs(horizontal - vertical) > scale * .005
            or max(abs(matrix[0, 1]), abs(matrix[1, 0])) > scale * .002):
        return None
    left, top = float(matrix[0, 2]), float(matrix[1, 2])
    right, bottom = left + horizontal, top + vertical
    if left < -2 or top < -2 or right > width + 2 or bottom > height + 2:
        return None
    try:
        return Bounds(max(0, round(left)), max(0, round(top)),
                      min(width, round(right)), min(height, round(bottom))).validate(width, height)
    except ValueError:
        return None


def capabilities():
    """Exercise native/WASM features needed by registration, not mock APIs."""
    random = np.random.default_rng(47)
    pixels = random.integers(0, 255, (128, 128), dtype=np.uint8)
    keys, descriptors = cv2.SIFT_create().detectAndCompute(pixels, None)
    if descriptors is None or len(keys) < 4:
        raise RuntimeError("OpenCV SIFT is unavailable in this runtime.")
    cv2.BFMatcher(cv2.NORM_L2).knnMatch(descriptors, descriptors, k=2)
    points = np.float32(((0, 0), (20, 0), (0, 20), (20, 20), (10, 13)))
    for estimator in (cv2.estimateAffine2D, cv2.estimateAffinePartial2D):
        matrix, _ = estimator(points, points + (3, 4), method=cv2.RANSAC)
        if matrix is None or not np.isfinite(matrix).all():
            raise RuntimeError("OpenCV affine registration is unavailable.")
    return dict(python=sys.version.split()[0], opencv=cv2.__version__, numpy=np.__version__,
                pillow=pillow_version, sift=True, affine=True, maxReferences=MAX_REFERENCES,
                referenceSide=REFERENCE_SIDE, maxInputSide=MAX_INPUT_SIDE,
                maxFramePixels=MAX_FRAME_PIXELS)


class BrowserVisionEngine:
    def __init__(self, maps):
        if isinstance(maps, str):
            if len(maps.encode("utf-8")) > MAX_MAP_BYTES:
                raise ValueError("The map catalog exceeds its browser limit.")
            maps = json.loads(maps)
        if not isinstance(maps, list) or len(maps) > 32:
            raise ValueError("Provide at most 32 map-data objects.")
        if len(json.dumps(maps, allow_nan=False).encode("utf-8")) > MAX_MAP_BYTES:
            raise ValueError("The map catalog exceeds its browser limit.")
        checked = {}
        for record in maps:
            data = MapData.from_dict(record)
            if not MAP_ID.fullmatch(data.id) or data.id in checked:
                raise ValueError("Map ids must be safe and unique.")
            checked[data.id] = data
        self.maps = checked
        self.references = ()

    def clear(self):
        self.references = ()
        return {"count": 0}

    def set_references(self, records):
        """Replace all references atomically; failure preserves the prior set."""
        if not isinstance(records, (list, tuple)) or len(records) > MAX_REFERENCES:
            raise ValueError("Provide at most eight complete map references.")
        replacements, seen = [], set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("Each reference must be an object.")
            map_id = record.get("mapId")
            if map_id not in self.maps or map_id in seen:
                raise ValueError("Each reference must identify a unique loaded map.")
            seen.add(map_id)
            image = _rgba_image(record.get("rgba"), record.get("width"), record.get("height"), reference=True)
            image.thumbnail((REFERENCE_SIDE, REFERENCE_SIDE), Image.Resampling.LANCZOS)
            replacements.append(MapReference(map_id, image))
        self.references = tuple(replacements)
        return {"count": len(replacements), "references": [
            {"mapId": reference.map_id, "width": reference.image_size[0], "height": reference.image_size[1]}
            for reference in replacements]}

    def analyze_rgba(self, rgba, width, height, context="live", ticket=None):
        if context not in ("live", "replay"):
            raise ValueError("Choose live or replay context explicitly.")
        start = time.perf_counter()
        if not self.references:
            _rgba_view(rgba, width, height)
            result = dict(ticket=ticket, width=width, height=height, registration=None,
                          position=None, zone=None, points=[],
                          reason="No canonical map references are loaded",
                          markerReason="Map layout is not verified; player position is unknown.",
                          zoneReason="Map layout is not verified; safe zone is unknown.")
            # Input validation is included in totalMs; none of these stages ran.
            result["timings"] = dict(decodeMs=0., registrationMs=0., markerMs=0.,
                                     zoneMs=0., totalMs=(time.perf_counter()-start)*1000)
            return _json_safe(result)
        image = _rgba_image(rgba, width, height)
        decoded = time.perf_counter()
        registration = register_map(image, self.references)
        registered = time.perf_counter()
        result = dict(ticket=ticket, width=width, height=height, registration=None,
                      position=None, zone=None, points=[], reason=registration.reason,
                      markerReason="Map layout is not verified; player position is unknown.",
                      zoneReason="Map layout is not verified; safe zone is unknown.")
        if registration.map_id is not None:
            result["registration"] = dict(mapId=registration.map_id,
                matrix=registration.map_to_image.tolist(), viewport=list(registration.viewport),
                diagnostics=_json_safe(registration.diagnostics))
            try:
                marker = recognize_registered_marker(image, registration, view_context=context)
                result["markerReason"] = marker.reason
            except Exception as error:
                marker = None
                result["markerReason"] = "Marker detection unavailable: " + str(error)[:500]
            if marker is not None and marker.position is not None:
                result["position"] = dict(x=marker.position[0], y=marker.position[1],
                    headingDegrees=marker.heading_degrees, method=marker.method, score=marker.score,
                    screenCenter=marker.screen_center, identityVerified=False)
            marked = time.perf_counter()
            bounds = _full_map_bounds(registration, image.size)
            if bounds is None:
                result["zoneReason"] = "Circle priority is unavailable for clipped, rotated, or distorted map views."
            else:
                detected = detect_safe_zone(image, bounds)
                result["zoneReason"] = detected.reason
                if detected.zone is not None:
                    zone = detected.zone
                    center = registration.image_point_to_map(
                        bounds.left + zone.center_x * (bounds.right - bounds.left),
                        bounds.top + zone.center_y * (bounds.bottom - bounds.top))
                    if center is not None:
                        radius_pixels = zone.radius * ((bounds.right - bounds.left) + (bounds.bottom - bounds.top)) / 2
                        map_scale = (registration.map_to_image[0, 0] + registration.map_to_image[1, 1]) / 2
                        result["zone"] = dict(centerX=center[0], centerY=center[1],
                                              radius=float(radius_pixels / map_scale), score=detected.score)
            data = self.maps[registration.map_id]
            for point in data.points:
                projected = registration.project_poi(point.x, point.y)
                result["points"].append(dict(id=point.id, visible=projected is not None,
                    imageX=projected[0] if projected is not None else None,
                    imageY=projected[1] if projected is not None else None))
        else:
            marked = registered
        finished = time.perf_counter()
        result["timings"] = dict(decodeMs=(decoded-start)*1000,
            registrationMs=(registered-decoded)*1000, markerMs=(marked-registered)*1000,
            zoneMs=(finished-marked)*1000, totalMs=(finished-start)*1000)
        return _json_safe(result)
