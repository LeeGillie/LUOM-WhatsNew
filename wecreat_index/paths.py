"""Where index.json / state.json live.

The data is kept in an application folder shared by every user of the
computer, not next to the code:

    Windows   %ProgramData%\\LUOM-WhatsNew          (C:\\ProgramData\\LUOM-WhatsNew)
    macOS     /Users/Shared/LUOM-WhatsNew
    Linux     $XDG_DATA_HOME/luom-whatsnew          (~/.local/share/luom-whatsnew)

Linux has no computer-wide folder an ordinary user may write to (/var/lib
needs root), so it falls back to the per-user XDG location; any platform
falls back the same way if the shared folder cannot be created.

``LUOM_WHATSNEW_DATA`` overrides all of this, and ``--out`` overrides it
per run. Data left under the program's previous name (WhatsNewWecreat), or
in the original ``<project>/data`` folder, is moved over on first use.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from typing import List, Optional

log = logging.getLogger(__name__)

APP_DIR_NAME = "LUOM-WhatsNew"
ENV_VAR = "LUOM_WHATSNEW_DATA"
#: Names used before the rename to "LUOM What's New"; still honoured / migrated.
OLD_APP_DIR_NAME = "WhatsNewWecreat"
OLD_ENV_VAR = "WHATSNEWWECREAT_DATA"

#: The source checkout - or, when running from the .pyz, the .pyz file itself.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#: True when running from a zipped .pyz rather than a source checkout.
ZIPPED = os.path.isfile(PROJECT_ROOT)
#: Where the very first versions wrote their output.
LEGACY_DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_FILENAME = "config.json"

DATA_FILES = ("index.json", "state.json")
#: Everything worth carrying over from an old data folder.
CARRY_OVER_FILES = DATA_FILES + (CONFIG_FILENAME,)


def _per_user_dir(name: str = APP_DIR_NAME) -> str:
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        return os.path.join(base, name)
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/" + name)
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, name.lower())


def _shared_dir(name: str = APP_DIR_NAME) -> Optional[str]:
    if sys.platform.startswith("win"):
        base = os.environ.get("PROGRAMDATA") or os.environ.get("ALLUSERSPROFILE") or r"C:\ProgramData"
        return os.path.join(base, name)
    if sys.platform == "darwin":
        return "/Users/Shared/" + name
    return None


def _usable(path: str) -> bool:
    """Create ``path`` if needed and confirm we can write into it."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return True
    except OSError:
        return False


def _override() -> Optional[str]:
    return os.environ.get(ENV_VAR) or os.environ.get(OLD_ENV_VAR)


def candidate_dirs() -> List[str]:
    override = _override()
    if override:
        return [os.path.abspath(os.path.expanduser(override))]
    shared = _shared_dir()
    return ([shared] if shared else []) + [_per_user_dir()]


def _share_with_all_users(path: str) -> None:
    """Let every local user update the files in a new shared Windows folder.

    ProgramData's default ACL lets any user create files but only the creator
    change them, which would lock other accounts (or a scheduled task running
    as another user) out of rewriting index.json. BUILTIN\\Users is granted
    Modify on this one folder, inherited by its files.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        subprocess.run(
            ["icacls", path, "/grant", "*S-1-5-32-545:(OI)(CI)M", "/Q"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("Could not widen permissions on %s: %s", path, exc)


def default_data_dir() -> str:
    """The first usable data folder for this machine (created if missing)."""
    candidates = candidate_dirs()
    shared = None if _override() else _shared_dir()
    for path in candidates:
        existed = os.path.isdir(path)
        if _usable(path):
            if path == shared and not existed:
                _share_with_all_users(path)
            return path
        log.warning("Cannot write to %s; trying the next location.", path)
    # Nothing writable - return the preferred one so the error names it.
    return candidates[0]


def find_config(data_dir: str) -> Optional[str]:
    """The ``config.json`` to use, or ``None`` for the built-in rules.

    Looked for in the data folder first (so every user shares one set of
    rules), then beside the .pyz, then in the source checkout.
    """
    places = [os.path.join(data_dir, CONFIG_FILENAME)]
    if ZIPPED:
        places.append(os.path.join(os.path.dirname(PROJECT_ROOT), CONFIG_FILENAME))
    else:
        places.append(os.path.join(PROJECT_ROOT, CONFIG_FILENAME))
    for path in places:
        if os.path.isfile(path):
            return path
    return None


def scan_command(out_dir: str, config_path: Optional[str]) -> List[str]:
    """Command line that runs one scan in a child process."""
    if ZIPPED:
        cmd = [sys.executable, PROJECT_ROOT, "scan"]
    else:
        cmd = [sys.executable, "-m", "wecreat_index"]
    cmd += ["--out", out_dir]
    if config_path:
        cmd += ["--config", config_path]
    return cmd


def has_data(data_dir: str) -> bool:
    return os.path.isfile(os.path.join(data_dir, "index.json"))


def old_data_dirs() -> List[str]:
    """Folders earlier versions may have written to, most likely first."""
    dirs = []
    shared = _shared_dir(OLD_APP_DIR_NAME)
    if shared:
        dirs.append(shared)
    dirs.append(_per_user_dir(OLD_APP_DIR_NAME))
    dirs.append(LEGACY_DATA_DIR)
    return dirs


def migrate_legacy_data(data_dir: str) -> List[str]:
    """Move data from an older location into ``data_dir``.

    Checks the folders used under the previous program name, then the
    original ``<project>/data`` folder. Only runs when ``data_dir`` has no
    index yet, so it never overwrites anything. Returns the files moved.
    """
    if has_data(data_dir):
        return []
    target = os.path.abspath(data_dir)
    for old in old_data_dirs():
        if os.path.abspath(old) == target or not has_data(old):
            continue
        moved = []
        os.makedirs(data_dir, exist_ok=True)
        for name in CARRY_OVER_FILES:
            src = os.path.join(old, name)
            dst = os.path.join(data_dir, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                shutil.copy2(src, dst)
                os.remove(src)
                moved.append(name)
        if moved:
            log.info("Moved %s from %s to %s", ", ".join(moved), old, data_dir)
            _remove_if_only_leftovers(old)
            return moved
    return []


def _remove_if_only_leftovers(folder: str) -> None:
    """Delete an emptied old folder (an old log file does not keep it alive)."""
    try:
        for name in os.listdir(folder):
            if name.lower().endswith((".log", ".log.old")):
                os.remove(os.path.join(folder, name))
        os.rmdir(folder)
    except OSError:
        pass
