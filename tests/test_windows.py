import ctypes
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from lootlizard import windows


class CaptureSelectionTests(unittest.TestCase):
    def setUp(self):
        self.primary = windows.Monitor(0, 0, 1920, 1080, True, "PRIMARY")
        self.left = windows.Monitor(-1920, -100, 1920, 1080, False, "LEFT")

    def test_capture_preserves_negative_monitor_coordinates(self):
        with patch.object(windows, "_IS_WINDOWS", True), patch.object(windows, "monitors", return_value=[self.primary, self.left]), patch("PIL.ImageGrab.grab", return_value="image") as grab:
            self.assertEqual(windows.capture_monitor(1, expected_name="LEFT"), "image")
            grab.assert_called_once_with(bbox=(-1920, -100, 0, 980), all_screens=True)

    def test_reordered_monitor_never_captures_a_different_display(self):
        with patch.object(windows, "_IS_WINDOWS", True), patch.object(windows, "monitors", return_value=[self.primary, self.left]), patch("PIL.ImageGrab.grab") as grab:
            with self.assertRaises(RuntimeError):
                windows.capture_monitor(1, expected_name="REMOVED")
            grab.assert_not_called()

    def test_missing_monitor_never_captures(self):
        with patch.object(windows, "_IS_WINDOWS", True), patch.object(windows, "monitors", return_value=[self.primary]), patch("PIL.ImageGrab.grab") as grab:
            with self.assertRaises(ValueError):
                windows.capture_monitor(1, expected_name="LEFT")
            grab.assert_not_called()


class FocusSafetyTests(unittest.TestCase):
    def test_foreground_query_preserves_a_64_bit_window_handle(self):
        handle = 0x123456789ABC
        native = SimpleNamespace(GetForegroundWindow=Mock(return_value=handle))
        with patch.object(windows, "_IS_WINDOWS", True), patch.object(windows, "_user32", return_value=native):
            self.assertEqual(windows.foreground_window(), handle)
        native.GetForegroundWindow.assert_called_once_with()
        self.assertEqual(native.GetForegroundWindow.argtypes, [])
        self.assertIs(native.GetForegroundWindow.restype, ctypes.c_void_p)

    def test_foreground_query_allows_a_temporarily_missing_foreground_window(self):
        for handle in (None, 0):
            with self.subTest(handle=handle):
                native = SimpleNamespace(GetForegroundWindow=Mock(return_value=handle))
                with patch.object(windows, "_IS_WINDOWS", True), patch.object(windows, "_user32", return_value=native):
                    self.assertIsNone(windows.foreground_window())

    def test_foreground_query_does_not_call_native_apis_on_other_platforms(self):
        with patch.object(windows, "_IS_WINDOWS", False), patch.object(windows, "_user32") as native:
            self.assertIsNone(windows.foreground_window())
        native.assert_not_called()

    def test_positioning_preserves_focus_z_order_and_negative_coordinates(self):
        child_handle = 0x123456789ABC
        top_level_handle = 0x222222222222
        # Only the two permitted positioning APIs exist on this fake.  Calling
        # an activation API such as SetForegroundWindow would fail the test.
        native = SimpleNamespace(
            GetAncestor=Mock(return_value=top_level_handle),
            SetWindowPos=Mock(return_value=1),
        )
        with patch.object(windows, "_IS_WINDOWS", True), patch.object(windows, "_user32", return_value=native):
            windows.move_window(child_handle, -3840, -900, 1180, 860)
        ancestor_args = native.GetAncestor.call_args.args
        self.assertEqual(ancestor_args[0].value, child_handle)
        self.assertEqual(ancestor_args[1], 2)  # GA_ROOT resolves Tk's child HWND.
        args = native.SetWindowPos.call_args.args
        self.assertEqual(args[:6], (top_level_handle, None, -3840, -900, 1180, 860))
        self.assertTrue(args[6] & 0x0010, "Positioning must include SWP_NOACTIVATE")
        self.assertTrue(args[6] & 0x0004, "Positioning must include SWP_NOZORDER")
        self.assertTrue(args[6] & 0x0200, "Positioning must include SWP_NOOWNERZORDER")
        self.assertIs(native.GetAncestor.restype, ctypes.c_void_p)
        self.assertEqual(native.SetWindowPos.argtypes[:2], [ctypes.c_void_p, ctypes.c_void_p])
        self.assertIs(native.SetWindowPos.restype, ctypes.c_int32)
        native.SetWindowPos.assert_called_once()

    def test_positioning_keeps_the_original_handle_when_no_ancestor_is_returned(self):
        handle = 0x123456789ABC
        native = SimpleNamespace(GetAncestor=Mock(return_value=None), SetWindowPos=Mock(return_value=1))
        with patch.object(windows, "_IS_WINDOWS", True), patch.object(windows, "_user32", return_value=native):
            windows.move_window(handle, 20, 30, 1180, 860)
        self.assertEqual(native.SetWindowPos.call_args.args[0].value, handle)


if __name__ == "__main__":
    unittest.main()
