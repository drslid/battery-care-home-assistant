"""Draw the Battery Care brand icons: a battery holding a heart, on transparency."""

import math
from pathlib import Path

from PIL import Image, ImageDraw

BRAND_DIR = Path(__file__).resolve().parents[1] / "custom_components/battery_care/brand"
TEAL = (22, 160, 133, 255)
WHITE = (255, 255, 255, 255)
CANVAS = 2048  # Drawn large, then downscaled for smooth edges.


def heart(center_x: float, center_y: float, width: float) -> list[tuple[float, float]]:
    """Return a heart outline whose bounding box is centred on the given point."""
    steps = 720
    curve = [
        (
            16 * math.sin(t) ** 3,
            -(
                13 * math.cos(t)
                - 5 * math.cos(2 * t)
                - 2 * math.cos(3 * t)
                - math.cos(4 * t)
            ),
        )
        for t in (2 * math.pi * i / steps for i in range(steps))
    ]
    xs = [x for x, _ in curve]
    ys = [y for _, y in curve]
    scale = width / (max(xs) - min(xs))
    mid_x = (max(xs) + min(xs)) / 2
    mid_y = (max(ys) + min(ys)) / 2
    return [
        (center_x + (x - mid_x) * scale, center_y + (y - mid_y) * scale)
        for x, y in curve
    ]


def draw() -> Image.Image:
    """Draw the icon at full resolution."""
    size = CANVAS
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)

    margin = 0.01 * size
    body_width = 0.62 * size
    body_left = (size - body_width) / 2
    body_top = margin + 0.08 * size
    body_bottom = size - margin
    radius = 0.11 * size

    cap_width = 0.3 * size
    cap_left = (size - cap_width) / 2
    pen.rounded_rectangle(
        (cap_left, margin, cap_left + cap_width, body_top + radius),
        radius=0.035 * size,
        fill=TEAL,
    )
    pen.rounded_rectangle(
        (body_left, body_top, body_left + body_width, body_bottom),
        radius=radius,
        fill=TEAL,
    )
    pen.polygon(
        heart(size / 2, (body_top + body_bottom) / 2, 0.6 * body_width), fill=WHITE
    )
    return image


def main() -> None:
    """Write icon.png (256 px) and icon@2x.png (512 px)."""
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    image = draw()
    for name, pixels in (("icon.png", 256), ("icon@2x.png", 512)):
        image.resize((pixels, pixels), Image.Resampling.LANCZOS).save(
            BRAND_DIR / name, optimize=True
        )


if __name__ == "__main__":
    main()
