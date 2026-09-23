"""Entry point of the packaged app, ``LUOM-WhatsNew.pyz``.

    LUOM-WhatsNew.pyz [options]          start the web UI (default)
    LUOM-WhatsNew.pyz serve [options]    the same, spelled out
    LUOM-WhatsNew.pyz scan [options]     run one scan and exit (for Task Scheduler / cron)

``serve`` takes the options of ``python -m wecreat_index.server`` and ``scan``
those of ``python -m wecreat_index``; add ``--help`` after either to list them.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from . import __version__

USAGE = __doc__

LOG_FILENAME = "luom-whatsnew.log"
LOG_MAX_BYTES = 1_000_000


def _redirect_output_if_windowless() -> None:
    """Under pythonw there is no console: send output to a log file instead.

    Without this, print/logging output would be lost and any startup error
    would vanish silently. The log sits in the data folder.
    """
    if sys.stderr is not None and sys.stdout is not None:
        return
    from .paths import default_data_dir

    path = os.path.join(default_data_dir(), LOG_FILENAME)
    try:
        if os.path.getsize(path) > LOG_MAX_BYTES:
            os.replace(path, path + ".old")
    except OSError:
        pass
    try:
        stream = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        stream = open(os.devnull, "w")
    sys.stdout = sys.stdout or stream
    sys.stderr = sys.stderr or stream


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    _redirect_output_if_windowless()

    command = args[0] if args and not args[0].startswith("-") else "serve"
    if args and args[0] == command:
        args = args[1:]

    if command == "scan":
        from .cli import main as scan_main
        return scan_main(args)
    if command == "serve":
        if args[:1] in (["-h"], ["--help"]):
            print(USAGE)
        from .server import main as serve_main
        return serve_main(args)
    if command in ("help", "version"):
        print(USAGE if command == "help" else "LUOM What's New " + __version__)
        return 0

    print("Unknown command %r.\n%s" % (command, USAGE), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
