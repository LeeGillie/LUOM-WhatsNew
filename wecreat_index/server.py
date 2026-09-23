"""Local web UI for the index: browse, filter, and run a scan from the browser.

    python -m wecreat_index.server            # http://127.0.0.1:8765, opens a browser
    python -m wecreat_index.server --port 9000 --no-browser
    python LUOM-WhatsNew.pyz                # the same, from the packaged app

Standard library only. Binds to loopback by default; the scan runs as a child
process (``python -m wecreat_index`` or ``LUOM-WhatsNew.pyz scan``) so its
output streams into the page exactly as it would print in a terminal.

Endpoints
    GET  /                 the UI (wecreat_index/ui/)
    GET  /api/info         data folder, whether an index exists, versions
    GET  /api/index        <data folder>/index.json
    GET  /api/state        <data folder>/state.json
    GET  /api/scan         scan status + log
    POST /api/scan         start a scan (409 if one is already running)
    POST /api/shutdown     stop the server (the page's "Exit" button)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import pkgutil
import subprocess
import sys
import threading
import urllib.request
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

from . import NOTICE, __version__
from .paths import default_data_dir, find_config, has_data, migrate_legacy_data, scan_command
from .store import INDEX_FILENAME, STATE_FILENAME

log = logging.getLogger("wecreat_index.server")

#: Only these files are served, from the package's ui/ folder (read through
#: pkgutil so it works from a source checkout and from inside the .pyz alike).
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/favicon-64.png": ("assets/favicon-64.png", "image/png"),
    "/assets/logo-256.webp": ("assets/logo-256.webp", "image/webp"),
    "/assets/splash.webp": ("assets/splash.webp", "image/webp"),
}

MAX_LOG_LINES = 500


def _now() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


class ScanRunner:
    """Runs one scan at a time as a child process and keeps its output."""

    def __init__(self, out_dir: str, config_path: Optional[str]) -> None:
        self.out_dir = out_dir
        self.config_path = config_path
        self._lock = threading.Lock()
        self.running = False
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.exit_code: Optional[int] = None
        self.lines: List[str] = []

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "exit_code": self.exit_code,
                "log": list(self.lines),
            }

    def start(self) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.started_at = _now()
            self.finished_at = None
            self.exit_code = None
            self.lines = []
        threading.Thread(target=self._run, name="scan", daemon=True).start()
        return True

    def _append(self, line: str) -> None:
        with self._lock:
            self.lines.append(line)
            if len(self.lines) > MAX_LOG_LINES:
                del self.lines[: len(self.lines) - MAX_LOG_LINES]

    def _run(self) -> None:
        cmd = scan_command(self.out_dir, self.config_path)
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        # No console window flashing up when started from pythonw on Windows.
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        code = -1
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=self.out_dir,
                env=env,
                creationflags=flags,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self._append(line.rstrip("\r\n"))
            code = proc.wait()
        except OSError as exc:
            self._append("Could not start the scan: %s" % exc)
        with self._lock:
            self.running = False
            self.exit_code = code
            self.finished_at = _now()
        log.info("Scan finished with exit code %s", code)


class Handler(BaseHTTPRequestHandler):
    server_version = "LUOM-WhatsNew"
    runner: ScanRunner
    out_dir: str

    # -- plumbing ---------------------------------------------------------- #

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter than stderr spam
        log.debug("%s - %s", self.address_string(), fmt % args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: Any) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8")

    def _file(self, path: str, content_type: str, missing: str) -> None:
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except FileNotFoundError:
            self._json(HTTPStatus.NOT_FOUND, {"error": missing})
            return
        self._send(HTTPStatus.OK, body, content_type)

    def _host_ok(self) -> bool:
        """Refuse requests addressed to another host name (DNS-rebinding guard)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
        return host in ("127.0.0.1", "localhost", "::1", self.server.server_address[0])

    # -- routes ------------------------------------------------------------ #

    def do_GET(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._json(HTTPStatus.FORBIDDEN, {"error": "bad host"})
            return
        path = urlsplit(self.path).path
        if path in STATIC_FILES:
            name, ctype = STATIC_FILES[path]
            body = pkgutil.get_data(__package__, "ui/" + name)
            if body is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "missing UI file"})
            else:
                self._send(HTTPStatus.OK, body, ctype)
        elif path == "/api/index":
            self._file(
                os.path.join(self.out_dir, INDEX_FILENAME),
                "application/json; charset=utf-8",
                "No index yet - run a scan.",
            )
        elif path == "/api/state":
            self._file(
                os.path.join(self.out_dir, STATE_FILENAME),
                "application/json; charset=utf-8",
                "No state yet - run a scan.",
            )
        elif path == "/api/scan":
            self._json(HTTPStatus.OK, self.runner.status())
        elif path == "/api/info":
            self._json(HTTPStatus.OK, self._info())
        else:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_ok():
            self._json(HTTPStatus.FORBIDDEN, {"error": "bad host"})
            return
        path = urlsplit(self.path).path
        if path not in ("/api/scan", "/api/shutdown"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        # A JSON content type cannot be sent cross-origin without a CORS
        # preflight, which this server never approves - so other sites cannot
        # trigger scans (or stop the program) through the browser.
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "expected application/json"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(min(length, 4096))

        if path == "/api/shutdown":
            self._json(HTTPStatus.OK, {"stopping": True})
            log.info("Exit requested from the page.")
            # shutdown() blocks until serve_forever returns, so not on this thread.
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        if self.runner.start():
            self._json(HTTPStatus.ACCEPTED, self.runner.status())
        else:
            self._json(HTTPStatus.CONFLICT, dict(self.runner.status(), error="A scan is already running."))

    def _info(self) -> Dict[str, Any]:
        return {
            "version": __version__,
            "data_dir": self.out_dir,
            "has_data": has_data(self.out_dir),
            "config": self.runner.config_path or "built-in rules",
            "python": sys.version.split()[0],
            "platform": sys.platform,
        }


class Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second process bind a port that is
    # already in use, so two copies would both "listen" on 8765. Elsewhere it
    # only skips the TIME_WAIT delay after a restart, which is wanted.
    allow_reuse_address = not sys.platform.startswith("win")


def already_running(url: str) -> bool:
    """True if a LUOM What's New server is already answering at ``url``."""
    try:
        with urllib.request.urlopen(url + "api/info", timeout=2) as resp:
            return "data_dir" in json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return False


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="LUOM-WhatsNew",
        description="Serve a local web UI for browsing the index and running scans.",
        epilog=NOTICE,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Port (default: 8765)")
    parser.add_argument("-o", "--out", default=None,
                        help="Directory holding index.json / state.json (default: shared app data folder)")
    parser.add_argument("-c", "--config", default=None,
                        help="config.json passed to scans (default: data folder, else built-in rules)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser tab")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log every request")
    parser.add_argument("--version", action="version", version="LUOM What's New " + __version__)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )

    if args.out is None:
        args.out = default_data_dir()
        migrate_legacy_data(args.out)
    out_dir = os.path.abspath(args.out)
    log.info("LUOM What's New %s - independent community index of help.wecreat.com; "
             "not affiliated with WeCreat.", __version__)
    log.info("Data folder: %s%s", out_dir, "" if has_data(out_dir) else "  (empty - the page will offer a first download)")

    config = os.path.abspath(args.config) if args.config else find_config(out_dir)
    Handler.runner = ScanRunner(out_dir, config)
    Handler.out_dir = out_dir

    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    url = "http://%s:%d/" % (shown_host, args.port)

    if already_running(url):
        # Started a second time (e.g. the launcher double-clicked again):
        # just bring up the copy that is already serving.
        log.info("LUOM What's New is already running at %s - opening it.", url)
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    try:
        httpd = Server((args.host, args.port), Handler)
    except OSError as exc:
        log.error("Could not listen on %s:%s - %s", args.host, args.port, exc)
        return 1
    httpd.daemon_threads = True

    log.info("LUOM What's New is running at %s  (Ctrl+C to stop)", url)
    if not args.no_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Stopping.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
