#!/usr/bin/env python3
"""Build the distributable: one .pyz file plus launchers, zipped for sharing.

    python build.py

Produces, under dist/:

    LUOM-WhatsNew.pyz                   the whole app in one file (~200 KB, mostly the LUOM artwork)
    LUOM-WhatsNew/                      what a user needs, ready to copy
        LUOM-WhatsNew.pyz
        Start LUOM What's New.cmd       Windows launcher (finds / offers to install Python)
        Start LUOM What's New.command   macOS launcher (double-clickable)
        start-luom-whatsnew.sh          Linux launcher
        README.txt                      end-user instructions
        LUOM-WhatsNew.ico               LUOM icon, for a desktop / Start menu shortcut
    LUOM-WhatsNew-<version>.zip         that folder, zipped

Standard library only (zipapp). The .pyz runs on any Python 3.8+.
"""

from __future__ import annotations

import os
import shutil
import stat
import sys
import tempfile
import zipapp
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
PACKAGE = os.path.join(ROOT, "wecreat_index")
PACKAGING = os.path.join(ROOT, "packaging")
DIST = os.path.join(ROOT, "dist")
APP_NAME = "LUOM-WhatsNew"

sys.path.insert(0, ROOT)
from wecreat_index import __version__  # noqa: E402

# Launchers: (source in packaging/, name in the bundle, line ending, executable)
LAUNCHERS = [
    ("Start LUOM What's New.cmd", "Start LUOM What's New.cmd", "\r\n", False),
    ("start-luom-whatsnew.sh", "Start LUOM What's New.command", "\n", True),
    ("start-luom-whatsnew.sh", "start-luom-whatsnew.sh", "\n", True),
    ("README.txt", "README.txt", "\r\n", False),
]


def build_pyz(target: str) -> None:
    """Zip the package (minus caches) into an executable archive."""
    with tempfile.TemporaryDirectory() as staging:
        shutil.copytree(
            PACKAGE,
            os.path.join(staging, "wecreat_index"),
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        zipapp.create_archive(
            staging,
            target=target,
            interpreter="/usr/bin/env python3",
            main="wecreat_index.app:main",
            compressed=True,
        )


def write_text(src: str, dst: str, newline: str) -> None:
    with open(src, "r", encoding="utf-8") as fh:
        text = fh.read().replace("\r\n", "\n")
    with open(dst, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace("\n", newline))


def main() -> int:
    bundle = os.path.join(DIST, APP_NAME)
    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(bundle)

    pyz = os.path.join(DIST, APP_NAME + ".pyz")
    build_pyz(pyz)
    shutil.copy2(pyz, os.path.join(bundle, APP_NAME + ".pyz"))

    executables = {APP_NAME + ".pyz"}
    for src, name, newline, executable in LAUNCHERS:
        dst = os.path.join(bundle, name)
        write_text(os.path.join(PACKAGING, src), dst, newline)
        if executable:
            os.chmod(dst, os.stat(dst).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            executables.add(name)

    shutil.copy2(os.path.join(PACKAGING, APP_NAME + ".ico"), os.path.join(bundle, APP_NAME + ".ico"))

    # Zip by hand so the macOS/Linux launchers keep their executable bit
    # even when the zip is built on Windows.
    archive = os.path.join(DIST, "%s-%s.zip" % (APP_NAME, __version__))
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(bundle)):
            info = zipfile.ZipInfo("%s/%s" % (APP_NAME, name))
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if name in executables else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            with open(os.path.join(bundle, name), "rb") as fh:
                zf.writestr(info, fh.read())

    for path in (pyz, archive):
        print("%-45s %7.1f KB" % (os.path.relpath(path, ROOT), os.path.getsize(path) / 1024))
    print("Bundle folder: %s" % os.path.relpath(bundle, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
