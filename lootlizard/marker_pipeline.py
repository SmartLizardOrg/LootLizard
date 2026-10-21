"""Fresh screenshot marker evidence in a separately verified map transform.

The viewing cone is a visual estimate of the local marker in live play. It
does not identify an account. A replay/observer input disables player estimates.
All returned coordinates use the canonical map, including zoomed/panned views.
"""

from dataclasses import dataclass, field
import math

import numpy as np
from PIL import Image

from . import self_marker
from .registration import Registration
from .vision import Profile, Recognition, recognize


@dataclass(frozen=True)
class MarkerRecognition(Recognition):
    method: str = "none"
    heading_degrees: float | None = None
    screen_center: tuple[float, float] | None = None
    diagnostics: dict = field(default_factory=dict)


def map_search_bounds(registration: Registration, size: tuple[int, int]):
    """Intersect the projected whole-map rectangle with the screenshot.

    Registration accepts only near-upright maps. The inverse transform still
    checks the final point, so an axis-aligned search box cannot admit a result
    beyond the actual map when there is a small allowed rotation.
    """
    if registration.map_id is None or registration.map_to_image is None:
        return None
    matrix = np.asarray(registration.map_to_image)
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        return None
    corners = np.array(((0., 0., 1.), (1., 0., 1.), (0., 1., 1.), (1., 1., 1.))) @ matrix.T
    if np.any(np.abs(corners[:, 2]) < 1e-9):
        return None
    pixels = corners[:, :2] / corners[:, 2:]
    left, top = np.maximum(np.floor(pixels.min(axis=0)), (0, 0)).astype(int)
    right, bottom = np.minimum(np.ceil(pixels.max(axis=0)), size).astype(int)
    vl, vt, vr, vb = registration.viewport
    bounds = tuple(int(n) for n in (max(left, vl), max(top, vt), min(right, vr), min(bottom, vb)))
    return bounds if bounds[0] < bounds[2] and bounds[1] < bounds[3] else None


def recognize_registered_marker(image: Image.Image, registration: Registration,
                                profile: Profile | None = None, *, view_context="live"):
    """Find a cone automatically, then optionally fall back to a trained icon.

    The live/replay choice is an explicit app setting. It is never inferred
    from a camera arrow. A conflicting trained icon or competing cone result
    abstains; neither one silently wins. No map or previous position is reused.
    """
    bounds = map_search_bounds(registration, image.size)
    if bounds is None:
        return MarkerRecognition(None, 0., "Map layout is not verified; player position is unknown.")
    if view_context != "live":
        return MarkerRecognition(None, 0., "Replay/observer image: own-player estimation is disabled.", True)
    cone = self_marker.find_self_marker(image, viewport=bounds, view_context="live")
    diagnostics = {"cone_reason": cone.reason, "cone_candidates": cone.candidates}
    trained = None
    trained_pixel = trained_position = None
    if profile is not None and profile.map_id == registration.map_id:
        trained = recognize(image, profile, registration.map_id)
        diagnostics["trained_reason"] = trained.reason
        if trained.position is not None and trained.layout_verified:
            # A profile's user-selected rectangle is not the canonical map.
            # Resolve the actual screenshot pixel before using registration.
            x, y = trained.position
            b = profile.bounds
            trained_pixel = (b.left + x * (b.right-b.left), b.top + y * (b.bottom-b.top))
            trained_position = registration.image_point_to_map(*trained_pixel)
    if cone.center is not None:
        position = registration.image_point_to_map(*cone.center)
        if position is None:
            return MarkerRecognition(None, 0., "The cone candidate is outside the registered map.", True,
                                     diagnostics=diagnostics)
        if trained_pixel is not None:
            if trained_position is None or math.dist(trained_pixel, cone.center) > max(12., cone.radius_px * 1.8):
                return MarkerRecognition(None, cone.score,
                    "The viewing cone and trained icon disagree; player position is unknown.", True,
                    diagnostics=diagnostics)
        return MarkerRecognition(position, cone.score,
            "Unique viewing-cone estimate; player identity is not verified.", True,
            "view-cone", cone.heading_degrees, tuple(cone.center), diagnostics)
    # An ambiguous cone search is a stronger reason to abstain than a matching
    # profile silhouette is a reason to select one of the competing candidates.
    if getattr(cone, "ambiguous", False):
        return MarkerRecognition(None, cone.score, cone.reason, True, diagnostics=diagnostics)
    if trained is not None and trained_position is not None:
        return MarkerRecognition(trained_position, trained.score, trained.reason, True,
                                 "trained-icon", diagnostics=diagnostics)
    reason = cone.reason
    if trained is not None:
        reason += " " + trained.reason
    return MarkerRecognition(None, cone.score, reason, True, diagnostics=diagnostics)
