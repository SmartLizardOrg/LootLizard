"""Recognize every shipped public map against the complete reference set."""
import json
from pathlib import Path
import unittest

from PIL import Image
from lootlizard.registration import MapReference, register_map

ASSETS = Path(__file__).resolve().parents[1] / "web/app/map-assets"


class BundledMapRecognitionTests(unittest.TestCase):
    def test_each_official_map_is_unique_after_resize_and_screen_offset(self):
        records = json.loads((ASSETS / "manifest.json").read_text(encoding="utf-8"))["references"]
        self.assertEqual(len(records), 11)
        images = {}
        for record in records:
            with Image.open(ASSETS / record["file"]) as image:
                images[record["mapId"]] = image.convert("RGB")
        references = tuple(MapReference(map_id, image) for map_id, image in images.items())
        for map_id, image in images.items():
            with self.subTest(map_id=map_id):
                frame = Image.new("RGB", (960, 720), (17, 24, 32))
                frame.paste(image.resize((640, 640), Image.Resampling.LANCZOS), (160, 40))
                result = register_map(frame, references)
                self.assertEqual(result.map_id, map_id, result.reason)
                for x, y in [(0.1, 0.2), (0.5, 0.5), (0.9, 0.8)]:
                    projected = result.project_poi(x, y)
                    self.assertIsNotNone(projected)
                    self.assertLess(abs(projected[0] - (160 + 640 * x)), 5)
                    self.assertLess(abs(projected[1] - (40 + 640 * y)), 5)
