"""Tk map presentation. Geometry/state ownership stays with Companion.

``draw_map(app)`` retains the screenshot-native crop/transform contract used by
``app._click``. Each visible POI has exactly one ``basement`` body tag; every POI
is numbered in the same order as ``app._ordered_targets``. No recognition,
registration, capture, focus, or worker state is changed here.
"""
from __future__ import annotations

import math
from PIL import Image, ImageTk

BACKGROUND = "#0B1017"
INK = "#111820"
AMBER = "#FFBA52"
AMBER_LIGHT = "#FFE0A5"
AMBER_DIM = "#C98632"
OUT_FILL = "#513717"
CYAN = "#63E5F3"
GREEN = "#83D6A3"
TEXT = "#E8EEF5"
MUTED = "#AAB8C6"


def _dpi(canvas):
    try:
        return max(1., min(2.5, float(canvas.winfo_fpixels("1i")) / 96))
    except (AttributeError, TypeError, ValueError):
        return 1.


def _overlap(first, second):
    return max(0., min(first[2], second[2]) - max(first[0], second[0])) * max(
        0., min(first[3], second[3]) - max(first[1], second[1]))


def _pill(canvas, text, centers, *, color, font, limits, occupied, tags=()):
    """Place a short label away from pins, keeping all text on the canvas."""
    item = canvas.create_text(*centers[0], text=text, fill=color, font=font, tags=tags)
    box = canvas.bbox(item)
    if not box:
        return
    half_width, half_height = (box[2] - box[0]) / 2 + 7, (box[3] - box[1]) / 2 + 4
    choices = []
    for order, (x, y) in enumerate(centers):
        x = min(max(x, limits[0] + half_width), limits[2] - half_width)
        y = min(max(y, limits[1] + half_height), limits[3] - half_height)
        candidate = (x - half_width, y - half_height, x + half_width, y + half_height)
        choices.append((sum(_overlap(candidate, taken) for taken in occupied), order, x, y, candidate))
    _, _, x, y, box = min(choices)
    canvas.coords(item, x, y)
    plate = canvas.create_rectangle(*box, fill=INK, outline=color, width=1, tags=tags)
    canvas.tag_lower(plate, item)
    occupied.append(box)


def _clip_segment(first, second, bounds):
    """Liang-Barsky clipping for a circle boundary, never a fake crop-edge arc."""
    x, y = first
    dx, dy = second[0] - x, second[1] - y
    lower, upper = 0., 1.
    for p, q in ((-dx, x-bounds[0]), (dx, bounds[2]-x),
                 (-dy, y-bounds[1]), (dy, bounds[3]-y)):
        if abs(p) < 1e-12:
            if q < 0:
                return None
            continue
        value = q / p
        if p < 0:
            lower = max(lower, value)
        else:
            upper = min(upper, value)
        if lower > upper:
            return None
    return (x+lower*dx, y+lower*dy), (x+upper*dx, y+upper*dy)


def _circle_paths(zone, registration, app, transform, view_box, image_box):
    ox, oy, sx, sy = transform
    left, top, _, _ = view_box
    points = []
    for step in range(181):
        angle = step * math.tau / 180
        x, y = zone.center_x + zone.radius*math.cos(angle), zone.center_y + zone.radius*math.sin(angle)
        if registration is not None:
            matrix = registration.map_to_image
            pixel = matrix @ (x, y, 1.)
            if abs(pixel[2]) < 1e-12:
                return []
            px, py = pixel[0]/pixel[2], pixel[1]/pixel[2]
        else:
            bounds = app.bounds
            px = bounds.left+x*(bounds.right-bounds.left)
            py = bounds.top+y*(bounds.bottom-bounds.top)
        points.append((ox+(px-left)*sx, oy+(py-top)*sy))
    paths, current = [], []
    for first, second in zip(points, points[1:]):
        clipped = _clip_segment(first, second, image_box)
        if clipped is None:
            if current:
                paths.append(current)
                current = []
            continue
        start, end = clipped
        if current and math.dist(current[-1], start) > .1:
            paths.append(current)
            current = []
        if not current:
            current.append(start)
        current.append(end)
    if current:
        paths.append(current)
    return paths


def _amount(distance, language):
    if distance >= 1000:
        number = f"{distance/1000:.1f}"
        return (number.replace(".", ",") if language == "hu" else number) + " km"
    return f"{distance:.0f} m"


def draw_map(app):
    """Draw the map without activating any window or touching detection state."""
    canvas = app.canvas
    canvas.delete("all")
    app._map_pin_hits, app._map_badge_hits, app._map_pin_items = {}, {}, {}
    cw, ch = canvas.winfo_width(), canvas.winfo_height()
    if cw < 2 or ch < 2:
        return
    dpi = _dpi(canvas)
    if app.image is None:
        canvas.create_text(cw/2, ch/2-24*dpi, text=app.t("Your map goes here"), fill=TEXT,
                           font=("Segoe UI", -round(24*dpi), "bold"))
        canvas.create_text(cw/2, ch/2+22*dpi,
                           text=app.t("Open your own image, or capture the game's display.\nThe app works only on request."),
                           fill=MUTED, width=max(160, cw-70*dpi), justify="center",
                           font=("Segoe UI", -round(14*dpi)))
        return
    registration = app._active_registration()
    selecting = app.mode == "calibrate" or (registration is None and (
        app.bounds is None or bool(getattr(app, "references", ()))))
    view_box = app._view_box()
    left, top, right, bottom = view_box
    view = app.image.crop(view_box)
    padding = min(28*dpi, cw/10, ch/10)
    scale = min((cw-2*padding)/view.width, (ch-2*padding)/view.height)
    rw, rh = max(1, int(view.width*scale)), max(1, int(view.height*scale))
    ox, oy = (cw-rw)/2, (ch-rh)/2
    sx, sy = rw/view.width, rh/view.height
    app.transform = (ox, oy, sx, sy)
    app.photo = ImageTk.PhotoImage(view.resize((rw, rh), Image.Resampling.LANCZOS), master=canvas)
    canvas.create_image(ox, oy, anchor="nw", image=app.photo, tags=("map_image",))
    if selecting:
        if app.first_corner and app.mode == "calibrate":
            x, y = ox+app.first_corner[0]*sx, oy+app.first_corner[1]*sy
            canvas.create_line(x-12*dpi, y, x+12*dpi, y, fill=CYAN, width=3)
            canvas.create_line(x, y-12*dpi, x, y+12*dpi, fill=CYAN, width=3)
        return
    if app.mode in ("marker_box", "marker_seed"):
        # Pixel selection must show the original icon, unobscured by large POIs.
        if app.marker_box:
            box_left, box_top, box_right, box_bottom = app.marker_box
            canvas.create_rectangle(ox+(box_left-left)*sx, oy+(box_top-top)*sy,
                                     ox+(box_right-left)*sx, oy+(box_bottom-top)*sy,
                                     outline=CYAN, width=2*dpi, tags=("setup_marker",))
        elif app.first_corner:
            x, y = ox+(app.first_corner[0]-left)*sx, oy+(app.first_corner[1]-top)*sy
            canvas.create_line(x-10*dpi, y, x+10*dpi, y, fill=CYAN, width=2*dpi, tags=("setup_marker",))
            canvas.create_line(x, y-10*dpi, x, y+10*dpi, fill=CYAN, width=2*dpi, tags=("setup_marker",))
        return

    def canvas_point(x, y):
        pixel = app._project_map_point(x, y)
        if pixel is None or not (left <= pixel[0] < right and top <= pixel[1] < bottom):
            return None
        return ox+(pixel[0]-left)*sx, oy+(pixel[1]-top)*sy

    image_box = (ox, oy, ox+rw, oy+rh)
    zone = getattr(app, "safe_zone", None)
    if zone is not None:
        for path in _circle_paths(zone, registration, app, app.transform, view_box, image_box):
            coordinates = [value for point in path for value in point]
            canvas.create_line(*coordinates, fill=INK, width=6*dpi, tags=("safe_zone",))
            canvas.create_line(*coordinates, fill="#F8F6E8", width=2*dpi, tags=("safe_zone",))

    ordered = app._ordered_targets()
    numbers = {point.id: number for number, (point, _) in enumerate(ordered, 1)}
    distances = {point.id: distance for point, distance in ordered}
    priorities = {point.id for point, _ in ordered[:3]} if app.position is not None else set()
    selected = getattr(app, "selected_point_id", None)
    marker_size = getattr(app, "marker_size", "large")
    if hasattr(marker_size, "get"):
        marker_size = marker_size.get()
    # A badge can remain readable without covering its geographic coordinate.
    # Cap extra HiDPI growth: the former filled 40*dpi circle hid map detail.
    pin_scale = min(dpi, 1.25)
    radius = (9 if marker_size == "medium" else 12)*pin_scale
    visible = []
    for point in app.data.points:
        projected = canvas_point(point.x, point.y)
        if projected is not None:
            visible.append((point, *projected, radius))
    player = canvas_point(*app.position) if app.position is not None else None
    occupied = [(x-7*pin_scale, y-7*pin_scale, x+7*pin_scale, y+7*pin_scale) for _, x, y, _ in visible]
    if player is not None:
        px, py = player
        occupied.append((px-13*pin_scale, py-13*pin_scale, px+13*pin_scale, py+13*pin_scale))
        # A single guide is enough; details for the other targets stay in the list.
        guide_id = selected or (ordered[0][0].id if ordered else None)
        for point, x, y, _ in visible:
            if point.id == guide_id:
                canvas.create_line(px, py, x, y, fill=INK, dash=(round(7*dpi), round(7*dpi)), width=5*dpi,
                                   tags=("target_guide",))
                canvas.create_line(px, py, x, y, fill=AMBER, dash=(round(7*dpi), round(7*dpi)), width=2*dpi,
                                   tags=("target_guide",))

    for point, x, y, r in visible:
        state = app._zone_state(point)
        is_selected, is_priority = point.id == selected, point.id in priorities
        border = AMBER_LIGHT if is_selected else (AMBER if is_priority or state != "OUT" else AMBER_DIM)
        fill = AMBER if state != "OUT" else OUT_FILL
        tag = ("basement", point.id, state.lower())
        offset = r+9*pin_scale
        choices = []
        for order, (dx, dy) in enumerate(((1, -1), (-1, -1), (1, 1), (-1, 1))):
            bx = min(max(x+dx*offset, r+6*pin_scale), cw-r-6*pin_scale)
            by = min(max(y+dy*offset, r+6*pin_scale), ch-r-6*pin_scale)
            box = (bx-r-3*pin_scale, by-r-3*pin_scale, bx+r+3*pin_scale, by+r+3*pin_scale)
            choices.append((sum(_overlap(box, taken) for taken in occupied), order, bx, by, box))
        _, _, bx, by, box = min(choices)
        occupied.append(box)
        length = math.hypot(bx-x, by-y)
        end = (bx-(bx-x)*r/length, by-(by-y)*r/length)
        canvas.create_line(x, y, *end, fill=INK, width=3.5*pin_scale, tags=("poi_stem", point.id))
        canvas.create_line(x, y, *end, fill=border, width=1.3*pin_scale, tags=("poi_stem", point.id))
        # The number is offset; only the tiny anchor below marks the location.
        canvas.create_oval(bx-r-2*pin_scale, by-r-2*pin_scale, bx+r+2*pin_scale, by+r+2*pin_scale,
                           fill=INK, outline=INK, width=pin_scale, tags=("poi_halo",))
        if state == "IN" or is_selected:
            canvas.create_oval(bx-r-pin_scale, by-r-pin_scale, bx+r+pin_scale, by+r+pin_scale,
                               outline=AMBER_LIGHT if is_selected else GREEN, width=1.3*pin_scale,
                               tags=("poi_halo",))
        if state == "OUT":
            body = canvas.create_polygon(bx, by-r, bx+r, by, bx, by+r, bx-r, by,
                                          fill=fill, outline=border, width=1.5*pin_scale, tags=tag)
        else:
            body = canvas.create_oval(bx-r, by-r, bx+r, by+r, fill=fill, outline=border,
                                      width=1.5*pin_scale, tags=tag)
        canvas.create_text(bx, by, text=str(numbers.get(point.id, "")), fill=INK if state != "OUT" else AMBER_LIGHT,
                           font=("Segoe UI", -round((14 if marker_size != "medium" else 11)*pin_scale), "bold"),
                           tags=("poi_number", point.id))
        app._map_pin_hits[point.id] = (x, y, 6*pin_scale)
        app._map_badge_hits[point.id] = (bx, by, r+3*pin_scale)
        app._map_pin_items[point.id] = (body, border, 1.5*pin_scale)

    # Draw anchors after every badge, so a nearby label cannot hide the exact
    # projected coordinate. The badge itself must never be read as the point.
    for point, x, y, _ in visible:
        reach = 4*pin_scale
        for coordinates in ((x-reach, y, x+reach, y), (x, y-reach, x, y+reach)):
            canvas.create_line(*coordinates, fill=INK, width=3.5*pin_scale, tags=("poi_anchor", point.id))
            canvas.create_line(*coordinates, fill=AMBER_LIGHT, width=1.2*pin_scale, tags=("poi_anchor", point.id))
        canvas.create_oval(x-1.5*pin_scale, y-1.5*pin_scale, x+1.5*pin_scale, y+1.5*pin_scale,
                           fill=AMBER, outline=INK, width=pin_scale, tags=("poi_anchor", point.id))

    limits = (8*dpi, 8*dpi, cw-8*dpi, ch-8*dpi)
    if player is not None:
        px, py = player
        canvas.create_oval(px-8*pin_scale, py-8*pin_scale, px+8*pin_scale, py+8*pin_scale,
                           outline=INK, width=4*pin_scale, tags=("player",))
        canvas.create_oval(px-8*pin_scale, py-8*pin_scale, px+8*pin_scale, py+8*pin_scale,
                           outline=CYAN, width=1.5*pin_scale, tags=("player",))
        canvas.create_oval(px-2.5*pin_scale, py-2.5*pin_scale, px+2.5*pin_scale, py+2.5*pin_scale,
                           fill=CYAN, outline=INK, width=pin_scale, tags=("player",))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            coordinates = (px+dx*5*pin_scale, py+dy*5*pin_scale, px+dx*12*pin_scale, py+dy*12*pin_scale)
            canvas.create_line(*coordinates, fill=INK, width=3.5*pin_scale, tags=("player",))
            canvas.create_line(*coordinates, fill=CYAN, width=1.5*pin_scale, tags=("player",))
        _pill(canvas, app.t("YOU"), [(px, py-25*pin_scale), (px, py+25*pin_scale),
                                    (px+42*pin_scale, py), (px-42*pin_scale, py)],
              color=CYAN, font=("Segoe UI", -round(14*pin_scale), "bold"), limits=limits,
              occupied=occupied, tags=("player_label",))

    for point, x, y, r in visible:
        distance = distances.get(point.id)
        if distance is None or (point.id != selected and point.id not in priorities):
            continue
        bx, by, badge_radius = app._map_badge_hits[point.id]
        text = _amount(distance, getattr(app, "language", "en"))
        _pill(canvas, text, [(bx, by-badge_radius-13*pin_scale), (bx, by+badge_radius+13*pin_scale),
                             (bx+54*pin_scale, by), (bx-54*pin_scale, by), (bx, by-badge_radius-34*pin_scale)],
              color=AMBER_LIGHT, font=("Segoe UI", -round(12*pin_scale), "bold"), limits=limits,
              occupied=occupied, tags=("poi_distance", point.id))

def _pin_at(app, x, y):
    nearby = [(math.hypot(x-px, y-py), point_id) for point_id, (px, py, radius)
              in getattr(app, "_map_pin_hits", {}).items() if math.hypot(x-px, y-py) <= radius]
    if nearby:
        return min(nearby)[1]
    badges = [(math.hypot(x-px, y-py), point_id) for point_id, (px, py, radius)
              in getattr(app, "_map_badge_hits", {}).items() if math.hypot(x-px, y-py) <= radius]
    return min(badges)[1] if badges else None


def bind_interactions(app):
    """Select real pins in position mode; preserve all setup/manual click paths."""
    if getattr(app, "_map_interactions_bound", False):
        return
    app._map_interactions_bound = True

    def click(event):
        point_id = _pin_at(app, event.x, event.y) if app.mode == "position" else None
        if point_id is not None:
            select = getattr(app, "_select_point", None)
            if select is not None:
                select(point_id)
            else:
                app.selected_point_id = point_id
                app.draw()
        else:
            app._click(event)
        return "break"

    def hover(event=None):
        point_id = (_pin_at(app, event.x, event.y) if event is not None and app.mode == "position" else None)
        previous = getattr(app, "_map_hover_id", None)
        if previous == point_id:
            return
        items = getattr(app, "_map_pin_items", {})
        if previous in items:
            item, border, width = items[previous]
            app.canvas.itemconfigure(item, outline=border, width=width)
        if point_id in items:
            app.canvas.itemconfigure(items[point_id][0], outline=AMBER_LIGHT, width=2.5*min(_dpi(app.canvas), 1.25))
        app._map_hover_id = point_id
        app.canvas.configure(cursor="hand2" if point_id else "")

    app.canvas.bind("<Button-1>", click)
    app.canvas.bind("<Motion>", hover, add="+")
    app.canvas.bind("<Leave>", lambda event: hover(), add="+")


# A concise alias is convenient for shells which delegate their draw method.
draw = draw_map
