from __future__ import annotations

from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets"
ICO_PATH = ASSET_DIR / "stock_translator.ico"
PNG_PATH = ASSET_DIR / "stock_translator_icon.png"


def main() -> int:
    configure_output()
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    canvas = draw_icon(1024)
    canvas.save(PNG_PATH)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    canvas.save(ICO_PATH, sizes=sizes)
    print(f"Wrote {ICO_PATH}")
    print(f"Wrote {PNG_PATH}")
    return 0


def configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def draw_icon(size: int) -> Image.Image:
    scale = size / 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    radius = int(216 * scale)
    margin = int(72 * scale)
    shadow_draw.rounded_rectangle(
        [margin, margin + int(18 * scale), size - margin, size - margin + int(18 * scale)],
        radius=radius,
        fill=(18, 34, 49, 92),
    )
    image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(int(24 * scale))))

    tile = rounded_gradient(size, margin, radius)
    image.alpha_composite(tile)
    draw = ImageDraw.Draw(image)

    graph_color = (143, 238, 204, 245)
    glow_color = (143, 238, 204, 72)
    points = [
        (int(220 * scale), int(662 * scale)),
        (int(350 * scale), int(570 * scale)),
        (int(454 * scale), int(610 * scale)),
        (int(548 * scale), int(480 * scale)),
        (int(662 * scale), int(514 * scale)),
        (int(806 * scale), int(350 * scale)),
    ]
    draw.line(points, fill=glow_color, width=int(46 * scale), joint="curve")
    draw.line(points, fill=graph_color, width=int(24 * scale), joint="curve")
    for x, y in points:
        draw.ellipse(
            [x - int(19 * scale), y - int(19 * scale), x + int(19 * scale), y + int(19 * scale)],
            fill=(255, 255, 255, 245),
        )
        draw.ellipse(
            [x - int(10 * scale), y - int(10 * scale), x + int(10 * scale), y + int(10 * scale)],
            fill=(20, 127, 113, 255),
        )

    badge_box = [
        int(198 * scale),
        int(196 * scale),
        int(596 * scale),
        int(592 * scale),
    ]
    draw.rounded_rectangle(
        badge_box,
        radius=int(108 * scale),
        fill=(255, 255, 255, 238),
        outline=(224, 241, 235, 230),
        width=int(8 * scale),
    )
    font = load_font(int(248 * scale), bold=True)
    text = "股"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (badge_box[0] + badge_box[2] - text_w) / 2 - bbox[0]
    text_y = (badge_box[1] + badge_box[3] - text_h) / 2 - bbox[1] - int(10 * scale)
    draw.text((text_x, text_y), text, font=font, fill=(17, 78, 105, 255))

    sparkle = [
        (int(790 * scale), int(212 * scale)),
        (int(822 * scale), int(288 * scale)),
        (int(902 * scale), int(320 * scale)),
        (int(822 * scale), int(352 * scale)),
        (int(790 * scale), int(430 * scale)),
        (int(758 * scale), int(352 * scale)),
        (int(680 * scale), int(320 * scale)),
        (int(758 * scale), int(288 * scale)),
    ]
    draw.polygon(sparkle, fill=(255, 199, 87, 255))
    draw.polygon(
        [(int(790 * scale), int(262 * scale)), (int(813 * scale), int(320 * scale)), (int(790 * scale), int(378 * scale)), (int(767 * scale), int(320 * scale))],
        fill=(255, 250, 213, 220),
    )

    return image


def rounded_gradient(size: int, margin: int, radius: int) -> Image.Image:
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    pixels = grad.load()
    for y in range(size):
        for x in range(size):
            nx = x / max(size - 1, 1)
            ny = y / max(size - 1, 1)
            mix = min(1.0, max(0.0, (nx * 0.55 + ny * 0.45)))
            r = int(14 + (21 - 14) * mix)
            g = int(126 + (65 - 126) * mix)
            b = int(115 + (99 - 115) * mix)
            pixels[x, y] = (r, g, b, 255)

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=255,
    )
    tile.alpha_composite(grad)
    tile.putalpha(mask)
    return tile


def load_font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = [
        "msjhbd.ttc" if bold else "msjh.ttc",
        "NotoSansCJK-Bold.ttc" if bold else "NotoSansCJK-Regular.ttc",
        "arialbd.ttf" if bold else "arial.ttf",
    ]
    font_dirs = [Path("C:/Windows/Fonts"), Path("/usr/share/fonts/opentype/noto")]
    for font_dir in font_dirs:
        for name in names:
            path = font_dir / name
            if path.is_file():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


if __name__ == "__main__":
    raise SystemExit(main())
