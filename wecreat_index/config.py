"""Configuration: site endpoints and the rules that decide what is Lumos Ultra related.

Everything here can be overridden from ``config.json`` next to the project root,
so the match rules can be tuned without touching code.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

# --------------------------------------------------------------------------- #
# Site
# --------------------------------------------------------------------------- #

SITE = "https://help.wecreat.com"
API_ROOT = "/wp-json/wp/v2"

#: WordPress custom post type used for knowledge-base articles.
POST_TYPE = "lsvr_kba"
#: Taxonomies attached to that post type.
CATEGORY_TAXONOMY = "lsvr_kba_cat"
TAG_TAXONOMY = "lsvr_kba_tag"


# --------------------------------------------------------------------------- #
# Match rules
# --------------------------------------------------------------------------- #

# Patterns matched against a category's slug AND its display name.
# A hit here means the article is unambiguously about the Lumos Ultra.
DIRECT_CATEGORY_PATTERNS = [
    r"lumos[\s_-]*ultra",
]

# Patterns matched against article title / excerpt / body text.
DIRECT_TEXT_PATTERNS = [
    r"lumos[\s_-]*ultra",
]

# Categories that cover hardware, accessories and software the Lumos Ultra uses,
# but which are shared with other machines. Articles matched only by these are
# recorded at "likely" confidence rather than "direct".
RELATED_CATEGORY_PATTERNS = [
    r"makeit[\s_-]*software",       # WeCreat MakeIt Software (+ its subcategories)
    r"software[\s_-]*user[\s_-]*manual",
    r"mopa[\s_-]*laser[\s_-]*module",   # 60W/100W MOPA module fits the Ultra
    r"smoke[\s_-]*purifier",
    r"fume[\s_-]*extractor",
    r"auto[\s_-]*pass[\s_-]*through[\s_-]*feeder",
    r"autoflow[\s_-]*conveyor",
]

# MakeIt workflow topics, matched against article title / excerpt / body text.
# WeCreat often files a software walkthrough under whichever machine it was
# written for (the color test grid lives in "Lumos / Lumos Flex", the material
# array test in "Vision/Vision Pro"), but the workflow is the same in MakeIt on
# the Ultra. A hit here is "likely" and is NOT subject to the other-machine
# exclusion below. The bare word "MakeIt" is deliberately absent: dozens of
# Vision/Vista connection guides mention it in passing.
SOFTWARE_TOPIC_PATTERNS = [
    r"test[\s_-]*(grid|array)",            # material / color test grids
    r"array[\s_-]*test",
    r"(material|colou?r|parameter)[\s_-]*test",
    r"colou?r[\s_-]*engrav",               # MOPA color engraving on metal
    r"pulse[\s_-]*width",                  # MOPA frequency / pulse width settings
]

# Subjects that are only wanted when the article is about the Lumos Ultra.
# If the TITLE matches one of these, the article is kept only on a ``direct``
# hit (it names the Ultra or sits in a Lumos Ultra category) - the shared
# category and MakeIt topic rules cannot pull it in. LightBurn is the case in
# point: WeCreat's LightBurn guides are written for Vision / Vista or for
# third-party lasers on the pass-through feeder.
ULTRA_REQUIRED_TITLE_PATTERNS = [
    r"light[\s_-]*burn",
]

# Topic labels attached to every indexed article, for filtering in the UI.
# They never decide whether an article is included.
TOPICS = {
    "LightBurn": [r"light[\s_-]*burn"],
    "Test grids": [r"test[\s_-]*(grid|array)", r"array[\s_-]*test", r"(material|colou?r|parameter)[\s_-]*test"],
    "Color engraving": [r"colou?r[\s_-]*engrav"],
    "MOPA / UV settings": [r"pulse[\s_-]*width", r"\bfrequency\b", r"\bmopa\b"],
    "Rotary": [r"\brotary\b", r"tumbler", r"cylind"],
    "Camera": [r"\bcamera\b"],
    "Firmware": [r"firmware"],
    "Connection": [r"\bwi-?fi\b", r"\busb\b", r"connect(ion|ing)?\b"],
    "Focus": [r"\bfocus", r"focal"],
    "Conveyor / feeder": [r"conveyor", r"feeder", r"autoflow"],
    "Maintenance": [r"\bclean", r"maintenan", r"replace"],
}

# Categories that belong to *other* machines. These never disqualify an article
# that explicitly names the Lumos Ultra, but they stop a machine-specific
# article from sneaking in on the "related" tier alone.
OTHER_MACHINE_CATEGORY_PATTERNS = [
    r"vision",
    r"vista",
    r"lumos[\s_-]*flex",
    r"wecreat-lumos$",              # "Lumos / Lumos Flex" category slug
    r"features-wecreat-lumos",
    r"maintenance-wecreat-lumos",
    r"materials-settings-wecreat-lumos",
    r"troubleshooting-wecreat-lumos",
    r"user-manual-wecreat-lumos",
    r"lumos-getting-started",
    r"slide-extension-for-lumos-lumos-flex",
]

#: Named rule sets. ``--profile`` selects one.
PROFILES = {
    # Only an explicit "Lumos Ultra" mention or a Lumos Ultra category.
    "strict": {
        "use_direct_categories": True,
        "use_direct_text": True,
        "use_related_categories": False,
        "use_software_topics": False,
    },
    # Same as strict; kept as a distinct name because it reads better in the
    # index metadata and leaves room to diverge later.
    "category-keyword": {
        "use_direct_categories": True,
        "use_direct_text": True,
        "use_related_categories": False,
        "use_software_topics": False,
    },
    # Direct hits plus shared software / accessory / module categories and
    # MakeIt workflow topics wherever they are filed.
    "broad": {
        "use_direct_categories": True,
        "use_direct_text": True,
        "use_related_categories": True,
        "use_software_topics": True,
    },
}

DEFAULT_PROFILE = "broad"


class Config:
    """Resolved runtime configuration."""

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        data = data or {}
        self.site: str = data.get("site", SITE).rstrip("/")
        self.post_type: str = data.get("post_type", POST_TYPE)
        self.category_taxonomy: str = data.get("category_taxonomy", CATEGORY_TAXONOMY)
        self.tag_taxonomy: str = data.get("tag_taxonomy", TAG_TAXONOMY)

        self.profile: str = data.get("profile", DEFAULT_PROFILE)
        self.direct_category_patterns: List[str] = data.get(
            "direct_category_patterns", DIRECT_CATEGORY_PATTERNS
        )
        self.direct_text_patterns: List[str] = data.get(
            "direct_text_patterns", DIRECT_TEXT_PATTERNS
        )
        self.related_category_patterns: List[str] = data.get(
            "related_category_patterns", RELATED_CATEGORY_PATTERNS
        )
        self.software_topic_patterns: List[str] = data.get(
            "software_topic_patterns", SOFTWARE_TOPIC_PATTERNS
        )
        self.ultra_required_title_patterns: List[str] = data.get(
            "ultra_required_title_patterns", ULTRA_REQUIRED_TITLE_PATTERNS
        )
        self.topics: Dict[str, List[str]] = data.get("topics", TOPICS)
        self.other_machine_category_patterns: List[str] = data.get(
            "other_machine_category_patterns", OTHER_MACHINE_CATEGORY_PATTERNS
        )

        self.page_size: int = int(data.get("page_size", 100))
        self.request_timeout: int = int(data.get("request_timeout", 45))
        self.max_retries: int = int(data.get("max_retries", 4))
        self.user_agent: str = data.get(
            "user_agent",
            "LUOM-WhatsNew/1.0 (independent community indexer for personal use; not affiliated with WeCreat)",
        )

    # -- derived ----------------------------------------------------------- #

    @property
    def api_base(self) -> str:
        return self.site + API_ROOT

    @property
    def rules(self) -> Dict[str, bool]:
        return PROFILES.get(self.profile, PROFILES[DEFAULT_PROFILE])

    def compiled(self, patterns: List[str]) -> List["re.Pattern"]:
        return [re.compile(p, re.IGNORECASE) for p in patterns]

    # -- loading ----------------------------------------------------------- #

    @classmethod
    def load(cls, path: Optional[str] = None, profile: Optional[str] = None) -> "Config":
        """Load ``config.json`` if it exists, then apply a profile override."""
        data: Dict[str, Any] = {}
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        if profile:
            data["profile"] = profile
        cfg = cls(data)
        if cfg.profile not in PROFILES:
            raise ValueError(
                "Unknown profile %r. Choose one of: %s"
                % (cfg.profile, ", ".join(sorted(PROFILES)))
            )
        return cfg

    def describe(self) -> Dict[str, Any]:
        """The slice of config worth recording in the generated index."""
        return {
            "site": self.site,
            "post_type": self.post_type,
            "profile": self.profile,
            "rules": self.rules,
        }
