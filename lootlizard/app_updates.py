"""Stable GitHub Releases updates; only actual exit cleanup may arm Velopack."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import urllib.error
import urllib.request

from .storage import preferences_path

REPOSITORY_URL = "https://github.com/molnard-labs/LootLizard"
LEGACY_REPOSITORY_URL = "https://github.com/SmartLizardOrg/LootLizard"
REPOSITORY_URLS = (REPOSITORY_URL, LEGACY_REPOSITORY_URL)
# The numeric repository ID survives an organization rename. Keep discovery
# redirects disabled and permit only these two known names for this repository.
LATEST_RELEASE_URL = "https://api.github.com/repositories/1428915855/releases/latest"
INSTALLER_URL = REPOSITORY_URL + "/releases/latest/download/LootLizard-Setup.exe"
PACKAGE_ID = "SmartLizardOrg.LootLizard"
CHECK_INTERVAL_SECONDS = 6*60*60
MAX_PACKAGE_BYTES = 1024*1024*1024
MAX_RELEASE_BYTES = 1024*1024
_CACHE_BYTES = 16*1024


def bootstrap():
    """Run SDK hooks before GUI/CV imports; never auto-apply on startup."""
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import velopack
        velopack.App().set_auto_apply_on_startup(False).run()


def _stable_version(value):
    if not isinstance(value, str) or not re.fullmatch(
            r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})", value):
        raise ValueError("Only stable three-part application versions are supported.")
    return tuple(map(int, value.split(".")))


def _manager_for_source(source):
    import velopack
    if isinstance(source, str) and source.startswith("https://"):
        source = velopack.HttpSource(source, velopack.HttpOptions(Headers=[], TimeoutMilliseconds=120000))
    options = velopack.UpdateOptions(AllowVersionDowngrade=False,
                                     MaximumDeltasBeforeFallback=-1, ExplicitChannel="win")
    manager = velopack.UpdateManager(source, options=options)
    if manager.get_is_portable() or manager.get_app_id() != PACKAGE_ID:
        return None
    _stable_version(manager.get_current_version())
    return manager


def _installed_manager():
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    # Locates the installed manifest without making a network request.
    return _manager_for_source(REPOSITORY_URL+"/releases/latest/download")


def _installed_packages_dir():
    executable = Path(sys.executable).resolve()
    if executable.parent.name.casefold() != "current":
        raise ValueError("The installed application's current directory could not be located.")
    return executable.parent.parent / "packages"


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise urllib.error.HTTPError(request.full_url, code, "Release discovery redirects are disabled", headers, fp)


def _json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate release metadata key.")
        result[key] = value
    return result


def _fetch_latest_release():
    request = urllib.request.Request(LATEST_RELEASE_URL, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "LootLizard application updater",
        "X-GitHub-Api-Version": "2022-11-28"})
    response = None
    deadline = time.monotonic()+8
    try:
        response = urllib.request.build_opener(_NoRedirects()).open(request, timeout=8)
        if response.getcode() != 200:
            raise ValueError("GitHub did not return release metadata.")
        declared = response.headers.get("Content-Length")
        if declared is not None and not 0 <= int(declared) <= MAX_RELEASE_BYTES:
            raise ValueError("Release metadata exceeds its size limit.")
        body = bytearray()
        read = getattr(response, "read1", response.read)
        while True:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Release discovery timed out.")
            transport = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
            if transport is not None:
                transport.settimeout(remaining)
            chunk = read(min(65536, MAX_RELEASE_BYTES+1-len(body)))
            if not chunk:
                break
            body.extend(chunk)
            if len(body) > MAX_RELEASE_BYTES:
                raise ValueError("Release metadata exceeds its size limit.")
        return json.loads(body.decode("utf-8"), object_pairs_hook=_json_object)
    except urllib.error.HTTPError as error:
        error.close()
        raise
    finally:
        if response is not None:
            response.close()


def _release_details(release):
    if not isinstance(release, dict) or release.get("draft") is not False or release.get("prerelease") is not False:
        raise ValueError("Only a published stable GitHub release is accepted.")
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not tag.startswith("v"):
        raise ValueError("The latest release has no stable version tag.")
    _stable_version(tag[1:])
    repository = next((url for url in REPOSITORY_URLS
                       if release.get("html_url") == url+"/releases/tag/"+tag), None)
    if repository is None:
        raise ValueError("Unexpected release repository or tag URL.")
    base = repository+"/releases/download/"+tag
    assets = release.get("assets")
    if not isinstance(assets, list) or len(assets) > 64:
        raise ValueError("Invalid release asset list.")
    feeds = [item for item in assets if isinstance(item, dict) and item.get("name") == "releases.win.json"]
    if (len(feeds) != 1 or feeds[0].get("browser_download_url") != base+"/releases.win.json"
            or type(feeds[0].get("size")) is not int or not 0 < feeds[0]["size"] <= MAX_RELEASE_BYTES):
        raise ValueError("The latest release has no canonical bounded Windows update feed.")
    return tag[1:], base, assets


@dataclass(frozen=True)
class AppUpdateResult:
    status: str
    version: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class _Package:
    Version: str
    FileName: str
    SHA256: str
    Size: int


def _sdk_asset(package):
    import velopack
    return velopack.VelopackAsset(PackageId=PACKAGE_ID, Version=package.Version, Type="Full",
        FileName=package.FileName, SHA1="", SHA256=package.SHA256, Size=package.Size,
        NotesMarkdown="", NotesHtml="")


class AppUpdateClient:
    """Single-flight staging. Native download cancellation is caller state only.

    No network or helper is started by construction. Verified expected metadata
    is cached separately from packages for offline recovery. Every ready/apply
    path verifies actual package size and streamed SHA-256 again.
    """
    def __init__(self, *, cache_path=None, _ci_source_dir=None):
        self._lock = threading.Lock()
        self._pending = self._manager = self._packages = None
        self._ci_source, self._scope = None, "github-stable"
        self._cache_path = Path(cache_path) if cache_path is not None else preferences_path().parent/"app-update.json"
        self.reason = ""
        if _ci_source_dir is not None:
            if (os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("LOOTLIZARD_INSTALL_TEST") != "1"
                    or not os.environ.get("RUNNER_TEMP")):
                raise ValueError("A local update feed is restricted to isolated installer CI.")
            root, source = Path(os.environ["RUNNER_TEMP"]).resolve(), Path(_ci_source_dir).resolve()
            if source == root or not source.is_relative_to(root) or not source.is_dir():
                raise ValueError("The CI update feed must be a directory inside RUNNER_TEMP.")
            self._ci_source, self._scope = str(source), "ci:"+str(source)
        try:
            self._manager = _installed_manager()
            if self._manager is not None:
                self._packages = _installed_packages_dir().resolve()
                self._current = self._manager.get_current_version()
                _stable_version(self._current)
        except Exception as error:
            self._manager = None
            self.reason = self._reason(error)
        self.installed = self._manager is not None

    @staticmethod
    def _reason(error):
        return " ".join(str(error).split())[:500] or type(error).__name__

    @property
    def has_pending(self):
        return self._pending is not None

    def _validate_asset(self, asset):
        if _stable_version(asset.Version) <= _stable_version(self._current):
            raise ValueError("Refusing an application downgrade or the current version.")
        if asset.PackageId != PACKAGE_ID or asset.Type != "Full":
            raise ValueError("Unexpected application package identity or type.")
        name = asset.FileName
        if not isinstance(name, str) or name != f"{PACKAGE_ID}-{asset.Version}-full.nupkg":
            raise ValueError("Unexpected application package filename.")
        if not isinstance(asset.SHA256, str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", asset.SHA256):
            raise ValueError("The application package has no SHA-256 checksum.")
        if type(asset.Size) is not int or not 0 < asset.Size <= MAX_PACKAGE_BYTES:
            raise ValueError("Unexpected application package size.")
        return _Package(asset.Version, name, asset.SHA256.lower(), asset.Size)

    def _package_path(self, package):
        path = self._packages/package.FileName
        if path.is_symlink() or not path.resolve().is_relative_to(self._packages):
            raise ValueError("The application package is outside its installed cache.")
        return path

    def _verify_package(self, package):
        path = self._package_path(package)
        if path.stat().st_size != package.Size:
            raise ValueError("The staged application package has the wrong size.")
        digest, count = hashlib.sha256(), 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024*1024):
                count += len(chunk)
                if count > package.Size:
                    raise ValueError("The staged application package grew during verification.")
                digest.update(chunk)
        if count != package.Size or digest.hexdigest() != package.SHA256:
            raise ValueError("The staged application package failed SHA-256 verification.")

    def _save_pending(self, package):
        value = dict(schema_version=1, repository=REPOSITORY_URL, scope=self._scope,
                     package_id=PACKAGE_ID, version=package.Version, filename=package.FileName,
                     sha256=package.SHA256, size=package.Size)
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("wb", dir=self._cache_path.parent,
                                             prefix=".app-update-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self._cache_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _read_pending(self):
        try:
            with self._cache_path.open("rb") as stream:
                raw = stream.read(_CACHE_BYTES+1)
            if len(raw) > _CACHE_BYTES:
                return None
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_json_object)
            if (not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1
                    or value.get("repository") not in REPOSITORY_URLS or value.get("scope") != self._scope
                    or value.get("package_id") != PACKAGE_ID):
                return None
            package = self._validate_asset(SimpleNamespace(PackageId=PACKAGE_ID, Type="Full",
                Version=value.get("version"), FileName=value.get("filename"),
                SHA256=value.get("sha256"), Size=value.get("size")))
            self._verify_package(package)
            return package
        except (OSError, ValueError, TypeError, RecursionError):
            return None

    def _forget_pending(self):
        self._pending = None
        try:
            self._cache_path.unlink(missing_ok=True)
        except OSError:
            pass

    def check_and_download(self):
        if not self.installed:
            return AppUpdateResult("unavailable", reason=self.reason)
        if not self._lock.acquire(blocking=False):
            return AppUpdateResult("busy")
        try:
            if self._pending is not None:
                self._verify_package(self._pending)
                return AppUpdateResult("ready", self._pending.Version)
            expected_version, base, assets = None, self._ci_source, None
            if base is None:
                expected_version, base, assets = _release_details(_fetch_latest_release())
                if _stable_version(expected_version) <= _stable_version(self._current):
                    self._forget_pending()
                    return AppUpdateResult("current", self._current)
            manager = _manager_for_source(base)
            if manager is None or manager.get_current_version() != self._current:
                raise ValueError("The application installation changed during update discovery.")
            update = manager.check_for_updates()
            if update is None:
                if expected_version is not None:
                    raise ValueError("The latest release has no matching higher Windows package.")
                self._forget_pending()
                return AppUpdateResult("current", self._current)
            if update.IsDowngrade:
                raise ValueError("Refusing an application downgrade or channel switch.")
            package = self._validate_asset(update.TargetFullRelease)
            if expected_version is not None:
                if package.Version != expected_version:
                    raise ValueError("The Windows package does not match the latest stable release tag.")
                matching = [item for item in assets if isinstance(item, dict) and item.get("name") == package.FileName]
                if (len(matching) != 1 or matching[0].get("browser_download_url") != base+"/"+package.FileName
                        or type(matching[0].get("size")) is not int or matching[0]["size"] != package.Size):
                    raise ValueError("The package is not the canonical asset of the latest GitHub release.")
                digest = matching[0].get("digest")
                if digest is not None and digest != "sha256:"+package.SHA256:
                    raise ValueError("GitHub and the Windows feed disagree on the package checksum.")
            path = self._package_path(package)
            if path.exists():
                try:
                    self._verify_package(package)
                except (OSError, ValueError):
                    # The SDK would otherwise skip checking this existing file.
                    path.unlink()
            manager.download_updates(update)
            self._verify_package(package)
            self._save_pending(package)
            self._manager, self._pending = manager, package
            return AppUpdateResult("ready", package.Version)
        except Exception as error:
            self._pending = None
            cached = self._read_pending()
            if cached is not None:
                self._pending = cached
                return AppUpdateResult("ready", cached.Version,
                    "A previously verified update is available; the latest release check failed.")
            return AppUpdateResult("error", reason=self._reason(error))
        finally:
            self._lock.release()

    def apply_on_exit(self, restart=False):
        """Verify bytes, then arm after cleanup; no network or worker wait.

        The helper's 60-second exit deadline begins only after hashing finishes.
        """
        if not self._lock.acquire(blocking=False):
            return False
        try:
            if not self.installed or self._pending is None:
                return False
            self._verify_package(self._pending)
            self._manager.wait_exit_then_apply_updates(
                _sdk_asset(self._pending), silent=True, restart=bool(restart), restart_args=[])
            self._pending = None
            return True
        except Exception as error:
            self.reason = self._reason(error)
            if self._pending is not None:
                try:
                    self._verify_package(self._pending)
                except (OSError, ValueError):
                    self._forget_pending()
            return False
        finally:
            self._lock.release()
