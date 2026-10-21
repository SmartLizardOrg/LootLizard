"""Release discovery/staging contracts using real temporary package bytes."""
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import threading
import unittest
from unittest import mock
import urllib.error
import urllib.request

from lootlizard import app_updates as updates

PACKAGE_BYTES = b"verified LootLizard package fixture\n"*100


def asset(version="0.9.0", **overrides):
    values = dict(PackageId=updates.PACKAGE_ID, Version=version, Type="Full",
                  FileName=f"{updates.PACKAGE_ID}-{version}-full.nupkg",
                  SHA256=hashlib.sha256(PACKAGE_BYTES).hexdigest(), Size=len(PACKAGE_BYTES))
    values.update(overrides)
    return SimpleNamespace(**values)


def release(target=None):
    target = target or asset()
    base = updates.REPOSITORY_URL+"/releases/download/v"+target.Version
    return dict(draft=False, prerelease=False, tag_name="v"+target.Version,
                html_url=updates.REPOSITORY_URL+"/releases/tag/v"+target.Version,
                assets=[dict(name="releases.win.json", size=400, browser_download_url=base+"/releases.win.json"),
                        dict(name=target.FileName, size=target.Size, digest="sha256:"+target.SHA256,
                             browser_download_url=base+"/"+target.FileName)])


class AppUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.packages = self.root/"install/packages"
        self.packages.mkdir(parents=True)
        self.cache = self.root/"preferences/app-update.json"
        self.manager = mock.Mock()
        self.manager.get_current_version.return_value = "0.8.0"
        # Real 1.2.161 pending assets have no hashes. They are NOT our trust input.
        self.manager.get_update_pending_restart.return_value = asset(SHA256="", Size=1)
        self.target = asset()
        self.info = SimpleNamespace(TargetFullRelease=self.target, IsDowngrade=False)
        self.manager.check_for_updates.return_value = self.info
        def download(info):
            path = self.packages/info.TargetFullRelease.FileName
            if not path.exists(): path.write_bytes(PACKAGE_BYTES)
        self.manager.download_updates.side_effect = download
        self.installed = mock.patch.object(updates, "_installed_manager", return_value=self.manager).start()
        self.factory = mock.patch.object(updates, "_manager_for_source", return_value=self.manager).start()
        mock.patch.object(updates, "_installed_packages_dir", return_value=self.packages).start()
        self.latest = mock.patch.object(updates, "_fetch_latest_release", return_value=release()).start()
        mock.patch.object(updates, "_sdk_asset",
                          side_effect=lambda p: SimpleNamespace(PackageId=updates.PACKAGE_ID, Type="Full", **asdict(p))).start()
        self.addCleanup(mock.patch.stopall)
        self.client = updates.AppUpdateClient(cache_path=self.cache)

    def download(self):
        result = self.client.check_and_download()
        self.assertEqual((result.status, result.version), ("ready", "0.9.0"), result.reason)
        return result

    def test_verified_download_never_arms_helper_and_close_arms_remote_expected_asset(self):
        self.download()
        self.assertTrue(self.client.has_pending)
        self.manager.get_update_pending_restart.assert_not_called()
        self.manager.wait_exit_then_apply_updates.assert_not_called()
        self.assertTrue(self.client.apply_on_exit())
        call = self.manager.wait_exit_then_apply_updates.call_args
        self.assertEqual(call.args[0].SHA256, self.target.SHA256)
        self.assertEqual(call.kwargs, dict(silent=True, restart=False, restart_args=[]))
        self.assertFalse(self.client.has_pending)
        self.assertFalse(self.client.apply_on_exit())

    def test_explicit_restart_does_not_replay_launch_pubg_arguments(self):
        self.download()
        self.assertTrue(self.client.apply_on_exit(restart=True))
        self.assertEqual(self.manager.wait_exit_then_apply_updates.call_args.kwargs,
                         dict(silent=True, restart=True, restart_args=[]))

    def test_latest_release_source_is_pinned_to_that_tag(self):
        self.download()
        self.factory.assert_called_once_with(updates.REPOSITORY_URL+"/releases/download/v0.9.0")

    def test_offline_restart_recovers_only_cached_expected_metadata_and_reverified_bytes(self):
        self.download()
        client = updates.AppUpdateClient(cache_path=self.cache)
        self.latest.side_effect = OSError("offline")
        result = client.check_and_download()
        self.assertEqual((result.status, result.version), ("ready", "0.9.0"))
        self.assertTrue(client.apply_on_exit())
        self.assertIn("previously verified", result.reason)
        self.manager.get_update_pending_restart.assert_not_called()

    def test_native_hashless_pending_alone_is_never_treated_as_verified(self):
        self.latest.side_effect = OSError("offline")
        self.assertEqual(self.client.check_and_download().status, "error")
        self.assertFalse(self.client.has_pending)
        self.assertFalse(self.client.apply_on_exit())

    def test_current_or_older_latest_release_never_downloads_or_arms(self):
        for version in ("0.8.0", "0.7.0"):
            self.latest.return_value = release(asset(version))
            self.assertEqual(self.client.check_and_download().status, "current")
        self.manager.download_updates.assert_not_called()
        self.assertFalse(self.client.apply_on_exit())

    def test_uninstalled_constructor_and_checks_never_use_network(self):
        self.installed.return_value = None
        client = updates.AppUpdateClient(cache_path=self.cache)
        self.assertFalse(client.installed)
        self.assertEqual(client.check_and_download().status, "unavailable")
        self.assertFalse(client.apply_on_exit())
        self.latest.assert_not_called()

    def test_missing_install_manifest_fails_soft(self):
        self.installed.side_effect = RuntimeError("No manifest")
        client = updates.AppUpdateClient(cache_path=self.cache)
        self.assertFalse(client.installed)
        self.assertEqual(client.check_and_download().reason, "No manifest")

    def test_first_offline_error_leaves_application_unchanged(self):
        self.latest.side_effect = OSError("offline")
        self.assertEqual((self.client.check_and_download().status, self.client.has_pending), ("error", False))
        self.assertFalse(self.client.apply_on_exit())

    def test_partial_or_wrong_hash_download_never_becomes_ready(self):
        for content in (PACKAGE_BYTES[:-1], b"X"+PACKAGE_BYTES[1:]):
            self.manager.download_updates.side_effect = lambda _, content=content: (self.packages/self.target.FileName).write_bytes(content)
            self.assertEqual(self.client.check_and_download().status, "error")
            self.assertFalse(self.client.has_pending)
        self.manager.wait_exit_then_apply_updates.assert_not_called()
        self.assertFalse(self.cache.exists())

    def test_existing_corrupt_package_is_removed_before_sdk_can_skip_it(self):
        path = self.packages/self.target.FileName
        path.write_bytes(b"X"+PACKAGE_BYTES[1:])
        def download(_):
            self.assertFalse(path.exists())
            path.write_bytes(PACKAGE_BYTES)
        self.manager.download_updates.side_effect = download
        self.download()
        self.assertEqual(path.read_bytes(), PACKAGE_BYTES)

    def test_existing_correct_package_is_still_verified_after_sdk_skip(self):
        path = self.packages/self.target.FileName
        path.write_bytes(PACKAGE_BYTES)
        self.manager.download_updates.side_effect = lambda _: None
        self.download()

    def test_altering_staged_bytes_after_download_blocks_apply(self):
        self.download()
        (self.packages/self.target.FileName).write_bytes(b"X"+PACKAGE_BYTES[1:])
        self.assertFalse(self.client.apply_on_exit())
        self.assertFalse(self.client.has_pending)
        self.manager.wait_exit_then_apply_updates.assert_not_called()

    def test_altering_ready_package_blocks_fast_ready_path_too(self):
        self.download()
        (self.packages/self.target.FileName).write_bytes(PACKAGE_BYTES[:-2])
        self.assertEqual(self.client.check_and_download().status, "error")
        self.assertFalse(self.client.has_pending)

    def test_corrupt_expected_cache_or_missing_package_cannot_recover(self):
        self.download()
        value = json.loads(self.cache.read_text())
        for mutate in (lambda v: v.update(repository="https://evil.invalid"),
                       lambda v: v.update(filename="../outside-full.nupkg"),
                       lambda v: v.update(sha256=""),
                       lambda v: v.update(version="0.7.0"),
                       lambda v: v.update(scope="ci:other"),
                       lambda v: v.update(size=True)):
            changed = dict(value)
            mutate(changed)
            self.cache.write_text(json.dumps(changed))
            client = updates.AppUpdateClient(cache_path=self.cache)
            self.latest.side_effect = OSError("offline")
            self.assertEqual(client.check_and_download().status, "error")
        self.cache.write_text(json.dumps(value))
        (self.packages/self.target.FileName).unlink()
        client = updates.AppUpdateClient(cache_path=self.cache)
        self.assertEqual(client.check_and_download().status, "error")

    def test_cache_replace_failure_does_not_mark_unpersisted_download_ready(self):
        with mock.patch.object(updates.os, "replace", side_effect=OSError("locked")):
            self.assertEqual(self.client.check_and_download().status, "error")
        self.assertFalse(self.client.has_pending)
        self.assertFalse(list(self.cache.parent.glob("*.tmp")))

    def test_invalid_or_nonstable_target_is_rejected_before_download(self):
        cases = [asset("0.8.0"), asset("0.7.0"), asset("0.9.0-beta.1"), asset("01.0.0"),
                 asset(PackageId="AnotherApp"), asset(Type="Delta"),
                 asset(FileName="../escape-full.nupkg"), asset(FileName="C:/escape-full.nupkg"),
                 asset(FileName="other-0.9.0-full.nupkg"), asset(SHA256=""),
                 asset(FileName=f"{updates.PACKAGE_ID}-1.0.0-full.nupkg"),
                 asset(SHA256="q"*64), asset(Size=0), asset(Size=True),
                 asset(Size=updates.MAX_PACKAGE_BYTES+1)]
        for target in cases:
            with self.subTest(target=target):
                self.info.TargetFullRelease = target
                self.assertEqual(self.client.check_and_download().status, "error")
                self.assertFalse(self.client.has_pending)
        self.manager.download_updates.assert_not_called()

    def test_feed_target_must_match_latest_stable_tag_and_github_asset(self):
        cases = []
        value = release(); value["tag_name"] = "v1.0.0"; value["html_url"] = updates.REPOSITORY_URL+"/releases/tag/v1.0.0"
        for item in value["assets"]: item["browser_download_url"] = item["browser_download_url"].replace("/v0.9.0/", "/v1.0.0/")
        cases.append(value)
        for key, replacement in (("size", 12), ("browser_download_url", "https://evil.invalid/package"),
                                 ("digest", "sha256:"+"b"*64)):
            value = release(); value["assets"][1][key] = replacement; cases.append(value)
        for value in cases:
            self.latest.return_value = value
            self.assertEqual(self.client.check_and_download().status, "error")
        self.manager.download_updates.assert_not_called()

    def test_draft_prerelease_untrusted_missing_or_duplicate_feed_rejected(self):
        cases = []
        for key, replacement in (("draft", True), ("prerelease", True), ("tag_name", "v0.9.0-beta"),
                                 ("tag_name", "0.9.0"), ("html_url", "https://evil.invalid/release")):
            value = release(); value[key] = replacement; cases.append(value)
        value = release(); value["assets"] = value["assets"][1:]; cases.append(value)
        value = release(); value["assets"].append(value["assets"][0]); cases.append(value)
        value = release(); value["assets"][0]["browser_download_url"] = "https://evil.invalid/feed"; cases.append(value)
        value = release(); value["assets"][0]["size"] = updates.MAX_RELEASE_BYTES+1; cases.append(value)
        for value in cases:
            self.latest.return_value = value
            self.assertEqual(self.client.check_and_download().status, "error")
        self.manager.download_updates.assert_not_called()

    def test_downgrade_flag_rejected_even_with_a_higher_version(self):
        self.info.IsDowngrade = True
        self.assertEqual(self.client.check_and_download().status, "error")
        self.manager.download_updates.assert_not_called()

    def test_close_during_download_does_not_wait_or_arm_helper(self):
        started, finish = threading.Event(), threading.Event()
        def download(_):
            started.set()
            finish.wait(3)
            (self.packages/self.target.FileName).write_bytes(PACKAGE_BYTES)
        self.manager.download_updates.side_effect = download
        thread = threading.Thread(target=self.client.check_and_download)
        thread.start()
        try:
            self.assertTrue(started.wait(2))
            self.assertFalse(self.client.apply_on_exit())
            self.assertEqual(self.client.check_and_download().status, "busy")
            self.manager.wait_exit_then_apply_updates.assert_not_called()
        finally:
            finish.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(self.client.has_pending)

    def test_failed_helper_launch_retains_verified_update_for_retry(self):
        self.download()
        self.manager.wait_exit_then_apply_updates.side_effect = OSError("helper unavailable")
        self.assertFalse(self.client.apply_on_exit())
        self.assertTrue(self.client.has_pending)
        self.assertEqual(self.client.reason, "helper unavailable")

    def test_ci_local_feed_is_double_gated_and_scoped_inside_runner_temp(self):
        source = self.root/"feed"; source.mkdir()
        for environment in ({}, {"GITHUB_ACTIONS":"true"}, {"GITHUB_ACTIONS":"true","LOOTLIZARD_INSTALL_TEST":"1"}):
            with mock.patch.dict("os.environ", environment, clear=True):
                with self.assertRaises(ValueError):
                    updates.AppUpdateClient(_ci_source_dir=source, cache_path=self.cache)
        environment = dict(GITHUB_ACTIONS="true", LOOTLIZARD_INSTALL_TEST="1", RUNNER_TEMP=str(self.root))
        with mock.patch.dict("os.environ", environment, clear=True):
            with self.assertRaises(ValueError): updates.AppUpdateClient(_ci_source_dir=self.root, cache_path=self.cache)
            with self.assertRaises(ValueError): updates.AppUpdateClient(_ci_source_dir=self.root.parent, cache_path=self.cache)
            client = updates.AppUpdateClient(_ci_source_dir=source, cache_path=self.cache)
            self.assertEqual(client.check_and_download().status, "ready")
            self.factory.assert_called_with(str(source.resolve()))
            self.latest.assert_not_called()


class SdkConfigurationTests(unittest.TestCase):
    def test_source_run_never_initializes_sdk(self):
        with mock.patch.object(updates.sys, "frozen", False, create=True), mock.patch.dict("sys.modules", {"velopack":None}):
            self.assertIsNone(updates._installed_manager())
            updates.bootstrap()

    def test_installed_source_uses_explicit_timeout_and_full_stable_packages(self):
        sdk = mock.Mock()
        sdk.UpdateManager.return_value.get_current_version.return_value = "0.8.0"
        sdk.UpdateManager.return_value.get_is_portable.return_value = False
        sdk.UpdateManager.return_value.get_app_id.return_value = updates.PACKAGE_ID
        with mock.patch.object(updates.sys, "platform", "win32"), mock.patch.object(updates.sys, "frozen", True, create=True), mock.patch.dict("sys.modules", {"velopack":sdk}):
            updates._installed_manager()
            sdk.HttpOptions.assert_called_once_with(Headers=[], TimeoutMilliseconds=120000)
            sdk.UpdateOptions.assert_called_once_with(AllowVersionDowngrade=False, MaximumDeltasBeforeFallback=-1, ExplicitChannel="win")
            updates.bootstrap()
            sdk.App.return_value.set_auto_apply_on_startup.assert_called_once_with(False)
            sdk.App.return_value.set_auto_apply_on_startup.return_value.run.assert_called_once_with()

    def test_portable_and_other_application_manifest_rejected(self):
        sdk = mock.Mock()
        with mock.patch.dict("sys.modules", {"velopack":sdk}):
            sdk.UpdateManager.return_value.get_is_portable.return_value = True
            self.assertIsNone(updates._manager_for_source(updates.REPOSITORY_URL))
            sdk.UpdateManager.return_value.get_is_portable.return_value = False
            sdk.UpdateManager.return_value.get_app_id.return_value = "AnotherApp"
            self.assertIsNone(updates._manager_for_source(updates.REPOSITORY_URL))


class ReleaseHttpTests(unittest.TestCase):
    def test_fixed_rest_url_timeout_and_body_limit(self):
        response = io.BytesIO(json.dumps(release()).encode())
        response.getcode = lambda: 200
        response.headers = {}
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(updates.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(updates._fetch_latest_release()["tag_name"], "v0.9.0")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, updates.LATEST_RELEASE_URL)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 8)
        self.assertTrue(response.closed)

    def test_declared_and_streamed_oversize_metadata_rejected(self):
        for body, headers in ((b"{}", {"Content-Length":str(updates.MAX_RELEASE_BYTES+1)}),
                              (b" "*(updates.MAX_RELEASE_BYTES+1), {})):
            response = io.BytesIO(body); response.getcode=lambda:200; response.headers=headers
            with mock.patch.object(updates.urllib.request, "build_opener") as factory:
                factory.return_value.open.return_value=response
                with self.assertRaises(ValueError): updates._fetch_latest_release()
            self.assertTrue(response.closed)

    def test_redirects_rejected_without_contacting_other_origin(self):
        request = urllib.request.Request(updates.LATEST_RELEASE_URL)
        with self.assertRaises(urllib.error.HTTPError):
            updates._NoRedirects().redirect_request(request, io.BytesIO(), 302, "redirect", {}, "https://evil.invalid")

    def test_duplicate_release_keys_rejected(self):
        response=io.BytesIO(b'{"draft":false,"draft":true}')
        response.getcode=lambda:200; response.headers={}
        with mock.patch.object(updates.urllib.request, "build_opener") as factory:
            factory.return_value.open.return_value=response
            with self.assertRaises(ValueError): updates._fetch_latest_release()


if __name__ == "__main__":
    unittest.main()
