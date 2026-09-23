# LUOM What's New

*Formerly WhatsNewWecreat. Renamed so that WeCreat's name only describes what
the program is for, not what it is called.*

Indexes the [WeCreat support knowledge base](https://help.wecreat.com) and keeps a
JSON index of every article relevant to the **WeCreat Lumos Ultra**, sorted by
publish date with the newest first — and reports what has appeared or changed
since the last run.

A free utility for members of
[Lumos Ultra Owners & Makers (LUOM)](https://www.facebook.com/groups/lumosultraownersmakers).

## What this is, and whose content it handles

LUOM What's New is an **indexer, searcher and cataloger** of WeCreat's public
knowledge base. It isn't the knowledge base and doesn't stand in for it.

* **LUOM does not write, maintain, host or own WeCreat's knowledge base.** The
  articles belong to WeCreat and live at <https://help.wecreat.com>. This tool
  reads them through WordPress's public API, lists the ones that concern the
  Lumos Ultra, and links to each original.
* **Not affiliated with, endorsed by or sponsored by WeCreat.** It isn't an
  official WeCreat product or support channel. WeCreat, Lumos Ultra and MakeIt
  are names and trademarks of their owner, used only descriptively ("for
  WeCreat owners", "articles about the Lumos Ultra"). The product name is
  LUOM's own, and WeCreat's logos and styling are not used.
* **Excerpts and links, not copies.** The UI shows titles and short excerpts,
  each linking to the original ("Read on help.wecreat.com"). `index.json` also
  stores each article's plain text so full-text search works offline. That copy
  stays on the user's computer. The download never includes an index, and
  `index.json` itself carries a `notice` asking not to republish it.

The same statement appears in:

* the page header subtitle
* the source note above the article list
* the About dialog (ⓘ button)
* the footer, the first-run dialog and the splash line
* `README.txt` in the download
* the `--help` output and the server's start-up log
* the launcher headers
* the User-Agent sent to help.wecreat.com
* every `index.json`

The wording lives in one place, `NOTICE` in `wecreat_index/__init__.py`, except
where the HTML needs its own phrasing. If you change it, keep those in step.

## Branding

The LUOM icon and splash artwork live full-size in `branding\` (`luom-icon.png`,
`luom-splash.png`). The app ships small copies, made by

```powershell
python branding\make_assets.py     # needs Pillow; only for regenerating assets
```

| Generated file | Used for |
| --- | --- |
| `wecreat_index\ui\assets\logo-256.webp` | header logo, first-run dialog, footer, "stopped" page |
| `wecreat_index\ui\assets\favicon-64.png` | browser tab icon |
| `wecreat_index\ui\assets\splash.webp` | start-up splash (once per browser tab, at least 1.8 s, click or `Esc` to skip) |
| `packaging\LUOM-WhatsNew.ico` | Windows shortcut icon, shipped in the download |

The UI colours (`--accent` / `--accent-2` in `app.css`) follow the logo's laser
blue to violet. The group link is in `ui\index.html`: the header's
**LUOM on Facebook** button, the footer, the first-run dialog and the stopped
page.

## How it gets the data

`help.wecreat.com` is WordPress. Knowledge-base articles live in the custom post
type `lsvr_kba` and are published through the public WP REST API:

```
https://help.wecreat.com/wp-json/wp/v2/lsvr_kba?per_page=100&page=1
https://help.wecreat.com/wp-json/wp/v2/lsvr_kba_cat?per_page=100
```

So there is no HTML scraping and nothing to re-fix when the theme changes. The
API gives the exact publish date that the article footer renders (the `date`
field — `2026-08-04T08:36:05` is the "August 4, 2026" at the bottom of the
framing article), plus `modified`, `link`, `title` and the category terms.

**No third-party packages.** Standard library only, Python 3.8+.

## Running it

```powershell
cd D:\DevHome\LUOM-WhatsNew
python -m wecreat_index
```

or press **F5** in VS Code ("Scan KB (broad)"), or **Ctrl+Shift+B** for the
build task.

### Sharing it: the one-file download

People who just want to use the app don't need this repository:

```powershell
python build.py        # or Ctrl+Shift+P > Run Task > "Build distributable (.pyz + zip)"
```

writes `dist\LUOM-WhatsNew-<version>.zip` (about 370 KB, mostly the LUOM artwork). Hand that zip out.
It unpacks to one folder:

| File | For |
| --- | --- |
| `LUOM-WhatsNew.pyz` | the whole app in one file, runs on any Python 3.8+ |
| `Start LUOM What's New.cmd` | Windows: double-click to start |
| `Start LUOM What's New.command` | macOS: double-click to start |
| `start-luom-whatsnew.sh` | Linux |
| `README.txt` | instructions written for end users |
| `LUOM-WhatsNew.ico` | LUOM icon, for a desktop / Start menu shortcut |
| `LICENSE.txt` | the MIT license |

The launchers look for Python 3.8+. If it's missing, they explain that and
**ask** before installing it. Windows uses `winget install Python.Python.3.12
--scope user`, which needs no admin rights; if winget isn't available, the
python.org download page opens. macOS uses Homebrew if present, otherwise the
python.org page. Linux offers the distribution's package-manager command. On
Windows the UI then runs with no console window (via `pythonw`). Output goes to
`luom-whatsnew.log` in the data folder, and the power button on the page
stops it. Starting it again while it's running just reopens the page.

The `.pyz` also works on its own:

```
python LUOM-WhatsNew.pyz                 # web UI (same options as wecreat_index.server)
python LUOM-WhatsNew.pyz scan            # one scan, for Task Scheduler / cron
python LUOM-WhatsNew.pyz scan --help
```

Packaged, it uses the built-in rules in `config.py`. A `config.json` in the data
folder, or next to the `.pyz`, overrides them. A source checkout also falls back
to the repository's `config.json`. Keep `config.py` and `config.json` in step
when changing the rules, so the download behaves the same as the repository.

### Where the data lives

`index.json` and the run baseline `state.json` are kept in an application folder
shared by every user of the computer, not in the project folder:

| OS | Data folder |
| --- | --- |
| Windows | `%ProgramData%\LUOM-WhatsNew` (normally `C:\ProgramData\LUOM-WhatsNew`) |
| macOS | `/Users/Shared/LUOM-WhatsNew` |
| Linux | `~/.local/share/luom-whatsnew` (`$XDG_DATA_HOME`). Linux has no shared folder an ordinary user can write to |

On Windows, when the program creates that folder it gives the local *Users*
group modify rights on it. Otherwise ProgramData lets only the account that
created a file change it. If the shared folder can't be created, it falls back
to the per-user folder
(`%LOCALAPPDATA%`, `~/Library/Application Support`). Set `LUOM_WHATSNEW_DATA`
to use a different folder, or pass `--out` for a single run. Data left by earlier
versions - `WhatsNewWecreat` folders under the old name, or the original `.\data`
folder - is moved over automatically the first time, unless the new folder
already has an index. The old `WHATSNEWWECREAT_DATA` variable still works.
Delete `state.json`, or pass `--reset`, to start change tracking over.

### Web UI

```powershell
python -m wecreat_index.server
```

or F5 → **"Web UI (browse + scan)"**. It serves <http://127.0.0.1:8765/> and
opens it in your browser. Still standard library only; the page is plain
HTML/CSS/JS with no CDN, so it works offline.

* **First start**: if the data folder has no index yet, a dialog explains that
  and offers **Download index now** (the progress shows in the dialog) or
  **Exit program** (stops the server).
* **Articles** tab: a scrolling card list, newest published first, grouped by
  month. Sort by published (either direction), last modified, first seen by the
  scanner, confidence, or title.
* **New since the last scan**: anything the latest scan found new or updated is
  pinned in a green section at the top, whatever the sort order. The same cards
  are tinted and badged *New* / *Updated* in their normal place, the tab shows
  "N new", and the browser tab title starts with "(N new)". The first scan only
  records a baseline, so nothing is marked until the second.
* **Search** with a *Search in* dropdown (everything, title, article text,
  excerpt, categories, match reasons, URL/slug, ID). `"exact phrase"` and
  `-exclude` work. A hit inside the article body shows the surrounding passage
  on the card. Press `/` to jump to the search box, `Esc` to clear it.
* **Dropdown filters**: section, category (shown with its parent, e.g.
  *Lumos Ultra › Features*), topic (LightBurn, test grids, rotary, camera, ...),
  confidence, status, *matched by* (which rule caught
  it), published year, tag (only if the site uses tags), plus a published date
  range. Each option shows how many articles it would leave. Clicking a
  category chip on a card filters to it. Filters live in the URL, so a bookmark
  keeps them.
* **View options**, remembered per browser in `localStorage`:
  * **Show articles not about the Lumos Ultra.** Off by default. When ticked,
    the `other` tier appears as muted cards badged *Not Lumos Ultra*, with a
    "Why it is not included" note. The Confidence dropdown gains *Not Lumos
    Ultra*, and the Scan state tab follows the same setting.
  * **Open articles in:**
    * **a separate browser window** (the default). This is one pop-up-style
      window, with no tab strip, placed on the right-hand part of the screen
      and reused for every article.
    * **the same browser tab each time.** One tab next to the app, reused.
    * **a new browser tab each time.**

    The page opens the article window or tab itself, under a name per mode, and
    keeps it as its *opener*. Browsers only let the opener send a window on
    another site to the next article. The window is found again even after the
    app page is reloaded. Ctrl-, Shift- and middle-click still open a normal
    new tab in every mode.
* **Scan state** tab: the `state.json` baseline, meaning run count, last and
  previous run, what the last run found new / updated / dropped, and a sortable,
  filterable table of every tracked article.
* **Run scan** button runs `python -m wecreat_index` in the background and
  streams its output into the page. When it finishes, the list reloads. The
  label beside it shows when the data was last downloaded
  (`index.json`'s `generated_at`). The power button next to it exits the
  program.

`--port`, `--host`, `--no-browser`, `-o/--out` and `-c/--config` are available.
The server binds to loopback, ignores requests addressed to other host names,
and only starts a scan or exits on a JSON `POST`, so other websites cannot
trigger either.

### Options

| Flag | Effect |
| --- | --- |
| `-o, --out DIR` | Where `index.json` and `state.json` go (default: the data folder above) |
| `-c, --config FILE` | Rules file (default `.\config.json`) |
| `-p, --profile NAME` | `broad` (default), `strict`, or `category-keyword` |
| `--reset` | Ignore the saved baseline and treat this as a first run |
| `--no-state` | Do not read or write `state.json` at all |
| `--dry-run` | Scan and report, write nothing |
| `-v` / `-q` | Debug logging / errors only |

## How an article is judged relevant

Category filtering alone is not enough. The article
*"What to Do if Framing is Offset with Lumos Ultra"* is filed under
**60W/100W MOPA Laser Module** and **Troubleshooting** — neither of which is a
Lumos Ultra category — so a category-only filter would miss it. Matching
therefore runs on two tiers, and every hit records *why* it matched.

**`direct`** — the article is unambiguously about the Ultra:

* it sits in a category whose slug or name matches `lumos[\s_-]*ultra`
  (Lumos Ultra, AutoFlow Conveyor for Lumos Ultra, Slide Extension For Lumos
  Ultra, User Manual), **or in a subcategory of one**. The generic Features,
  Getting Started, Maintenance, Materials & Settings and Troubleshooting
  categories (slugs `features`, `getting-started`, ...) are children of Lumos
  Ultra, **or**
* its title, excerpt or body text names the Lumos Ultra.

**`likely`** — the article covers shared hardware, accessories or software the
Ultra uses, without naming it: WeCreat MakeIt Software (and its subcategories),
the software user manual, the 60W/100W MOPA laser module, the smoke
purifier / fume extractor, the pass-through feeder, the AutoFlow conveyor.

A `likely` candidate is dropped if it is also filed under a category belonging
to a different machine (Vision, Vision Pro, Vista, Lumos / Lumos Flex) — that
exclusion never applies to a `direct` hit, so a Lumos-category article that
explicitly discusses the Ultra still comes through.

**`likely` (MakeIt topic)** — the title, excerpt or body walks through a MakeIt
workflow: material / color **test grids** and array tests, color engraving, and
MOPA frequency / pulse width settings. WeCreat files these under whichever
machine the article was written for — *"Color Engraving with WeCreat Lumos"*
sits in Lumos / Lumos Flex, *"Array Test for New Materials"* in Vision/Vision
Pro — but the workflow is the same in MakeIt on the Ultra, so the other-machine
exclusion does **not** apply to this rule. A bare mention of "MakeIt" is not
enough; dozens of Vision/Vista connection guides say "open MakeIt" in passing.
Extend `software_topic_patterns` in `config.json` to cover more MakeIt features.

**Ultra-only subjects (LightBurn)** — if an article's *title* is about LightBurn,
it is kept only on a `direct` hit: it names the Lumos Ultra or sits in a Lumos
Ultra category. The shared-category and MakeIt-topic rules cannot pull it in.
WeCreat's LightBurn guides so far are written for Vision / Vista, or for other
brands' lasers on the pass-through feeder, so none qualify yet. The rule is
there for the first one that covers the Ultra. A LightBurn mention in the body
of an otherwise relevant article (e.g. a release note) doesn't trigger this
rule. Add more such subjects in `ultra_required_title_patterns`.

**Topics** — every indexed article also gets topic labels (`topics` in
`config.json`: LightBurn, Test grids, Color engraving, MOPA / UV settings,
Rotary, Camera, Firmware, Connection, Focus, Conveyor / feeder, Maintenance).
They are used only for filtering in the UI; they never decide inclusion.

**`other`**: everything else. **The whole knowledge base is indexed.**
Articles that fail the tests above aren't dropped. They are kept at confidence
`other`, with the reason in `match_reasons`:

* "filed under another machine: Vision/Vision Pro"
* "title is about LightBurn … but does not name the Lumos Ultra"
* "shared category …, but also filed under another machine"
* "no Lumos Ultra category, mention, shared category or MakeIt topic"

The UI hides them unless *Show articles not about the Lumos Ultra* is ticked.
The "what's new" summary (`changes_since_last_run`, the banner, the pinned
section) covers only the Lumos Ultra articles. A new `other` article gets
`status: "new"` on its record, and is counted in `counts.other_new`, but never
floods the summary. An article that moves into the Lumos Ultra tiers is
reported as new. One that moves out is listed under `no_longer_matching`, with
a `reason`. The first scan after upgrading from a version that didn't index
everything takes the `other` articles as a baseline, so they aren't all flagged
as new.

This is the **`broad`** profile, which is the default. `strict` keeps only the
`direct` tier; everything else becomes `other`.

All of it is data, not code: edit `config.json` to add a keyword, add a
category, or loosen an exclusion. The patterns are case-insensitive regular
expressions matched against both the category slug and its display name.

## `index.json`

```jsonc
{
  "schema": 1,
  "notice": "LUOM What's New is a free, independent tool ... please do not republish it.",
  "content_owner": "WeCreat - https://help.wecreat.com (articles are linked, not owned or maintained by LUOM)",
  "generated_at": "2026-09-19T21:04:11",
  "previous_run": "2026-09-12T08:00:02",
  "run_number": 4,
  "source": { "site": "...", "post_type": "lsvr_kba", "profile": "broad", "rules": { ... } },
  "sort": "published date, newest first",
  "counts": {
    "articles_scanned": 345,
    "indexed": 345,          // the whole knowledge base
    "matched": 157,          // direct + likely: about the Lumos Ultra
    "direct": 24,
    "likely": 133,
    "other": 188,            // indexed, not about the Lumos Ultra
    "new": 2,                // new / updated / no_longer_matching: Lumos Ultra articles only
    "updated": 1,
    "no_longer_matching": 0,
    "other_new": 0
  },
  "changes_since_last_run": {
    "new": [ { "id": 4857, "title": "...", "url": "...", "published": "September 4, 2026" } ],
    "updated": [ { "id": 4375, "title": "...", "previously_modified": "...", "modified": "..." } ],
    "no_longer_matching": []
  },
  "articles": [
    {
      "id": 4375,
      "title": "What to Do if Framing is Offset with Lumos Ultra",
      "url": "https://help.wecreat.com/kb/what-to-do-if-framing-is-offset-with-lumos-ultra/",
      "slug": "what-to-do-if-framing-is-offset-with-lumos-ultra",
      "published": "August 4, 2026",
      "published_iso": "2026-08-04T08:36:05",
      "modified": "August 4, 2026",
      "modified_iso": "2026-08-04T08:36:07",
      "categories": ["60W/100W MOPA Laser Module", "Troubleshooting"],
      "category_slugs": ["60w-100w-mopa-laser-module", "troubleshooting"],
      "category_paths": ["60W/100W MOPA Laser Module", "Troubleshooting"],
      "tags": [],
      "topics": ["Focus"],
      "confidence": "direct",
      "match_reasons": ["title mentions 'lumos[\\s_-]*ultra'"],
      "excerpt": "If the red light framing preview does not align with ...",
      "text": "If the red light framing preview does not align with ... (full plain text, capped at 20,000 chars)",
      "status": "new",
      "first_seen": "2026-09-19T21:04:11",
      "last_seen": "2026-09-19T21:04:11"
    }
  ]
}
```

`articles` is the sorted list — newest publish date first. `status` on each
record is `new`, `updated` or `unchanged` relative to the previous run.
`category_paths` gives each category with its parents ("Lumos Ultra › Features"),
because several sections reuse the same child names. `text` is the plain article
body, used by the UI's full-text search. The
first run has no baseline, so it flags nothing as new; it records the baseline
and the *second* run starts reporting.

## Layout

```
LUOM-WhatsNew\
  wecreat_index\
    __init__.py
    __main__.py     python -m wecreat_index
    cli.py          argument parsing, run orchestration, console summary
    config.py       endpoints, match profiles, config.json loading
    api.py          WP REST client: pagination, retry/backoff, gzip
    matcher.py      the direct / likely relevance decision
    store.py        record building, sorting, state diff, JSON output
    paths.py        per-OS data folder, config lookup, legacy .\data migration
    server.py       python -m wecreat_index.server - local web UI + scan runner
    app.py          entry point of LUOM-WhatsNew.pyz (serve / scan)
    ui\             index.html, app.css, app.js, assets\ (no external assets)
  branding\         full-size LUOM artwork + make_assets.py
  packaging\        launchers, end-user README.txt, LUOM-WhatsNew.ico
  tests\
    test_matcher.py matching rules, dates, diffing
    test_paths.py   data-folder choice and migration
    test_app.py     .pyz entry point, the build itself, second-launch handling
                    (49 tests in all, offline)
  .vscode\          launch, tasks, settings
  build.py          builds dist\LUOM-WhatsNew.pyz and the zip to share
  config.json       editable match rules
  scan.py           single-file entry point for VS Code Run/Debug
  serve.py          same, for the web UI
```

## Platforms

Pure Python standard library plus a browser page, so it runs anywhere Python
3.8+ does. It has been run on Windows 11 with Python 3.12, 3.13 and 3.9, both
from source and as the packaged `.pyz` through the Windows launcher. It has not
yet been run on macOS or Linux; the shell launcher has only been syntax-checked
and run under Git Bash.

* **Windows 10/11**: primary target. Data in `C:\ProgramData\LUOM-WhatsNew`.
* **macOS** (Python from python.org or Homebrew): works. Data in
  `/Users/Shared/LUOM-WhatsNew`.
* **Linux**, including a Raspberry Pi or a NAS that runs Python: works. Data is
  per user (see above). On a machine with no screen, run
  `python -m wecreat_index.server --no-browser --host 0.0.0.0`. Note that the
  host-name guard then only accepts the machine's own addresses, so browsing
  from another device needs that guard relaxed.
* **Browser**: any current Chrome, Edge, Firefox or Safari (2023 or later;
  the page uses CSS `color-mix` and `<dialog>`).
* **Not supported**: phones or tablets as the *host*, since there's no Python.
  They can view the page if it's served from a computer on the network.

## Tests

```powershell
python -m unittest discover -s tests -v
```

They run offline against fixtures, including the real framing article's
category arrangement, so the "category filtering alone would miss it" case stays
covered.

## Running it on a schedule

Task Scheduler, weekly:

```
Program:   python
Arguments: -m wecreat_index
Start in:  D:\DevHome\LUOM-WhatsNew
```

Each run rewrites `index.json` in the data folder with `changes_since_last_run`
filled in, so checking that block is enough to see what WeCreat has published.
The web UI picks up a scheduled run's results when you switch back to its tab.
If the task runs as a different account (e.g. SYSTEM), the shared ProgramData
folder means the UI still sees the same data.

## Notes

* The scan is read-only and hits the public API only — roughly four requests for
  the whole knowledge base.
* If WeCreat ever renames the post type or taxonomy, change `post_type` /
  `category_taxonomy` in `config.json`; current values are discoverable at
  `https://help.wecreat.com/wp-json/wp/v2/types`.

## License

The code is under the MIT License; see `LICENSE`. That covers this tool only.
The knowledge-base articles it indexes and links to belong to WeCreat and are
not part of this project or its license.
