"""Offline tests for the matching rules and the date handling.

Run: python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wecreat_index.config import Config  # noqa: E402
from wecreat_index.matcher import Matcher, strip_html  # noqa: E402
from wecreat_index.store import (  # noqa: E402
    apply_diff,
    collect,
    human_date,
    parse_wp_datetime,
)

# A trimmed copy of the live taxonomy.
CATEGORIES = {
    162: {"name": "Lumos Ultra", "slug": "lumos-ultra"},
    195: {"name": "User Manual", "slug": "user-manual-lumos-ultra"},
    190: {"name": "Features", "slug": "features", "parent": 162},
    196: {"name": "Features", "slug": "features-wecreat-lumos", "parent": 161},
    201: {"name": "60W/100W MOPA Laser Module", "slug": "60w-100w-mopa-laser-module"},
    194: {"name": "Troubleshooting", "slug": "troubleshooting"},
    151: {"name": "Vision/Vision Pro", "slug": "wecreat-vision-vision-pro"},
    153: {"name": "WeCreat MakeIt Software", "slug": "wecreat-makeit-software"},
    161: {"name": "Lumos / Lumos Flex", "slug": "wecreat-lumos"},
    152: {"name": "Smoke Purifier/Fume extractor", "slug": "smoke-purifier-fume-extractor"},
}


def article(aid, title, content="", cats=(), date="2026-01-01T00:00:00",
            modified=None, excerpt=""):
    return {
        "id": aid,
        "slug": "slug-%s" % aid,
        "link": "https://help.wecreat.com/kb/slug-%s/" % aid,
        "date": date,
        "modified": modified or date,
        "status": "publish",
        "title": {"rendered": title},
        "excerpt": {"rendered": excerpt},
        "content": {"rendered": content},
        "lsvr_kba_cat": list(cats),
        "lsvr_kba_tag": [],
    }


class MatcherTests(unittest.TestCase):
    def matcher(self, profile="broad"):
        return Matcher(Config({"profile": profile}), CATEGORIES)

    def test_direct_category(self):
        result = self.matcher().evaluate(
            article(1, "Unboxing your machine", cats=[162])
        )
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "direct")

    def test_subcategory_of_lumos_ultra_is_direct(self):
        """"Features" with slug ``features`` is a child of Lumos Ultra."""
        result = self.matcher().evaluate(
            article(4880, "Explanations about Frequency and Pulse Width", cats=[190, 196])
        )
        self.assertEqual(result[0], "direct")
        self.assertTrue(any("under Lumos Ultra" in r for r in result[1]))

    def test_same_name_under_another_machine_is_not_direct(self):
        result = self.matcher().evaluate(
            article(9, "Engraving tips", cats=[196])
        )
        self.assertIsNone(result)

    def test_title_mention(self):
        result = self.matcher().evaluate(
            article(2, "How to Level the Lumos Ultra Bed", cats=[194])
        )
        self.assertEqual(result[0], "direct")
        self.assertTrue(any("title" in r for r in result[1]))

    def test_the_framing_article_is_caught_despite_its_categories(self):
        """The real article Lee linked: MOPA + Troubleshooting, no Ultra category."""
        result = self.matcher().evaluate(
            article(
                4375,
                "What to Do if Framing is Offset with Lumos Ultra",
                content="<p>If the <strong>red light framing preview</strong> ...</p>",
                cats=[201, 194],
            )
        )
        self.assertIsNotNone(result)
        self.assertEqual(result[0], "direct")

    def test_body_only_mention(self):
        result = self.matcher().evaluate(
            article(
                3,
                "Choosing a focus height",
                content="<p>On the Lumos&nbsp;Ultra the optimal height differs.</p>",
                cats=[194],
            )
        )
        self.assertEqual(result[0], "direct")

    def test_unrelated_machine_is_skipped(self):
        self.assertIsNone(
            self.matcher().evaluate(
                article(4, "Replace the X-axis belt for Vision 20W", cats=[151])
            )
        )

    def test_shared_software_is_likely_under_broad(self):
        result = self.matcher("broad").evaluate(
            article(5, "MakeIt: importing an SVG", cats=[153])
        )
        self.assertEqual(result[0], "likely")

    def test_shared_software_is_skipped_under_strict(self):
        self.assertIsNone(
            self.matcher("strict").evaluate(
                article(6, "MakeIt: importing an SVG", cats=[153])
            )
        )

    def test_shared_category_tied_to_another_machine_is_skipped(self):
        """Fume extractor article filed under Lumos / Lumos Flex stays out."""
        self.assertIsNone(
            self.matcher("broad").evaluate(
                article(7, "Cleaning the filter", cats=[152, 161])
            )
        )

    def test_makeit_test_grid_is_caught_under_another_machine(self):
        """The real color-engraving article: filed under Lumos / Lumos Flex only."""
        result = self.matcher("broad").evaluate(
            article(
                3542,
                "Color Engraving with WeCreat Lumos",
                content="<p>In MakeIt, open the <b>Color Test Grid</b> ...</p>",
                cats=[161],
            )
        )
        self.assertEqual(result[0], "likely")
        self.assertTrue(any("MakeIt topic" in r for r in result[1]))

    def test_material_array_test_is_caught_under_vision(self):
        result = self.matcher("broad").evaluate(
            article(2966, "Array Test for New Materials", cats=[151])
        )
        self.assertEqual(result[0], "likely")
        self.assertTrue(any(r.startswith("title covers") for r in result[1]))

    def test_passing_makeit_mention_is_not_a_topic(self):
        """Vision connection guides mention MakeIt without covering a workflow."""
        self.assertIsNone(
            self.matcher("broad").evaluate(
                article(2933, "WiFi Connection Guide",
                        content="<p>Open MakeIt and select the device.</p>",
                        cats=[151])
            )
        )

    def test_software_topics_are_skipped_under_strict(self):
        self.assertIsNone(
            self.matcher("strict").evaluate(
                article(2966, "Array Test for New Materials", cats=[151])
            )
        )

    def test_lightburn_without_the_ultra_is_dropped(self):
        """A LightBurn guide in a shared category still needs to name the Ultra."""
        self.assertIsNone(
            self.matcher("broad").evaluate(
                article(3306, "Feeder Connection with Other Laser Models using LightBurn",
                        content="<p>Works with all WeCreat lasers.</p>", cats=[153])
            )
        )

    def test_lightburn_with_the_ultra_is_direct(self):
        result = self.matcher("broad").evaluate(
            article(9001, "Using LightBurn with the Lumos Ultra", cats=[153])
        )
        self.assertEqual(result[0], "direct")

    def test_lightburn_in_an_ultra_category_is_direct(self):
        result = self.matcher("broad").evaluate(
            article(9002, "LightBurn camera setup", cats=[190])
        )
        self.assertEqual(result[0], "direct")

    def test_passing_lightburn_mention_does_not_gate(self):
        """Only a LightBurn *title* needs the Ultra; a body mention is fine."""
        result = self.matcher("broad").evaluate(
            article(3195, "Software Version Information",
                    content="<p>Added LightBurn file import.</p>", cats=[153])
        )
        self.assertEqual(result[0], "likely")

    def test_topics_are_labelled(self):
        topics = self.matcher().topics(
            article(9003, "Color engraving on steel",
                    content="<p>Run a test grid, then import into LightBurn.</p>")
        )
        self.assertIn("LightBurn", topics)
        self.assertIn("Test grids", topics)
        self.assertIn("Color engraving", topics)
        self.assertNotIn("Rotary", topics)

    def test_strip_html_drops_scripts_and_entities(self):
        text = strip_html("<p>Lumos&nbsp;Ultra</p><script>var x = '<b>';</script>")
        self.assertIn("Lumos", text)
        self.assertNotIn("var x", text)


class DateTests(unittest.TestCase):
    def test_human_date_matches_the_article_footer(self):
        self.assertEqual(human_date("2026-08-04T08:36:05"), "August 4, 2026")

    def test_z_suffix_is_handled(self):
        self.assertIsNotNone(parse_wp_datetime("2026-08-04T15:36:05Z"))

    def test_bad_value_is_tolerated(self):
        self.assertEqual(human_date(None), "")
        self.assertEqual(human_date("not a date"), "")


class SortAndDiffTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config({"profile": "broad"})
        self.matcher = Matcher(self.cfg, CATEGORIES)
        self.articles = [
            article(10, "Lumos Ultra alpha", cats=[162], date="2025-03-04T10:00:00"),
            article(11, "Lumos Ultra bravo", cats=[162], date="2026-08-04T10:00:00"),
            article(12, "Lumos Ultra charlie", cats=[162], date="2026-01-15T10:00:00"),
        ]

    def records(self):
        return collect(self.articles, self.matcher, self.cfg, CATEGORIES, {})

    def test_sorted_newest_first(self):
        titles = [r["title"] for r in self.records()]
        self.assertEqual(titles, ["Lumos Ultra bravo", "Lumos Ultra charlie", "Lumos Ultra alpha"])

    def test_first_run_flags_nothing_as_new(self):
        changes, state = apply_diff(self.records(), {"runs": 0, "articles": {}})
        self.assertEqual(changes["new"], [])
        self.assertEqual(state["runs"], 1)
        self.assertEqual(len(state["articles"]), 3)

    def test_second_run_detects_new_updated_and_dropped(self):
        _, baseline = apply_diff(self.records(), {"runs": 0, "articles": {}})

        # A brand new article, an edit to an existing one, one gone.
        self.articles.append(
            article(13, "Lumos Ultra delta", cats=[162], date="2026-09-01T10:00:00")
        )
        self.articles[1]["modified"] = "2026-09-10T12:00:00"
        self.articles = [a for a in self.articles if a["id"] != 10]

        changes, _ = apply_diff(self.records(), baseline)
        self.assertEqual([c["id"] for c in changes["new"]], [13])
        self.assertEqual([c["id"] for c in changes["updated"]], [11])
        self.assertEqual([c["id"] for c in changes["no_longer_matching"]], [10])

    def test_first_seen_survives_across_runs(self):
        _, baseline = apply_diff(self.records(), {"runs": 0, "articles": {}})
        first_seen = baseline["articles"]["11"]["first_seen"]
        _, second = apply_diff(self.records(), baseline)
        self.assertEqual(second["articles"]["11"]["first_seen"], first_seen)


class WholeKnowledgeBaseTests(unittest.TestCase):
    """Every article is indexed; the ones not about the Ultra are tier 'other'."""

    def setUp(self):
        self.cfg = Config({"profile": "broad"})
        self.matcher = Matcher(self.cfg, CATEGORIES)
        self.articles = [
            article(20, "Lumos Ultra alpha", cats=[162]),
            article(21, "Replace the X-axis belt for Vision 20W", cats=[151]),
            article(22, "Cleaning the filter", cats=[152, 161]),
            article(23, "Some general notice"),
        ]

    def records(self):
        return collect(self.articles, self.matcher, self.cfg, CATEGORIES, {})

    def by_id(self, records):
        return {r["id"]: r for r in records}

    def test_everything_is_indexed_with_a_reason(self):
        recs = self.by_id(self.records())
        self.assertEqual(set(recs), {20, 21, 22, 23})
        self.assertEqual(recs[20]["confidence"], "direct")
        for aid in (21, 22, 23):
            self.assertEqual(recs[aid]["confidence"], "other")
            self.assertTrue(recs[aid]["match_reasons"])
        self.assertIn("another machine: Vision/Vision Pro", recs[21]["match_reasons"][0])
        self.assertIn("also filed under another machine", recs[22]["match_reasons"][0])
        self.assertIn("no Lumos Ultra", recs[23]["match_reasons"][0])

    def test_lightburn_reason(self):
        self.articles.append(article(24, "Using LightBurn with feeders", cats=[153]))
        rec = self.by_id(self.records())[24]
        self.assertEqual(rec["confidence"], "other")
        self.assertIn("LightBurn", rec["match_reasons"][0])

    def test_counts_split_relevant_and_other(self):
        from wecreat_index.store import build_index
        recs = self.records()
        changes, _ = apply_diff(recs, {"runs": 0, "articles": {}})
        counts = build_index(recs, changes, self.cfg, {"runs": 0}, scanned=4)["counts"]
        self.assertEqual((counts["indexed"], counts["matched"], counts["other"]), (4, 1, 3))

    def test_upgrade_does_not_flag_old_other_articles_as_new(self):
        """A state file from before 'index everything' only knows relevant articles."""
        old_state = {"runs": 3, "articles": {"20": {"confidence": "direct", "modified_iso": "2026-01-01T00:00:00"}}}
        recs = self.records()
        changes, state = apply_diff(recs, old_state)
        self.assertEqual(changes["new"], [])
        self.assertEqual(changes["other_new"], 0)
        self.assertTrue(all(r["status"] == "unchanged" for r in recs))
        self.assertTrue(state["tracks_other"])

    def test_later_runs_report_changes_between_tiers(self):
        _, baseline = apply_diff(self.records(), {"runs": 0, "articles": {}})

        # 23 starts naming the Ultra; 20 is re-filed as a Vision article; 25 is a new irrelevant one.
        self.articles[3] = article(23, "Some general notice", content="<p>Also on the Lumos Ultra.</p>")
        self.articles[0] = article(20, "Alpha", cats=[151])
        self.articles.append(article(25, "Vista fan swap", cats=[151]))

        recs = self.records()
        changes, _ = apply_diff(recs, baseline)
        status = {r["id"]: r["status"] for r in recs}
        self.assertEqual([c["id"] for c in changes["new"]], [23])        # newly about the Ultra
        self.assertEqual(status[23], "new")
        self.assertEqual(changes["other_new"], 1)                         # 25: new, but not in the summary
        self.assertEqual(status[25], "new")
        dropped = changes["no_longer_matching"]
        self.assertEqual([d["id"] for d in dropped], [20])
        self.assertIn("not about the Lumos Ultra", dropped[0]["reason"])

    def test_article_gone_from_site(self):
        _, baseline = apply_diff(self.records(), {"runs": 0, "articles": {}})
        self.articles = self.articles[1:]
        changes, _ = apply_diff(self.records(), baseline)
        self.assertEqual(changes["no_longer_matching"][0]["reason"], "no longer on help.wecreat.com")


if __name__ == "__main__":
    unittest.main()
