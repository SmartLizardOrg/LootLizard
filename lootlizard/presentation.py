"""Short, player-facing summaries of the application's existing state."""

from dataclasses import dataclass
import time


@dataclass(frozen=True)
class MainPresentation:
    title: str
    detail: str
    map_name: str
    rooms: str
    freshness: str
    circle: str
    selection_title: str
    selection_detail: str
    tone: str = "neutral"


def present(app) -> MainPresentation:
    """Keep diagnostics out of the map while never implying stale guidance."""
    t = app.t
    registration = app._active_registration()
    has_image = app.image is not None
    data_available = app.data.id in getattr(app, "map_data", {app.data.id: app.data})
    verified = has_image and data_available and (registration is not None or (
        not getattr(app, "references", ()) and app.bounds is not None))
    mode = getattr(app, "mode", "position")
    map_name = app.data.name if has_image and verified else t("Waiting for a map")
    points = list(app.data.points) if verified else []
    title, detail, tone = t("Open your game map"), t("Then refresh here or press Ctrl+Shift+B."), "neutral"
    if mode == "calibrate":
        title, detail = t("Select the map corners"), t("Click the two opposite corners of the full map.")
    elif mode == "marker_box":
        title, detail = t("Select your icon"), t("Click two corners around your icon on the map.")
    elif mode == "marker_seed":
        title, detail = t("Choose an icon pixel"), t("Click a solid colored pixel inside your icon.")
    elif getattr(app, "capture_busy", False):
        title, detail = t("Refreshing map…"), t("Keep the game map open for a moment.")
    elif has_image:
        future = getattr(app, "future", None)
        pending = future is not None and not future.done()
        if pending and not verified:
            title, detail = t("Reading map…"), t("Finding the map and available rooms.")
        elif not data_available:
            title, detail = t("Map data unavailable"), t("Check map updates or import data in Settings.")
            map_name, tone = app.data.name, "warning"
        elif not verified:
            identified = getattr(getattr(app, "registration", None), "map_id", None)
            if identified and identified not in getattr(app, "map_data", {}):
                title, detail = t("No rooms for this map"), t("Choose another map or add room data in Settings.")
                map_name = identified.replace("_", " ").replace("-", " ").title()
            else:
                title, detail = t("Map not recognized"), t("Open the map and zoom out, then refresh.")
            tone = "warning"
        elif getattr(app, "position", None) is not None:
            title = (t("Your position is set") if getattr(app, "position_method", None) == "manual"
                     else t("Position estimated"))
            detail = (t("Rooms inside the white circle come first.") if getattr(app, "safe_zone", None)
                      else t("Choose a room to inspect its distance."))
            tone = "ready"
        elif app.bounds is not None or registration is not None:
            title, detail, tone = t("Rooms are ready"), t("Your position is not visible. All rooms are still marked."), "ready"
        else:
            title, detail, tone = t("Add your map reference"), t("Open Settings to load a map catalog or set map bounds."), "warning"
    if getattr(app, "_status_level", "") == "error":
        title, detail, tone = t("Could not refresh the map"), t("Check the capture display in Settings and try again."), "warning"
    if getattr(app, "hotkey_registration", "") == "failed":
        title, detail, tone = (t("Shortcut unavailable"),
            t("Use Refresh map, or check shortcut details in Settings."), "warning")
    captured = getattr(app, "captured_monotonic", None)
    if not has_image:
        freshness = t("No image yet")
    elif not getattr(app, "image_is_capture", False):
        freshness = t("Opened image")
    elif captured is None:
        freshness = t("Captured image")
    else:
        age = max(0, int(time.monotonic() - captured))
        freshness = t("Updated just now") if age < 10 else t("Updated {age}s ago", age=age)
        if (age >= 30 and mode == "position" and not getattr(app, "capture_busy", False)
                and getattr(app, "_status_level", "") != "error"
                and getattr(app, "hotkey_registration", "") != "failed"):
            detail, tone = t("This image is getting old. Refresh after moving."), "warning"
    zone = getattr(app, "safe_zone", None) if verified else None
    circle = (t("{count} inside circle", count=sum(zone.contains(p.x, p.y) for p in points))
              if zone is not None else t("Circle unknown"))
    selected = next((p for p in points if p.id == getattr(app, "selected_point_id", None)), None)
    ordered = app._ordered_targets() if points else []
    if selected is None:
        selection_title = t("Choose a destination")
        selection_detail = (t("Select a pin or a room in the list.") if points
                            else t("Refresh a supported map to show rooms."))
    else:
        selection_title = app._point_name(selected)
        distance = next((d for p, d in ordered if p.id == selected.id), None)
        state = app._zone_state(selected)
        state_text = {"IN": t("Inside white circle"), "OUT": t("Outside white circle"),
                      "UNKNOWN": t("Circle unknown")}[state]
        selection_detail = (t("≈ {distance} m · {reason}", distance=f"{distance:,.0f}", reason=state_text)
                            if distance is not None else state_text)
    return MainPresentation(title, detail, str(map_name), t("{count} rooms", count=len(points)),
                            freshness, circle, str(selection_title), str(selection_detail), tone)
