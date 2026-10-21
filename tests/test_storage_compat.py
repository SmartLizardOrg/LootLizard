"""Read the old product's settings/profiles without modifying them."""

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_app_state as fixtures
from lootlizard.storage import (preferences_path, legacy_preferences_path,
    legacy_profile_directory, read_preferences, save_preferences)


class StorageCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        environment = patch.dict(os.environ, {"LOCALAPPDATA": self.temporary.name})
        environment.start()
        self.addCleanup(environment.stop)

    def write_legacy(self, value):
        path = legacy_preferences_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_default_fallback_preserves_old_preferences_and_new_saves_are_separate(self):
        legacy = self.write_legacy({"language":"hu", "reference_catalog":"C:/local/catalog.json"})
        original = legacy.read_bytes()
        settings = read_preferences()
        self.assertEqual(settings["language"], "hu")
        self.assertFalse(preferences_path().exists())
        save_preferences(settings)
        self.assertEqual(legacy.read_bytes(), original)
        self.assertEqual(preferences_path().parent.name, "LootLizard")
        self.assertEqual(read_preferences()["reference_catalog"], "C:/local/catalog.json")

    def test_new_or_explicit_settings_never_fall_back_to_legacy(self):
        self.write_legacy({"language":"hu"})
        save_preferences({"language":"en"})
        self.assertEqual(read_preferences(), {"language":"en"})
        preferences_path().write_text("invalid", encoding="utf-8")
        self.assertEqual(read_preferences(), {})
        self.assertEqual(read_preferences(Path(self.temporary.name)/"missing-custom.json"), {})

    def test_oversized_legacy_settings_are_rejected(self):
        path = self.write_legacy({})
        path.write_text(" "*(128*1024+1), encoding="utf-8")
        self.assertEqual(read_preferences(), {})

    def test_old_profile_is_loaded_in_place_but_write_directory_is_new(self):
        fixture = fixtures.AppStateTests()
        fixture.setUp()
        app = fixture.app
        app.settings_path = None
        app.marker_preview = fixtures._Widget()
        app.profile_label = fixtures._Widget()
        old = legacy_profile_directory(app.data.id)
        old.mkdir(parents=True)
        (old/"profile.json").write_text("{}", encoding="utf-8")
        profile = SimpleNamespace(map_id=app.data.id)
        with patch("lootlizard.app.Profile.load", return_value=profile) as load:
            app._load_profile()
        load.assert_called_once_with(old)
        self.assertIs(app.profile, profile)
        self.assertNotEqual(app._profile_directory(), old)
        self.assertIn("LootLizard", app._profile_directory().parts)

    def test_existing_new_profile_is_not_silently_replaced_by_an_old_profile(self):
        fixture = fixtures.AppStateTests()
        fixture.setUp()
        app = fixture.app
        app.settings_path = None
        app.marker_preview = fixtures._Widget()
        app.profile_label = fixtures._Widget()
        current = app._profile_directory()
        current.mkdir(parents=True)
        (current/"profile.json").write_text("{}", encoding="utf-8")
        with patch("lootlizard.app.Profile.load", side_effect=ValueError("invalid current profile")) as load:
            app._load_profile()
        load.assert_called_once_with(current)
        self.assertIsNone(app.profile)


if __name__ == "__main__":
    unittest.main()
