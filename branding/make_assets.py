#!/usr/bin/env python3
"""Turn the full-size LUOM artwork in this folder into the small files the app ships.

    python branding/make_assets.py

Needs Pillow (``pip install pillow``) - only here, to regenerate the assets.
The app itself stays standard-library only; the generated files are committed.

    luom-icon.png   (1254x1254)  ->  wecreat_index/ui/assets/logo-256.webp  header / dialogs
                                     wecreat_index/ui/assets/favicon-64.png browser tab
                                     packaging/LUOM-WhatsNew.ico          Windows shortcut icon
    luom-splash.png (1672x941)   ->  wecreat_index/ui/assets/splash.webp    start-up splash
"""

from __future__ import annotations

import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "wecreat_index", "ui", "assets")
PACKAGING = os.path.join(ROOT, "packaging")


def round_badge(img: Image.Image) -> Image.Image:
    """Keep the circular badge, make the black corners transparent.

    The artwork sits on a black square; on the light theme those corners
    would show as a dark box. A soft-edged circle just outside the glow ring
    keeps the glow and drops the corners.
    """
    img = img.convert("RGBA")
    size = img.size[0]
    mask = Image.new("L", img.size, 0)
    inset = int(size * 0.035)
    ImageDraw.Draw(mask).ellipse((inset, inset, size - inset, size - inset), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(size * 0.006))
    img.putalpha(mask)
    return img


def main() -> None:
    os.makedirs(ASSETS, exist_ok=True)

    icon = round_badge(Image.open(os.path.join(HERE, "luom-icon.png")))
    icon.resize((256, 256), Image.LANCZOS).save(
        os.path.join(ASSETS, "logo-256.webp"), quality=85, method=6)
    icon.resize((64, 64), Image.LANCZOS).save(
        os.path.join(ASSETS, "favicon-64.png"), optimize=True)
    icon.save(os.path.join(PACKAGING, "LUOM-WhatsNew.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

    splash = Image.open(os.path.join(HERE, "luom-splash.png")).convert("RGB")
    splash.thumbnail((1600, 1600), Image.LANCZOS)
    splash.save(os.path.join(ASSETS, "splash.webp"), quality=80, method=6)

    for folder, name in [(ASSETS, n) for n in sorted(os.listdir(ASSETS))] + [(PACKAGING, "LUOM-WhatsNew.ico")]:
        path = os.path.join(folder, name)
        print("%-60s %7.1f KB" % (os.path.relpath(path, ROOT), os.path.getsize(path) / 1024))


if __name__ == "__main__":
    main()
