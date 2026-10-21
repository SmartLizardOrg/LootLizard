"""Package an existing PyInstaller Windows build without publishing anything.

Run this with the Python environment used to build the executable, so the
recorded dependency versions and copied licenses describe that build.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import sys
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_FILES = (
    "launcher.py", "pyproject.toml", "README.md", "LICENSE",
    "THIRD_PARTY_NOTICES.md", ".gitignore", ".gitattributes",
    "README.hu.md",
    "CONTRIBUTING.md",
)
SOURCE_DIRECTORIES = (
    "lootlizard", "data", "tests", "scripts", ".github",
)
COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", "*.pyo", "*.egg-info", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", ".venv", "venv", ".git",
    "captures", "screenshots", "profiles", "references", ".env", ".env.*",
)


def sanitize_label(value: str) -> str:
    """Keep a label in a single, reasonably short Windows filename component."""
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(" .-_")[:80]
    if not label:
        raise ValueError("The label must contain a letter or digit.")
    return label


def binary_target(executable: Path) -> str:
    """Read the PE machine field rather than guessing from the packaging host."""
    with executable.open("rb") as stream:
        header = stream.read(64)
        if len(header) != 64 or header[:2] != b"MZ":
            raise ValueError("The binary is not a Windows PE executable.")
        stream.seek(struct.unpack_from("<I", header, 0x3C)[0])
        signature = stream.read(6)
    if len(signature) != 6 or signature[:4] != b"PE\x00\x00":
        raise ValueError("The binary has an invalid Windows PE header.")
    machine = struct.unpack_from("<H", signature, 4)[0]
    architectures = {0x014C: "x86", 0x8664: "x64", 0xAA64: "arm64"}
    if machine not in architectures:
        raise ValueError(f"Unsupported Windows binary architecture: 0x{machine:04x}")
    return "windows-" + architectures[machine]


def copy_license(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_runtime_licenses(destination: Path) -> None:
    runtime = Path(sys.base_prefix)
    python_licenses = [runtime / name for name in ("LICENSE.txt", "LICENSE")
                       if (runtime / name).is_file()]
    if not python_licenses:
        raise ValueError("Python's runtime license was not found in sys.base_prefix.")
    for source in python_licenses:
        copy_license(source, destination / "Python" / source.name)

    tcl_root = runtime / "tcl"
    tcl_licenses = [path for path in sorted(tcl_root.rglob("*"))
                    if path.is_file()
                    and path.name.lower().startswith(("license", "copying", "notice"))]
    if not tcl_licenses:
        raise ValueError("Tcl/Tk license files were not found in the Python runtime's tcl directory.")
    for source in tcl_licenses:
        copy_license(source, destination / "TclTk" / source.relative_to(tcl_root))


def copy_distribution_licenses(name: str, destination: Path) -> str:
    distribution = metadata.distribution(name)
    copied = 0
    for index, item in enumerate(distribution.files or ()):
        parts = [part.lower() for part in Path(str(item)).parts]
        if not any(part.startswith(("license", "copying", "notice")) for part in parts):
            continue
        source = Path(distribution.locate_file(item))
        if source.is_file():
            copy_license(source, destination / name / f"{index:04d}-{source.name}")
            copied += 1
    if not copied:
        raise ValueError(f"No license files were found in the installed {name} distribution.")
    return distribution.version


def github_metadata() -> dict[str, str | None]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return {"build_origin": "local-unpublished", "git_commit": None,
                "git_ref": None, "repository": None}
    server = os.environ.get("GITHUB_SERVER_URL")
    repository = os.environ.get("GITHUB_REPOSITORY")
    return {
        "build_origin": "github-actions",
        "git_commit": os.environ.get("GITHUB_SHA"),
        "git_ref": os.environ.get("GITHUB_REF"),
        "repository": f"{server.rstrip('/')}/{repository}" if server and repository else None,
    }


def package_release(binary: Path, output: Path, label: str) -> tuple[Path, Path]:
    binary = binary.expanduser().resolve()
    output = output.expanduser().resolve()
    binary_directory = binary if binary.is_dir() else binary.parent
    executable = binary_directory / "LootLizard.exe"
    if not executable.is_file():
        raise ValueError("--binary must name the onedir folder or its LootLizard.exe.")
    if binary.is_file() and binary != executable:
        raise ValueError("The executable must be named LootLizard.exe.")
    if output == binary_directory or binary_directory in output.parents:
        raise ValueError("The output directory must be outside the binary directory.")
    target = binary_target(executable)
    label = sanitize_label(label)
    bundle = output / f"LootLizard-{label}-{target}"
    archive = output / (bundle.name + ".zip")
    checksum_file = output / "SHA256SUMS.txt"
    if bundle.exists() or archive.exists():
        raise FileExistsError("The selected bundle or ZIP already exists; choose another label/output.")
    if checksum_file.exists():
        if not checksum_file.is_file():
            raise ValueError("SHA256SUMS.txt already exists and is not a file.")
        if any(line.split(maxsplit=1)[-1].strip(" *") == archive.name
               for line in checksum_file.read_text(encoding="ascii").splitlines() if line.strip()):
            raise FileExistsError("A checksum for this archive already exists; choose another label/output.")
    for item in SOURCE_FILES + SOURCE_DIRECTORIES:
        if not (ROOT / item).exists():
            raise FileNotFoundError(f"Required source entry is missing: {item}")
    with (ROOT / "pyproject.toml").open("rb") as source_file:
        application_version = tomllib.load(source_file)["project"]["version"]
    # Fail early when the caller is not using the build environment.
    for name in ("Pillow", "PyInstaller", "opencv-python-headless", "numpy"):
        metadata.distribution(name)

    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(binary_directory, bundle)
    for name in ("README.md", "README.hu.md", "LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(ROOT / name, bundle / name)
    (bundle / "start-pubg.cmd").write_text(
        '@echo off\nstart "" "%~dp0LootLizard.exe" --launch-pubg\n',
        encoding="ascii", newline="\r\n")

    source = bundle / "source"
    source.mkdir()
    for name in SOURCE_FILES:
        shutil.copy2(ROOT / name, source / name)
    for name in SOURCE_DIRECTORIES:
        shutil.copytree(ROOT / name, source / name, ignore=COPY_IGNORE)

    licenses = bundle / "LICENSES"
    licenses.mkdir()
    copy_runtime_licenses(licenses)
    pillow_version = copy_distribution_licenses("Pillow", licenses)
    pyinstaller_version = copy_distribution_licenses("PyInstaller", licenses)
    opencv_version = copy_distribution_licenses("opencv-python-headless", licenses)
    numpy_version = copy_distribution_licenses("numpy", licenses)
    (licenses / "README.txt").write_text(
        "Licenses copied from the Python/Tcl/Tk runtime and Pillow/PyInstaller,\n"
        "OpenCV-headless and NumPy distributions used by this build.\n"
        "Pillow's license file also contains notices for its bundled libraries.\n"
        "PyInstaller is a build\n"
        "tool; its license includes the bootloader distribution exception.\n"
        "Community coordinate notices are in ../THIRD_PARTY_NOTICES.md.\n",
        encoding="utf-8")
    dependencies = {
        "python": platform.python_version(),
        "pillow": pillow_version,
        "pyinstaller": pyinstaller_version,
        "opencv-python-headless": opencv_version,
        "numpy": numpy_version,
    }
    (bundle / "BUILD_DEPENDENCIES.json").write_text(
        json.dumps(dependencies, indent=2) + "\n", encoding="utf-8")
    build_info = {
        "application_version": application_version,
        "label": label,
        **github_metadata(),
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "pillow": pillow_version,
        "pyinstaller": pyinstaller_version,
        "opencv-python-headless": opencv_version,
        "numpy": numpy_version,
        "packaging_platform": platform.platform(),
        "target": target,
        "bundle_mode": "onedir",
        "signed": False,
        "limitations": [
            "Automatic zoom-aware maps require an explicitly loaded local full-map reference catalog; no game images are bundled.",
            "The experimental matcher finds an icon appearance; PUBG player identity is not verified.",
            "Automatic viewing-cone estimates require a unique visible body/fan in explicit live-play context; clipping, occlusion and clutter can abstain.",
            "Replay/observer mode disables automatic player estimates. Live/replay context is not classified automatically.",
            "Optional local Windows OCR can suggest Erangel/Taego from place labels; it never authorizes geometry or point placement and may be unavailable on another Windows setup.",
            "Own squad color or slot changes can make an old profile match a teammate; real solo/squad examples are needed.",
            "Map identification can abstain on extreme zoom, insufficient terrain detail, unknown references, or ambiguous matches.",
            "Own icon is optional for point projection; fixed-layout trained-icon profiles still require their saved framing and resolution.",
            "Community points are unverified; loot/accessibility state is unknown.",
            "White safe-zone detection is experimental; clipped registered maps and missing or ambiguous rings leave zone priority unavailable.",
            "Circle membership and distances are screenshot estimates, not route or future-circle predictions.",
            "No installed autostart, official PUBG authorization, or anti-cheat compatibility claim.",
        ],
    }
    (bundle / "BUILD_INFO.json").write_text(
        json.dumps(build_info, indent=2) + "\n", encoding="utf-8")
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as package:
        for path in sorted(bundle.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(output))
    with archive.open("rb") as archive_file:
        digest = hashlib.file_digest(archive_file, "sha256").hexdigest()
    prefix = ""
    if checksum_file.exists() and checksum_file.stat().st_size:
        if not checksum_file.read_text(encoding="ascii").endswith("\n"):
            prefix = "\n"
    with checksum_file.open("a", encoding="ascii", newline="\n") as checksums:
        checksums.write(f"{prefix}{digest}  {archive.name}\n")
    return archive, checksum_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path,
                        help="PyInstaller onedir folder, or LootLizard.exe inside it")
    parser.add_argument("--output", required=True, type=Path,
                        help="Destination directory; existing releases are preserved")
    parser.add_argument("--label", required=True,
                        help="Release label, such as 0.3.0; sanitized for filenames")
    args = parser.parse_args()
    try:
        archive, checksum_file = package_release(args.binary, args.output, args.label)
    except (OSError, ValueError, metadata.PackageNotFoundError) as error:
        parser.exit(1, f"Packaging failed: {error}\nAny partial output is left untouched.\n")
    print(f"Created {archive}\nSHA256: {checksum_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
