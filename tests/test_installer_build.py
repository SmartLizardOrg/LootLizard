"""Artifact validation does not execute installers or require the native SDK."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import build_installer as build


class InstallerBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.payload = self.root / "payload"
        for name in ("LootLizard.exe", "LICENSE", "THIRD_PARTY_NOTICES.md",
                     "source/scripts/build_installer.py", "source/.github/workflows/release.yml"):
            path = self.payload / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        (self.payload / "BUILD_INFO.json").write_text(json.dumps({"application_version": "0.8.0"}))
        (self.payload / "_internal").mkdir()
        (self.payload / "LICENSES").mkdir()
        self.output = self.root / "release" / "velopack"

    def make_feed(self, directory=None, **changes):
        directory = directory or self.output
        directory.mkdir(parents=True, exist_ok=True)
        name = f"{build.PACKAGE_ID}-0.8.0-full.nupkg"
        package = directory / name
        package.write_bytes(b"a complete synthetic package")
        asset = dict(PackageId=build.PACKAGE_ID, Version="0.8.0", Type="Full",
                     FileName=name, Size=package.stat().st_size,
                     SHA256=hashlib.sha256(package.read_bytes()).hexdigest().upper())
        asset.update(changes)
        (directory / "releases.win.json").write_text(json.dumps({"Assets": [asset]}))
        return package

    def test_feed_accepts_exact_package_with_verified_size_and_sha(self):
        package = self.make_feed()
        self.assertEqual(build.validate_feed(self.output, "0.8.0"), [self.output / "releases.win.json", package])

    def test_feed_rejects_corruption_wrong_version_and_untrusted_paths(self):
        for changes in ({"SHA256": "a" * 64}, {"Size": 1}, {"Version": "0.8.1"},
                        {"PackageId": "OtherApp"}, {"Type": "Delta"},
                        {"FileName": "../escape-full.nupkg"}):
            with self.subTest(changes=changes):
                self.make_feed(**changes)
                with self.assertRaises(ValueError):
                    build.validate_feed(self.output, "0.8.0")

    def test_feed_rejects_multiple_packages_in_a_fresh_output(self):
        self.make_feed()
        feed = self.output / "releases.win.json"
        document = json.loads(feed.read_text())
        document["Assets"] *= 2
        feed.write_text(json.dumps(document))
        with self.assertRaises(ValueError):
            build.validate_feed(self.output, "0.8.0")

    def test_builder_packages_enriched_payload_and_emits_only_public_asset_allowlist(self):
        calls = []

        def fake_vpk(command, **kwargs):
            calls.append(command)
            if command[-1] == "-H":
                return SimpleNamespace(stdout="Velopack CLI 1.2.161", stderr="")
            self.make_feed()
            (self.output / f"{build.PACKAGE_ID}-Setup.exe").write_bytes(b"synthetic setup")
            (self.output / "assets.win.json").write_text("deployment-only")
            return SimpleNamespace(stdout="", stderr="")

        with mock.patch.object(build.metadata, "version", return_value="1.2.161"), mock.patch.object(build.subprocess, "run", side_effect=fake_vpk):
            assets = build.build_installer(self.payload, self.output, self.root / "vpk.exe")
        self.assertEqual([item.name for item in assets], ["LootLizard-Setup.exe", "releases.win.json", f"{build.PACKAGE_ID}-0.8.0-full.nupkg"])
        command = calls[1]
        self.assertEqual(command[command.index("--packDir") + 1], str(self.payload.resolve()))
        self.assertNotIn("--skipVeloAppCheck", command)
        self.assertIn("--noPortable", command)
        manifest = json.loads((self.output / "installer-assets.json").read_text())
        self.assertEqual({item["name"] for item in manifest["assets"]}, {item.name for item in assets})
        self.assertNotIn("assets.win.json", {item.name for item in assets})

    def test_missing_source_or_notices_fails_before_tool_execution(self):
        (self.payload / "source/.github/workflows/release.yml").unlink()
        with mock.patch.object(build.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                build.build_installer(self.payload, self.output, self.root / "vpk.exe")
            run.assert_not_called()

    def test_production_version_mismatch_and_prerelease_are_rejected(self):
        for version in ("0.7.99", "0.8.0-beta.1", "00.8.0"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                build.build_installer(self.payload, self.output, self.root / "vpk.exe", version=version)

    def test_fixture_override_is_refused_outside_explicit_runner(self):
        for environment in ({}, {"GITHUB_ACTIONS": "true", "LOOTLIZARD_INSTALL_TEST": "1", "RUNNER_TEMP": str(self.root / "elsewhere")}):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment, clear=True), self.assertRaises(ValueError):
                build.build_installer(self.payload, self.output, self.root / "vpk.exe", version="0.7.99", ci_fixture=True)

    def test_sdk_tool_version_must_match(self):
        with mock.patch.object(build.metadata, "version", return_value="1.2.0"), mock.patch.object(build.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                build.build_installer(self.payload, self.output, self.root / "vpk.exe")
            run.assert_not_called()
        with mock.patch.object(build.metadata, "version", return_value="1.2.161"), mock.patch.object(build.subprocess, "run", return_value=SimpleNamespace(stdout="Velopack CLI 1.2.0", stderr="")):
            with self.assertRaises(ValueError):
                build.build_installer(self.payload, self.output, self.root / "vpk.exe")

    def test_checksums_cover_exact_installer_feed_package_and_zip(self):
        package = self.make_feed()
        release = self.output.parent
        archive = release / "LootLizard-0.8.0-windows-x64.zip"
        archive.write_bytes(b"portable")
        installer = self.output / "LootLizard-Setup.exe"
        installer.write_bytes(b"installer")
        result = build.finalize_checksums(release, [package, archive, installer, self.output / "releases.win.json"])
        lines = result.read_text().splitlines()
        self.assertEqual(len(lines), 4)
        for line in lines:
            digest, name = line.split("  ")
            candidate = archive if name == archive.name else self.output / name
            self.assertEqual(digest, build.sha256(candidate))

    def test_checksums_refuse_outside_files_and_duplicate_basenames(self):
        package = self.make_feed()
        outside = self.root / package.name
        outside.write_bytes(b"outside")
        with self.assertRaises(ValueError):
            build.finalize_checksums(self.output.parent, [outside])
        with self.assertRaises(ValueError):
            build.finalize_checksums(self.output.parent, [package, package])


if __name__ == "__main__":
    unittest.main()
