"""Small, public Windows integrations for the standalone companion.

This module reads the display configuration and process *names*, captures a
screen on demand, and registers a keyboard shortcut.  It does not open a game
process, inject code, read memory, or inspect network traffic.  Importing it has
no side effects, and the non-Windows fallbacks allow the rest of the project to
be imported on other platforms.
"""

from __future__ import annotations

import csv
import ctypes
import io
import os
import subprocess
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PIL import Image


_IS_WINDOWS = os.name == "nt"
_DPI_LOCK = threading.Lock()
_dpi_attempted = False

# Use explicitly sized values for Win32 integers, and pointer-sized types for
# handles and message parameters.  In particular, HWND must never be c_int.
_BOOL = ctypes.c_int32
_DWORD = ctypes.c_uint32
_UINT = ctypes.c_uint32
_LONG = ctypes.c_int32
_HANDLE = ctypes.c_void_p
_WPARAM = ctypes.c_size_t
_LPARAM = ctypes.c_ssize_t


class _RECT(ctypes.Structure):
    _fields_ = [("left", _LONG), ("top", _LONG),
                ("right", _LONG), ("bottom", _LONG)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", _LONG), ("y", _LONG)]


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", _HANDLE), ("message", _UINT),
                ("wParam", _WPARAM), ("lParam", _LPARAM),
                ("time", _DWORD), ("pt", _POINT), ("lPrivate", _DWORD)]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", _DWORD), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", _DWORD),
                ("szDevice", ctypes.c_wchar * 32)]


@dataclass(frozen=True, slots=True)
class Monitor:
    """A monitor's full bounds in Windows virtual-desktop pixels.

    Coordinates may be negative when a monitor is left of or above the primary
    display.  Call :func:`enable_dpi_awareness` before creating the UI so these
    pixels agree with screenshot and window-position coordinates.
    """

    x: int
    y: int
    width: int
    height: int
    primary: bool
    name: str


def _windows_required() -> None:
    if not _IS_WINDOWS:
        raise RuntimeError("This feature is available only on Windows.")


def _user32():
    _windows_required()
    return ctypes.WinDLL("user32", use_last_error=True)


def _last_error(action: str) -> RuntimeError:
    code = ctypes.get_last_error()
    detail = ctypes.FormatError(code).strip() if code else "Unknown Windows error"
    return RuntimeError(f"{action}: {detail} (Windows error {code}).")


def enable_dpi_awareness() -> None:
    """Request per-monitor DPI awareness before the first Tk window is made.

    This is best effort: a packaged executable's manifest or the embedding
    application may already have chosen a DPI mode.  It is a no-op elsewhere.
    """
    global _dpi_attempted
    if not _IS_WINDOWS:
        return
    with _DPI_LOCK:
        if _dpi_attempted:
            return
        _dpi_attempted = True
        user32 = _user32()
        set_context = getattr(user32, "SetProcessDpiAwarenessContext", None)
        if set_context is not None:
            set_context.argtypes = [_HANDLE]
            set_context.restype = _BOOL
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2.
            if set_context(_HANDLE(-4)):
                return
            if ctypes.get_last_error() == 5:  # Already established by a manifest.
                return
        try:
            shcore = ctypes.WinDLL("shcore", use_last_error=True)
            set_awareness = shcore.SetProcessDpiAwareness
            set_awareness.argtypes = [ctypes.c_int]
            set_awareness.restype = _LONG  # HRESULT, always 32 bits.
            result = set_awareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE.
            if result in (0, -2147024891):  # S_OK or E_ACCESSDENIED (already set).
                return
        except (OSError, AttributeError):
            pass
        fallback = user32.SetProcessDPIAware
        fallback.argtypes = []
        fallback.restype = _BOOL
        fallback()


def monitors() -> list[Monitor]:
    """Return active monitors, primary first, then sorted by position and name.

    The returned list supplies indices for :func:`capture_monitor`.  An empty
    list is returned on non-Windows platforms.  Display-query errors on Windows
    raise RuntimeError, rather than silently capturing a different monitor.
    """
    if not _IS_WINDOWS:
        return []
    user32 = _user32()
    callback_type = ctypes.WINFUNCTYPE(
        _BOOL, _HANDLE, _HANDLE, ctypes.POINTER(_RECT), _LPARAM
    )
    user32.GetMonitorInfoW.argtypes = [_HANDLE, ctypes.POINTER(_MONITORINFOEXW)]
    user32.GetMonitorInfoW.restype = _BOOL
    user32.EnumDisplayMonitors.argtypes = [
        _HANDLE, ctypes.POINTER(_RECT), callback_type, _LPARAM
    ]
    user32.EnumDisplayMonitors.restype = _BOOL
    found: list[Monitor] = []
    errors: list[RuntimeError] = []

    @callback_type
    def collect(handle, _dc, _rect, _data):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetMonitorInfoW(handle, ctypes.byref(info)):
            errors.append(_last_error("Could not read display details"))
            return 0
        rect = info.rcMonitor
        found.append(Monitor(
            x=rect.left, y=rect.top,
            width=rect.right - rect.left, height=rect.bottom - rect.top,
            primary=bool(info.dwFlags & 1), name=info.szDevice,
        ))
        return 1

    success = user32.EnumDisplayMonitors(None, None, collect, 0)
    if errors:
        raise errors[0]
    if not success:
        raise _last_error("Could not enumerate displays")
    return sorted(found, key=lambda item: (not item.primary, item.x, item.y, item.name))


def capture_monitor(index: int, expected_name: str | None = None) -> Image.Image:
    """Capture exactly one monitor on demand using Pillow's public screen API.

    The selected index must come from :func:`monitors`.  Pass that monitor's
    ``name`` as ``expected_name`` so reconnecting a display or changing the
    primary monitor cannot silently capture an unrelated screen after the list
    order changes.  A stale selection is rejected before any screen is read.
    Negative coordinates are preserved; Pillow's ``all_screens=True`` uses the
    full virtual desktop.  This function never activates a window or sends game
    input; the selected display is read without changing foreground focus.
    """
    _windows_required()
    displays = monitors()
    if index < 0 or index >= len(displays):
        raise ValueError("The selected display is no longer available. Refresh the display list.")
    monitor = displays[index]
    if expected_name is not None and monitor.name != expected_name:
        raise RuntimeError("The display configuration changed. Refresh the display list and select the capture monitor again.")
    from PIL import ImageGrab

    bounds = (monitor.x, monitor.y,
              monitor.x + monitor.width, monitor.y + monitor.height)
    try:
        return ImageGrab.grab(bbox=bounds, all_screens=True)
    except OSError as exc:
        raise RuntimeError(f"Could not capture the selected display: {exc}") from exc


def foreground_window() -> int | None:
    """Read the current foreground HWND without changing window focus.

    The pointer-sized handle can be compared immediately before and after an
    on-demand capture/matching/UI-update cycle in a manual focus regression
    check.  None means Windows has no foreground window at that instant, or
    this platform is not Windows.  No window title or process data is queried.
    """
    if not _IS_WINDOWS:
        return None
    user32 = _user32()
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = _HANDLE
    handle = user32.GetForegroundWindow()
    return int(handle) if handle else None


def launch_pubg() -> None:
    """Ask the installed Steam client to launch PUBG, without waiting for it."""
    if not _IS_WINDOWS:
        raise RuntimeError("Launching PUBG through Steam is available only on Windows.")
    try:
        os.startfile("steam://rungameid/578080")
    except OSError as exc:
        raise RuntimeError("Could not open Steam. Install Steam and PUBG, then try again.") from exc


def pubg_running() -> bool:
    """Check for TslGame.exe by name with tasklist; never open the process.

    Missing tasklist, timeouts, and non-Windows systems return False.  This is a
    launcher/status convenience, not a guarantee that a playable match exists.
    """
    if not _IS_WINDOWS:
        return False
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq TslGame.exe", "/FO", "CSV", "/NH"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, errors="replace", check=False, timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False
    return any(row and row[0].strip().casefold() == "tslgame.exe"
               for row in csv.reader(io.StringIO(result.stdout)))


def move_window(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    """Position a native top-level window, including on negative coordinates.

    A Tk ``winfo_id()`` can refer to a child; GetAncestor resolves its containing
    top-level window.  SetWindowPos explicitly preserves foreground activation
    and stacking order, including when recovering from a display change.
    Dimensions must be positive.
    """
    _windows_required()
    if width <= 0 or height <= 0:
        raise ValueError("Window width and height must be positive.")
    user32 = _user32()
    user32.GetAncestor.argtypes = [_HANDLE, _UINT]
    user32.GetAncestor.restype = _HANDLE
    user32.SetWindowPos.argtypes = [
        _HANDLE, _HANDLE, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, _UINT
    ]
    user32.SetWindowPos.restype = _BOOL
    window = _HANDLE(hwnd)
    top_level = user32.GetAncestor(window, 2)  # GA_ROOT.
    flags = 0x0004 | 0x0010 | 0x0200  # NOZORDER, NOACTIVATE, NOOWNERZORDER.
    if not user32.SetWindowPos(top_level or window, None, x, y, width, height, flags):
        raise _last_error("Could not position the companion window")


class Hotkey:
    """Register Ctrl+Shift+B on a dedicated Windows message-loop thread.

    ``callback`` runs on that worker thread.  Supply a callback that only puts
    an event into a thread-safe queue; drain that queue from Tk's main thread.
    Never pass a callback that directly operates Tk widgets.

    ``start()`` is non-blocking.  ``ready`` becomes set after registration is
    attempted; ``error`` is None on success or a human-readable failure message.
    Call ``close()`` when the application exits.  A Hotkey is started only once.
    """

    _ID = 0xBC01
    _WM_HOTKEY = 0x0312
    _WM_QUIT = 0x0012

    def __init__(self, callback: Callable[[], None]):
        self.callback = callback
        self.error: str | None = None
        self.ready = threading.Event()
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._thread_id: int | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None or self.ready.is_set():
                return
            if self._closed.is_set():
                self.error = "The keyboard shortcut has already been closed."
                self.ready.set()
                return
            if not _IS_WINDOWS:
                self.error = "The global keyboard shortcut is available only on Windows."
                self.ready.set()
                return
            self._thread = threading.Thread(
                target=self._run, name="lootlizard-hotkey", daemon=True
            )
            self._thread.start()

    def _run(self) -> None:
        registered = False
        user32 = None
        try:
            user32 = _user32()
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentThreadId.argtypes = []
            kernel32.GetCurrentThreadId.restype = _DWORD
            user32.PeekMessageW.argtypes = [
                ctypes.POINTER(_MSG), _HANDLE, _UINT, _UINT, _UINT
            ]
            user32.PeekMessageW.restype = _BOOL
            user32.GetMessageW.argtypes = [ctypes.POINTER(_MSG), _HANDLE, _UINT, _UINT]
            user32.GetMessageW.restype = _BOOL
            user32.RegisterHotKey.argtypes = [_HANDLE, ctypes.c_int, _UINT, _UINT]
            user32.RegisterHotKey.restype = _BOOL
            user32.UnregisterHotKey.argtypes = [_HANDLE, ctypes.c_int]
            user32.UnregisterHotKey.restype = _BOOL
            message = _MSG()
            # Explicitly create this thread's queue before publishing its ID;
            # close() can then safely post WM_QUIT even during registration.
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
            with self._lock:
                self._thread_id = int(kernel32.GetCurrentThreadId())
            if self._closed.is_set():
                return
            modifiers = 0x0002 | 0x0004 | 0x4000  # CONTROL, SHIFT, NOREPEAT.
            if not user32.RegisterHotKey(None, self._ID, modifiers, ord("B")):
                self.error = str(_last_error(
                    "Could not register Ctrl+Shift+B; another application may already use it"
                ))
                return
            registered = True
            self.ready.set()
            while not self._closed.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result == -1:
                    self.error = str(_last_error("The keyboard shortcut message loop failed"))
                    break
                if result == 0:
                    break
                if message.message == self._WM_HOTKEY and message.wParam == self._ID:
                    if not self._closed.is_set():
                        try:
                            self.callback()
                        except Exception as exc:
                            self.error = f"The keyboard shortcut callback failed: {exc}"
        except Exception as exc:
            self.error = f"Could not start the keyboard shortcut: {exc}"
        finally:
            if registered and user32 is not None:
                user32.UnregisterHotKey(None, self._ID)
            with self._lock:
                self._thread_id = None
            self.ready.set()

    def close(self) -> None:
        """Stop the message loop and release the shortcut; safe to call twice."""
        self._closed.set()
        with self._lock:
            thread_id = self._thread_id
            thread = self._thread
        if thread_id is not None and _IS_WINDOWS:
            user32 = _user32()
            user32.PostThreadMessageW.argtypes = [_DWORD, _UINT, _WPARAM, _LPARAM]
            user32.PostThreadMessageW.restype = _BOOL
            user32.PostThreadMessageW(thread_id, self._WM_QUIT, 0, 0)
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
