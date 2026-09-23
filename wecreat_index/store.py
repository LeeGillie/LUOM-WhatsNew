"""Build the index record set, diff it against the previous run, and write it out."""

from __future__ import annotations

import datetime as _dt
import html
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import NOTICE
from .config import Config
from .matcher import OTHER, RELEVANT, Matcher, rendered, strip_html

log = logging.getLogger(__name__)

INDEX_FILENAME = "index.json"
STATE_FILENAME = "state.json"

SCHEMA_VERSION = 1

#: Plain article text kept per record so the UI can search inside articles.
TEXT_LIMIT = 20000


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #

def parse_wp_datetime(value: Optional[str]) -> Optional[_dt.datetime]:
    """Parse a WordPress ISO timestamp. Python 3.9's fromisoformat chokes on 'Z'."""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return _dt.datetime.fromisoformat(text)
    except ValueError:
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})", text)
        if not match:
            return None
        return _dt.datetime(*(int(g) for g in match.groups()))


def human_date(value: Optional[str]) -> str:
    """'2026-08-04T08:36:05' -> 'August 4, 2026' (what the article footer shows)."""
    parsed = parse_wp_datetime(value)
    if not parsed:
        return ""
    return "%s %d, %d" % (parsed.strftime("%B"), parsed.day, parsed.year)


def sort_key(record: Dict[str, Any]) -> Tuple[_dt.datetime, int]:
    parsed = parse_wp_datetime(record.get("published_iso"))
    if parsed is None:
        parsed = _dt.datetime.min
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return (parsed, int(record.get("id", 0)))


def now_iso() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #

def category_path(term_id: int, categories: Dict[int, Dict[str, Any]]) -> str:
    """``"WeCreat MakeIt Software › Features"`` - parent chain, entities decoded.

    Several sections reuse the same child names (Features, Getting Started,
    Troubleshooting), so the bare name alone does not say which one is meant.
    """
    names: List[str] = []
    seen = set()
    current = int(term_id)
    while current and current not in seen and current in categories:
        seen.add(current)
        term = categories[current]
        names.append(html.unescape(term.get("name", "")))
        current = int(term.get("parent") or 0)
    if not names:
        return "(unknown #%s)" % term_id
    return " › ".join(reversed(names))


def build_record(
    article: Dict[str, Any],
    confidence: str,
    reasons: List[str],
    cfg: Config,
    categories: Dict[int, Dict[str, str]],
    tags: Dict[int, Dict[str, str]],
    topics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    cat_ids = article.get(cfg.category_taxonomy) or []
    tag_ids = article.get(cfg.tag_taxonomy) or []

    title = strip_html(rendered(article.get("title")))
    excerpt = strip_html(rendered(article.get("excerpt")))
    text = strip_html(rendered(article.get("content")))
    if len(text) > TEXT_LIMIT:
        text = text[:TEXT_LIMIT].rstrip() + "..."
    if len(excerpt) > 400:
        excerpt = excerpt[:397].rstrip() + "..."

    return {
        "id": int(article.get("id", 0)),
        "title": title,
        "url": article.get("link", ""),
        "slug": article.get("slug", ""),
        "published": human_date(article.get("date")),
        "published_iso": article.get("date", ""),
        "modified": human_date(article.get("modified")),
        "modified_iso": article.get("modified", ""),
        "categories": [
            categories.get(int(i), {}).get("name", "(unknown #%s)" % i) for i in cat_ids
        ],
        "category_slugs": [
            categories.get(int(i), {}).get("slug", "") for i in cat_ids
        ],
        "category_paths": [category_path(int(i), categories) for i in cat_ids],
        "tags": [tags.get(int(i), {}).get("name", "(unknown #%s)" % i) for i in tag_ids],
        "topics": list(topics or []),
        "confidence": confidence,
        "match_reasons": reasons,
        "excerpt": excerpt,
        "text": text,
    }


def collect(
    articles: List[Dict[str, Any]],
    matcher: Matcher,
    cfg: Config,
    categories: Dict[int, Dict[str, str]],
    tags: Dict[int, Dict[str, str]],
) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for article in articles:
        if article.get("status") not in (None, "publish"):
            continue
        # Every article is indexed; the ones not about the Lumos Ultra are
        # kept at confidence "other" with the reasons they were left out.
        confidence, reasons = matcher.classify(article)
        records.append(
            build_record(
                article, confidence, reasons, cfg, categories, tags,
                topics=matcher.topics(article),
            )
        )
    records.sort(key=sort_key, reverse=True)
    return records


# --------------------------------------------------------------------------- #
# State / diff
# --------------------------------------------------------------------------- #

def load_state(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {"schema": SCHEMA_VERSION, "runs": 0, "articles": {}}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (ValueError, OSError) as exc:
        log.warning("Could not read %s (%s) - starting from a clean state.", path, exc)
        return {"schema": SCHEMA_VERSION, "runs": 0, "articles": {}}
    state.setdefault("articles", {})
    state.setdefault("runs", 0)
    return state


def is_relevant(record: Dict[str, Any]) -> bool:
    return record.get("confidence") in RELEVANT


def apply_diff(
    records: List[Dict[str, Any]], state: Dict[str, Any]
) -> Tuple[Dict[str, List[Dict[str, str]]], Dict[str, Any]]:
    """Tag each record new/updated/unchanged and return the change summary.

    A first run has no baseline, so nothing is flagged new - everything is
    ``unchanged`` and the baseline is recorded for next time.

    The change lists (and so the "what's new" counts) cover the articles
    about the Lumos Ultra. Articles in the ``other`` tier still get a status,
    so the UI can mark them when they are shown, but they never flood the
    summary. An article that moves from ``other`` into the Lumos Ultra list
    counts as new there.

    State files written before the whole knowledge base was indexed do not
    know the ``other`` articles; on that first run they are taken as a
    baseline instead of being reported as new.
    """
    known: Dict[str, Any] = state.get("articles", {})
    first_run = state.get("runs", 0) == 0
    other_baseline = first_run or not state.get("tracks_other", False)
    stamp = now_iso()

    new_items: List[Dict[str, str]] = []
    updated_items: List[Dict[str, str]] = []
    other_new = 0
    seen_ids = set()

    def summary(record: Dict[str, Any]) -> Dict[str, Any]:
        return {"id": record["id"], "title": record["title"], "url": record["url"],
                "published": record["published"]}

    for record in records:
        key = str(record["id"])
        seen_ids.add(key)
        previous = known.get(key)
        relevant = is_relevant(record)

        if previous is None:
            record["first_seen"] = stamp
            if first_run or (not relevant and other_baseline):
                record["status"] = "unchanged"
            else:
                record["status"] = "new"
                if relevant:
                    new_items.append(summary(record))
                else:
                    other_new += 1
        else:
            record["first_seen"] = previous.get("first_seen", stamp)
            was_relevant = previous.get("confidence") in RELEVANT
            changed = previous.get("modified_iso") != record["modified_iso"]
            if relevant and not was_relevant:
                record["status"] = "new"              # newly about the Lumos Ultra
                new_items.append(summary(record))
            elif changed:
                record["status"] = "updated"
                if relevant:
                    updated_items.append(
                        {
                            "id": record["id"],
                            "title": record["title"],
                            "url": record["url"],
                            "previously_modified": previous.get("modified_iso", ""),
                            "modified": record["modified_iso"],
                        }
                    )
            else:
                record["status"] = "unchanged"
        record["last_seen"] = stamp

    by_id = {str(r["id"]): r for r in records}
    removed_items = []
    for key, value in known.items():
        if value.get("confidence") not in RELEVANT:
            continue
        current = by_id.get(key)
        if current is not None and is_relevant(current):
            continue
        removed_items.append(
            {
                "id": int(key),
                "title": value.get("title", ""),
                "url": value.get("url", ""),
                "last_seen": value.get("last_seen", ""),
                "reason": ("now marked as not about the Lumos Ultra" if current is not None
                           else "no longer on help.wecreat.com"),
            }
        )

    changes = {
        "new": new_items,
        "updated": updated_items,
        "no_longer_matching": removed_items,
        "other_new": other_new,
    }

    next_state = {
        "schema": SCHEMA_VERSION,
        "tracks_other": True,
        "runs": int(state.get("runs", 0)) + 1,
        "last_run": stamp,
        "previous_run": state.get("last_run", ""),
        "articles": {
            str(r["id"]): {
                "title": r["title"],
                "url": r["url"],
                "published_iso": r["published_iso"],
                "modified_iso": r["modified_iso"],
                "confidence": r["confidence"],
                "first_seen": r["first_seen"],
                "last_seen": r["last_seen"],
            }
            for r in records
        },
    }
    return changes, next_state


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def build_index(
    records: List[Dict[str, Any]],
    changes: Dict[str, List[Dict[str, str]]],
    cfg: Config,
    state: Dict[str, Any],
    scanned: int,
) -> Dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "notice": NOTICE,
        "content_owner": "WeCreat - https://help.wecreat.com (articles are linked, not owned or maintained by LUOM)",
        "generated_at": now_iso(),
        "previous_run": state.get("last_run", ""),
        "run_number": int(state.get("runs", 0)) + 1,
        "source": cfg.describe(),
        "sort": "published date, newest first",
        "counts": {
            "articles_scanned": scanned,
            "indexed": len(records),
            "matched": sum(1 for r in records if is_relevant(r)),
            "direct": sum(1 for r in records if r["confidence"] == "direct"),
            "likely": sum(1 for r in records if r["confidence"] == "likely"),
            "other": sum(1 for r in records if r["confidence"] == OTHER),
            "new": len(changes["new"]),
            "updated": len(changes["updated"]),
            "no_longer_matching": len(changes["no_longer_matching"]),
            "other_new": changes.get("other_new", 0),
        },
        "changes_since_last_run": changes,
        "articles": records,
    }


def write_json(path: str, payload: Dict[str, Any]) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)
