"""Decide which knowledge-base articles are relevant to the WeCreat Lumos Ultra.

Two tiers of evidence:

``direct``
    The article sits in a Lumos Ultra category (or a subcategory of one, such
    as Lumos Ultra > Features), or its title/body names the Lumos Ultra outright.

``likely``
    The article sits in a category that covers hardware, accessories or
    software the Lumos Ultra uses but which is shared with other machines
    (MakeIt software, the 60W/100W MOPA module, the fume extractor, the
    pass-through feeder) and is not tied to a different machine, or its text
    walks through a MakeIt workflow (test grids, color engraving, pulse width)
    wherever it is filed. Only collected under the ``broad`` profile.

``other``
    Everything else. :meth:`Matcher.classify` returns this tier with the
    reasons the article was left out, so the whole knowledge base can be
    indexed while the UI shows the Lumos Ultra articles by default.

Every entry carries the reasons for its tier, so a questionable one in the
index can be traced back without re-running anything.
"""

from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Optional, Tuple

from .config import Config

#: Confidence given to articles that are indexed but not about the Lumos Ultra.
OTHER = "other"
#: The confidences that count as "about the Lumos Ultra".
RELEVANT = ("direct", "likely")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def strip_html(value: str) -> str:
    """Rendered HTML -> plain text, good enough for keyword matching."""
    if not value:
        return ""
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", value)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def rendered(field: Any) -> str:
    """WordPress returns ``{"rendered": "..."}`` for title/excerpt/content."""
    if isinstance(field, dict):
        return field.get("rendered", "") or ""
    if isinstance(field, str):
        return field
    return ""


class Matcher:
    def __init__(self, cfg: Config, categories: Dict[int, Dict[str, str]]) -> None:
        self.cfg = cfg
        self.categories = categories
        self.rules = cfg.rules

        self._direct_cat = cfg.compiled(cfg.direct_category_patterns)
        self._direct_text = cfg.compiled(cfg.direct_text_patterns)
        self._related_cat = cfg.compiled(cfg.related_category_patterns)
        self._software_topic = cfg.compiled(cfg.software_topic_patterns)
        self._other_machine_cat = cfg.compiled(cfg.other_machine_category_patterns)
        self._ultra_required = cfg.compiled(cfg.ultra_required_title_patterns)
        self._topics = [(label, cfg.compiled(pats)) for label, pats in cfg.topics.items()]

    # -- helpers ----------------------------------------------------------- #

    def _category_terms(self, article: Dict[str, Any]) -> List[Dict[str, str]]:
        ids = article.get(self.cfg.category_taxonomy) or []
        terms = []
        for term_id in ids:
            term = self.categories.get(int(term_id))
            if term:
                terms.append(term)
            else:
                terms.append({"name": "(unknown #%s)" % term_id, "slug": ""})
        return terms

    def _ancestors(self, term: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parent, grandparent, ... of a category term (nearest first).

        WeCreat nests generic names under each machine - "Features",
        "Getting Started", "Materials & Settings" with slugs like ``features``
        are children of Lumos Ultra - so the term alone does not say which
        machine it belongs to.
        """
        out: List[Dict[str, Any]] = []
        seen = set()
        parent = int(term.get("parent") or 0)
        while parent and parent not in seen and parent in self.categories:
            seen.add(parent)
            ancestor = self.categories[parent]
            out.append(ancestor)
            parent = int(ancestor.get("parent") or 0)
        return out

    @staticmethod
    def _any_match(patterns, haystacks: List[str]) -> Optional[str]:
        for pattern in patterns:
            for hay in haystacks:
                if hay and pattern.search(hay):
                    return pattern.pattern
        return None

    def topics(self, article: Dict[str, Any]) -> List[str]:
        """Topic labels for an article (title + body), in config order."""
        text = "%s %s" % (
            strip_html(rendered(article.get("title"))),
            strip_html(rendered(article.get("content"))),
        )
        return [
            label for label, patterns in self._topics
            if any(p.search(text) for p in patterns)
        ]

    # -- the decision ------------------------------------------------------ #

    def evaluate(self, article: Dict[str, Any]) -> Optional[Tuple[str, List[str]]]:
        """Return ``(confidence, reasons)`` or ``None`` if the article is not relevant."""
        reasons: List[str] = []
        terms = self._category_terms(article)
        title = strip_html(rendered(article.get("title")))
        body = strip_html(rendered(article.get("content")))
        excerpt = strip_html(rendered(article.get("excerpt")))

        # --- direct: a Lumos Ultra category, or a child of one ------------- #
        if self.rules.get("use_direct_categories", True):
            for term in terms:
                hit = self._any_match(self._direct_cat, [term["slug"], term["name"]])
                if hit:
                    reasons.append("category %r is Lumos Ultra specific" % term["name"])
                    continue
                for ancestor in self._ancestors(term):
                    if self._any_match(self._direct_cat, [ancestor["slug"], ancestor["name"]]):
                        reasons.append(
                            "category %r is under Lumos Ultra specific %r"
                            % (term["name"], ancestor["name"])
                        )
                        break

        # --- direct: the text names the machine --------------------------- #
        if self.rules.get("use_direct_text", True):
            for pattern in self._direct_text:
                if pattern.search(title):
                    reasons.append("title mentions %r" % pattern.pattern)
                    continue
                hits = len(pattern.findall(body)) + len(pattern.findall(excerpt))
                if hits:
                    reasons.append(
                        "body mentions %r (%d time%s)"
                        % (pattern.pattern, hits, "" if hits == 1 else "s")
                    )

        if reasons:
            return "direct", reasons

        # --- subjects wanted only for the Ultra (LightBurn) --------------- #
        if self._any_match(self._ultra_required, [title]):
            return None

        # --- likely: shared accessory / software categories --------------- #
        if self.rules.get("use_related_categories", False):
            other_machine = [
                term["name"]
                for term in terms
                if self._any_match(self._other_machine_cat, [term["slug"], term["name"]])
            ]

            related = [
                term["name"]
                for term in terms
                if self._any_match(self._related_cat, [term["slug"], term["name"]])
            ]

            if related and not other_machine:
                reasons.extend(
                    "shared category %r applies to the Lumos Ultra" % name
                    for name in related
                )

        # --- likely: a MakeIt workflow, wherever it is filed -------------- #
        if self.rules.get("use_software_topics", False):
            for pattern in self._software_topic:
                if pattern.search(title):
                    reasons.append("title covers MakeIt topic %r" % pattern.pattern)
                elif pattern.search(body) or pattern.search(excerpt):
                    reasons.append("body covers MakeIt topic %r" % pattern.pattern)

        if reasons:
            return "likely", reasons

        return None

    def classify(self, article: Dict[str, Any]) -> Tuple[str, List[str]]:
        """Like :meth:`evaluate`, but never ``None``.

        Articles that are not relevant come back as ``("other", reasons)``,
        the reasons saying why they were left out, so the index can hold the
        whole knowledge base and still tell the two apart.
        """
        verdict = self.evaluate(article)
        if verdict:
            return verdict
        return OTHER, self._why_not(article)

    def _why_not(self, article: Dict[str, Any]) -> List[str]:
        terms = self._category_terms(article)
        title = strip_html(rendered(article.get("title")))

        # Name the machine's top-level section ("Vision/Vision Pro"), not a
        # generic child such as "Features" that every machine has.
        other_machine = sorted({
            html.unescape((self._ancestors(term) or [term])[-1]["name"])
            for term in terms
            if self._any_match(self._other_machine_cat, [term["slug"], term["name"]])
            or any(self._any_match(self._other_machine_cat, [a["slug"], a["name"]])
                   for a in self._ancestors(term))
        })
        related = [
            html.unescape(term["name"])
            for term in terms
            if self._any_match(self._related_cat, [term["slug"], term["name"]])
        ]

        if self._any_match(self._ultra_required, [title]):
            return ["title is about LightBurn (or another Ultra-only subject) but does not name the Lumos Ultra"]
        if related and other_machine:
            return ["shared category %s, but also filed under another machine: %s"
                    % (", ".join(repr(r) for r in related), ", ".join(other_machine))]
        if related and not self.rules.get("use_related_categories", False):
            return ["shared category %s only counts under the broad profile"
                    % ", ".join(repr(r) for r in related)]
        if other_machine:
            return ["filed under another machine: %s" % ", ".join(other_machine)]
        return ["no Lumos Ultra category, mention, shared category or MakeIt topic"]
