"""Build the public README demo GIF.

The animation is a short explanatory walkthrough: a blank agent session becomes
a project-grounded answer. The abstract background was generated with the
Zorai project's FAL workflow, while all visible Snipara branding and product
copy are composited locally from the canonical v2 logo assets. Keeping those
layers separate prevents image generation from inventing a lookalike logo,
watermark, or unreadable product UI.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "snipara-project-brain-demo.gif"
BACKGROUND = ROOT / "assets" / "snipara-continuity-background.jpg"
LOGO = ROOT / "assets" / "brand-logo-v2-inverted.png"
WIDTH, HEIGHT = 960, 540
FPS = 10
DURATION_SECONDS = 10


def font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
        )
        if mono
        else (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/Library/Fonts/Microsoft/Verdana.ttf",
        )
    )
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


FONT = {
    "micro": font(12),
    "xs": font(14),
    "sm": font(16),
    "body": font(19),
    "hero": font(39),
    "mono": font(15, mono=True),
}


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def ease(value: float, start: float, end: float) -> float:
    """Smoothstep timing that gives cards a calm, deliberate entrance."""
    x = clamp((value - start) / (end - start))
    return x * x * (3 - 2 * x)


def rgba(hex_color: str, alpha: int = 255) -> tuple[int, int, int, int]:
    value = hex_color.removeprefix("#")
    return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), alpha)


def draw_centered(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, typeface: ImageFont.FreeTypeFont, fill) -> None:
    bbox = draw.textbbox((0, 0), value, font=typeface)
    draw.text((xy[0] - (bbox[2] - bbox[0]) / 2, xy[1] - (bbox[3] - bbox[1]) / 2), value, font=typeface, fill=fill)


def rounded_panel(
    image: Image.Image,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    radius: int = 18,
    outline: tuple[int, int, int, int] | None = None,
    width: int = 1,
) -> None:
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    panel = ImageDraw.Draw(layer)
    panel.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    image.alpha_composite(layer)


def add_logo(image: Image.Image, x: int, y: int, width: int, opacity: float = 1.0) -> None:
    logo = Image.open(LOGO).convert("RGBA")
    ratio = width / logo.width
    logo = logo.resize((width, round(logo.height * ratio)), Image.Resampling.LANCZOS)
    if opacity < 1:
        alpha = logo.getchannel("A").point(lambda value: round(value * clamp(opacity)))
        logo.putalpha(alpha)
    image.alpha_composite(logo, (x, y))


def background_frame(t: float) -> Image.Image:
    """Use the FAL still as a restrained texture, with a deterministic drift."""
    if BACKGROUND.exists():
        source = Image.open(BACKGROUND).convert("RGB")
        source = ImageOps.fit(source, (WIDTH + 96, HEIGHT + 54), method=Image.Resampling.LANCZOS)
        # Keep the generated texture stable so the GIF can delta-compress it;
        # the motion comes from the staged UI, pulse, cursor, and progress rail.
        pan_x = 42
        pan_y = 22
        image = source.crop((pan_x, pan_y, pan_x + WIDTH, pan_y + HEIGHT)).convert("RGBA")
        image = ImageEnhance.Color(image).enhance(0.68)
        image = ImageEnhance.Brightness(image).enhance(0.58)
    else:
        image = Image.new("RGBA", (WIDTH, HEIGHT), rgba("#07111F"))

    veil = Image.new("RGBA", image.size, rgba("#07111F", 155))
    image.alpha_composite(veil)

    # A very soft moving bloom connects the FAL texture to the UI states.
    bloom = Image.new("RGBA", image.size, (0, 0, 0, 0))
    bloom_draw = ImageDraw.Draw(bloom)
    cx = 550 + round(math.sin(t * 0.52) * 90)
    cy = 190 + round(math.cos(t * 0.43) * 22)
    for radius, alpha in ((220, 7), (150, 10), (92, 15)):
        bloom_draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=rgba("#46D6D0", alpha))
    image.alpha_composite(bloom)
    return image


def render(t: float) -> Image.Image:
    image = background_frame(t)
    draw = ImageDraw.Draw(image)

    # Keep the background legible as atmosphere, not as a second UI. Draw the
    # low-opacity grid on its own layer because ImageDraw does not composite
    # alpha when drawing directly onto an RGBA image.
    grid = Image.new("RGBA", image.size, (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid)
    for x in range(0, WIDTH, 64):
        grid_draw.line((x, 0, x, HEIGHT), fill=rgba("#C7D8F0", 4), width=1)
    for y in range(0, HEIGHT, 64):
        grid_draw.line((0, y, WIDTH, y), fill=rgba("#C7D8F0", 3), width=1)
    image.alpha_composite(grid)
    draw = ImageDraw.Draw(image)

    add_logo(image, 40, 22, 184)
    rounded_panel(image, (758, 26, 918, 58), rgba("#0C252A", 205), radius=16, outline=rgba("#3BD6BA", 115))
    draw = ImageDraw.Draw(image)
    draw.ellipse((777, 37, 787, 47), fill="#6DE7C8")
    draw.text((798, 32), "MCP connected", font=FONT["micro"], fill="#C5F7EA")

    draw.text((40, 93), "Your agent knows how to code.", font=FONT["hero"], fill="#F5F8FF")
    draw.text((40, 138), "It just forgets the project.", font=FONT["hero"], fill="#AAB9D2")

    left_in = ease(t, 0.45, 1.45)
    handoff = ease(t, 2.5, 4.3)
    answer = ease(t, 4.35, 6.55)
    close = ease(t, 7.15, 8.5)

    left_x, right_x, card_y, card_w, card_h = 40, 492, 222, 428, 218

    # Blank session: the agent has to reconstruct the project from scratch.
    left_shift = round((1 - left_in) * -24)
    lx = left_x + left_shift
    rounded_panel(image, (lx, card_y, lx + card_w, card_y + card_h), rgba("#0A1423", round(225 * left_in)), radius=22, outline=rgba("#566580", round(150 * left_in)), width=1)
    draw = ImageDraw.Draw(image)
    if left_in > 0:
        draw.text((lx + 24, card_y + 20), "BLANK SESSION", font=FONT["micro"], fill="#C9D4E8")
    rounded_panel(image, (lx + 24, card_y + 55, lx + card_w - 24, card_y + 111), rgba("#07101C", round(238 * left_in)), radius=13, outline=rgba("#20304A", round(180 * left_in)))
    draw = ImageDraw.Draw(image)
    prompt = "I need to understand this codebase..."
    if left_in > 0:
        draw.text((lx + 42, card_y + 74), prompt, font=FONT["mono"], fill="#D5DFF0")
        cursor_x = lx + 42 + draw.textlength(prompt, font=FONT["mono"]) + 8
        draw.line((cursor_x, card_y + 75, cursor_x, card_y + 94), fill="#6DE7C8", width=2)
    blank_lines = [("Search files", "broad rediscovery"), ("Revisit decisions", "session starts over")]
    for index, (label, detail) in enumerate(blank_lines):
        yy = card_y + 139 + index * 28
        if left_in > 0:
            draw.ellipse((lx + 25, yy + 4, lx + 32, yy + 11), fill="#F19A8E")
            draw.text((lx + 43, yy), label, font=FONT["sm"], fill="#D7E0EF")
            draw.text((lx + 205, yy + 1), detail, font=FONT["micro"], fill="#A4B0C5")

    # Handoff: a real Snipara logo sits at the center of the transition.
    if handoff > 0:
        draw.line((470, 332, 492, 332), fill="#6DE7C8", width=2)
        pulse_x = 470 + round(22 * handoff)
        draw.ellipse((pulse_x - 5, 327, pulse_x + 5, 337), fill="#F5FFFC")

    right_shift = round((1 - handoff) * 28)
    rx = right_x + right_shift
    rounded_panel(image, (rx, card_y, rx + card_w, card_y + card_h), rgba("#0B2526", round(232 * handoff)), radius=22, outline=rgba("#51D5B4", round(210 * handoff)), width=1)
    draw = ImageDraw.Draw(image)
    if handoff > 0:
        draw.text((rx + 24, card_y + 20), "WITH SNIPARA", font=FONT["micro"], fill="#8BF0D4")
    add_logo(image, rx + 24, card_y + 51, 126, handoff)
    draw = ImageDraw.Draw(image)
    if handoff > 0:
        draw.text((rx + 166, card_y + 62), "context ready", font=FONT["body"], fill="#F2FFFC")
        draw.text((rx + 166, card_y + 91), "source-backed · shared · persistent", font=FONT["micro"], fill="#A7EAD9")

    lines = [
        ("Decision", "PostgreSQL is the source of truth"),
        ("Change", "Auth moved behind the service boundary"),
        ("Relevant", "3 files · 2 prior agent sessions"),
    ]
    visible = answer * len(lines)
    for index, (label, value) in enumerate(lines):
        line_progress = clamp(visible - index)
        if line_progress <= 0:
            continue
        yy = card_y + 131 + index * 25
        draw.ellipse((rx + 24, yy + 5, rx + 31, yy + 12), fill="#6DE7C8")
        draw.text((rx + 42, yy), label, font=FONT["micro"], fill="#8BF0D4")
        draw.text((rx + 104, yy - 1), value, font=FONT["xs"], fill="#E1FBF4")
        if line_progress < 1:
            draw.line((rx + 42, yy + 20, rx + 42 + round(330 * line_progress), yy + 20), fill="#6DE7C8", width=2)

    # A tiny story rail lands only after the answer is visible.
    if close > 0:
        rail_y = 482
        draw.line((455, rail_y, 880, rail_y), fill="#8291AB", width=2)
        stages = [(455, "Agent asks"), (665, "Snipara recalls"), (880, "Agent starts")]
        for index, (x, label) in enumerate(stages):
            reached = ease(close, index * 0.25, min(1, index * 0.25 + 0.45))
            if reached > 0:
                draw.ellipse((x - 8, rail_y - 8, x + 8, rail_y + 8), fill="#6DE7C8")
                draw_centered(draw, (x, 510), label, FONT["micro"], "#DDE7F3")
        draw.text((40, 470), "Project context, not a blank session.", font=FONT["body"], fill="#F5F8FF")

    # A short, unobtrusive progress indicator makes the loop feel intentional.
    draw.rounded_rectangle((40, 526, 920, 529), radius=2, fill="#162740")
    draw.rounded_rectangle((40, 526, 40 + round(880 * clamp(t / DURATION_SECONDS)), 529), radius=2, fill="#6DE7C8")
    return image.convert("RGB")


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame_count = DURATION_SECONDS * FPS
    palette = render(0).quantize(colors=128, method=Image.Quantize.MEDIANCUT)
    frames = [palette]
    frames.extend(
        render(index / FPS).quantize(palette=palette, dither=Image.Dither.NONE)
        for index in range(1, frame_count)
    )
    # Optimized deltas keep the README asset lightweight while remaining
    # compatible with GitHub's Markdown image viewer.
    frames[0].save(
        OUTPUT,
        save_all=True,
        append_images=frames[1:],
        duration=round(1000 / FPS),
        loop=0,
        optimize=True,
        disposal=1,
    )
    print(f"wrote {OUTPUT} ({frame_count} frames, {DURATION_SECONDS}s, {FPS}fps)")


if __name__ == "__main__":
    main()
