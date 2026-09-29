"""Generate the default Open Graph card.

Social platforms need a real raster image for link previews. Rather than committing
a binary blob of unknown provenance, the card is generated from the same brand
colours the stylesheet uses, so it can be regenerated whenever the branding changes:

    python manage.py build_og_image

The output lands in ``static/img/og-default.png``, which is the path
``apps.core.seo.og_image_url`` falls back to. Regenerating is idempotent.
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management.base import BaseCommand

WIDTH, HEIGHT = 1200, 630
INK = (8, 9, 12)
GOLD = (212, 175, 55)
CREAM = (247, 242, 231)


class Command(BaseCommand):
    help = "Generate the default Open Graph card used when a page has no image."

    def handle(self, *args, **options):
        from PIL import Image, ImageDraw

        # Resolve through the staticfiles finders first so the file is written
        # into whichever directory STATIC_ROOT actually points at.
        target = finders.find("img/og-default.png")
        if target:
            output = Path(target)
        else:
            output = Path(settings.BASE_DIR) / "static" / "img" / "og-default.png"
            output.parent.mkdir(parents=True, exist_ok=True)

        image = Image.new("RGB", (WIDTH, HEIGHT), INK)
        draw = ImageDraw.Draw(image)

        # A gold rule frames the card the way the storefront's borders do.
        draw.rectangle([40, 40, WIDTH - 40, HEIGHT - 40], outline=GOLD, width=3)
        draw.line([(120, 470), (1080, 470)], fill=GOLD, width=2)

        _draw_text(draw, (600, 250), "EXPORT ZONE", 76, GOLD, anchor="mm")
        _draw_text(
            draw,
            (600, 355),
            "PREMIUM CLOTHING  ·  MEHERPUR",
            30,
            CREAM,
            anchor="mm",
        )
        _draw_text(
            draw,
            (600, 520),
            "Denim  ·  Shirts  ·  Polo T-Shirts",
            26,
            (150, 146, 138),
            anchor="mm",
        )

        image.save(output, format="PNG", optimize=True)
        self.stdout.write(
            self.style.SUCCESS(f"Wrote {output} ({output.stat().st_size} bytes)")
        )


def _draw_text(draw, position, text, size, colour, *, anchor="mm"):
    """Draw text with whichever TrueType font is available, else the default."""
    font = None
    for candidate in (
        "C:/Windows/Fonts/georgiab.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
    ):
        try:
            from PIL import ImageFont

            font = ImageFont.truetype(candidate, size)
            break
        except OSError:
            continue
    draw.text(position, text, fill=colour, font=font, anchor=anchor)
