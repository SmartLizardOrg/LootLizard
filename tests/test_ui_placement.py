"""Placement uses absolute virtual-desktop pixels, never Tk negative offsets."""

from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lootlizard.app import Companion
from lootlizard.ui_shell import settings_placement


class SettingsPlacementTests(unittest.TestCase):
    def setUp(self):
        self.displays = [SimpleNamespace(x=0, y=0, width=2560, height=1440),
                         SimpleNamespace(x=-3840, y=-120, width=3840, height=2160)]

    def test_negative_monitor_contains_all_settings_edges(self):
        x, y, width, height = settings_placement((-3720, 90, 1440, 960), self.displays, 1)
        self.assertLess(x, 0)
        self.assertGreaterEqual(x, -3840)
        self.assertGreaterEqual(y, -120)
        self.assertLessEqual(x+width, 0)
        self.assertLessEqual(y+height, 2040)
        self.assertEqual((width, height), (740, 790))

    def test_native_call_receives_absolute_negative_x_without_tk_geometry(self):
        app = Companion.__new__(Companion)
        app.displays, app.target_index = self.displays, 1
        app.root = Mock()
        app.root.winfo_rootx.return_value = -3720
        app.root.winfo_rooty.return_value = 90
        app.root.winfo_width.return_value = 1440
        app.root.winfo_height.return_value = 960
        class Settings:
            def __init__(self):
                self.update_idletasks = Mock()
                self.winfo_id = Mock(return_value=42)
                self.deiconify, self.lift = Mock(), Mock()
        app.settings_window = Settings()
        with patch("lootlizard.app.tk.Toplevel", Settings), patch("lootlizard.app.windows.move_window") as move:
            app.open_settings()
        move.assert_called_once_with(42, -3370, 175, 740, 790)
        app.settings_window.deiconify.assert_called_once()

    def test_primary_edge_and_offscreen_root_clamp_to_target_monitor(self):
        for root_bounds in ((2300, 1300, 900, 700), (9000, 9000, 900, 700)):
            x, y, width, height = settings_placement(root_bounds, self.displays, 0)
            self.assertGreaterEqual(x, 0)
            self.assertGreaterEqual(y, 0)
            self.assertLessEqual(x+width, 2560)
            self.assertLessEqual(y+height, 1440)


if __name__ == "__main__":
    unittest.main()
