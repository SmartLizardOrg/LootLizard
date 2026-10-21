"""Headless installed-binary test hook, restricted to isolated CI runners.

This exercises the same client and native updater used by the application,
without creating Tk windows, capturing screens, or registering game hotkeys.
Normal releases always use app_updates.REPOSITORY_URL.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .app_updates import AppUpdateClient


def _runner_path(value: str | None) -> Path:
    root = Path(os.environ["RUNNER_TEMP"]).resolve()
    if not value:
        raise ValueError("A CI runner path is required.")
    path = Path(value).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Installer probe paths must be inside RUNNER_TEMP.")
    return path


def run_probe(args) -> None:
    if (os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("LOOTLIZARD_INSTALL_TEST") != "1"
            or not os.environ.get("RUNNER_TEMP")):
        raise RuntimeError("The installer probe is restricted to isolated GitHub Actions tests.")
    report_path = _runner_path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _probe(args, report_path)
    except Exception as exc:
        # A windowed frozen binary would otherwise open an error dialog and
        # stall the headless test instead of returning useful CI diagnostics.
        report_path.write_text(json.dumps(dict(status="error", reason=str(exc))), encoding="utf-8")
        raise SystemExit(1) from exc


def _probe(args, report_path: Path) -> None:
    source = None
    if args.ci_update_source:
        source = _runner_path(args.ci_update_source)
        if not source.is_dir():
            raise ValueError("The local CI update feed must be a directory.")
    client = AppUpdateClient(**({"_ci_source_dir": str(source)} if source else {}))
    if not client.installed:
        raise RuntimeError("The installer probe must run from an installed LootLizard package: " + client.reason)
    report = dict(installed=client.installed, current_version=client._manager.get_current_version(),
                  available_version=None, pending_version=None, status="installed", apply_scheduled=False)
    if args.download:
        result = client.check_and_download()
        report.update(status=result.status, available_version=result.version, reason=result.reason)
        if result.status not in ("ready", "current"):
            report_path.write_text(json.dumps(report), encoding="utf-8")
            raise RuntimeError("Installer update probe failed: " + result.reason)
    pending = client._manager.get_update_pending_restart()
    if pending is not None:
        report["pending_version"] = pending.Version
    if args.apply_on_exit:
        if not args.download or not client.has_pending:
            raise ValueError("The apply probe requires a completely downloaded update.")
        report["apply_scheduled"] = client.apply_on_exit(restart=False)
        if not report["apply_scheduled"]:
            raise RuntimeError("Could not schedule the installer update: " + client.reason)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
