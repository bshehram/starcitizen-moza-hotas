"""Makes dashboard/scdash.ico, the icon of the `SC Dashboard.lnk` shortcut (`scdash.py shortcut`).

The page's look in a few pixels (PLAN §11, direction B "Avionics"): the ink-blue ground, the
gray-blue corner brackets of its panes, and one cyan accent, a segmented meter. Each size is drawn
on its own pixel grid (lines snapped to whole pixels, then the drawing is shrunk from four times
the size), so the small sizes stay crisp instead of being scaled down from the large one.

Needs Pillow (in tools/requirements.txt); the dashboard itself never imports it. Run from the
project root after a change, and commit the .ico with this script:

    python dashboard/make_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent / "scdash.ico"
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
SUPER = 4                                  # drawn at four times the size, then shrunk

# The page's own colors (web/style.css): --c-pane, --c-line-2, --c-br, --c-accent, --c-accent-dim.
GROUND = (0x0A, 0x10, 0x17, 255)
EDGE = (0x26, 0x34, 0x44, 255)
BRACKET = (0x4A, 0x61, 0x76, 255)
ACCENT = (0x46, 0xD3, 0xE6, 255)
ACCENT_DIM = (0x1D, 0x55, 0x60, 255)


def frame(size):
    """The icon at `size` pixels square."""
    n = size * SUPER
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def box(x0, y0, x1, y1, fill):         # a rectangle in whole target pixels, end exclusive
        d.rectangle([x0 * SUPER, y0 * SUPER, x1 * SUPER - 1, y1 * SUPER - 1], fill=fill)

    radius = size * 0.2 * SUPER
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=radius, fill=EDGE)
    edge = max(1, size // 32)
    d.rounded_rectangle([edge * SUPER, edge * SUPER, n - 1 - edge * SUPER, n - 1 - edge * SUPER],
                        radius=max(0.0, radius - edge * SUPER), fill=GROUND)

    # Corner brackets, as on the page's panes.
    w = max(1, round(size / 16))
    m = max(2, round(size * 0.14))
    a = max(3, round(size * 0.22))
    for left in (True, False):
        for top in (True, False):
            x0 = m if left else size - m - a
            y0 = m if top else size - m - a
            xv = m if left else size - m - w          # the vertical arm's x
            yh = m if top else size - m - w           # the horizontal arm's y
            box(x0, yh, x0 + a, yh + w, BRACKET)
            box(xv, y0, xv + w, y0 + a, BRACKET)

    # The accent: a horizontal segmented meter across the middle, like the page's, two thirds lit.
    count = 3 if size <= 24 else 5
    lit = 2 if count == 3 else 3
    gap = max(1, round(size * 0.04))
    span = round(size * 0.78) - round(size * 0.22)
    sw = max(1, (span - gap * (count - 1)) // count)
    total = count * sw + gap * (count - 1)
    x = (size - total) // 2
    h = max(2, round(size * 0.18))
    y = (size - h) // 2
    for i in range(count):
        box(x, y, x + sw, y + h, ACCENT if i < lit else ACCENT_DIM)
        x += sw + gap
    return img.resize((size, size), Image.LANCZOS)


def main():
    frames = [frame(s) for s in SIZES]
    frames[-1].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    print("Wrote %s (%s px)" % (OUT, ", ".join(str(s) for s in SIZES)))


if __name__ == "__main__":
    main()
