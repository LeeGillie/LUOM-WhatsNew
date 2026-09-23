"""Tests for the GitHub update check and the in-place installer. Offline:
GitHub is replaced by canned answers, and the "new release" is a tiny .pyz
built here that reports whatever version the test wants."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
import zipapp
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from wecreat_index import __version__, update  # noqa: E402

ZIP_URL = "https://github.com/x/y/releases/download/v9.9.0/LUOM-WhatsNew-9.9.0.zip"


def fake_pyz(version: str) -> bytes:
    """A .pyz whose `version` command answers like the real one."""
    tmp = tempfile.mkdtemp()
    try:
        src = os.path.join(tmp, "src")
        os.makedirs(src)
        with open(os.path.join(src, "__main__.py"), "w", encoding="utf-8") as fh:
            fh.write("print(\"LUOM What's New %s\")\n" % version)
        target = os.path.join(tmp, "app.pyz")
        zipapp.create_archive(src, target)
        with open(target, "rb") as fh:
            return fh.read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def release_zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, (content, executable) in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (stat.S_IFREG | (0o755 if executable else 0o644)) << 16
            zf.writestr(info, content)
    return buf.getvalue()


def release_json(version: str, data: bytes, digest: str = None) -> dict:
    return {
        "tag_name": "v" + version,
        "html_url": "https://github.com/x/y/releases/tag/v" + version,
        "published_at": "2026-09-30T12:00:00Z",
        "assets": [
            {"name": "notes.txt", "browser_download_url": "https://example.invalid/notes.txt"},
            {"name": "LUOM-WhatsNew-%s.zip" % version, "browser_download_url": ZIP_URL,
             "size": len(data), "digest": digest or "sha256:" + hashlib.sha256(data).hexdigest()},
        ],
    }


class FakeGitHub:
    """Stands in for update._get: the API answer, then the zip."""

    def __init__(self, release: dict, data: bytes) -> None:
        self.release, self.data, self.calls = release, data, []

    def __call__(self, url, accept):
        self.calls.append(url)
        body = self.data if url == ZIP_URL else json.dumps(self.release).encode("utf-8")
        return io.BytesIO(body)


class VersionTests(unittest.TestCase):
    def test_compare(self):
        self.assertTrue(update.is_newer("1.0.1", "1.0.0"))
        self.assertTrue(update.is_newer("v1.10.0", "1.9.9"))      # numeric, not text order
        self.assertFalse(update.is_newer("1.0", "1.0.0"))         # same version
        self.assertFalse(update.is_newer("0.9.9", "1.0.0"))
        self.assertFalse(update.is_newer("1.1.0-beta", "1.0.0"))  # not a plain version: ignored
        self.assertFalse(update.is_newer("", "1.0.0"))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = tempfile.mkdtemp()
        self.app_dir = tempfile.mkdtemp()
        self.zip = release_zip({"LUOM-WhatsNew/LUOM-WhatsNew.pyz": (fake_pyz("9.9.0"), True)})
        self.github = FakeGitHub(release_json("9.9.0", self.zip), self.zip)
        patches = [mock.patch.object(update, "_get", self.github),
                   mock.patch.object(update, "app_dir", return_value=self.app_dir)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)
        shutil.rmtree(self.app_dir, ignore_errors=True)

    def test_newer_release_found_and_cached(self):
        info = update.check(self.data_dir)
        self.assertTrue(info["newer"])
        self.assertEqual(info["latest"], "9.9.0")
        self.assertEqual(info["current"], __version__)
        self.assertEqual(info["asset_url"], ZIP_URL)
        self.assertTrue(info["can_install"], info["install_blocker"])
        update.check(self.data_dir)                 # served from the cache
        self.assertEqual(len(self.github.calls), 1)
        update.check(self.data_dir, force=True)     # "Check for updates" asks again
        self.assertEqual(len(self.github.calls), 2)

    def test_same_version_is_not_newer(self):
        self.github.release = release_json(__version__, self.zip)
        self.assertFalse(update.check(self.data_dir)["newer"])

    def test_offline_is_quiet(self):
        with mock.patch.object(update, "_get", side_effect=OSError("no network")):
            info = update.check(self.data_dir)
        self.assertFalse(info["newer"])
        self.assertIn("error", info)
        self.assertFalse(os.path.exists(os.path.join(self.data_dir, update.CACHE_FILENAME)))

    def test_cache_from_another_version_is_ignored(self):
        with open(os.path.join(self.data_dir, update.CACHE_FILENAME), "w", encoding="utf-8") as fh:
            json.dump({"current": "0.0.1", "checked_at": "2999-01-01T00:00:00", "latest": "0.0.2"}, fh)
        self.assertEqual(update.check(self.data_dir)["latest"], "9.9.0")

    def test_source_checkout_cannot_install(self):
        with mock.patch.object(update, "app_dir", return_value=None):
            info = update.check(self.data_dir)
        self.assertTrue(info["newer"])
        self.assertFalse(info["can_install"])
        self.assertIn("source", info["install_blocker"])

    def test_release_without_checksum_cannot_install(self):
        release = release_json("9.9.0", self.zip)
        del release["assets"][1]["digest"]
        self.github.release = release
        self.assertFalse(update.check(self.data_dir)["can_install"])


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.old = {
            "LUOM-WhatsNew.pyz": fake_pyz(__version__),
            "README.txt": b"old readme",
            "LUOM-WhatsNew.ico": b"icon",
            "my-notes.txt": b"the user's own file",
        }
        for name, content in self.old.items():
            with open(os.path.join(self.folder, name), "wb") as fh:
                fh.write(content)

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def read(self, name):
        with open(os.path.join(self.folder, name), "rb") as fh:
            return fh.read()

    def run_install(self, files, version="9.9.0", digest=None):
        data = release_zip(files)
        info = update._summarise(release_json(version, data, digest))
        with mock.patch.object(update, "_get", FakeGitHub({}, data)):
            return update.install(info, self.folder)

    def assert_untouched(self):
        for name, content in self.old.items():
            self.assertEqual(self.read(name), content, name)
        self.assertEqual(sorted(os.listdir(self.folder)), sorted(self.old))   # no leftovers

    def test_swaps_in_the_new_files(self):
        new_pyz = fake_pyz("9.9.0")
        changed = self.run_install({
            "LUOM-WhatsNew/LUOM-WhatsNew.pyz": (new_pyz, True),
            "LUOM-WhatsNew/README.txt": (b"new readme", False),
            "LUOM-WhatsNew/LUOM-WhatsNew.ico": (b"icon", False),
            "LUOM-WhatsNew/LICENSE.txt": (b"MIT", False),
            "LUOM-WhatsNew/start-luom-whatsnew.sh": (b"#!/bin/sh\n", True),
        })
        self.assertEqual(self.read("LUOM-WhatsNew.pyz"), new_pyz)
        self.assertEqual(self.read("README.txt"), b"new readme")
        self.assertEqual(self.read("LICENSE.txt"), b"MIT")
        self.assertEqual(self.read("my-notes.txt"), b"the user's own file")
        self.assertNotIn("LUOM-WhatsNew.ico", changed)            # identical: left alone
        self.assertEqual(changed[-1], "LUOM-WhatsNew.pyz")         # the program goes last
        self.assertFalse([n for n in os.listdir(self.folder) if n.endswith(".new")])
        if os.name == "posix":
            self.assertTrue(os.stat(os.path.join(self.folder, "start-luom-whatsnew.sh")).st_mode & stat.S_IXUSR)

    def test_checksum_mismatch_changes_nothing(self):
        with self.assertRaisesRegex(update.UpdateError, "checksum"):
            self.run_install({"LUOM-WhatsNew/LUOM-WhatsNew.pyz": (fake_pyz("9.9.0"), True)},
                             digest="sha256:" + "0" * 64)
        self.assert_untouched()

    def test_program_reporting_the_wrong_version_changes_nothing(self):
        with self.assertRaisesRegex(update.UpdateError, "reports version"):
            self.run_install({
                "LUOM-WhatsNew/LUOM-WhatsNew.pyz": (fake_pyz("1.2.3"), True),
                "LUOM-WhatsNew/README.txt": (b"new readme", False),
            })
        self.assert_untouched()

    def test_unexpected_paths_are_refused(self):
        for bad in ("LUOM-WhatsNew/../evil.txt", "LUOM-WhatsNew/sub/file.txt", "other/file.txt"):
            with self.subTest(bad=bad), self.assertRaisesRegex(update.UpdateError, "unexpected"):
                self.run_install({"LUOM-WhatsNew/LUOM-WhatsNew.pyz": (fake_pyz("9.9.0"), True),
                                  bad: (b"x", False)})
        self.assert_untouched()

    def test_zip_without_the_program_is_refused(self):
        with self.assertRaisesRegex(update.UpdateError, "does not contain"):
            self.run_install({"LUOM-WhatsNew/README.txt": (b"new readme", False)})
        self.assert_untouched()

    def test_not_newer_is_refused(self):
        with self.assertRaisesRegex(update.UpdateError, "latest"):
            self.run_install({"LUOM-WhatsNew/LUOM-WhatsNew.pyz": (fake_pyz(__version__), True)},
                             version=__version__)
        self.assert_untouched()


class RestartTests(unittest.TestCase):
    def test_restart_keeps_the_options_but_not_the_browser(self):
        cmd = update.restart_command(["--port", "9000", "--no-browser"])
        self.assertEqual(cmd[0], sys.executable)
        self.assertEqual(cmd[2:], ["serve", "--port", "9000", "--no-browser"])


class PageTests(unittest.TestCase):
    def test_update_setting_is_on_the_page_and_on_by_default(self):
        import pkgutil
        html = pkgutil.get_data("wecreat_index", "ui/index.html").decode("utf-8")
        self.assertIn('id="optCheckUpdates"', html)
        self.assertIn('id="updateBar"', html)
        self.assertIn("Nothing about you or your data is sent", html)
        js = pkgutil.get_data("wecreat_index", "ui/app.js").decode("utf-8")
        self.assertIn('readPref(PREF_KEYS.checkUpdates, "1") === "1"', js)


if __name__ == "__main__":
    unittest.main()
