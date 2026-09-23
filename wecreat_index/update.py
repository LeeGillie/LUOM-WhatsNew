"""Check GitHub for a newer release and, when asked, install it in place.

The check reads one small JSON document from GitHub's public API - the
latest release of the project - and compares its version with this one.
Nothing about the user or their data is sent. The result is cached in the
data folder so the check runs at most once every CHECK_INTERVAL.

Installing only works for the packaged app (LUOM-WhatsNew.pyz and its
launchers, all in one folder). It downloads the release zip, verifies it
against the SHA-256 digest GitHub publishes for it, checks that the new
program starts and reports the expected version, and only then swaps the
files in. Anything unexpected stops it before a file is replaced.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import io
import json
import logging
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from typing import Any, Dict, List, Optional, Tuple

from . import __version__
from .paths import PROJECT_ROOT, ZIPPED

log = logging.getLogger(__name__)

REPO = "LeeGillie/LUOM-WhatsNew"
LATEST_API = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES_PAGE = "https://github.com/%s/releases/latest" % REPO
APP_NAME = "LUOM-WhatsNew"
PYZ_NAME = APP_NAME + ".pyz"

CACHE_FILENAME = "update-check.json"
CHECK_INTERVAL = _dt.timedelta(hours=20)
TIMEOUT = 15
MAX_DOWNLOAD = 50 * 1024 * 1024


class UpdateError(Exception):
    """A readable reason the update was not installed; nothing was replaced."""


# --------------------------------------------------------------------- versions

def parse_version(text: str) -> Optional[Tuple[int, ...]]:
    """``"v1.2.0"`` -> ``(1, 2, 0)``; None for anything that is not a plain version."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", (text or "").strip())
    if not m:
        return None
    parts = tuple(int(p) for p in m.group(1).split("."))
    while len(parts) > 1 and parts[-1] == 0:   # 1.2 == 1.2.0
        parts = parts[:-1]
    return parts


def is_newer(candidate: str, current: str = __version__) -> bool:
    new, cur = parse_version(candidate), parse_version(current)
    return bool(new and cur and new > cur)


# --------------------------------------------------------------------- checking

def app_dir() -> Optional[str]:
    """The folder holding LUOM-WhatsNew.pyz, or None when running from source."""
    return os.path.dirname(PROJECT_ROOT) if ZIPPED else None


def _get(url: str, accept: str) -> urllib.request.addinfourl:
    req = urllib.request.Request(url, headers={
        "Accept": accept,
        "User-Agent": "%s/%s (+https://github.com/%s)" % (APP_NAME, __version__, REPO),
    })
    return urllib.request.urlopen(req, timeout=TIMEOUT)


def _summarise(release: Dict[str, Any]) -> Dict[str, Any]:
    """The parts of a GitHub release the page and the installer need."""
    tag = release.get("tag_name") or ""
    version = tag[1:] if tag[:1] in "vV" else tag
    asset = next((a for a in release.get("assets") or []
                  if re.fullmatch(re.escape(APP_NAME) + r"-[\w.]+\.zip", a.get("name") or "")), None)
    return {
        "latest": version,
        "newer": is_newer(version),
        "notes_url": release.get("html_url") or RELEASES_PAGE,
        "published_at": release.get("published_at"),
        "asset_url": asset.get("browser_download_url") if asset else None,
        "asset_size": asset.get("size") if asset else None,
        "asset_digest": asset.get("digest") if asset else None,
    }


def _install_blocker(info: Dict[str, Any]) -> Optional[str]:
    """Why "Update now" cannot work here, or None if it can."""
    folder = app_dir()
    if folder is None:
        return "Running from the source code - update it with git, or download the release."
    if not info.get("asset_url"):
        return "This release has no download for the program."
    if not str(info.get("asset_digest") or "").startswith("sha256:"):
        return "This release has no checksum to verify the download against."
    if not os.access(folder, os.W_OK):
        return "The program's folder cannot be written to (%s)." % folder
    return None


def _now() -> _dt.datetime:
    return _dt.datetime.now().replace(microsecond=0)


def check(data_dir: str, force: bool = False) -> Dict[str, Any]:
    """Latest-release info, from the cache when it is recent enough.

    Never raises: a failed check comes back with ``error`` set, so an offline
    computer only means no banner.
    """
    cache = os.path.join(data_dir, CACHE_FILENAME)
    info: Optional[Dict[str, Any]] = None
    if not force:
        try:
            with open(cache, encoding="utf-8") as fh:
                cached = json.load(fh)
            age = _now() - _dt.datetime.fromisoformat(cached["checked_at"])
            # A cache written by another version says nothing about this one.
            if cached.get("current") == __version__ and _dt.timedelta(0) <= age < CHECK_INTERVAL:
                info = cached
        except (OSError, ValueError, KeyError, TypeError):
            pass

    if info is None:
        try:
            with _get(LATEST_API, "application/vnd.github+json") as resp:
                release = json.loads(resp.read().decode("utf-8"))
            info = dict(_summarise(release), current=__version__, checked_at=_now().isoformat())
        except (OSError, ValueError) as exc:
            log.info("Update check failed: %s", exc)
            return {"current": __version__, "newer": False, "error": "Could not reach GitHub.",
                    "notes_url": RELEASES_PAGE}
        try:
            with open(cache, "w", encoding="utf-8") as fh:
                json.dump(info, fh, indent=2)
        except OSError:
            pass

    info = dict(info, newer=is_newer(info.get("latest", "")))
    blocker = _install_blocker(info)
    info["can_install"] = blocker is None
    info["install_blocker"] = blocker
    return info


# --------------------------------------------------------------------- installing

def _download(info: Dict[str, Any]) -> bytes:
    size = info.get("asset_size") or 0
    if size > MAX_DOWNLOAD:
        raise UpdateError("The download is unexpectedly large (%d bytes)." % size)
    try:
        with _get(info["asset_url"], "application/octet-stream") as resp:
            data = resp.read(MAX_DOWNLOAD + 1)
    except OSError as exc:
        raise UpdateError("The download failed: %s" % exc) from exc
    if len(data) > MAX_DOWNLOAD:
        raise UpdateError("The download is unexpectedly large.")
    want = str(info.get("asset_digest") or "").partition("sha256:")[2].lower()
    got = hashlib.sha256(data).hexdigest()
    if not want or got != want:
        raise UpdateError("The download does not match GitHub's checksum, so it was not used.")
    return data


def _bundle_files(data: bytes) -> Dict[str, Tuple[bytes, bool]]:
    """``{file name: (content, executable)}`` from a release zip.

    The zip must be one flat LUOM-WhatsNew/ folder holding the program;
    anything else (sub-folders, odd paths) is refused.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UpdateError("The download is not a valid zip file.") from exc
    files: Dict[str, Tuple[bytes, bool]] = {}
    prefix = APP_NAME + "/"
    with zf:
        for item in zf.infolist():
            if item.is_dir():
                continue
            name = item.filename[len(prefix):] if item.filename.startswith(prefix) else ""
            if not name or "/" in name or "\\" in name or name.startswith(".") or ":" in name:
                raise UpdateError("The download contains an unexpected file: %s" % item.filename)
            mode = item.external_attr >> 16
            files[name] = (zf.read(item), bool(mode & stat.S_IXUSR))
    if PYZ_NAME not in files:
        raise UpdateError("The download does not contain %s." % PYZ_NAME)
    return files


def _reported_version(pyz: str) -> str:
    """Run the downloaded program once and ask its version."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run([sys.executable, pyz, "version"], capture_output=True, text=True,
                             timeout=60, creationflags=flags).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        raise UpdateError("The new version could not be started: %s" % exc) from exc
    return out.strip().rpartition(" ")[2]


def install(info: Dict[str, Any], folder: Optional[str] = None) -> List[str]:
    """Download, verify and swap in the release described by ``info``.

    Returns the names of the files that changed. Raises UpdateError, with
    nothing replaced, if any check fails.
    """
    folder = folder or app_dir()
    if folder is None:
        raise UpdateError("Running from the source code - there is no program file to replace.")
    if not info.get("newer"):
        raise UpdateError("This is already the latest version.")

    files = _bundle_files(_download(info))

    # Write everything next to the old files first; nothing is replaced yet.
    staged: List[Tuple[str, str]] = []
    try:
        for name, (content, executable) in sorted(files.items()):
            target = os.path.join(folder, name)
            try:
                with open(target, "rb") as fh:
                    if fh.read() == content:
                        continue        # unchanged - leave it alone
            except OSError:
                pass
            fd, tmp = tempfile.mkstemp(prefix="." + name + ".", suffix=".new", dir=folder)
            with os.fdopen(fd, "wb") as fh:
                fh.write(content)
            if executable:
                os.chmod(tmp, os.stat(tmp).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            staged.append((tmp, target))

        new_pyz = next((tmp for tmp, target in staged if os.path.basename(target) == PYZ_NAME), None)
        if new_pyz is not None:
            reported = _reported_version(new_pyz)
            if parse_version(reported) != parse_version(info["latest"]):
                raise UpdateError("The new program reports version %r, expected %s."
                                  % (reported, info["latest"]))
    except OSError as exc:
        _discard(staged)
        raise UpdateError("Could not write the new files: %s" % exc) from exc
    except UpdateError:
        _discard(staged)
        raise

    # The swap. Each os.replace is atomic; the program goes last so a
    # failure part-way leaves the old program working.
    staged.sort(key=lambda pair: os.path.basename(pair[1]) == PYZ_NAME)
    done: List[str] = []
    for tmp, target in staged:
        try:
            os.replace(tmp, target)
        except OSError as exc:
            _discard([pair for pair in staged if os.path.exists(pair[0])])
            raise UpdateError("Could not replace %s: %s" % (os.path.basename(target), exc)) from exc
        done.append(os.path.basename(target))
    log.info("Updated to %s: %s", info["latest"], ", ".join(done) or "no files changed")
    return done


def _discard(staged: List[Tuple[str, str]]) -> None:
    for tmp, _ in staged:
        try:
            os.remove(tmp)
        except OSError:
            pass


def restart_command(argv: List[str]) -> List[str]:
    """How to start the (new) program again with the same options, minus the browser."""
    args = [a for a in argv if a != "--no-browser"]
    return [sys.executable, PROJECT_ROOT, "serve"] + args + ["--no-browser"]
