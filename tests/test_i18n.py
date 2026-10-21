from collections import Counter
from string import Formatter
import unittest

from lootlizard.i18n import HU, LANGUAGES, normalize_language, translate


class LocalizationTests(unittest.TestCase):
    def test_english_is_default_and_hungarian_is_optional(self):
        self.assertEqual(LANGUAGES, {"en": "English", "hu": "Magyar"})
        self.assertEqual(translate("Launch PUBG"), "Launch PUBG")
        self.assertEqual(translate("Launch PUBG", "hu"), "PUBG indítása")
        self.assertEqual(translate("Language", "hu"), "Nyelv")

    def test_invalid_saved_language_falls_back_to_english(self):
        for value in (None, False, 1, [], {}, "", "de", "hu-HU", "Magyar"):
            with self.subTest(value=value):
                self.assertEqual(normalize_language(value), "en")
                self.assertEqual(translate("Launch PUBG", value), "Launch PUBG")
        self.assertEqual(normalize_language(" HU "), "hu")
        self.assertEqual(normalize_language("EN"), "en")

    def test_unknown_message_falls_back_to_english_literal(self):
        self.assertEqual(translate("An unknown message", "hu"), "An unknown message")
        self.assertEqual(translate("Unknown {name}", "hu", name="Erangel"), "Unknown Erangel")

    def test_no_values_preserves_literal_braces_and_templates(self):
        self.assertEqual(translate("literal {} {unknown}", "hu"), "literal {} {unknown}")
        self.assertEqual(translate("On demand · v{version}", "hu"), "Kérésre frissül · v{version}")

    def test_dynamic_values_and_numeric_formatting(self):
        message = "Automatic icon match · {score:.2f} similarity · approximate straight-line distances"
        self.assertIn("0.95 similarity", translate(message, score=.946))
        self.assertIn("0.95 hasonlóság", translate(message, "hu", score=.946))
        self.assertEqual(translate("Monitor {number} · {width}×{height}", "hu",
                                   number=2, width=1920, height=1080), "2. monitor · 1920×1080")
        self.assertEqual(translate("Recognition failed: {reason}", "hu", reason="test"),
                         "Felismerés sikertelen: test")

    def test_every_catalogue_entry_preserves_placeholders_and_format_specs(self):
        formatter = Formatter()
        def fields(message):
            return Counter((field, spec, conversion)
                           for _, field, spec, conversion in formatter.parse(message)
                           if field is not None)
        self.assertGreater(len(HU), 100)
        for english, hungarian in HU.items():
            with self.subTest(message=english):
                self.assertIsInstance(english, str)
                self.assertIsInstance(hungarian, str)
                self.assertTrue(english and hungarian)
                self.assertEqual(fields(english), fields(hungarian))

    def test_profile_recognition_reasons_are_translatable(self):
        message = "Ambiguous: multiple objects resemble the trained icon"
        self.assertNotEqual(translate(message, "hu"), message)
        message = "Recognition unavailable: {error}"
        self.assertEqual(translate(message, "hu", error="test"),
                         "A felismerés nem érhető el: test")


if __name__ == "__main__":
    unittest.main()
