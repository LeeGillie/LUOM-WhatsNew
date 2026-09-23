"""Command line entry point."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List, Optional

from . import NOTICE, __version__
from .api import WeCreatApi, WeCreatApiError
from .config import PROFILES, Config
from .matcher import Matcher
from .paths import default_data_dir, find_config, migrate_legacy_data
from .store import (
    INDEX_FILENAME,
    STATE_FILENAME,
    apply_diff,
    build_index,
    collect,
    load_state,
    write_json,
)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="wecreat_index",
        description=(
            "Read WeCreat's public knowledge base and index every article relevant "
            "to the Lumos Ultra, newest first."
        ),
        epilog=NOTICE,
    )
    parser.add_argument(
        "-o", "--out", default=None,
        help="Directory for index.json and state.json (default: the shared "
             "application data folder, e.g. C:\\ProgramData\\LUOM-WhatsNew)",
    )
    parser.add_argument(
        "-c", "--config", default=None,
        help="config.json overriding the match rules (default: config.json in the "
             "data folder, else the project's, else the built-in rules)",
    )
    parser.add_argument(
        "-p", "--profile", choices=sorted(PROFILES),
        help="Match profile (default: whatever config.json says, else 'broad')",
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Ignore and overwrite the saved state, treating this as a first run",
    )
    parser.add_argument(
        "--no-state", action="store_true",
        help="Do not read or write state.json (no new/updated tracking)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scan and report, but write nothing to disk",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    parser.add_argument("-q", "--quiet", action="store_true", help="Errors only")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    level = logging.DEBUG if args.verbose else logging.ERROR if args.quiet else logging.INFO
    logging.basicConfig(level=level, format="%(message)s", stream=sys.stderr)
    log = logging.getLogger("wecreat_index")

    if args.out is None:
        args.out = default_data_dir()
        migrate_legacy_data(args.out)
    if args.config is None:
        args.config = find_config(args.out)

    try:
        cfg = Config.load(args.config, args.profile)
    except (ValueError, OSError) as exc:
        log.error("Configuration problem: %s", exc)
        return 2

    log.info("Scanning %s  (profile: %s)", cfg.site, cfg.profile)
    api = WeCreatApi(cfg)

    try:
        categories = api.categories()
        tags = api.tags()
        articles = api.articles()
    except WeCreatApiError as exc:
        log.error("Scan failed: %s", exc)
        return 1

    log.info("Fetched %d article(s) and %d categor(y/ies).", len(articles), len(categories))

    matcher = Matcher(cfg, categories)
    records = collect(articles, matcher, cfg, categories, tags)

    index_path = os.path.join(args.out, INDEX_FILENAME)
    state_path = os.path.join(args.out, STATE_FILENAME)

    state = {"schema": 1, "runs": 0, "articles": {}}
    if not args.no_state and not args.reset:
        state = load_state(state_path)

    changes, next_state = apply_diff(records, state)
    index = build_index(records, changes, cfg, state, scanned=len(articles))

    if args.dry_run:
        log.info("Dry run - nothing written.")
    else:
        write_json(index_path, index)
        if not args.no_state:
            write_json(state_path, next_state)

    counts = index["counts"]
    log.info(
        "Matched %d article(s): %d direct, %d likely; %d more indexed as not about the Lumos Ultra.",
        counts["matched"], counts["direct"], counts["likely"], counts["other"],
    )
    if state.get("runs", 0) == 0:
        log.info("First run - baseline recorded; the next run will report what is new.")
    else:
        log.info(
            "Since the last run: %d new, %d updated, %d no longer matching.",
            counts["new"], counts["updated"], counts["no_longer_matching"],
        )
        for item in changes["new"]:
            log.info("  NEW      %s  %s", item["published"], item["title"])
        for item in changes["updated"]:
            log.info("  UPDATED  %s", item["title"])

    if not args.dry_run:
        log.info("Index written to %s", index_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
