"""Evidence/timeout/bridge contracts with OCR mocked; no installed OCR needed."""

import base64
from io import BytesIO
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

from lootlizard import map_text


def line(text, x, y, *, height=24):
    words = []
    for word in text.split():
        width = max(8, len(word)*12)
        words.append({"text": word, "bounds": [x, y, width, height]})
        x += width+8
    return {"text": text, "words": words}


def response(*lines):
    return {"ok": True, "frames": [{"lines": list(lines)}]}


class MapTextTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (1200, 900), "#284040")

    def identify(self, payload, allowed=("erangel", "taego")):
        with patch.object(map_text, "_run_bridge", return_value=payload):
            return map_text.identify_map_text(self.image, allowed)

    def test_two_distinct_separated_labels_are_support_only(self):
        result = self.identify(response(line("Georgopol", 150, 200), line("Pochinki", 650, 500)))
        self.assertEqual(result.map_id, "erangel")
        self.assertEqual(set(result.matched_labels), {"Georgopol", "Pochinki"})
        self.assertTrue(result.available)
        self.assertIn("suggests", result.reason)
        self.assertFalse(hasattr(result, "map_to_image"))
        self.assertFalse(hasattr(result, "position"))

    def test_single_city_and_duplicate_variant_do_not_qualify(self):
        payload = response(line("Novorepnoye", 200, 300))
        payload["frames"].append(payload["frames"][0])
        result = self.identify(payload)
        self.assertIsNone(result.map_id)
        self.assertEqual(result.matched_labels, ("Novorepnoye",))

    def test_shared_generic_ui_and_place_words_abstain(self):
        result = self.identify(response(line("School Prison Hospital", 100, 100),
                                        line("Terminal Palace Fishing Camp", 350, 500),
                                        line("TEAMS ALIVE TIME REPORT", 100, 650)))
        self.assertIsNone(result.map_id)
        self.assertFalse(result.matched_labels)

    def test_two_supported_maps_or_conflicting_single_label_abstain(self):
        erangel = [line("Georgopol", 100, 120), line("Pochinki", 350, 500)]
        for taego in ([line("Buk San Sa", 700, 200)],
                      [line("Buk San Sa", 700, 200), line("Kang Neung", 700, 600)]):
            with self.subTest(taego=taego):
                result = self.identify(response(*(erangel+taego)))
                self.assertIsNone(result.map_id)
                self.assertTrue("Conflicting" in result.reason or "Ambiguous" in result.reason)

    def test_allowed_map_ids_are_respected(self):
        result = self.identify(response(line("Georgopol", 100, 120), line("Pochinki", 350, 500)), ("taego",))
        self.assertIsNone(result.map_id)
        self.assertFalse(result.matched_labels)

    def test_bounded_long_label_ocr_errors_and_accents(self):
        result = self.identify(response(line("B u/qs.an;Sa", 180, 200), line("IKamg$Neung", 700, 600)))
        self.assertEqual(result.map_id, "taego")
        self.assertEqual({match.edits for match in result.matches}, {1, 2})
        result = self.identify(response(line("Gatko", 180, 200), line("Georgopxxxx", 700, 600)))
        self.assertIsNone(result.map_id)
        self.assertFalse(result.matched_labels)

    def test_nearby_labels_and_border_hud_text_do_not_qualify(self):
        for payload in (response(line("Gatka", 100, 100), line("Pochinki", 110, 110)),
                        response(line("Georgopol", 30, 0), line("Pochinki", 300, 870))):
            with self.subTest(payload=payload):
                self.assertIsNone(self.identify(payload).map_id)

    def test_distant_words_cannot_be_joined_to_invent_a_city_name(self):
        separated = line("Ho San", 100, 120)
        separated["words"][1]["bounds"][0] = 800
        result = self.identify(response(separated, line("Buk San Sa", 150, 600)))
        self.assertIsNone(result.map_id)
        self.assertNotIn("Ho San", result.matched_labels)

    def test_timeout_and_unavailable_backend_are_fail_soft(self):
        with patch.object(map_text, "_run_bridge", side_effect=subprocess.TimeoutExpired("ocr", 1)):
            result = map_text.identify_map_text(self.image, ["erangel"], timeout=30)
        self.assertIsNone(result.map_id)
        self.assertIn("timed out", result.reason)
        self.assertFalse(result.available)
        result = self.identify({"ok": False, "error": "English OCR language is not installed"})
        self.assertIsNone(result.map_id)
        self.assertIn("not installed", result.reason)

    def test_invalid_or_oversized_ocr_output_is_rejected(self):
        for payload in ({"ok": True, "frames": None},
                        {"ok": True, "frames": [{"lines": [{"words": [0]}]}]},
                        response(*[line("Gatka", 100, 100)]*1001)):
            with self.subTest(payload_type=type(payload)):
                result = self.identify(payload)
                self.assertIsNone(result.map_id)
                self.assertFalse(result.available)

    def test_hidden_bridge_receives_pixels_in_stdin_not_file_or_command(self):
        output = SimpleNamespace(returncode=0, stdout=json.dumps(response()), stderr="")
        with patch.object(map_text, "_powershell", return_value=Path("powershell.exe")), \
                patch.object(map_text.subprocess, "run", return_value=output) as run:
            result = map_text.identify_map_text(self.image, ["erangel"], timeout=100)
        self.assertIsNone(result.map_id)
        args, kwargs = run.call_args
        self.assertIn("-NoProfile", args[0])
        self.assertIn("-NonInteractive", args[0])
        self.assertIn("-EncodedCommand", args[0])
        self.assertEqual(kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.assertGreater(kwargs["timeout"], 0)
        self.assertLessEqual(kwargs["timeout"], 8)
        request = json.loads(kwargs["input"])
        self.assertEqual(len(request["frames"]), 2)
        pixels = Image.open(BytesIO(base64.b64decode(request["frames"][0]["png_base64"])))
        self.assertEqual(pixels.size, self.image.size)
        self.assertEqual(pixels.getpixel((100, 100)), self.image.getpixel((100, 100)))

    def test_unavailable_platform_starts_no_child_process(self):
        with patch.object(map_text, "_powershell", return_value=None), \
                patch.object(map_text.subprocess, "run") as run:
            result = map_text.identify_map_text(self.image, ["erangel"])
        run.assert_not_called()
        self.assertFalse(result.available)

    def test_bounds_are_restored_from_actual_resize_factors(self):
        self.image = Image.new("RGB", (4000, 2001))
        payload = response(line("Georgopol", 150, 200), line("Pochinki", 650, 500))
        result = self.identify(payload)
        self.assertEqual(result.map_id, "erangel")
        self.assertAlmostEqual(result.matches[0].bounds[0], 150/.75)
        self.assertAlmostEqual(result.matches[0].bounds[1], 200/(1501/2001))

    def test_invalid_input_or_unsupported_vocabulary_does_not_invoke_ocr(self):
        with patch.object(map_text, "_run_bridge") as run:
            for image, maps, timeout in ((None, ["erangel"], 8),
                                         (self.image, "erangel", 8),
                                         (self.image, ["camp-jackal"], 8),
                                         (self.image, ["erangel"], float("nan"))):
                with self.subTest(maps=maps, timeout=timeout):
                    self.assertIsNone(map_text.identify_map_text(image, maps, timeout=timeout).map_id)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
