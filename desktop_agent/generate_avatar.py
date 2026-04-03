"""
desktop_agent/generate_avatar.py
──────────────────────────────────────────────────────────────────
Generates the Orallexa Pixel Bull — NFT desktop pet style.

Design: Front-facing flat pixel creature with gold diamond accents
from the Orallexa logo. 5 color variants based on market conditions.

Run once to generate all assets:
    python desktop_agent/generate_avatar.py

Output:
    assets/avatar/pixel_bull_{bullish,bearish,neutral,listening,thinking}.png
    assets/avatar/pixel_bull_sheet.png
    assets/avatar/bull_idle.png          (alias for neutral)
    assets/avatar/bull_walk.gif          (simple animation)
    assets/avatar/bull_state_*.png       (state sprites)
    assets/avatar/bull_r_*.png           (walk right frames)
    assets/avatar/bull_l_*.png           (walk left frames)
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw
import math

OUT_DIR = Path(__file__).parent.parent / "assets" / "avatar"
PX = 8         # pixel size
N_FRAMES = 6   # walk cycle frames

# ── Pixel Bull Grid (12x13, front-facing) ────────────────────────────────────
# B=body, E=eye, N=nose, G=gold accent, _=transparent
BULL_GRID = [
    "____BBBB____",  # 0 horns
    "___B____B___",  # 1 horn tips
    "__GBBBBBBBG_",  # 2 head top + gold corners
    "_BBBBBBBBBB_",  # 3 head
    "_BBEBBBBEBB_",  # 4 eyes
    "_BBBBBBBBBB_",  # 5 face
    "_BBBNNNNBBB_",  # 6 nostrils
    "_BBBBBBBBBB_",  # 7 chin
    "__BBBBBBBB__",  # 8 body
    "__BGBBBBGB__",  # 9 body + gold accents
    "__BBBBBBBB__",  # 10 body lower
    "__BB____BB__",  # 11 legs
    "__BB____BB__",  # 12 feet
]

# ── Color Palettes ───────────────────────────────────────────────────────────
PALETTES = {
    "bullish": {
        "B": (220, 60, 60),    # red body — market up (中国红=涨)
        "E": (40, 20, 20),
        "N": (160, 40, 40),
        "G": (255, 215, 0),
    },
    "bearish": {
        "B": (50, 170, 90),    # green body — market down
        "E": (15, 50, 25),
        "N": (30, 130, 60),
        "G": (255, 215, 0),
    },
    "neutral": {
        "B": (212, 175, 55),   # gold body — sideways
        "E": (80, 60, 10),
        "N": (180, 145, 35),
        "G": (255, 235, 100),
    },
    "listening": {
        "B": (100, 160, 220),  # blue body — voice active
        "E": (20, 50, 90),
        "N": (70, 130, 190),
        "G": (255, 215, 0),
    },
    "thinking": {
        "B": (150, 120, 200),  # purple body — AI analysis
        "E": (50, 30, 80),
        "N": (120, 90, 170),
        "G": (255, 215, 0),
    },
}

# New expression palettes
PALETTES["sleeping"] = {
    "B": (140, 130, 120),   # muted grey-brown — sleepy
    "E": (100, 90, 80),     # nearly closed eyes
    "N": (120, 110, 100),
    "G": (180, 160, 80),    # dim gold
}
PALETTES["happy"] = {
    "B": (255, 180, 60),    # bright orange-gold — excited
    "E": (60, 30, 10),
    "N": (220, 150, 40),
    "G": (255, 235, 100),
}
PALETTES["surprised"] = {
    "B": (255, 200, 100),   # bright yellow — surprised
    "E": (20, 20, 20),      # wide eyes (dark)
    "N": (220, 170, 70),
    "G": (255, 255, 150),
}
PALETTES["angry"] = {
    "B": (180, 50, 50),     # dark red — angry
    "E": (255, 60, 60),     # red glowing eyes
    "N": (140, 30, 30),
    "G": (255, 150, 0),     # fiery gold
}

# Sleeping bull grid — closed eyes (E replaced with B), Zzz above
SLEEPING_GRID = [
    "____BBBB____",  # 0 horns
    "___B____B___",  # 1 horn tips
    "__GBBBBBBBG_",  # 2 head top
    "_BBBBBBBBBB_",  # 3 head
    "_BB_BBBB_BB_",  # 4 closed eyes (lines)
    "_BBBBBBBBBB_",  # 5 face
    "_BBBNNNNBBB_",  # 6 nostrils
    "_BBBBBBBBBB_",  # 7 chin
    "__BBBBBBBB__",  # 8 body (slightly lower — slouching)
    "__BGBBBBGB__",  # 9 body + gold
    "__BBBBBBBB__",  # 10 body lower
    "__BB____BB__",  # 11 legs
    "__BB____BB__",  # 12 feet
]

# Happy bull grid — ^ ^ eyes (smiling)
HAPPY_GRID = [
    "____BBBB____",
    "___B____B___",
    "__GBBBBBBBG_",
    "_BBBBBBBBBB_",
    "_BB_BBB_BBB_",  # ^ ^ happy eyes (small lines)
    "_BBBBBBBBBB_",
    "_BBBNNNBBBB_",  # smaller nose — smile
    "_BBBBBBBBBB_",
    "__BBBBBBBB__",
    "__BGBBBBGB__",
    "__BBBBBBBB__",
    "__BB____BB__",
    "__BB____BB__",
]

# Surprised bull grid — O O eyes
SURPRISED_GRID = [
    "____BBBB____",
    "___B____B___",
    "__GBBBBBBBG_",
    "_BBBBBBBBBB_",
    "_BEEBBBBEEB_",  # O O big eyes
    "_BEEBBBBEEB_",
    "_BBBNNNNBBB_",
    "_BBBBBBBBBB_",
    "__BBBBBBBB__",
    "__BGBBBBGB__",
    "__BBBBBBBB__",
    "__BB____BB__",
    "__BB____BB__",
]

# Map old state names to palette names
STATE_MAP = {
    "idle": "neutral",
    "listening": "listening",
    "thinking": "thinking",
    "confident": "bullish",
    "warning": "bearish",
    "wait": "neutral",
    "sleeping": "sleeping",
    "happy": "happy",
    "surprised": "surprised",
    "angry": "angry",
}

# Expression states use custom grids
EXPRESSION_GRIDS = {
    "sleeping": SLEEPING_GRID,
    "happy": HAPPY_GRID,
    "surprised": SURPRISED_GRID,
}

GRID_W = len(BULL_GRID[0])
GRID_H = len(BULL_GRID)
SPRITE_W = GRID_W * PX
SPRITE_H = GRID_H * PX


def draw_pixel_bull(palette: dict, offset_y: int = 0,
                    grid: list[str] | None = None) -> Image.Image:
    """Draw a pixel bull with the given color palette and optional custom grid."""
    use_grid = grid or BULL_GRID
    img = Image.new("RGBA", (SPRITE_W, SPRITE_H + abs(offset_y)), (0, 0, 0, 0))
    for y, row in enumerate(use_grid):
        for x, ch in enumerate(row):
            if ch == "_":
                continue
            color = palette.get(ch, palette["B"])
            for py in range(PX):
                for px_x in range(PX):
                    img.putpixel(
                        (x * PX + px_x, y * PX + py + offset_y),
                        (*color, 255),
                    )
    return img


def draw_walk_frame(palette: dict, frame: int) -> Image.Image:
    """Draw a walk frame with leg animation (simple bob)."""
    t = (frame / N_FRAMES) * 2 * math.pi
    bob = round(2 * abs(math.sin(t)))

    # Modify grid for this frame: alternate leg positions
    grid = [row for row in BULL_GRID]

    img = Image.new("RGBA", (SPRITE_W, SPRITE_H + 4), (0, 0, 0, 0))
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == "_":
                continue
            color = palette.get(ch, palette["B"])
            y_off = bob if y < 11 else 0  # body bobs, feet stay
            for py in range(PX):
                for px_x in range(PX):
                    ny = y * PX + py + y_off
                    nx = x * PX + px_x
                    if 0 <= ny < SPRITE_H + 4 and 0 <= nx < SPRITE_W:
                        img.putpixel((nx, ny), (*color, 255))
    return img


def _frames_to_gif(frames: list[Image.Image], path: Path, duration: int = 120) -> None:
    out = []
    for f in frames:
        bg = Image.new("RGBA", f.size, (255, 255, 255, 255))
        bg.alpha_composite(f)
        out.append(bg.convert("RGB").quantize(colors=128, dither=0))
    out[0].save(str(path), save_all=True, append_images=out[1:],
                duration=duration, loop=0, disposal=2)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Generate all palette variants
    for name, pal in PALETTES.items():
        img = draw_pixel_bull(pal)
        img.save(OUT_DIR / f"pixel_bull_{name}.png")

    # Preview sheet
    sheet = Image.new("RGBA", (550, 130), (10, 10, 15, 255))
    x = 10
    for name in PALETTES:
        bull = Image.open(OUT_DIR / f"pixel_bull_{name}.png")
        sheet.paste(bull, (x, 12), bull)
        x += 110
    sheet.save(OUT_DIR / "pixel_bull_sheet.png")

    # State sprites (backward compatible with character_window.py)
    neutral = draw_pixel_bull(PALETTES["neutral"])
    neutral.save(OUT_DIR / "bull_idle.png")

    for state, pal_name in STATE_MAP.items():
        grid = EXPRESSION_GRIDS.get(state)
        img = draw_pixel_bull(PALETTES[pal_name], grid=grid)
        img.save(OUT_DIR / f"bull_state_{state}.png")

    # Walk frames (using neutral palette)
    pal = PALETTES["neutral"]
    right_frames = [draw_walk_frame(pal, i) for i in range(N_FRAMES)]
    left_frames = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in right_frames]

    for i, f in enumerate(right_frames):
        f.save(OUT_DIR / f"bull_r_{i:02d}.png")
    for i, f in enumerate(left_frames):
        f.save(OUT_DIR / f"bull_l_{i:02d}.png")

    _frames_to_gif(right_frames, OUT_DIR / "bull_walk.gif")

    total = len(PALETTES) + 1 + len(STATE_MAP) + N_FRAMES * 2 + 2
    print(f"Generated {total} sprites  ->  {OUT_DIR}")
    for p in sorted(OUT_DIR.iterdir()):
        if p.suffix in (".png", ".gif"):
            print(f"  {p.name}")


if __name__ == "__main__":
    main()
