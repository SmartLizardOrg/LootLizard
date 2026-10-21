"""Production cannot select the local update source used by installer CI."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from lootlizard import installer_probe


class InstallerProbeTests(unittest.TestCase):
    def test_probe_is_disabled_outside_explicit_ci_environment(self):
        args = SimpleNamespace(report="report.json")
        for environment in ({}, {"GITHUB_ACTIONS": "true"},
                            {"GITHUB_ACTIONS": "true", "LOOTLIZARD_INSTALL_TEST": "1"}):
            with self.subTest(environment=environment), mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(installer_probe, "AppUpdateClient") as client:
                with self.assertRaises(RuntimeError):
                    installer_probe.run_probe(args)
                client.assert_not_called()

    def test_probe_paths_are_restricted_to_ephemeral_runner_directory(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.dict(os.environ, {"RUNNER_TEMP": temporary}):
            root = Path(temporary)
            self.assertEqual(installer_probe._runner_path(str(root / "report.json")), root.resolve() / "report.json")
            for path in (None, str(root), str(root / ".." / "outside.json")):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    installer_probe._runner_path(path)

    def test_failed_installed_probe_reports_and_exits_without_an_error_dialog(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "reports/result.json"
            environment = dict(GITHUB_ACTIONS="true", LOOTLIZARD_INSTALL_TEST="1", RUNNER_TEMP=temporary)
            args = SimpleNamespace(report=str(report), ci_update_source=None)
            with mock.patch.dict(os.environ, environment), mock.patch.object(installer_probe, "AppUpdateClient", return_value=SimpleNamespace(installed=False, reason="missing manifest")):
                with self.assertRaises(SystemExit) as result:
                    installer_probe.run_probe(args)
                self.assertEqual(result.exception.code, 1)
                self.assertIn("missing manifest", report.read_text(encoding="utf-8"))
