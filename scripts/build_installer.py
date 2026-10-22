"""Build and validate Velopack release assets; never install or publish them.

The payload is the enriched directory created by package_release.py, so the
installer and full update package retain source and dependency notices too.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

PACKAGE_ID = "SmartLizardOrg.LootLizard"
CHANNEL = "win"
VELOPACK_VERSION = "1.2.161"
INSTALLER_NAME = "LootLizard-Setup.exe"
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_feed(output: Path, version: str) -> list[Path]:
    """Allow only the exact full package described by this release's feed."""
    feed = output / f"releases.{CHANNEL}.json"
    document = json.loads(feed.read_text(encoding="utf-8-sig"))
    assets = document.get("Assets") if isinstance(document, dict) else None
    if not isinstance(assets, list) or len(assets) != 1:
        raise ValueError("A fresh release feed must contain exactly one full package.")
    asset = assets[0]
    expected = f"{PACKAGE_ID}-{version}-full.nupkg"
    if not isinstance(asset, dict) or (asset.get("PackageId"), asset.get("Version"), asset.get("Type"), asset.get("FileName")) != (PACKAGE_ID, version, "Full", expected):
        raise ValueError("The generated feed does not describe the requested release.")
    package = output / expected
    if not package.is_file() or asset.get("Size") != package.stat().st_size:
        raise ValueError("The full package is absent or its feed size is incorrect.")
    if not isinstance(asset.get("SHA256"), str) or asset["SHA256"].lower() != sha256(package):
        raise ValueError("The full package SHA256 differs from its feed.")
    return [feed, package]


def build_installer(payload: Path, output: Path, vpk: Path, *, version: str | None = None,
                    ci_fixture: bool = False) -> list[Path]:
    payload, output, vpk = payload.resolve(), output.resolve(), vpk.resolve()
    if output == payload or payload in output.parents:
        raise ValueError("Installer output must be outside its payload.")
    for name in ("LootLizard.exe", "BUILD_INFO.json", "LICENSE", "THIRD_PARTY_NOTICES.md",
                 "source/scripts/build_installer.py", "source/.github/workflows/release.yml"):
        if not (payload / name).is_file():
            raise ValueError(f"The enriched payload is missing {name}.")
    if not (payload / "_internal").is_dir() or not (payload / "LICENSES").is_dir():
        raise ValueError("An onedir payload with dependency notices is required.")
    info = json.loads((payload / "BUILD_INFO.json").read_text(encoding="utf-8"))
    version = version or info["application_version"]
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("The installer requires a stable three-part version.")
    if version != info["application_version"] and not ci_fixture:
        raise ValueError("The package version must match the payload version.")
    if ci_fixture:
        runner = Path(os.environ.get("RUNNER_TEMP", "")).resolve()
        if (os.environ.get("GITHUB_ACTIONS") != "true"
                or os.environ.get("LOOTLIZARD_INSTALL_TEST") != "1"
                or not os.environ.get("RUNNER_TEMP")
                or runner not in output.parents or runner not in payload.parents
                or version != "0.7.99"):
            raise ValueError("The older fixture is restricted to isolated installer CI.")
    if metadata.version("velopack") != VELOPACK_VERSION:
        raise ValueError(f"The build requires velopack=={VELOPACK_VERSION}.")
    help_result = subprocess.run([str(vpk), "-H"], check=True, capture_output=True, text=True)
    if f"Velopack CLI {VELOPACK_VERSION}" not in help_result.stdout + help_result.stderr:
        raise ValueError("The vpk tool version must match the Python SDK.")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use an empty installer output directory to avoid mixing feeds.")
    output.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(vpk), "--skip-updates", "--yes", "pack",
                    "--packId", PACKAGE_ID, "--packVersion", version,
                    "--packDir", str(payload), "--mainExe", "LootLizard.exe",
                    "--packTitle", "LootLizard", "--packAuthors", "molnard-labs",
                    "--channel", CHANNEL, "--runtime", "win-x64", "--noPortable",
                    "--shortcuts", "Desktop,StartMenuRoot", "--outputDir", str(output)], check=True)
    assets = validate_feed(output, version)
    generated = output / f"{PACKAGE_ID}-{CHANNEL}-Setup.exe"
    if not generated.is_file() or generated.stat().st_size == 0:
        raise ValueError("Velopack did not produce its setup executable.")
    installer = output / INSTALLER_NAME
    shutil.copy2(generated, installer)
    assets.insert(0, installer)
    # assets.win.json describes the original generated setup name and is for
    # vpk upload. We publish a stable alias with gh, so never publish that file.
    manifest = {"package_id": PACKAGE_ID, "version": version, "channel": CHANNEL,
                "velopack": VELOPACK_VERSION,
                "assets": [{"name": item.name, "sha256": sha256(item), "bytes": item.stat().st_size}
                           for item in assets]}
    (output / "installer-assets.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return assets


def finalize_checksums(release: Path, assets: list[Path]) -> Path:
    """Write one deterministic checksum list for precisely the published files."""
    release = release.resolve()
    paths = sorted(assets, key=lambda path: path.name)
    if len({path.name for path in paths}) != len(paths):
        raise ValueError("Published asset basenames must be unique.")
    for path in paths:
        if not path.is_file() or release not in path.resolve().parents:
            raise ValueError("Every release asset must be a file below the release directory.")
    result = release / "SHA256SUMS.txt"
    result.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in paths), encoding="ascii")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vpk", type=Path, required=True)
    parser.add_argument("--version")
    parser.add_argument("--ci-fixture", action="store_true")
    parser.add_argument("--release-root", type=Path,
                        help="Also checksum these installer assets and all top-level release ZIPs")
    args = parser.parse_args()
    assets = build_installer(args.payload, args.output, args.vpk,
                             version=args.version, ci_fixture=args.ci_fixture)
    if args.release_root:
        finalize_checksums(args.release_root, assets + list(args.release_root.glob("*.zip")))
    for item in assets:
        print(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
