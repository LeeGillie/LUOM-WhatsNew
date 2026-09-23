"""Offline tests for the data-folder selection and the legacy migration."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wecreat_index import paths  # noqa: E402


class DataDirTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_env_override_wins(self):
        target = os.path.join(self.tmp, "custom")
        with mock.patch.dict(os.environ, {paths.ENV_VAR: target}):
            self.assertEqual(paths.default_data_dir(), os.path.abspath(target))
        self.assertTrue(os.path.isdir(target))

    def test_windows_uses_programdata(self):
        with mock.patch.object(paths.sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {"PROGRAMDATA": self.tmp}, clear=False):
            os.environ.pop(paths.ENV_VAR, None)
            os.environ.pop(paths.OLD_ENV_VAR, None)
            self.assertEqual(paths.candidate_dirs()[0], os.path.join(self.tmp, "LUOM-WhatsNew"))

    def test_macos_uses_users_shared(self):
        with mock.patch.object(paths.sys, "platform", "darwin"), \
                mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(paths.ENV_VAR, None)
            self.assertEqual(paths.candidate_dirs()[0], "/Users/Shared/LUOM-WhatsNew")

    def test_linux_falls_back_to_xdg(self):
        with mock.patch.object(paths.sys, "platform", "linux"), \
                mock.patch.dict(os.environ, {"XDG_DATA_HOME": self.tmp}, clear=False):
            os.environ.pop(paths.ENV_VAR, None)
            self.assertEqual(paths.candidate_dirs(), [os.path.join(self.tmp, "luom-whatsnew")])

    def test_old_env_var_is_still_honoured(self):
        target = os.path.join(self.tmp, "old-style")
        with mock.patch.dict(os.environ, {paths.OLD_ENV_VAR: target}):
            os.environ.pop(paths.ENV_VAR, None)
            self.assertEqual(paths.candidate_dirs(), [os.path.abspath(target)])

    def test_unwritable_shared_dir_falls_back(self):
        good = os.path.join(self.tmp, "user")
        with mock.patch.object(paths, "candidate_dirs", return_value=["shared", good]), \
                mock.patch.object(paths, "_usable", side_effect=lambda p: p == good):
            self.assertEqual(paths.default_data_dir(), good)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.legacy = os.path.join(self.tmp, "legacy")
        self.target = os.path.join(self.tmp, "target")
        os.makedirs(self.legacy)
        for name in paths.DATA_FILES:
            with open(os.path.join(self.legacy, name), "w") as fh:
                json.dump({"file": name}, fh)

        # Point the migration at temp folders only - never the real
        # C:\ProgramData\WhatsNewWecreat or ./data of this machine.
        self.old_app = os.path.join(self.tmp, "WhatsNewWecreat")
        self.fake_dirs = mock.patch.object(
            paths, "old_data_dirs", return_value=[self.old_app, self.legacy])
        self.fake_dirs.start()

    def tearDown(self):
        self.fake_dirs.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_moves_old_output_once(self):
        with mock.patch.object(paths, "LEGACY_DATA_DIR", self.legacy):
            moved = paths.migrate_legacy_data(self.target)
            self.assertEqual(sorted(moved), sorted(paths.DATA_FILES))
            self.assertTrue(paths.has_data(self.target))
            self.assertFalse(os.path.exists(self.legacy))  # emptied and removed
            self.assertEqual(paths.migrate_legacy_data(self.target), [])

    def test_moves_data_from_the_old_program_name_first(self):
        os.makedirs(self.old_app)
        for name in paths.CARRY_OVER_FILES + ("whatsnewwecreat.log",):
            with open(os.path.join(self.old_app, name), "w") as fh:
                fh.write("{}")
        moved = paths.migrate_legacy_data(self.target)
        self.assertEqual(sorted(moved), sorted(paths.CARRY_OVER_FILES))
        self.assertTrue(os.path.isfile(os.path.join(self.target, "config.json")))
        self.assertFalse(os.path.exists(self.old_app))    # log removed, folder gone
        self.assertTrue(os.path.exists(self.legacy))      # untouched: first match wins

    def test_default_old_dirs_include_previous_name_and_project_data(self):
        self.fake_dirs.stop()
        try:
            dirs = paths.old_data_dirs()
        finally:
            self.fake_dirs.start()
        self.assertTrue(any(d.rstrip("/\\").endswith("WhatsNewWecreat") for d in dirs))
        self.assertIn(paths.LEGACY_DATA_DIR, dirs)

    def test_never_overwrites_existing_data(self):
        os.makedirs(self.target)
        with open(os.path.join(self.target, "index.json"), "w") as fh:
            fh.write('{"keep": true}')
        with mock.patch.object(paths, "LEGACY_DATA_DIR", self.legacy):
            self.assertEqual(paths.migrate_legacy_data(self.target), [])
        with open(os.path.join(self.target, "index.json")) as fh:
            self.assertIn("keep", fh.read())


if __name__ == "__main__":
    unittest.main()
