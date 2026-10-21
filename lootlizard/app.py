"""On-demand local map registration and optional trained-icon recognition."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import queue
import re
import tempfile
import time
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from . import __version__
from .core import Bounds, MapData, SafeZone, nearest
from .storage import read_preferences, resource_path, save_preferences, preferences_path, legacy_profile_directory
from . import windows
from .vision import Profile, Recognition, create_profile, recognize
from .zone_vision import ZoneDetection, detect_safe_zone
from .registration import Registration, load_reference_catalog, register_map
from .marker_pipeline import recognize_registered_marker, map_search_bounds
from .map_text import identify_map_text
from .i18n import LANGUAGES, normalize_language, translate
from .presentation import present
from .ui_shell import build_ui, settings_placement
from .map_updates import MapUpdateClient, SyncResult


BG = "#0d131b"
PANEL = "#151e29"
TEXT = "#eef3f8"
MUTED = "#9aabba"
ACCENT = "#64dce8"
GOLD = "#ffbc48"


class _Text(str):
    """Rendered text retaining its message and values for an in-place refresh."""

    def __new__(cls, rendered, message, values):
        instance = super().__new__(cls, rendered)
        instance.message, instance.values = message, values
        return instance


class Companion:
    def __init__(self, root: tk.Tk, *, settings_path: Path | None = None, smoke_test: bool = False):
        self.root = root
        self.settings_path = settings_path
        self.smoke_test = smoke_test
        self.settings = {} if smoke_test else read_preferences(settings_path)
        self.language = normalize_language(self.settings.get("language"))
        self._localized_widgets = {}
        self._status_message = None
        self._status_level = "info"
        self.hotkey_receipt_count = 0
        self.hotkey_receipt_at = None
        self.hotkey_registration = "disabled" if smoke_test else "registering"
        self.hotkey_failure = None
        self.data = MapData.load(resource_path("data/erangel.json"))
        self.map_data = {self.data.id: self.data}
        for path in resource_path("data/erangel.json").parent.glob("*.json"):
            try:
                bundled = MapData.load(path)
                self.map_data[bundled.id] = bundled
            except (OSError, ValueError, TypeError):
                continue
        self._feed_map_ids = set(self.map_data)
        self._local_map_ids = set()
        self._local_map_files = {}
        self._load_local_map_files()
        self.map_data_revision = None
        self.map_data_sha256 = None
        self.map_update_status = "bundled"
        self.map_update_reason = ""
        self.map_updates_enabled = self.settings.get("automatic_map_updates") is not False
        self.map_update_client = None
        self.map_update_future = None
        self.map_update_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="map-data-sync")
        self.map_update_token = 0
        self.map_update_next_at = 0.
        self.map_update_stop = threading.Event()
        self.image: Image.Image | None = None
        self.image_is_capture = False
        self.photo = None
        self.bounds: Bounds | None = None
        self.position: tuple[float, float] | None = None
        self.position_method = None
        self.position_score = 0.
        self.view_heading_degrees = None
        self.view_context = "replay" if self.settings.get("observer_image") is True else "live"
        self.safe_zone: SafeZone | None = None
        self.zone_reason = "Safe zone has not been checked for this image."
        self.captured_at: datetime | None = None
        self.captured_monotonic: float | None = None
        self.mode = "position"
        self.first_corner: tuple[int, int] | None = None
        self.marker_box = None
        self.profile: Profile | None = None
        self.references = ()
        self.reference_catalog: Path | None = None
        self.registration: Registration | None = None
        self.map_text_result = None
        self.recognition_id = 0
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="marker-recognition")
        self.future = None
        self.marker_photo = None
        self.transform = (0.0, 0.0, 1.0, 1.0)
        self.events: queue.SimpleQueue = queue.SimpleQueue()
        self.capture_busy = False
        self.selected_point_id = None
        self._row_point_ids = {}
        self.marker_size = "medium" if self.settings.get("marker_size") == "medium" else "large"
        self.hotkey: windows.Hotkey | None = None
        self.closed = False
        self.displays = windows.monitors()
        self.capture_index = self._saved_display("capture_monitor", next((i for i, m in enumerate(self.displays) if m.primary), 0))
        self.target_index = self._saved_display("output_monitor", next((i for i, m in enumerate(self.displays) if not m.primary), 0))
        self._build_ui()
        self._initialize_map_updates()
        if not smoke_test:
            self._load_profile()
            saved_catalog = self.settings.get("reference_catalog")
            if isinstance(saved_catalog, str) and saved_catalog:
                self._load_map_catalog(Path(saved_catalog), persist=False)
        self._place_window(self.target_index)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if not smoke_test:
            self.hotkey = windows.Hotkey(lambda: self.events.put("capture"))
            self.hotkey.start()
        self.root.after(100, self._tick)

    def _load_local_map_files(self):
        records = self.settings.get("local_map_files", {})
        if not isinstance(records, dict):
            return
        for map_id, filename in list(records.items())[:32]:
            if not isinstance(map_id, str) or not 1 <= len(map_id) <= 160 or not isinstance(filename, str):
                continue
            self._local_map_ids.add(map_id)
            self._local_map_files[map_id] = filename
            try:
                data = MapData.load(Path(filename))
                if data.id != map_id:
                    raise ValueError("The imported map id changed")
                self.map_data[map_id] = data
            except (OSError, ValueError, TypeError):
                # A missing local override must not silently become feed data.
                self.map_data.pop(map_id, None)
        self.data = self.map_data.get(self.data.id, self.data)

    def _initialize_map_updates(self):
        if self.smoke_test:
            self._update_map_feedback()
            return
        configuration = self.settings_path or preferences_path()
        self.map_update_client = MapUpdateClient(configuration.parent / "maps-cache.json")
        cached = self.map_update_client.load_cached()
        if cached is not None:
            self._apply_map_snapshot(cached)
            self.map_update_status = "cached"
        self._update_map_feedback()

    def _automatic_updates_changed(self):
        self.map_updates_enabled = bool(self.automatic_updates.get())
        self.settings["automatic_map_updates"] = self.map_updates_enabled
        self._persist()
        self.map_update_token += 1
        if self.map_update_future is not None:
            self.map_update_future.cancel()
        self.map_update_next_at = 0. if self.map_updates_enabled else float("inf")
        if not self.map_updates_enabled:
            self.map_update_status = "disabled"
        self._update_map_feedback()

    def _check_map_updates(self, *, force=False):
        if self.closed or self.smoke_test or self.map_update_client is None:
            return False
        if not force and (not self.map_updates_enabled or time.monotonic() < self.map_update_next_at):
            return False
        if self.map_update_future is not None and not self.map_update_future.done():
            return False
        token, client, stop = self.map_update_token, self.map_update_client, self.map_update_stop
        self.map_update_status = "checking"
        self.map_update_next_at = time.monotonic() + 60
        self._update_map_feedback()
        def fetch():
            try:
                result = client.check(force=force)
            except Exception as error:
                result = SyncResult(snapshot=None, changed=False, status="error", reason=str(error),
                                    next_check_seconds=60.)
            if not stop.is_set() and not self.closed:
                self.events.put(("map_update", token, result))
        self.map_update_future = self.map_update_executor.submit(fetch)
        return True

    def _accept_map_update(self, token, result):
        if self.closed or token != self.map_update_token:
            return
        self.map_update_status, self.map_update_reason = result.status, result.reason
        self.map_update_next_at = time.monotonic() + max(1., result.next_check_seconds)
        if result.snapshot is not None:
            if result.snapshot.content_sha256 != getattr(self, "map_data_sha256", None):
                self._apply_map_snapshot(result.snapshot)
            else:
                self.map_data_revision = result.snapshot.revision
        self._update_map_feedback()

    def _apply_map_snapshot(self, snapshot):
        """Apply validated POIs on the UI thread, retaining same-map geometry."""
        old_ids = getattr(self, "_feed_map_ids", set(self.map_data))
        local_ids = getattr(self, "_local_map_ids", set())
        catalog = {key: value for key, value in self.map_data.items()
                   if key not in old_ids or key in local_ids}
        incoming = {data.id: data for data in snapshot.maps}
        catalog.update({key: value for key, value in incoming.items() if key not in local_ids})
        self.map_data = catalog
        self._feed_map_ids = set(incoming) - local_ids
        self.map_data_revision = snapshot.revision
        self.map_data_sha256 = snapshot.content_sha256
        registration = getattr(self, "registration", None)
        map_id = registration.map_id if registration is not None and registration.map_id else self.data.id
        replacement = catalog.get(map_id)
        if replacement is None:
            # Recognition belongs to the current image, not the old POI list.
            # Its eventual map id is checked against this catalog on acceptance.
            self.position, self.safe_zone, self.bounds = None, None, None
            self.position_method, self.view_heading_degrees, self.position_score = None, None, 0.
            self.selected_point_id = None
            self.zone_reason = "Map data is unavailable for this map."
        else:
            if replacement.id != self.data.id:
                self.position, self.safe_zone = None, None
                self.position_method, self.view_heading_degrees, self.position_score = None, None, 0.
                self.profile = None
            self.data = replacement
            if not any(point.id == self.selected_point_id for point in replacement.points):
                self.selected_point_id = None
            self._configure(self.map_label, text=replacement.name)
            self._configure(self.data_label, text=self.t(
                '{count} community points · verify in game', count=len(replacement.points)))
        self._render_results()
        self.draw()

    def _update_map_feedback(self):
        if not hasattr(self, "map_update_label"):
            return
        revision = getattr(self, "map_data_revision", None)
        version = self.t("Map data · {revision}", revision=revision[:16]) if revision else self.t("Built-in map data")
        status = getattr(self, "map_update_status", "bundled")
        if status == "checking":
            summary = self.t("Checking map updates…")
        elif status in ("offline", "error"):
            summary = self.t("Offline · saved map data remains available")
        elif not getattr(self, "map_updates_enabled", True):
            summary = self.t("Automatic map updates are off")
        else:
            summary = version
        self._configure(self.map_update_label, text=version if summary == version else str(version)+"\n"+str(summary))
        raw = getattr(self, "map_update_reason", "")
        self._configure(self.map_update_diagnostic_label, text=self.t(
            "Map update status: {name}\nRevision: {revision}\n{reason}", name=status,
            revision=revision or "—", reason=raw))

    def _saved_display(self, key, default):
        name = self.settings.get(key)
        return next((i for i, m in enumerate(self.displays) if m.name == name), default)

    def t(self, message, **values):
        if isinstance(message, _Text):
            values, message = message.values, message.message
        rendered_values = {key: self._detail(value) if key in ("error", "reason") else value
                           for key, value in values.items()}
        return _Text(translate(message, self.language, **rendered_values), message, values)

    def _detail(self, value):
        """Translate known application diagnostics, preserving raw system details."""
        if isinstance(value, BaseException) and value.args and isinstance(value.args[0], _Text):
            return self.t(value.args[0])
        value = str(value)
        native = re.fullmatch(r"(.+?): (.*) \(Windows error (\d+)\)\.", value)
        if native:
            return translate("{action}: {error} (Windows error {code}).", self.language,
                             action=self._detail(native.group(1)), error=self._detail(native.group(2)),
                             code=native.group(3))
        prefixes = (("Recognition unavailable: ", "error"),
                    ("Registration unavailable: ", "error"),
                    ("Safe-zone detection unavailable: ", "error"),
                    ("Reference map is unsuitable: ", "reason"),
                    ("Could not capture the selected display: ", "error"),
                    ("The keyboard shortcut callback failed: ", "error"),
                    ("Could not start the keyboard shortcut: ", "error"))
        for prefix, field in prefixes:
            if value.startswith(prefix):
                return translate(prefix + "{" + field + "}", self.language,
                                 **{field: self._detail(value[len(prefix):])})
        patterns = (
            (r"(.+): a finite number is required", "{name}: a finite number is required"),
            (r"(.+): expected a value between 0 and 1", "{name}: expected a value between 0 and 1"),
            (r"A non-empty (.+) is required", "A non-empty {name} is required"),
            (r"(.+) is too long", "{name} is too long"),
            (r"Duplicate point id: (.+)", "Duplicate point id: {name}"),
            (r"(.+) exceeds its file-size limit", "{name} exceeds its file-size limit"),
            (r"Invalid (.+) format, mode, or dimensions", "Invalid {name} format, mode, or dimensions"),
        )
        for pattern, message in patterns:
            match = re.fullmatch(pattern, value)
            if match:
                return translate(message, self.language, name=match.group(1))
        action, separator, details = value.partition(": ")
        localized_action = translate(action, self.language)
        if separator and localized_action != action:
            return localized_action + separator + details
        return translate(value, self.language)

    def _widget(self, factory, *args, **kwargs):
        widget = factory(*args, **kwargs)
        if "text" in kwargs:
            self._localized_widgets[widget] = kwargs["text"]
        return widget

    def _configure(self, widget, **kwargs):
        if "text" in kwargs:
            self._localized_widgets[widget] = kwargs["text"]
        widget.configure(**kwargs)

    def _status(self, message, *, level="info"):
        self._status_message = message
        self._status_level = level
        self.status.set(message)
        self.status_label.configure(fg={"info": TEXT, "success": ACCENT,
                                        "warning": GOLD, "error": "#ffb1ac"}.get(level, TEXT))
        self._refresh_presentation()

    def _update_hotkey_feedback(self):
        if self.hotkey_registration == "ready":
            message, color = self.t("Ctrl+Shift+B · active"), ACCENT
        elif self.hotkey_registration == "failed":
            message, color = self.t("Ctrl+Shift+B · unavailable: {error}",
                                    error=self.hotkey_failure), "#ffb1ac"
        elif self.hotkey_registration == "disabled":
            message, color = self.t("Ctrl+Shift+B · disabled in test mode"), MUTED
        else:
            message, color = self.t("Ctrl+Shift+B · registering…"), GOLD
        self.hotkey_state_label.configure(text=message, fg=color)
        last_time = (self.hotkey_receipt_at.strftime("%H:%M:%S")
                     if self.hotkey_receipt_at else self.t("never"))
        self.hotkey_receipt_label.configure(text=self.t(
            "Hotkey received: {count} · last: {time}", count=self.hotkey_receipt_count, time=last_time))

    def _point_name(self, point):
        # Localize bundled generic labels while retaining custom/imported names.
        match = re.fullmatch(r"Secret basement (\d{2})", point.name)
        if self.data.id == "erangel" and match and point.id == f"erangel-{match.group(1)}":
            return self.t("Secret basement {number}", number=match.group(1))
        match = re.fullmatch(r"Secret room (\d{2})", point.name)
        if self.data.id == "taego" and match and point.id == f"taego-{match.group(1)}":
            return self.t("Secret room {number}", number=match.group(1))
        return point.name

    def _point_short_name(self, point):
        match = re.fullmatch(r"Secret (basement|room) (\d{2})", point.name)
        if match and point.id == f"{self.data.id}-{match.group(2)}" and self.data.id in ("erangel", "taego"):
            return self.t("Basement {number}" if match.group(1) == "basement" else "Room {number}",
                          number=match.group(2))
        return self._point_name(point)

    def _render_results(self):
        self._row_point_ids = {}
        for item in self.results.get_children():
            self.results.delete(item)
        self._update_zone_display()
        if self.image is None or self.data.id not in self.map_data or (getattr(self, "references", ()) and self._active_registration() is None):
            self._refresh_presentation()
            return
        for number, (point, distance) in enumerate(self._ordered_targets(), 1):
            state = self._zone_state(point)
            amount = "—"
            if distance is not None:
                amount = f"{distance:,.0f}"
                if self.language == "hu":
                    amount = amount.replace(",", " ")
                amount += " m"
            tag = "target" if self.position is not None and number <= 3 else state.lower()
            item = self.results.insert("", "end", values=(f"{number}. {self._point_short_name(point)}",
                                                        self.t(state) if state != "UNKNOWN" else "—", amount), tags=(tag,))
            self._row_point_ids[item] = point.id
            if point.id == getattr(self, "selected_point_id", None) and hasattr(self.results, "selection_set"):
                self.results.selection_set(item)
        self._refresh_presentation()

    def _active_registration(self):
        registration = getattr(self, "registration", None)
        return (registration if registration is not None and registration.map_id == self.data.id
                and registration.map_to_image is not None and self.data.id in self.map_data else None)

    def _view_box(self):
        registration = self._active_registration()
        if self.mode == "calibrate":
            return (0, 0, self.image.width, self.image.height)
        if registration is not None:
            return map_search_bounds(registration, self.image.size) or registration.viewport
        if self.bounds is not None and not getattr(self, "references", ()):
            return self.bounds.as_box()
        return (0, 0, self.image.width, self.image.height)

    def _project_map_point(self, x, y):
        """Return full screenshot pixels, clipping off-view projected points."""
        if self.data.id not in self.map_data:
            return None
        registration = self._active_registration()
        if registration is not None:
            return registration.project_poi(x, y)
        if getattr(self, "references", ()) or self.bounds is None:
            return None
        return (self.bounds.left + x * (self.bounds.right-self.bounds.left),
                self.bounds.top + y * (self.bounds.bottom-self.bounds.top))

    def _registered_full_bounds(self, registration, image_size=None):
        """The legacy circle/icon setup needs the complete, axis-aligned map.

        A clipped/rotated/anisotropic view must not be normalized as a full map.
        Tiny feature-fit rounding differences at the image border are tolerated.
        """
        matrix = registration.map_to_image
        if matrix is None or (image_size is None and self.image is None):
            return None
        image_width, image_height = image_size or self.image.size
        horizontal, vertical = float(matrix[0, 0]), float(matrix[1, 1])
        scale = max(abs(horizontal), abs(vertical))
        if (min(horizontal, vertical) <= 0 or abs(horizontal-vertical) > scale*.005
                or max(abs(matrix[0, 1]), abs(matrix[1, 0])) > scale*.002):
            return None
        left, top = float(matrix[0, 2]), float(matrix[1, 2])
        right, bottom = left+horizontal, top+vertical
        if left < -2 or top < -2 or right > image_width+2 or bottom > image_height+2:
            return None
        try:
            return Bounds(max(0, round(left)), max(0, round(top)),
                          min(image_width, round(right)), min(image_height, round(bottom))).validate(image_width, image_height)
        except ValueError:
            return None

    def _zone_state(self, point):
        zone = getattr(self, "safe_zone", None)
        return "UNKNOWN" if zone is None else ("IN" if zone.contains(point.x, point.y) else "OUT")

    def _ordered_targets(self):
        if self.data.id not in self.map_data:
            return []
        zone = getattr(self, "safe_zone", None)
        if self.position is not None:
            return nearest(self.data, self.position, count=len(self.data.points), zone=zone)
        # There is no distance ranking until a fresh icon position is available.
        points = sorted(self.data.points,
                        key=lambda point: (zone is not None and not zone.contains(point.x, point.y), point.id))
        return [(point, None) for point in points]

    def _update_zone_display(self):
        zone = getattr(self, "safe_zone", None)
        reason = getattr(self, "zone_reason", "")
        if zone is None:
            message = (self.t("White circle unknown — {reason}", reason=reason) if reason
                       else self.t("White circle unknown — no safe-zone priority."))
            color = MUTED
        else:
            count = sum(zone.contains(point.x, point.y) for point in self.data.points)
            message = self.t("White circle: {count}/{total} basements inside · inside-first targets",
                             count=count, total=len(self.data.points))
            if reason:
                message = str(message) + "\n" + self._detail(reason)
            color = ACCENT
        self._configure(self.zone_label, text=message, fg=color)

    def _language_changed(self, event=None):
        selected = self.language_choice.get()
        language = next((code for code, name in LANGUAGES.items() if name == selected), "en")
        self._apply_language(language)
        self.settings["language"] = self.language
        self._persist()

    def _apply_language(self, language):
        self.language = normalize_language(language)
        for widget, message in tuple(self._localized_widgets.items()):
            if widget.winfo_exists():
                widget.configure(text=self.t(message) if isinstance(message, _Text) else message)
        if self._status_message is not None:
            self.status.set(self.t(self._status_message) if isinstance(self._status_message, _Text)
                            else self._status_message)
        for number, title in enumerate(("General", "Advanced", "Diagnostics")):
            self.tabs.tab(number, text=self.t(title))
        self.settings_window.title(self.t("Settings"))
        self.marker_size_choice.configure(values=[self.t("Large"), self.t("Medium")])
        self.marker_size_choice.current(0 if self.marker_size == "large" else 1)
        self.results.heading("name", text=self.t("Room"))
        self.results.heading("zone", text=self.t("Zone"))
        self.results.heading("distance", text=self.t("≈ m"))
        self.language_choice.set(LANGUAGES[self.language])
        for choice, index in ((self.capture_choice, self.capture_index),
                              (self.output_choice, self.target_index)):
            choice.configure(values=self._display_names())
            choice.current(index)
        self._render_results()
        self._update_age()
        self._update_hotkey_feedback()
        self._update_map_feedback()
        self.draw()

    def _build_ui(self):
        build_ui(self)
        # The renderer owns canvas hit testing; setup clicks retain _click.
        from .map_renderer import bind_interactions
        bind_interactions(self)

    def open_settings(self):
        placement = None
        if isinstance(self.settings_window, tk.Toplevel):
            placement = settings_placement((self.root.winfo_rootx(), self.root.winfo_rooty(),
                self.root.winfo_width(), self.root.winfo_height()), self.displays, self.target_index)
        self.settings_window.deiconify()
        if placement is not None:
            self.settings_window.update_idletasks()
            # Tk's negative geometry offsets refer to the right/bottom edge;
            # SetWindowPos accepts the absolute virtual-desktop coordinates.
            windows.move_window(self.settings_window.winfo_id(), *placement)
        self.settings_window.lift()

    def close_settings(self):
        self.settings_window.withdraw()

    def _marker_size_changed(self, event=None):
        self.marker_size = "medium" if self.marker_size_choice.current() == 1 else "large"
        self.settings["marker_size"] = self.marker_size
        self._persist()
        self.draw()

    def _table_selected(self, event=None):
        selection = self.results.selection()
        if selection:
            self._select_point(self._row_point_ids.get(selection[0]))

    def _select_point(self, point_id):
        # Selection is presentation-only and can never restore pending geometry.
        registration = self._active_registration()
        if self.image is None or (self.bounds is None and registration is None):
            return False
        if getattr(self, "references", ()) and registration is None:
            return False
        if not any(point.id == point_id for point in self.data.points):
            return False
        self.selected_point_id = point_id
        if hasattr(self.results, "selection_set"):
            item = next((row for row, value in self._row_point_ids.items() if value == point_id), None)
            if item and self.results.selection() != (item,):
                self.results.selection_set(item)
                self.results.see(item)
        self._refresh_presentation()
        self.draw()
        return True

    def _refresh_presentation(self):
        if not hasattr(self, "main_status_label"):
            return
        summary = present(self)
        self.main_status_label.configure(text=summary.title,
            fg=GOLD if summary.tone == "warning" else TEXT)
        self.main_detail_label.configure(text=summary.detail)
        self.summary_map_label.configure(text=summary.map_name)
        self.room_count_label.configure(text=summary.rooms)
        self.freshness_label.configure(text=summary.freshness)
        self.circle_badge_label.configure(text=summary.circle,
            fg="#b5d8b0" if self.safe_zone is not None and self._active_registration() is not None
            or self.safe_zone is not None and not self.references else MUTED)
        self.selection_title_label.configure(text=summary.selection_title)
        self.selection_detail_label.configure(text=summary.selection_detail)

    def _display_names(self):
        return [self.t('Monitor {number} · {width}×{height}', number=i+1, width=m.width, height=m.height) + (self.t(' · primary') if m.primary else "")
                for i, m in enumerate(self.displays)]

    def _place_window(self, index):
        monitor = self.displays[index]
        width, height = min(1440, monitor.width - 30), min(960, monitor.height - 80)
        self.root.update_idletasks()
        windows.move_window(self.root.winfo_id(), monitor.x + 15, monitor.y + 30, max(1080, width), max(700, height))

    def _persist(self):
        if self.smoke_test:
            return
        try:
            save_preferences(self.settings, self.settings_path)
        except OSError as error:
            self._status(self.t('Could not save settings: {error}', error=error))

    def _profile_directory(self):
        configuration = self.settings_path or preferences_path()
        identifier = hashlib.sha256(self.data.id.encode("utf-8")).hexdigest()[:24]
        return configuration.parent / "profiles" / identifier

    def _load_map_catalog(self, path, *, persist=True):
        """Load only a user-selected catalog; never auto-discover game assets."""
        try:
            path = Path(path).resolve()
            references = load_reference_catalog(path)
            if not references:
                raise ValueError("The local catalog has no map references")
            self._clear_results(clear_zone=True)
            self.bounds = None
            self.references, self.reference_catalog = references, path
            if persist:
                self.settings["reference_catalog"] = str(path)
                self._persist()
            self._configure(self.reference_label, text=self.t(
                "Local map catalog active · {count} reference(s)", count=len(references)), fg=ACCENT)
            self._configure(self.hint, text=self.t(
                "Open the game map at any supported zoom, then Ctrl+Shift+B. Basement markers do not require your icon. Unknown maps are withheld."))
            self._status(self.t("Local references loaded — capture or open a map image."), level="success")
            if self.image is not None:
                self.mode, self.first_corner = "position", None
                self._start_recognition()
                self.draw()
            return True
        except (OSError, ValueError, TypeError) as error:
            self._status(self.t("Could not load the local map catalog: {error}", error=error), level="error")
            return False

    def import_map_catalog(self):
        filename = filedialog.askopenfilename(title=self.t("Select your local map reference catalog"),
                                             filetypes=[(self.t("Map JSON"), "*.json")], parent=self.root)
        if filename:
            self._load_map_catalog(Path(filename))

    def disable_map_catalog(self):
        self.references, self.reference_catalog = (), None
        self.settings.pop("reference_catalog", None)
        self._persist()
        self._configure(self.reference_label, text=self.t(
            "Local map catalog disabled · fixed-layout profile mode"), fg=MUTED)
        self._clear_results(clear_zone=True)
        if self.image is not None:
            self.set_image(self.image, captured=self.image_is_capture)
        else:
            self._status(self.t("Local map catalog disabled. Fixed-layout setup is available."))

    def _load_profile(self):
        self.profile = None
        self.marker_photo = None
        self.marker_preview.configure(image="")
        directory = self._profile_directory()
        if self.settings_path is None and not (directory / "profile.json").exists():
            # Read the old format in place; all future saves use LootLizard.
            directory = legacy_profile_directory(self.data.id)
        if not (directory / "profile.json").exists():
            self._configure(self.profile_label, text=self.t('No icon profile yet.'), fg=GOLD)
            self._status(self.t("Setup required — open the full map, capture it, then select map bounds and save your icon sample."), level="warning")
            return
        try:
            profile = Profile.load(directory)
            if profile.map_id != self.data.id:
                raise ValueError(self.t('Profile created for another map'))
            self.profile = profile
            self._show_profile()
            self._configure(self.hint, text=self.t('Open the trained full game map, then press Ctrl+Shift+B. The trained icon is found automatically while the game keeps focus.'))
            self._status(self.t("Ready — open the full game map and press Ctrl+Shift+B."), level="success")
        except (OSError, ValueError, TypeError) as error:
            self._configure(self.profile_label, text=self.t('Could not load the saved profile.'), fg=GOLD)
            self._status(self.t('A new icon profile is needed: {error}', error=error), level="error")

    def _show_profile(self):
        self._configure(self.profile_label, text=self.t('Icon profile active · experimental recognition'), fg=ACCENT)
        preview = Image.fromarray(self.profile.mask).resize((70, 70), Image.Resampling.NEAREST)
        self.marker_photo = ImageTk.PhotoImage(preview)
        self.marker_preview.configure(image=self.marker_photo)

    def begin_marker_setup(self):
        registration = self._active_registration()
        if registration is not None:
            self.bounds = self._registered_full_bounds(registration)
        if self.image is None or self.bounds is None:
            self._status(self.t('First, open a full map image and select its bounds.'), level="warning")
            return
        self._clear_results()
        self.mode, self.first_corner, self.marker_box = "marker_box", None, None
        self.close_settings()
        self._configure(self.hint, text=self.t('Icon sample · 1/3\nClick the top-left corner of a small box around YOUR icon. Leave a 2–3 pixel margin and include the entire icon.'))
        self._status(self.t("Icon setup 1/3 — click the icon box's top-left corner."), level="warning")
        self.draw()

    def _start_recognition(self, *, zone_only=False, quiet=False):
        if self.image is None:
            return
        if getattr(self, "references", ()):
            self._start_registration(zone_only=zone_only, quiet=quiet)
            return
        if self.bounds is None:
            return
        ticket = self.recognition_id
        profile, snapshot, map_id, bounds = self.profile, self.image.copy(), self.data.id, self.bounds
        track_icon = profile is not None and not zone_only
        view_context = getattr(self, "view_context", "live")
        if self.future and not self.future.running():
            self.future.cancel()
        self.zone_reason = "Checking the white safe-zone ring…"
        self._render_results()
        if not quiet:
            self._status(self.t('Searching for the trained icon…') if track_icon
                         else self.t("Checking the white safe-zone ring…"))
            self._configure(self.hint, text=self.t('Automatic recognition…\nYou can stay in the game; the result updates here.'))
        def analyze():
            try:
                result = (recognize(snapshot, profile, map_id) if view_context == "live" else
                          Recognition(None, 0., "Replay/observer image: own-player estimation is disabled.", True)) if track_icon else None
            except Exception as error:
                result = Recognition(position=None, score=0.0, reason=str(error))
            try:
                zone = (detect_safe_zone(snapshot, bounds) if result is None or result.layout_verified
                        else ZoneDetection(None, 0.0, "Map layout is not verified; safe zone is unknown."))
            except Exception:
                zone = ZoneDetection(None, 0.0, "Safe-zone detection failed; circle priority is unavailable.")
            self.events.put(("recognized", ticket, result, zone))
        self.future = self.executor.submit(analyze)

    def _start_registration(self, *, zone_only=False, quiet=False):
        ticket = self.recognition_id
        snapshot, references = self.image.copy(), tuple(self.references)
        profile = self.profile if not zone_only else None
        view_context = getattr(self, "view_context", "live")
        if self.future and not self.future.running():
            self.future.cancel()
        self.zone_reason = "Checking the white safe-zone ring…"
        self._render_results()
        if not quiet:
            self._status(self.t("Identifying the map and its zoom/pan…"))
            self._configure(self.hint, text=self.t(
                "Automatic map registration…\nYou can stay in the game; your icon is optional."))

        def analyze():
            try:
                registration = register_map(snapshot, references)
            except Exception as error:
                registration = Registration(None, None, (0, 0, *snapshot.size),
                                            "Registration unavailable: " + str(error))
            text_evidence = None
            if registration.map_id is None:
                try:
                    text_evidence = identify_map_text(snapshot, [ref.map_id for ref in references])
                except Exception:
                    # OCR is an optional local hint and must never disable the
                    # existing geometry checks or the on-demand capture path.
                    pass
            marker = None
            if registration.map_id is not None and not zone_only:
                try:
                    marker = recognize_registered_marker(snapshot, registration, profile, view_context=view_context)
                except Exception as error:
                    marker = Recognition(None, 0., "Recognition unavailable: " + str(error))
            zone = ZoneDetection(None, 0., "Map layout is not verified; safe zone is unknown.")
            if registration.map_id is not None:
                full_bounds = self._registered_full_bounds(registration, snapshot.size)
                if full_bounds is None:
                    zone = ZoneDetection(None, 0., "Circle priority is unavailable for clipped, rotated, or distorted map views.")
                else:
                    try:
                        zone = detect_safe_zone(snapshot, full_bounds)
                    except Exception:
                        zone = ZoneDetection(None, 0., "Safe-zone detection failed; circle priority is unavailable.")
            self.events.put(("registered", ticket, registration, marker, zone, text_evidence))

        self.future = self.executor.submit(analyze)

    def _accept_registration(self, ticket, registration, marker_result=None, zone_result=None, text_result=None):
        if ticket != self.recognition_id or self.closed:
            return
        self.registration = registration
        self.map_text_result = text_result
        self.bounds = None
        available = getattr(self, "map_data", {self.data.id: self.data})
        matching_data = available.get(registration.map_id)
        if registration.map_to_image is None or matching_data is None:
            self.position, self.safe_zone = None, None
            self.position_method, self.view_heading_degrees, self.position_score = None, None, 0.
            self.zone_reason = "Map layout is not verified; safe zone is unknown."
            if registration.map_id is not None and matching_data is None:
                message = self.t("Map identified as {name}, but no matching point data is loaded. Import that map's JSON in Setup.", name=registration.map_id)
                self._configure(self.map_label, text=registration.map_id)
                self._configure(self.data_label, text=self.t("No matching point data loaded"))
            elif text_result is not None and text_result.map_id is not None:
                data = available.get(text_result.map_id)
                name = data.name if data else text_result.map_id
                message = self.t("Text suggests {name} ({labels}) — zoom out to place points.",
                                 name=name, labels=", ".join(text_result.matched_labels))
                self._configure(self.map_label, text=self.t("Not verified"))
                self._configure(self.data_label, text=self.t("Point placement needs a verified map transform"))
            else:
                message = self.t("Map not verified — overlays withheld: {reason}", reason=registration.reason)
                self._configure(self.map_label, text=self.t("Not verified"))
                self._configure(self.data_label, text=self.t("Point placement needs a verified map transform"))
            self._configure(self.hint, text=message)
            self._status(message, level="warning")
            self._render_results()
            self.draw()
            return
        if matching_data.id != self.data.id:
            self.profile = None
            self.data = matching_data
            if not self.smoke_test:
                self._load_profile()
        self.data = matching_data
        self._configure(self.map_label, text=self.data.name)
        self._configure(self.data_label, text=self.t('{count} community points · verify in game', count=len(self.data.points)))
        if zone_result is not None:
            self.safe_zone, self.zone_reason = zone_result.zone, zone_result.reason
        if marker_result is not None:
            self.position = marker_result.position
        if self.position is not None:
            method = (getattr(marker_result, "method", "trained-icon") if marker_result is not None
                      else getattr(self, "position_method", None))
            self._set_position(self.position, automatic=method in ("trained-icon", "view-cone"),
                               score=marker_result.score if marker_result else getattr(self, "position_score", 0.),
                               method=method,
                               heading_degrees=(getattr(marker_result, "heading_degrees", None) if marker_result is not None
                                                else getattr(self, "view_heading_degrees", None)))
            return
        count = sum(self._project_map_point(point.x, point.y) is not None for point in self.data.points)
        self._configure(self.hint, text=self.t(
            "Basements are projected onto the registered map. Off-screen points are hidden. Your icon is optional; distances require a fresh unique icon match or a manual check position."))
        if marker_result is not None and marker_result.position is None:
            self._status(self.t("{name} registered · {count} visible points · icon distances unavailable: {reason}",
                                name=self.data.name, count=count, reason=marker_result.reason), level="warning")
        else:
            self._status(self.t("{name} registered · {count} visible points · icon optional",
                                name=self.data.name, count=count), level="success")
        self._render_results()
        self.draw()

    def _accept_recognition(self, ticket, result, zone_result=None):
        if ticket != self.recognition_id or self.closed:
            return
        if self.data.id not in self.map_data:
            return
        if zone_result is not None:
            self.safe_zone, self.zone_reason = zone_result.zone, zone_result.reason
        if result is None:
            self._render_results()
            self.draw()
            return
        if not result.layout_verified:
            self.bounds = None
            self.safe_zone = None
            self.zone_reason = "Map layout is not verified; safe zone is unknown."
        if result.position is None:
            self._configure(self.hint, text=self.t("No unique match.\nCheck the full map and your icon's appearance, then capture again.\nThe previous marker has been cleared."))
            self._status(self.t('Recognition failed: {reason}', reason=result.reason), level="error")
            self._render_results()
            self.draw()
            return
        self._set_position(result.position, automatic=True, score=result.score)

    def _capture_changed(self, event=None):
        self.capture_index = self.capture_choice.current()
        self.settings["capture_monitor"] = self.displays[self.capture_index].name
        self._clear_image()
        self._persist()

    def _output_changed(self, event=None):
        self.target_index = self.output_choice.current()
        self.settings["output_monitor"] = self.displays[self.target_index].name
        self._place_window(self.target_index)
        self._persist()

    def _view_context_changed(self):
        self.view_context = "replay" if self.observer_image.get() else "live"
        self.settings["observer_image"] = self.view_context == "replay"
        self._clear_results(clear_zone=True)
        self._persist()
        if self.image is not None:
            self._start_recognition()
        self.draw()

    def _clear_results(self, *, clear_zone=False):
        self.recognition_id += 1
        self.position = None
        self.selected_point_id = None
        self.position_method = None
        self.position_score = 0.
        self.view_heading_degrees = None
        if clear_zone:
            self.registration = None
            self.map_text_result = None
            self.safe_zone = None
            self.zone_reason = "Safe zone has not been checked for this image."
        for item in self.results.get_children():
            self.results.delete(item)
        self._render_results()

    def _clear_image(self):
        self.image, self.bounds = None, None
        self.captured_at, self.captured_monotonic = None, None
        self.mode, self.first_corner = "position", None
        self._clear_results(clear_zone=True)
        self._configure(self.hint, text=self.t('Capture or open an image of the full, zoomed-out game map.'))
        self.draw()

    def _calibration_key(self):
        if self.image is None:
            return ""
        monitor = self.displays[self.capture_index]
        return f"{self.data.id}|{monitor.name}|{self.image.width}x{self.image.height}"

    def set_image(self, image: Image.Image, *, captured=False):
        self.image = image.convert("RGB")
        self.image_is_capture = captured
        self.captured_at, self.captured_monotonic = datetime.now(), time.monotonic()
        self._clear_results(clear_zone=True)
        self.bounds = None
        self.first_corner = None
        self.mode = "position"
        if not getattr(self, "references", ()) and self.data.id not in self.map_data:
            self._status(self.t("Map data is unavailable for this map."), level="warning")
            self.draw()
            return
        if getattr(self, "references", ()):
            self.draw()
            self._start_recognition()
            return
        if self.profile is not None:
            if tuple(self.image.size) == tuple(self.profile.image_size):
                self.bounds = self.profile.bounds
                self._show_profile()
                self.draw()
                self._start_recognition()
                return
            self._configure(self.profile_label, text=self.t("Profile size mismatch · new setup required"), fg=GOLD)
            mismatch = self.t("Profile size mismatch: expected {expected}, received {actual}. Select the correct source display or recreate the profile in Setup.",
                              expected=f"{self.profile.image_size[0]}×{self.profile.image_size[1]}",
                              actual=f"{self.image.width}×{self.image.height}")
            self._configure(self.hint, text=mismatch)
            self._status(mismatch, level="warning")
            self.draw()
            return
        if captured:
            record = self.settings.get("calibrations", {})
            if isinstance(record, dict):
                coords = record.get(self._calibration_key())
                try:
                    if isinstance(coords, list) and len(coords) == 4 and all(type(v) is int for v in coords):
                        self.bounds = Bounds(*coords).validate(self.image.width, self.image.height)
                except ValueError:
                    self.bounds = None
        if self.bounds:
            self._configure(self.hint, text=self.t('Map bounds are available. Save your icon sample in One-time setup to enable automatic use.'))
            self._status(self.t("Image received — no icon profile. In Setup, choose '3. Save your icon sample'."), level="warning")
            self._start_recognition(zone_only=True, quiet=True)
        else:
            self.calibrate()
            self._status(self.t("Image received — setup required: select the map's top-left and bottom-right corners, then save your icon sample in Setup."), level="warning")
        self.draw()

    def capture(self):
        if self.capture_busy:
            self._status(self.t("Capture is already in progress…"), level="warning")
            return
        self.capture_busy = True
        self._clear_results(clear_zone=True)
        self._status(self.t("Capturing Monitor {number}…", number=self.capture_index + 1))
        self.draw()
        self.root.update_idletasks()
        try:
            current = windows.monitors()
            if current != self.displays:
                if not current:
                    raise RuntimeError(self.t('No display is available'))
                capture_name = self.displays[self.capture_index].name
                output_name = self.displays[self.target_index].name
                self.displays = current
                self.capture_index = next((i for i, m in enumerate(current) if m.name == capture_name), 0)
                self.target_index = next((i for i, m in enumerate(current) if m.name == output_name), 0)
                for choice, index in [(self.capture_choice, self.capture_index), (self.output_choice, self.target_index)]:
                    choice.configure(values=self._display_names())
                    choice.current(index)
                self._clear_image()
                self._status(self.t('The display layout changed. Check the capture source and companion display, then capture again.'), level="warning")
                return
            if self.capture_index == self.target_index:
                self._status(self.t('The game and companion use the same display. Select a separate capture source, or import an image with a single display.'), level="warning")
                return
            # Also catch a manually dragged companion overlapping the game screen.
            monitor = self.displays[self.capture_index]
            left, top = self.root.winfo_rootx(), self.root.winfo_rooty()
            right, bottom = left+self.root.winfo_width(), top+self.root.winfo_height()
            if (left < monitor.x+monitor.width and right > monitor.x and
                    top < monitor.y+monitor.height and bottom > monitor.y):
                self._status(self.t('The companion overlaps the capture display. Move it fully to the other display, then capture again.'), level="warning")
                return
            self.set_image(windows.capture_monitor(self.capture_index, expected_name=self.displays[self.capture_index].name), captured=True)
        except Exception as error:
            self._status(self.t('Could not capture the image: {error}. Try borderless mode or import an image.', error=error), level="error")
        finally:
            self.capture_busy = False

    def import_image(self):
        filename = filedialog.askopenfilename(title=self.t('Open your map image'), filetypes=[(self.t('Image files'), "*.png *.jpg *.jpeg *.bmp *.webp"), (self.t('All files'), "*.*")])
        if not filename:
            return
        try:
            with Image.open(filename) as image:
                if image.width * image.height > 40_000_000:
                    raise ValueError(self.t('The image must not exceed 40 megapixels'))
                self.set_image(image.copy())
        except Exception as error:
            messagebox.showerror(self.t('Could not open the image'), self._detail(error), parent=self.root)

    def calibrate(self):
        if self.data.id not in self.map_data:
            self._status(self.t("Map data is unavailable for this map."), level="warning")
            return
        if self.image is None:
            self._status(self.t('First, capture or open an image of the full game map.'))
            return
        self.close_settings()
        self.mode, self.first_corner = "calibrate", None
        self._clear_results(clear_zone=True)
        self._configure(self.hint, text=self.t('Map bounds · 1/2\nClick the TOP-LEFT corner of the entire square map. The full map must be visible without zooming or panning.'))
        self._status(self.t("Map setup 1/2 — click the map's top-left corner."), level="warning")
        self.draw()

    def _click(self, event):
        if self.image is None:
            return
        ox, oy, sx, sy = self.transform
        x, y = (event.x - ox) / sx, (event.y - oy) / sy
        if self.mode == "calibrate":
            if not (0 <= x < self.image.width and 0 <= y < self.image.height):
                return
            point = (int(x), int(y))
            if self.first_corner is None:
                self.first_corner = point
                self._configure(self.hint, text=self.t('Map bounds · 2/2\nNow click the BOTTOM-RIGHT corner of the full map.'))
                self._status(self.t("Map setup 2/2 — click the map's bottom-right corner."), level="warning")
                self.draw()
                return
            try:
                bounds = Bounds(*self.first_corner, *point).validate(self.image.width, self.image.height)
            except ValueError:
                self.first_corner = None
                self._configure(self.hint, text=self.t("Invalid bounds. Select the square map's top-left and bottom-right corners again."))
                self._status(self.t("Invalid bounds. Select the square map's top-left and bottom-right corners again."), level="warning")
                self.draw()
                return
            self.bounds, self.mode = bounds, "position"
            if self.image_is_capture:
                records = self.settings.get("calibrations", {})
                if not isinstance(records, dict):
                    records = {}
                records[self._calibration_key()] = list(bounds.as_box())
                self.settings["calibrations"] = records
                self._persist()
            self._configure(self.hint, text=self.t('Map bounds are ready. Select Save your icon sample in One-time setup.'))
            self._status(self.t("Map bounds ready — save your icon sample in Setup."), level="warning")
            self._start_recognition(zone_only=True, quiet=True)
            self.draw()
            return
        registration = self._active_registration()
        if registration is not None and self.mode == "position":
            left, top, right, bottom = self._view_box()
            position = registration.image_point_to_map(x+left, y+top)
            if position is not None:
                self._clear_results()
                self._set_position(position)
                if self.safe_zone is None:
                    self._start_recognition(zone_only=True, quiet=True)
            return
        if self.bounds is None:
            return
        view_left, view_top, view_right, view_bottom = self._view_box()
        if not (0 <= x < view_right-view_left and 0 <= y < view_bottom-view_top):
            return
        full_point = (int(x+view_left), int(y+view_top))
        if not (self.bounds.left <= full_point[0] < self.bounds.right
                and self.bounds.top <= full_point[1] < self.bounds.bottom):
            return
        if self.mode == "marker_box":
            if self.first_corner is None:
                self.first_corner = full_point
                self._configure(self.hint, text=self.t('Icon sample · 2/3\nClick the bottom-right corner of the small box around the icon.'))
                self._status(self.t("Icon setup 2/3 — click the icon box's bottom-right corner."), level="warning")
            else:
                left, top = self.first_corner
                right, bottom = full_point
                if not (7 <= right-left <= 90 and 7 <= bottom-top <= 90):
                    self.first_corner = None
                    self._configure(self.hint, text=self.t('Select a tight 7–90 pixel box around the icon. Start again at its top-left corner.'))
                    self._status(self.t('Select a tight 7–90 pixel box around the icon. Start again at its top-left corner.'), level="warning")
                else:
                    self.marker_box, self.mode = (left, top, right, bottom), "marker_seed"
                    self._configure(self.hint, text=self.t("Icon sample · 3/3\nClick a clear, solid-color part of your icon INSIDE the selected box. The profile's map reference will be saved locally."))
                    self._status(self.t("Icon setup 3/3 — click a solid-color icon pixel inside the box."), level="warning")
            self.draw()
            return
        if self.mode == "marker_seed":
            left, top, right, bottom = self.marker_box
            if not (left <= full_point[0] < right and top <= full_point[1] < bottom):
                self._status(self.t("Click inside the selected icon box."), level="warning")
                return
            try:
                self._status(self.t("Training icon profile…"))
                self.root.update_idletasks()
                profile = create_profile(self.image, self.bounds, self.marker_box, full_point, self.data.id)
                result = recognize(self.image, profile, self.data.id)
                if result.position is None:
                    raise ValueError(self.t('The training image has no unique match either: {reason}', reason=result.reason))
                if not self.smoke_test:
                    profile.save(self._profile_directory())
                self.profile = profile
                self.mode, self.first_corner, self.marker_box = "position", None, None
                self._show_profile()
                if getattr(self, "view_context", "live") == "live":
                    position = result.position
                    registration = self._active_registration()
                    if registration is not None:
                        b = profile.bounds
                        position = registration.image_point_to_map(
                            b.left + position[0]*(b.right-b.left),
                            b.top + position[1]*(b.bottom-b.top))
                    if position is not None:
                        self._set_position(position, automatic=True, score=result.score)
                else:
                    self._clear_results()
                self._status(self.t('Icon profile saved. The next Ctrl+Shift+B updates automatically without another click.'), level="success")
                self._start_recognition(zone_only=True, quiet=True)
            except (OSError, ValueError, TypeError) as error:
                self._status(self.t('Could not create the profile: {error}', error=error), level="error")
            return
        # Manual selection remains available for setup/debugging only.
        self._clear_results()
        self._set_position(self.bounds.normalized(*full_point))
        if self.safe_zone is None:
            self._start_recognition(zone_only=True, quiet=True)

    def _set_position(self, position, *, automatic=False, score=0.0,
                      method="trained-icon", heading_degrees=None):
        self.position = position
        self.position_method = method if automatic else "manual"
        self.position_score = score if automatic else 0.
        self.view_heading_degrees = heading_degrees if method == "view-cone" and automatic else None
        self._render_results()
        self._configure(self.hint, text=self.t(
            "Visible basements are projected onto the registered map; off-screen points stay hidden. Gold 1–3 use the detected circle first, then distance.\nRefresh: open the game map → Ctrl+Shift+B.") if self._active_registration() is not None else
            self.t("All basements are marked. Gold 1–3 are priority targets: inside the detected white circle first, then nearest. If the circle is unknown, ranking uses distance only.\nRefresh: open the game map → Ctrl+Shift+B."))
        self._status(self.t('View cone estimate · approximate straight-line distances') if automatic and method == "view-cone" else
                     self.t('Automatic icon match · {score:.2f} similarity · approximate straight-line distances', score=score) if automatic
                        else self.t("Manual check position · a new capture clears this position") if self._active_registration() is not None
                        else self.t('Manual check position · the hotkey updates automatically using the icon profile'), level="success")
        self.draw()

    def draw(self):
        from .map_renderer import draw_map
        self._refresh_presentation()
        draw_map(self)

    def import_data(self):
        filename = filedialog.askopenfilename(title=self.t('Normalized map data'), filetypes=[(self.t("Map JSON"), "*.json")])
        if not filename:
            return
        try:
            data = MapData.load(Path(filename))
            self.map_data[data.id] = data
            self._local_map_ids.add(data.id)
            self._local_map_files[data.id] = str(Path(filename).resolve())
            self.settings["local_map_files"] = dict(self._local_map_files)
            self._persist()
            self.data = data
            self._configure(self.map_label, text=data.name)
            self._configure(self.data_label, text=self.t('{count} imported points · check the source', count=len(data.points)))
            self._clear_image()
            self._load_profile()
            self._status(self.t('{name} · {count} points loaded. Open a new image and select the map bounds.', name=data.name, count=len(data.points)))
        except (OSError, ValueError, TypeError) as error:
            messagebox.showerror(self.t('Invalid map data'), self._detail(error), parent=self.root)

    def export_data(self):
        filename = filedialog.asksaveasfilename(title=self.t('Export map data'), defaultextension=".json", filetypes=[(self.t("Map JSON"), "*.json")])
        if not filename:
            return
        try:
            Path(filename).write_text(json.dumps(self.data.to_dict(), indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
            self._status(self.t('Map data exported with source attribution.'))
        except OSError as error:
            messagebox.showerror(self.t('Export failed'), self._detail(error), parent=self.root)

    def launch_game(self):
        try:
            windows.launch_pubg()
            self._status(self.t('The PUBG launch request was passed to Steam.'))
        except (OSError, RuntimeError) as error:
            self._status(self.t('Could not launch Steam: {error}', error=error))

    def help(self):
        guide = "\n\n".join(self.t(paragraph) for paragraph in (
            "In Settings > Advanced, load your local full-map reference catalog and matching point data. Open the game map and select Refresh map or press Ctrl+Shift+B. Unknown maps and off-screen rooms are withheld.",
            "A unique viewing cone can estimate your position without an icon sample. The cyan YOU marker is an estimate, not verified identity. For replay or spectator images, enable Replay / observer image in Settings > General to disable automatic estimates.",
            "City names may give an optional text hint after map registration fails. A text hint does not place points: zoom out and capture again. Windows OCR may be unavailable on another computer.",
            "Distances are approximate straight-line estimates. Circle priority can be unavailable on clipped or uncertain maps. Refresh after movement or a circle change. Without a catalog, the older fixed-layout icon setup remains available. Game reference images stay local."))
        messagebox.showinfo(self.t('Usage · v{version}', version=__version__), guide, parent=self.root)

    def _tick(self):
        if self.closed:
            return
        while not self.events.empty():
            event = self.events.get()
            if event == "capture":
                self.hotkey_receipt_count += 1
                self.hotkey_receipt_at = datetime.now()
                self._update_hotkey_feedback()
                self.capture()
            elif isinstance(event, tuple) and event[0] == "recognized":
                self._accept_recognition(event[1], event[2], event[3] if len(event) > 3 else None)
            elif isinstance(event, tuple) and event[0] == "registered":
                self._accept_registration(*event[1:])
            elif isinstance(event, tuple) and event[0] == "map_update":
                self._accept_map_update(event[1], event[2])
        if self.hotkey and self.hotkey.ready.is_set():
            if self.hotkey.error:
                self.hotkey_failure = self.hotkey.error
                self.hotkey_registration = "failed"
                self._status(self.t('The hotkey is inactive: {error}', error=self.hotkey.error), level="error")
                self.hotkey.error = None
            elif self.hotkey_registration != "failed":
                self.hotkey_registration = "ready"
        self._update_hotkey_feedback()
        self._update_age()
        if getattr(self, "map_update_client", None) is not None:
            self._check_map_updates()
        self.root.after(100, self._tick)

    def _update_age(self):
        if self.captured_at is not None and self.captured_monotonic is not None:
            age = max(0, int(time.monotonic()-self.captured_monotonic))
            text = (self.t('Captured: {time} · {age}s ago', time=self.captured_at.strftime('%H:%M:%S'), age=age) if self.image_is_capture
                    else self.t("Imported: {time} · {age}s ago\nThe image's capture time is unknown.", time=self.captured_at.strftime('%H:%M:%S'), age=age))
            if self.position is None:
                text += self.t(' · no position')
            if age >= 60:
                text += self.t('\nOutdated image · capture again in game!')
            self._configure(self.age_label, text=text, fg=GOLD if age >= 60 else MUTED)
        else:
            self._configure(self.age_label, text=self.t('No position selected yet.'), fg=MUTED)
        self._refresh_presentation()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.recognition_id += 1
        if hasattr(self, "map_update_stop"):
            self.map_update_stop.set()
            self.map_update_token += 1
        if getattr(self, "map_update_future", None) is not None:
            self.map_update_future.cancel()
        if hasattr(self, "map_update_executor"):
            self.map_update_executor.shutdown(wait=False, cancel_futures=True)
        if self.hotkey:
            self.hotkey.close()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()


def _smoke(app: Companion):
    # Synthetic fixture only: no screenshots, no game, no persistent settings.
    assert app.language == "en" and app.tabs.tab(1, "text") == "Advanced", "English is not the default"
    original_path, original_smoke = app.settings_path, app.smoke_test
    try:
        with tempfile.TemporaryDirectory() as temporary:
            app.settings_path = Path(temporary) / "settings.json"
            app.smoke_test = False
            app.language_choice.set("Magyar")
            app._language_changed()
            assert read_preferences(app.settings_path).get("language") == "hu", "Language was not saved"
            assert app.tabs.tab(0, "text") == "Általános", "Tabs did not translate"
            assert "Készen áll" in app.status.get(), "Existing status did not translate"
            for diagnostic in ("Map bounds must be inside the image",
                               "The selected display is no longer available. Refresh the display list.",
                               "Invalid mask.png format, mode, or dimensions"):
                assert app._detail(diagnostic) != diagnostic, "App-owned diagnostic did not translate"
    finally:
        app.settings_path, app.smoke_test = original_path, original_smoke
    app.language_choice.set("English")
    app._language_changed()
    # Simulate a queued hotkey receipt without registering or sending a key.
    original_capture = app.capture
    received = []
    foreground = windows.foreground_window()
    try:
        app.capture = lambda: received.append(True)
        app.events.put("capture")
        app._tick()
        assert received and app.hotkey_receipt_count == 1 and app.hotkey_receipt_at is not None
        assert "received: 1" in app.hotkey_receipt_label.cget("text"), "Hotkey receipt is not visible"
        assert windows.foreground_window() == foreground, "Hotkey receipt changed foreground focus"
    finally:
        app.capture = original_capture
    class FailedHotkey:
        class ready:
            @staticmethod
            def is_set():
                return True
        error = "Synthetic registration failure"
    try:
        app.hotkey = FailedHotkey()
        app._tick()
        assert app.hotkey.error is None, "Registration error was not consumed"
        app._tick()
        assert app.hotkey_registration == "failed", "Registration failure did not persist"
        assert "unavailable" in app.hotkey_state_label.cget("text"), "Registration failure is not visible"
    finally:
        app.hotkey = None
        app.hotkey_registration, app.hotkey_failure = "disabled", None
        app._update_hotkey_feedback()
    image = Image.new("RGB", (1000, 800), "#243442")
    texture = Image.effect_noise((700, 700), 45).point(lambda v: v//2).convert("RGB")
    image.paste(texture, (100, 50))
    base = image.copy()
    def marker(target, x, y):
        draw = ImageDraw.Draw(target)
        draw.polygon([(x, y-20), (x+20, y), (x+10, y), (x+10, y+20),
                      (x-10, y+20), (x-10, y), (x-20, y)], fill=(40, 240, 140))
    marker(image, 420, 400)
    app.set_image(image)
    assert "setup required" in app.status.get(), "Missing setup is not prominent"
    app.root.update()
    class Event:
        pass
    def click(x, y):
        ox, oy, sx, sy = app.transform
        left, top, _, _ = app._view_box()
        event = Event()
        event.x, event.y = ox+(x-left)*sx, oy+(y-top)*sy
        app._click(event)
        app.root.update()
    click(100, 50)
    assert "Map setup 2/2" in app.status.get(), "Map setup banner did not advance"
    corner = app.first_corner
    app._apply_language("hu")
    assert "Keret kijelölése" in app.hint.cget("text") and app.first_corner == corner
    app._apply_language("en")
    assert "Map bounds" in app.hint.cget("text"), "Active setup step did not translate back"
    click(800, 750)
    assert app.bounds is not None, "Calibration failed"
    assert "Map bounds ready" in app.status.get(), "Map setup banner retained an obsolete step"
    click(350, 350)
    assert app.position is not None and len(app.results.get_children()) == len(app.data.points), "Target list UI failed"
    canvas_text = [app.canvas.itemcget(item, "text") for item in app.canvas.find_all()
                   if app.canvas.type(item) == "text"]
    distance_text = [app.canvas.itemcget(item, "text") for item in app.canvas.find_withtag("poi_distance")
                     if app.canvas.type(item) == "text"]
    assert len(distance_text) == 3 and all(text.endswith((" m", " km")) for text in distance_text), "Nearest distance labels are absent"
    position, bounds, generation = app.position, app.bounds, app.recognition_id
    first = app.results.get_children()[0]
    assert "Basement" in app.results.item(first, "values")[0], "Default point names are not English"
    app._apply_language("hu")
    first = app.results.get_children()[0]
    assert "Pince" in app.results.item(first, "values")[0], "Result names did not translate"
    assert (app.position, app.bounds, app.recognition_id) == (position, bounds, generation), "Language changed recognition state"
    app._apply_language("en")
    assert not app.settings.get("calibrations"), "Imported calibration polluted capture settings"
    # Train the profile through the setup UI once.
    app.begin_marker_setup()
    assert "Icon setup 1/3" in app.status.get(), "Icon setup banner is absent"
    click(397, 377)
    assert "Icon setup 2/3" in app.status.get(), "Icon setup banner did not advance"
    click(443, 423)
    assert "Icon setup 3/3" in app.status.get(), "Icon seed banner is absent"
    click(420, 400)
    assert app.profile is not None, f"Profile setup failed: {app.status.get()}"
    app.set_image(Image.new("RGB", (1001, 800)))
    assert app.position is None and "Profile size mismatch" in app.status.get(), "Profile mismatch is not explicit"
    fresh = base.copy()
    marker(fresh, 600, 300)
    foreground = windows.foreground_window()
    app.set_image(fresh)
    app._apply_language("hu")
    assert app.position is None and len(app.results.get_children()) == len(app.data.points), "New image hid basement data"
    assert all(app.results.item(item, "values")[-1] == "—" for item in app.results.get_children()), "New image retained old distances"
    deadline = time.monotonic()+15
    while app.position is None and time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    assert app.position is not None, f"Automatic worker failed: {app.status.get()}"
    assert abs(app.position[0]-500/700) < .04 and abs(app.position[1]-250/700) < .04
    assert len(app.results.get_children()) == len(app.data.points), "Automatic all-target list absent"
    assert "Automatikus ikonminta-egyezés" in app.status.get(), "Worker result used an outdated language"
    app._apply_language("en")
    assert "Automatic icon match" in app.status.get(), "Current result did not translate back"
    assert windows.foreground_window() == foreground, "Automatic recognition changed the foreground window"
    # Circle classification shares this snapshot, but does not require an icon.
    ring_frame = fresh.copy()
    ImageDraw.Draw(ring_frame).ellipse((240, 190, 660, 610), outline="white", width=3)
    app.set_image(ring_frame)
    deadline = time.monotonic()+15
    while not app.future.done() and time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    app._tick()
    assert app.position is not None and app.safe_zone is not None, f"Circle analysis failed: {app.zone_reason}"
    assert abs(app.safe_zone.center_x-.5) < .03 and abs(app.safe_zone.radius-.3) < .03
    assert len(app.canvas.find_withtag("basement")) == len(app.data.points), "Not all basements are marked"
    assert len(app.canvas.find_withtag("safe_zone")) == 2, "Detected circle is not displayed"
    target_rows = [app.results.item(item, "values") for item in app.results.get_children()]
    inside_count = sum(app.safe_zone.contains(point.x, point.y) for point in app.data.points)
    assert [row[1] for row in target_rows] == ["IN"]*inside_count+["OUT"]*(len(target_rows)-inside_count)
    zone = app.safe_zone
    app._apply_language("hu")
    assert "kör" in app.zone_label.cget("text").lower() and app.safe_zone == zone
    app._apply_language("en")
    # An older worker result must not overwrite a newer snapshot/selection.
    current = app.position
    app._accept_recognition(app.recognition_id-1, Recognition(position=(0, 0), score=1.0, reason="stale"))
    assert app.position == current, "Stale recognition overwrote the current result"
    # No marker in the next image must leave no previous nearest locations.
    app.set_image(base)
    assert app.safe_zone is None, "New image retained the old circle"
    app._accept_recognition(app.recognition_id-1, None, ZoneDetection(zone, 1., "stale circle"))
    assert app.safe_zone is None, "Old analysis restored a stale circle"
    deadline = time.monotonic()+15
    while not app.future.done() and time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    app._tick()
    assert app.position is None and len(app.results.get_children()) == len(app.data.points), "Failed recognition hid basement data"
    assert all(app.results.item(item, "values")[-1] == "—" for item in app.results.get_children()), "Failed recognition retained old distances"
    app.close()
    print("GUI smoke passed: English default, saved/live EN-HU switching, hotkey feedback, setup warnings, automatic marker, all basements, circle-priority targets, stale position/circle reset, focus preserved")


def run(*, launch_game=False, smoke_test=False, settings_path=None):
    windows.enable_dpi_awareness()
    root = tk.Tk()
    app = Companion(root, settings_path=Path(settings_path) if settings_path else None, smoke_test=smoke_test)
    if smoke_test:
        try:
            _smoke(app)
        finally:
            if not app.closed:
                app.close()
        return
    if launch_game:
        root.after(400, app.launch_game)
    root.mainloop()
