"""Native Tk shell: a quiet map workspace and an explicit settings window."""

import tkinter as tk
from tkinter import ttk

from .i18n import LANGUAGES

BG = "#0d131b"
PANEL = "#151e29"
CARD = "#1c2835"
LINE = "#2b3948"
TEXT = "#eef3f8"
MUTED = "#9aabba"
AMBER = "#ffbc48"
CYAN = "#64dce8"


def settings_placement(window_bounds, displays, target_index):
    """Return absolute desktop pixels, including monitors left of the primary."""
    left, top, window_width, window_height = window_bounds
    center_x, center_y = left + window_width // 2, top + window_height // 2
    monitor = next((item for item in displays if item.x <= center_x < item.x+item.width
                    and item.y <= center_y < item.y+item.height), displays[target_index])
    width, height = min(740, monitor.width-60), min(790, monitor.height-90)
    x = max(monitor.x+20, min(center_x-width//2, monitor.x+monitor.width-width-20))
    y = max(monitor.y+20, min(center_y-height//2, monitor.y+monitor.height-height-50))
    return x, y, width, height


def build_ui(app):
    root, t = app.root, app.t
    root.title("LootLizard")
    root.configure(background=BG)
    root.minsize(1080, 700)
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 11))
    style.configure("TButton", font=("Segoe UI", 11), padding=(14, 9), background=CARD, foreground=TEXT, borderwidth=0)
    style.map("TButton", background=[("active", "#2d4052")])
    style.configure("Accent.TButton", background=AMBER, foreground="#151a21", font=("Segoe UI", 11, "bold"))
    style.map("Accent.TButton", background=[("active", "#ffd17a")])
    style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=TEXT, padding=7)
    style.map("TCombobox", fieldbackground=[("readonly", CARD)], foreground=[("readonly", TEXT)])
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", "#354330")
    style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("Segoe UI", 11))
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=CARD, foreground=MUTED, padding=(20, 12), font=("Segoe UI", 11))
    style.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", AMBER)])
    style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT,
                    rowheight=51, borderwidth=0, font=("Segoe UI", 11))
    style.configure("Treeview.Heading", background=PANEL, foreground=MUTED,
                    font=("Segoe UI", 9, "bold"), padding=(6, 9), relief="flat")
    style.map("Treeview", background=[("selected", "#354330")], foreground=[("selected", "#fff0d0")])

    def label(parent, text="", *, color=TEXT, size=11, bold=False, bg=BG, **kwargs):
        return app._widget(tk.Label, parent, text=text, bg=bg, fg=color, anchor="w",
                           font=("Segoe UI", size, "bold" if bold else "normal"), **kwargs)

    top = tk.Frame(root, bg=BG, height=66)
    top.pack(fill="x", padx=22, pady=(12, 10))
    label(top, "LOOTLIZARD", color=AMBER, size=16, bold=True).pack(side="left")
    app._widget(ttk.Button, top, text=t("Settings"), command=app.open_settings).pack(side="right")
    app._widget(ttk.Button, top, text=t("Open image…"), command=app.import_image).pack(side="right", padx=(0, 8))
    app._widget(ttk.Button, top, text=t("Refresh map"), command=app.capture, style="Accent.TButton").pack(side="right", padx=(14, 8))
    label(top, "Ctrl+Shift+B", color=MUTED, size=10).pack(side="right", padx=(10, 0))

    body = tk.Frame(root, bg=BG)
    body.pack(fill="both", expand=True, padx=22, pady=(0, 18))
    body.columnconfigure(0, weight=1)
    body.columnconfigure(1, weight=0, minsize=420)
    body.rowconfigure(1, weight=1)
    map_head = tk.Frame(body, bg=BG)
    map_head.grid(row=0, column=0, sticky="ew", padx=(0, 18), pady=(0, 10))
    app.summary_map_label = label(map_head, t("Waiting for a map"), size=19, bold=True)
    app.summary_map_label.pack(side="left")
    app.freshness_label = label(map_head, "", color=MUTED, size=10)
    app.freshness_label.pack(side="right")
    app.canvas = tk.Canvas(body, bg="#080e15", highlightthickness=1, highlightbackground=LINE, cursor="arrow")
    app.canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 18))
    app.canvas.bind("<Configure>", lambda event: app.draw())

    side = tk.Frame(body, bg=PANEL, width=420, padx=18, pady=18)
    side.grid(row=0, column=1, rowspan=2, sticky="nsew")
    side.grid_propagate(False)
    side.columnconfigure(0, weight=1)
    side.rowconfigure(9, weight=1)
    label(side, t("DESTINATIONS"), color=MUTED, size=10, bold=True, bg=PANEL).grid(row=0, column=0, sticky="ew")
    app.main_status_label = label(side, "", color=TEXT, size=17, bold=True, bg=PANEL, wraplength=380, justify="left")
    app.main_status_label.grid(row=1, column=0, sticky="ew", pady=(10, 5))
    app.main_detail_label = label(side, "", color=MUTED, size=11, bg=PANEL, wraplength=380, justify="left")
    app.main_detail_label.grid(row=2, column=0, sticky="ew", pady=(0, 15))
    chips = tk.Frame(side, bg=PANEL)
    chips.grid(row=3, column=0, sticky="ew", pady=(0, 18))
    app.room_count_label = label(chips, "", color=AMBER, size=11, bold=True, bg=PANEL)
    app.room_count_label.pack(side="left")
    app.circle_badge_label = label(chips, "", color=MUTED, size=10, bg=PANEL)
    app.circle_badge_label.pack(side="right")
    selected = tk.Frame(side, bg=CARD, padx=14, pady=13)
    selected.grid(row=4, column=0, sticky="ew", pady=(0, 20))
    app.selection_title_label = label(selected, "", color=AMBER, size=14, bold=True, bg=CARD, wraplength=345)
    app.selection_title_label.pack(fill="x")
    app.selection_detail_label = label(selected, "", color=TEXT, size=11, bg=CARD, wraplength=345)
    app.selection_detail_label.pack(fill="x", pady=(6, 0))
    label(side, t("ALL ROOMS"), color=MUTED, size=10, bold=True, bg=PANEL).grid(row=5, column=0, sticky="ew")
    label(side, t("Inside circle first · straight-line distance"), color=MUTED, size=9, bg=PANEL).grid(row=6, column=0, sticky="ew", pady=(5, 8))
    table = tk.Frame(side, bg=PANEL)
    table.grid(row=9, column=0, sticky="nsew")
    app.results = ttk.Treeview(table, columns=("name", "zone", "distance"), show="headings", selectmode="browse", height=7)
    for key, text in (("name", "Room"), ("zone", "Zone"), ("distance", "≈ m")):
        app.results.heading(key, text=t(text))
    app.results.column("name", width=180, minwidth=150, stretch=True)
    app.results.column("zone", width=55, minwidth=45, stretch=False, anchor="center")
    # Keep digits and the unit away from the native scrollbar, including bold
    # priority rows at 150% display scaling. Full names live in the detail card.
    app.results.column("distance", width=110, minwidth=100, stretch=False, anchor="center")
    scroll = ttk.Scrollbar(table, orient="vertical", command=app.results.yview)
    app.results.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    app.results.pack(side="left", fill="both", expand=True)
    app.results.tag_configure("in", foreground="#b5d8b0")
    app.results.tag_configure("out", foreground="#b5bfcb")
    app.results.tag_configure("unknown", foreground=TEXT)
    app.results.tag_configure("target", foreground=AMBER, font=("Segoe UI", 11, "bold"))
    app.results.bind("<<TreeviewSelect>>", app._table_selected)
    label(side, t("Room locations are community supplied."), color=MUTED, size=9, bg=PANEL).grid(row=10, column=0, sticky="ew", pady=(13, 0))

    settings = tk.Toplevel(root)
    settings.withdraw()
    settings.transient(root)
    settings.title(t("Settings"))
    settings.configure(background=BG)
    settings.geometry("740x790")
    settings.minsize(620, 560)
    settings.protocol("WM_DELETE_WINDOW", app.close_settings)
    app.settings_window = settings
    settings_head = tk.Frame(settings, bg=BG)
    settings_head.pack(fill="x", padx=22, pady=(18, 12))
    label(settings_head, t("Settings"), size=20, bold=True).pack(side="left")
    app._widget(ttk.Button, settings_head, text=t("Close"), command=app.close_settings).pack(side="right")
    app.tabs = ttk.Notebook(settings)
    app.tabs.pack(fill="both", expand=True, padx=22, pady=(0, 20))

    def page(title):
        frame = tk.Frame(app.tabs, bg=BG)
        view = tk.Canvas(frame, bg=BG, highlightthickness=0, yscrollincrement=25)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=view.yview)
        view.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        view.pack(side="left", fill="both", expand=True)
        content = tk.Frame(view, bg=BG, padx=4, pady=18)
        item = view.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda event: view.configure(scrollregion=view.bbox("all")))
        view.bind("<Configure>", lambda event: view.itemconfigure(item, width=event.width))
        def wheel(event):
            if event.delta:
                view.yview_scroll(-1 if event.delta > 0 else 1, "units")
            return "break"
        view.bind("<MouseWheel>", wheel)
        content.bind("<MouseWheel>", wheel)
        app.tabs.add(frame, text=t(title))
        return content, view

    general, app.game_scroll = page("General")
    advanced, app.setup_scroll = page("Advanced")
    diagnostics, _ = page("Diagnostics")
    def text(parent, message, *, color=MUTED, size=11, bold=False):
        widget = label(parent, message, color=color, size=size, bold=bold, wraplength=625, justify="left")
        widget.pack(fill="x", pady=(0, 9))
        return widget
    def section(parent, title):
        text(parent, t(title), color=TEXT, size=12, bold=True)
    def button(parent, title, command):
        widget = app._widget(ttk.Button, parent, text=t(title), command=command)
        widget.pack(fill="x", pady=(0, 8))
        return widget
    def choice(parent, title, values, current, callback):
        text(parent, t(title))
        widget = ttk.Combobox(parent, state="readonly", values=values)
        widget.current(current)
        widget.pack(fill="x", pady=(0, 20))
        widget.bind("<<ComboboxSelected>>", callback)
        return widget
    app.language_choice = choice(general, "Language", list(LANGUAGES.values()), list(LANGUAGES).index(app.language), app._language_changed)
    app.capture_choice = choice(general, "Capture source", app._display_names(), app.capture_index, app._capture_changed)
    app.output_choice = choice(general, "Companion display", app._display_names(), app.target_index, app._output_changed)
    app.marker_size_choice = choice(general, "Marker size", [t("Large"), t("Medium")], 0 if app.marker_size == "large" else 1, app._marker_size_changed)
    section(general, "Map updates")
    app.automatic_updates = tk.BooleanVar(value=app.map_updates_enabled)
    app._widget(ttk.Checkbutton, general, text=t("Automatic map updates"), variable=app.automatic_updates,
                command=app._automatic_updates_changed).pack(anchor="w", pady=(0, 8))
    app.map_update_label = text(general, t("Built-in map data"))
    button(general, "Check now", lambda: app._check_map_updates(force=True))
    app.observer_image = tk.BooleanVar(value=app.view_context == "replay")
    app._widget(ttk.Checkbutton, general, text=t("Replay / observer image"), variable=app.observer_image,
                command=app._view_context_changed).pack(anchor="w", pady=(0, 8))
    text(general, t("Enable for replay images to turn off automatic player estimates."))
    button(general, "Launch PUBG", app.launch_game)
    button(general, "Help", app.help)

    section(advanced, "Local map references")
    app.reference_label = text(advanced, t("Local map catalog disabled · fixed-layout profile mode"))
    button(advanced, "Load local map catalog…", app.import_map_catalog)
    button(advanced, "Disable map catalog", app.disable_map_catalog)
    text(advanced, t("Use your own local reference catalog for map identification and zoom/pan placement."))
    section(advanced, "Optional icon / fixed-layout setup")
    app.profile_label = text(advanced, t("No icon profile yet."), color=AMBER)
    app.marker_preview = tk.Label(advanced, bg=BG)
    app.marker_preview.pack(anchor="w", pady=(0, 8))
    app.calibrate_button = button(advanced, "Select map bounds", app.calibrate)
    button(advanced, "Save your icon sample", app.begin_marker_setup)
    text(advanced, t("Open a full, zoomed-out map before selecting bounds or saving an icon sample."))
    section(advanced, "Map data")
    app.map_label = text(advanced, app.data.name, color=TEXT)
    app.data_label = text(advanced, t("{count} community points · verify in game", count=len(app.data.points)))
    button(advanced, "Import JSON…", app.import_data)
    button(advanced, "Export…", app.export_data)

    section(diagnostics, "Current status")
    app.status = tk.StringVar()
    app.status_label = tk.Label(diagnostics, textvariable=app.status, bg=BG, fg=TEXT,
                               font=("Segoe UI", 11), wraplength=625, anchor="w", justify="left")
    app.status_label.pack(fill="x", pady=(0, 16))
    app.hotkey_state_label = text(diagnostics, "")
    app.hotkey_receipt_label = text(diagnostics, "")
    app.map_update_diagnostic_label = text(diagnostics, "")
    app.zone_label = text(diagnostics, "")
    app.age_label = text(diagnostics, "")
    app.hint = text(diagnostics, t("Open the game map, then refresh."), color=TEXT)
    app._status(t("Ready · images are captured only on request"))
    app._update_hotkey_feedback()
    app._update_map_feedback()
    app._render_results()
