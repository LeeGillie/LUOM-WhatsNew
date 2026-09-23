"""LUOM What's New - an independent indexer of WeCreat knowledge-base articles
relevant to the Lumos Ultra. Not affiliated with WeCreat; see ``NOTICE``.

The WeCreat support site (https://help.wecreat.com) is WordPress. Knowledge-base
articles live in the custom post type ``lsvr_kba`` and are exposed through the
public WP REST API, so this package talks to the API rather than scraping HTML.
"""

__version__ = "1.0.0"

APP_NAME = "LUOM What's New"

#: One-paragraph statement of what this tool is - and is not. Shown in the CLI
#: help and the server log, and written into every index.json.
NOTICE = (
    "LUOM What's New is a free, independent tool made for members of the Lumos "
    "Ultra Owners & Makers (LUOM) Facebook group. It only indexes, searches and "
    "catalogs WeCreat's public knowledge base at https://help.wecreat.com and links "
    "to the original articles. LUOM does not write, maintain, host or own that "
    "knowledge base, and this tool is not affiliated with, endorsed by or sponsored "
    "by WeCreat. The articles belong to WeCreat; WeCreat, Lumos Ultra and MakeIt are "
    "names of their owner, used only to describe what this tool works with. The "
    "index is for personal use on your own computer - please do not republish it."
)
