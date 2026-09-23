"""Tests for the packaged entry point, the .pyz build and the server's
second-launch handling. Offline; the .pyz test runs a child Python."""

from __future__ import annotations

import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import build  # noqa: E402
from wecreat_index import __version__, app, paths, server  # noqa: E402


class DispatchTests(unittest.TestCase):
    def test_scan_goes_to_the_cli(self):
        with mock.patch("wecreat_index.cli.main", return_value=0) as scan:
            self.assertEqual(app.main(["scan", "--dry-run"]), 0)
        scan.assert_called_once_with(["--dry-run"])

    def test_default_is_the_web_ui(self):
        with mock.patch("wecreat_index.server.main", return_value=0) as serve:
            app.main(["--port", "9000"])
        serve.assert_called_once_with(["--port", "9000"])

    def test_serve_spelled_out(self):
        with mock.patch("wecreat_index.server.main", return_value=0) as serve:
            app.main(["serve", "--no-browser"])
        serve.assert_called_once_with(["--no-browser"])

    def test_unknown_command(self):
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(app.main(["frobnicate"]), 2)

    def test_windowless_output_goes_to_a_log_file(self):
        tmp = tempfile.mkdtemp()
        try:
            with mock.patch.object(sys, "stderr", None), mock.patch.object(sys, "stdout", None), \
                    mock.patch("wecreat_index.paths.default_data_dir", return_value=tmp):
                app._redirect_output_if_windowless()
                print("hello from pythonw")
                sys.stdout.flush()
                stream = sys.stdout
            stream.close()
            with open(os.path.join(tmp, app.LOG_FILENAME), encoding="utf-8") as fh:
                self.assertIn("hello from pythonw", fh.read())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ConfigAndCommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_config_in_data_folder_wins(self):
        cfg = os.path.join(self.tmp, "config.json")
        with open(cfg, "w") as fh:
            fh.write("{}")
        self.assertEqual(paths.find_config(self.tmp), cfg)

    def test_source_checkout_falls_back_to_project_config(self):
        self.assertEqual(paths.find_config(self.tmp), os.path.join(ROOT, "config.json"))

    def test_scan_command_from_source(self):
        cmd = paths.scan_command("OUT", None)
        self.assertEqual(cmd[1:3], ["-m", "wecreat_index"])
        self.assertNotIn("--config", cmd)

    def test_scan_command_from_pyz(self):
        with mock.patch.object(paths, "ZIPPED", True), \
                mock.patch.object(paths, "PROJECT_ROOT", "/x/LUOM-WhatsNew.pyz"):
            cmd = paths.scan_command("OUT", "cfg.json")
        self.assertEqual(cmd[1:3], ["/x/LUOM-WhatsNew.pyz", "scan"])
        self.assertEqual(cmd[-2:], ["--config", "cfg.json"])


class BuiltInRulesTests(unittest.TestCase):
    def test_config_json_matches_the_built_in_rules(self):
        """The download runs on the built-ins, the repo on config.json - keep them equal."""
        import json
        from wecreat_index.config import Config
        with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as fh:
            data = json.load(fh)
        from_file, built_in = Config(data), Config({})
        for key in data:
            if key.startswith("_"):
                continue
            self.assertEqual(getattr(from_file, key), getattr(built_in, key),
                             "config.json %r differs from config.py" % key)


class NoticeTests(unittest.TestCase):
    """The 'LUOM does not maintain WeCreat's knowledge base' notice must not get lost."""

    def test_index_json_carries_the_notice(self):
        from wecreat_index import NOTICE
        from wecreat_index.config import Config
        from wecreat_index.store import build_index
        idx = build_index([], {"new": [], "updated": [], "no_longer_matching": []},
                          Config({}), {"runs": 0}, scanned=0)
        self.assertEqual(idx["notice"], NOTICE)
        self.assertIn("does not write, maintain, host or own", idx["notice"])
        self.assertIn("not affiliated with", idx["notice"])
        self.assertIn("help.wecreat.com", idx["content_owner"])

    def test_page_states_it_everywhere(self):
        import pkgutil
        html = pkgutil.get_data("wecreat_index", "ui/index.html").decode("utf-8")
        for phrase in (
            'id="about"',                                     # About dialog
            'id="aboutBtn"',                                  # header button to open it
            "LUOM does not write, maintain, host or own WeCreat's knowledge base",
            "not affiliated with, endorsed by or sponsored by WeCreat",
            "indexer, searcher and cataloger",
            'class="source-note"',                            # note above the list
            "Independent LUOM index of WeCreat's public help articles",
        ):
            self.assertIn(phrase, html)
        js = pkgutil.get_data("wecreat_index", "ui/app.js").decode("utf-8")
        self.assertIn("Read on help.wecreat.com", js)

    def test_viewer_options_are_on_the_page(self):
        import pkgutil
        html = pkgutil.get_data("wecreat_index", "ui/index.html").decode("utf-8")
        self.assertIn('id="optShowOther"', html)
        self.assertIn('id="optLinkMode"', html)
        js = pkgutil.get_data("wecreat_index", "ui/app.js").decode("utf-8")
        # Non-Lumos Ultra articles are hidden unless the viewer opts in.
        self.assertIn('readPref(PREF_KEYS.showOther, "0") === "1"', js)

    def test_cli_help_shows_the_notice(self):
        out = io.StringIO()
        with mock.patch("sys.stdout", out), self.assertRaises(SystemExit):
            from wecreat_index.cli import parse_args
            parse_args(["--help"])
        self.assertIn("does not write, maintain, host or own", " ".join(out.getvalue().split()))


class PyzBuildTests(unittest.TestCase):
    """Build the real archive and run it with a child interpreter."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.pyz = os.path.join(cls.tmp, "LUOM-WhatsNew.pyz")
        build.build_pyz(cls.pyz)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def run_pyz(self, *args):
        return subprocess.run(
            [sys.executable, self.pyz] + list(args),
            cwd=self.tmp, capture_output=True, text=True, timeout=60,
        )

    def test_version(self):
        out = self.run_pyz("version")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(__version__, out.stdout)

    def test_scan_help(self):
        out = self.run_pyz("scan", "--help")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("--out", out.stdout)

    def test_ui_files_are_readable_inside_the_zip(self):
        code = (
            "import sys; sys.path.insert(0, sys.argv[1]); import pkgutil;"
            "from wecreat_index import paths;"
            "print(paths.ZIPPED, all(pkgutil.get_data('wecreat_index', 'ui/' + n)"
            " for n in ('index.html', 'app.js', 'app.css', 'assets/favicon-64.png',"
            " 'assets/logo-256.webp', 'assets/splash.webp')))"
        )
        out = subprocess.run([sys.executable, "-c", code, self.pyz],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.split(), ["True", "True"], out.stderr)

    def test_no_caches_or_tests_are_packed(self):
        import zipfile
        names = zipfile.ZipFile(self.pyz).namelist()
        self.assertFalse([n for n in names if "__pycache__" in n or n.endswith(".pyc")])
        self.assertFalse([n for n in names if n.startswith("tests/")])


class SecondLaunchTests(unittest.TestCase):
    def test_detects_a_running_copy_and_refuses_to_share_the_port(self):
        tmp = tempfile.mkdtemp()
        server.Handler.out_dir = tmp
        server.Handler.runner = server.ScanRunner(tmp, None)
        httpd = server.Server(("127.0.0.1", 0), server.Handler)
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = "http://127.0.0.1:%d/" % port
            self.assertTrue(server.already_running(url))
            with self.assertRaises(OSError):
                server.Server(("127.0.0.1", port), server.Handler)
        finally:
            httpd.shutdown()
            httpd.server_close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_nothing_running(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.assertFalse(server.already_running("http://127.0.0.1:%d/" % port))


if __name__ == "__main__":
    unittest.main()
