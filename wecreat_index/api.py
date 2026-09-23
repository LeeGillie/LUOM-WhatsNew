"""Thin WordPress REST client for the WeCreat support site.

Standard library only, so the project runs on a bare Python install with no
virtual environment and no ``pip install`` step.
"""

from __future__ import annotations

import gzip
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .config import Config

log = logging.getLogger(__name__)

#: Fields we ask WordPress for. Keeps responses small; the server may ignore
#: ``_fields`` on some setups, which is harmless because we read defensively.
ARTICLE_FIELDS = (
    "id,slug,link,date,date_gmt,modified,modified_gmt,status,"
    "title,excerpt,content"
)


class WeCreatApiError(RuntimeError):
    pass


class WeCreatApi:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    # -- transport --------------------------------------------------------- #

    def _get(self, path: str, params: Dict[str, Any]) -> Tuple[Any, Dict[str, str]]:
        url = "%s/%s?%s" % (
            self.cfg.api_base,
            path.lstrip("/"),
            urllib.parse.urlencode(params),
        )
        last_error: Optional[Exception] = None

        for attempt in range(1, self.cfg.max_retries + 1):
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.cfg.user_agent,
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=self.cfg.request_timeout) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    headers = {k.lower(): v for k, v in resp.headers.items()}
                    return json.loads(raw.decode("utf-8")), headers
            except urllib.error.HTTPError as exc:
                # A page past the end returns 400 with code rest_post_invalid_page_number.
                if exc.code == 400:
                    body = exc.read().decode("utf-8", "replace")
                    if "invalid_page_number" in body:
                        return [], {}
                    raise WeCreatApiError("HTTP 400 from %s: %s" % (url, body[:300]))
                if exc.code in (408, 429, 500, 502, 503, 504) and attempt < self.cfg.max_retries:
                    last_error = exc
                elif exc.code == 404:
                    raise WeCreatApiError(
                        "HTTP 404 from %s - the endpoint or post type may have changed." % url
                    )
                else:
                    raise WeCreatApiError("HTTP %s from %s" % (exc.code, url))
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt >= self.cfg.max_retries:
                    raise WeCreatApiError("Could not reach %s: %s" % (url, exc))
                last_error = exc

            backoff = min(2 ** attempt, 15)
            log.warning("Request failed (%s), retrying in %ss ...", last_error, backoff)
            time.sleep(backoff)

        raise WeCreatApiError("Gave up on %s: %s" % (url, last_error))

    def _paginate(self, path: str, params: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        page = 1
        total_pages = None
        while True:
            call = dict(params)
            call.update({"per_page": self.cfg.page_size, "page": page})
            items, headers = self._get(path, call)
            if not items:
                return
            if total_pages is None:
                total_pages = int(headers.get("x-wp-totalpages", 0) or 0)
                total = headers.get("x-wp-total")
                if total:
                    log.info("%s: %s items across %s page(s)", path, total, total_pages or "?")
            for item in items:
                yield item
            if total_pages and page >= total_pages:
                return
            if len(items) < self.cfg.page_size:
                return
            page += 1

    # -- endpoints --------------------------------------------------------- #

    def categories(self) -> Dict[int, Dict[str, str]]:
        """``{term_id: {"name": ..., "slug": ..., "parent": ...}}`` for the KB category taxonomy."""
        out: Dict[int, Dict[str, str]] = {}
        params = {"_fields": "id,name,slug,count,parent"}
        for term in self._paginate(self.cfg.category_taxonomy, params):
            out[int(term["id"])] = {
                "name": term.get("name", ""),
                "slug": term.get("slug", ""),
                "count": term.get("count", 0),
                "parent": int(term.get("parent") or 0),
            }
        return out

    def tags(self) -> Dict[int, Dict[str, str]]:
        out: Dict[int, Dict[str, str]] = {}
        try:
            for term in self._paginate(self.cfg.tag_taxonomy, {"_fields": "id,name,slug"}):
                out[int(term["id"])] = {
                    "name": term.get("name", ""),
                    "slug": term.get("slug", ""),
                }
        except WeCreatApiError as exc:  # tags are optional on this site
            log.warning("Skipping tags: %s", exc)
        return out

    def articles(self) -> List[Dict[str, Any]]:
        """Every published knowledge-base article, newest first."""
        params = {
            "orderby": "date",
            "order": "desc",
            "status": "publish",
            "_fields": "%s,%s,%s" % (
                ARTICLE_FIELDS,
                self.cfg.category_taxonomy,
                self.cfg.tag_taxonomy,
            ),
        }
        return list(self._paginate(self.cfg.post_type, params))
