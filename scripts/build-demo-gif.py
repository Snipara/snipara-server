"""Build the short README demo GIF from deterministic, product-shaped frames.

The artifact is intentionally a compact conceptual walkthrough, not a claim that
the exact UI is part of the self-hosted server. It gives a new visitor a visual
answer to: what changes when an agent can recall the project?
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "snipara-project-brain-demo.gif"
WIDTH, HEIGHT = 960, 540
FPS = 10
DURATION_SECONDS = 12


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


FONT = {"xs": font(14), "sm": font(16), "body": font(20), "title": font(30), "hero": font(42), "mono": font(16, mono=True)}


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, radius: int = 18, outline: str | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text_center(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, typeface: ImageFont.FreeTypeFont, fill: str) -> None:
    bbox = draw.textbbox((0, 0), value, font=typeface)
    draw.text((xy[0] - (bbox[2] - bbox[0]) / 2, xy[1] - (bbox[3] - bbox[1]) / 2), value, font=typeface, fill=fill)


def progress(t: float, start: float, end: float) -> float:
    if t <= start:
        return 0.0
    if t >= end:
        return 1.0
    x = (t - start) / (end - start)
    return x * x * (3 - 2 * x)


def draw_mark(draw: ImageDraw.ImageDraw, x: int, y: int, scale: int = 1) -> None:
    color = "#68E5C7"
    purple = "#9B8CFF"
    draw.rounded_rectangle((x, y, x + 42 * scale, y + 42 * scale), radius=12 * scale, fill="#F8FAFC")
    cx, cy = x + 21 * scale, y + 21 * scale
    draw.line((cx, y + 10 * scale, cx, y + 32 * scale), fill="#0E1726", width=2 * scale)
    draw.line((x + 10 * scale, cy, x + 32 * scale, cy), fill="#0E1726", width=2 * scale)
    draw.ellipse((cx - 6 * scale, cy - 6 * scale, cx + 6 * scale, cy + 6 * scale), fill="#0E1726")
    for dx, dy, fill in ((10, 10, purple), (32, 10, color), (10, 32, color), (32, 32, purple)):
        draw.ellipse((x + (dx - 3) * scale, y + (dy - 3) * scale, x + (dx + 3) * scale, y + (dy + 3) * scale), fill=fill)


def render(t: float) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#0A1220")
    draw = ImageDraw.Draw(image)

    # A quiet background grid makes the state change legible without looking like a dashboard.
    for x in range(0, WIDTH, 48):
        draw.line((x, 0, x, HEIGHT), fill="#101D31", width=1)
    for y in range(0, HEIGHT, 48):
        draw.line((0, y, WIDTH, y), fill="#101D31", width=1)

    draw_mark(draw, 42, 28)
    draw.text((96, 38), "Snipara Project Brain", font=FONT["body"], fill="#F8FAFC")
    rounded(draw, (752, 30, 918, 68), "#102A2A", 18, "#28564F")
    draw.ellipse((771, 43, 783, 55), fill="#68E5C7")
    draw.text((793, 38), "MCP connected", font=FONT["xs"], fill="#A8F1DE")

    draw.text((42, 99), "Your agent already knows how to code.", font=FONT["hero"], fill="#F8FAFC")
    draw.text((42, 145), "The problem is that it forgets your project.", font=FONT["hero"], fill="#A9B7D2")

    without = progress(t, 0.4, 2.3)
    with_brain = progress(t, 2.4, 5.0)
    answer = progress(t, 5.0, 8.4)
    close = progress(t, 8.5, 10.5)

    # Left card: the blank-session loop.
    left_x, right_x, card_y, card_w, card_h = 42, 492, 224, 426, 214
    rounded(draw, (left_x, card_y, left_x + card_w, card_y + card_h), "#131F32", 22, "#25344D")
    draw.text((left_x + 24, card_y + 22), "WITHOUT SNIPARA", font=FONT["xs"], fill="#8392AC")
    rounded(draw, (left_x + 24, card_y + 58, left_x + card_w - 24, card_y + 122), "#0C1524", 14)
    draw.text((left_x + 42, card_y + 78), "I need to understand this codebase...", font=FONT["mono"], fill="#A9B7D2")
    draw.text((left_x + 24, card_y + 148), "Search files", font=FONT["sm"], fill="#B8C4D7")
    draw.text((left_x + 24, card_y + 178), "Rediscover decisions", font=FONT["sm"], fill="#B8C4D7")
    draw.text((left_x + 260, card_y + 148), "Start over", font=FONT["sm"], fill="#FFB4A9")
    draw.text((left_x + 260, card_y + 178), "Every session", font=FONT["sm"], fill="#FFB4A9")
    if without > 0:
        draw.line((left_x + 24, card_y + card_h - 16, left_x + 24 + int((card_w - 48) * without), card_y + card_h - 16), fill="#66758F", width=3)

    # Right card: the remembered project path.
    alpha = int(255 * with_brain)
    if alpha:
        rounded(draw, (right_x, card_y, right_x + card_w, card_y + card_h), "#122A2A", 22, "#2E7468")
        draw.text((right_x + 24, card_y + 22), "WITH SNIPARA", font=FONT["xs"], fill="#8FF0D5")
        rounded(draw, (right_x + 24, card_y + 58, right_x + card_w - 24, card_y + 122), "#0B1B23", 14, "#24564F")
        draw_mark(draw, right_x + 42, card_y + 69, 1)
        draw.text((right_x + 100, card_y + 76), "Project Brain", font=FONT["body"], fill="#F8FAFC")
        draw.text((right_x + 100, card_y + 103), "context returned in seconds", font=FONT["xs"], fill="#8FF0D5")
        lines = [
            "Decision: PostgreSQL is the source of truth",
            "Change: auth moved behind the service boundary",
            "Relevant: 3 files, 2 prior agent sessions",
        ]
        visible = int(round(answer * len(lines)))
        for index, line in enumerate(lines[:visible]):
            draw.ellipse((right_x + 28, card_y + 151 + index * 20, right_x + 35, card_y + 158 + index * 20), fill="#68E5C7")
            draw.text((right_x + 48, card_y + 143 + index * 20), line, font=FONT["xs"], fill="#D4F7EE")

    # Bottom story line.
    if close:
        draw.line((170, 484, 790, 484), fill="#2B3A55", width=3)
        stages = [(170, "Agent asks"), (480, "Snipara recalls"), (790, "First edit")]
        for index, (x, label) in enumerate(stages):
            fill = "#68E5C7" if index < 2 or close > 0.45 else "#556680"
            draw.ellipse((x - 10, 474, x + 10, 494), fill=fill)
            text_center(draw, (x, 520), label, FONT["xs"], "#D4DDEC")
        draw.text((42, 474), "Project context, not a blank session.", font=FONT["body"], fill="#F8FAFC")

    return image


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [render(index / FPS).quantize(colors=256, method=Image.Quantize.MEDIANCUT) for index in range(DURATION_SECONDS * FPS)]
    # Keep full frames instead of delta-optimizing them: GitHub's image viewer
    # and several Markdown previews handle full-frame GIFs more consistently.
    frames[0].save(OUTPUT, save_all=True, append_images=frames[1:], duration=1000 // FPS, loop=0, optimize=False, disposal=2)
    print(f"wrote {OUTPUT} ({len(frames)} frames, {DURATION_SECONDS}s)")


if __name__ == "__main__":
    main()
