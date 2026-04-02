"""
Generate showcase GIF and hero banner for the Orallexa README.

Outputs:
  - assets/showcase_demo.gif  (480x160 animated GIF)
  - assets/hero_banner.png    (800x200 static banner)
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ASSETS = Path(__file__).resolve().parent
AVATAR = ASSETS / "avatar"

# Theme colours (Art Deco / Gatsby noir)
BG_COLOR = (10, 10, 15)          # #0A0A0F
GOLD = (212, 175, 55)            # #D4AF37
GOLD_DIM = (160, 130, 40)        # muted gold for subtitles
WHITE = (220, 220, 220)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_and_resize(path: Path, size: tuple[int, int]) -> Image.Image:
    """Load an RGBA image and resize it to *size*, preserving transparency."""
    img = Image.open(path).convert("RGBA")
    return img.resize(size, Image.LANCZOS)


def get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return the best available font at the requested size."""
    # Try common system fonts on Windows
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/consola.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    # Fallback to PIL default
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# 1. Animated showcase GIF  (480 x 160)
# ---------------------------------------------------------------------------

def create_showcase_gif() -> None:
    W, H = 480, 160
    SPRITE = 96                       # sprite render size
    SECTION_W = W // 3                # 160 px per section
    DURATION_MS = 180                 # per-frame duration

    # Load walk frames (6 frames)
    walk_frames = [
        load_and_resize(AVATAR / f"bull_r_{i:02d}.png", (SPRITE, SPRITE))
        for i in range(6)
    ]
    # State sprites
    thinking = load_and_resize(AVATAR / "bull_state_thinking.png", (SPRITE, SPRITE))
    confident = load_and_resize(AVATAR / "bull_state_confident.png", (SPRITE, SPRITE))

    font_label = get_font(13)
    font_status = get_font(11)

    # We create 6 frames total (one per walk animation frame)
    gif_frames: list[Image.Image] = []

    for idx in range(6):
        frame = Image.new("RGBA", (W, H), BG_COLOR)
        draw = ImageDraw.Draw(frame)

        # --- Thin gold dividers ---
        for x_div in (SECTION_W, SECTION_W * 2):
            draw.line([(x_div, 10), (x_div, H - 10)], fill=GOLD_DIM, width=1)

        # --- Left section: walking bull ---
        sprite_y = (H - SPRITE) // 2 - 5
        walk_x = (SECTION_W - SPRITE) // 2
        frame.paste(walk_frames[idx], (walk_x, sprite_y), walk_frames[idx])
        # Label
        bbox = draw.textbbox((0, 0), "Scanning...", font=font_label)
        tw = bbox[2] - bbox[0]
        draw.text(((SECTION_W - tw) // 2, H - 28), "Scanning...", fill=GOLD, font=font_label)

        # --- Middle section: thinking ---
        mid_x = SECTION_W + (SECTION_W - SPRITE) // 2
        frame.paste(thinking, (mid_x, sprite_y), thinking)
        label = "Analyzing..."
        bbox = draw.textbbox((0, 0), label, font=font_label)
        tw = bbox[2] - bbox[0]
        draw.text(
            (SECTION_W + (SECTION_W - tw) // 2, H - 28),
            label, fill=GOLD, font=font_label,
        )

        # --- Right section: confident + BUY ---
        right_x = SECTION_W * 2 + (SECTION_W - SPRITE) // 2
        frame.paste(confident, (right_x, sprite_y), confident)
        label = "BUY Signal!"
        bbox = draw.textbbox((0, 0), label, font=font_label)
        tw = bbox[2] - bbox[0]
        draw.text(
            (SECTION_W * 2 + (SECTION_W - tw) // 2, H - 28),
            label, fill=(80, 220, 80), font=font_label,   # green for BUY
        )

        # --- Top labels (tiny) ---
        for i_sec, sec_label in enumerate(["Market Scan", "AI Analysis", "Decision"]):
            bbox = draw.textbbox((0, 0), sec_label, font=font_status)
            tw = bbox[2] - bbox[0]
            draw.text(
                (SECTION_W * i_sec + (SECTION_W - tw) // 2, 6),
                sec_label, fill=GOLD_DIM, font=font_status,
            )

        # Animated progress dots under "Analyzing..." to keep all 6 frames unique
        dots = "." * (idx % 3 + 1)
        draw.text((SECTION_W + 10, H - 14), dots, fill=GOLD_DIM, font=font_status)

        # Convert to RGB for GIF
        rgb_frame = Image.new("RGB", (W, H), BG_COLOR)
        rgb_frame.paste(frame, mask=frame.split()[3])
        gif_frames.append(rgb_frame)

    out_path = ASSETS / "showcase_demo.gif"
    # Convert all frames to palette mode with the same palette
    palette_frames = [f.quantize(colors=256, method=Image.Quantize.MEDIANCUT) for f in gif_frames]
    palette_frames[0].save(
        out_path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=DURATION_MS,
        loop=0,
        disposal=2,  # restore to background each frame (prevents dedup)
    )
    print(f"Saved showcase GIF -> {out_path}  ({len(gif_frames)} frames)")


# ---------------------------------------------------------------------------
# 2. Static hero banner  (800 x 200)
# ---------------------------------------------------------------------------

def create_hero_banner() -> None:
    W, H = 800, 200

    banner = Image.new("RGBA", (W, H), BG_COLOR)
    draw = ImageDraw.Draw(banner)

    # Decorative gold border lines (Art Deco feel)
    draw.rectangle([(4, 4), (W - 5, H - 5)], outline=GOLD_DIM, width=2)
    draw.rectangle([(10, 10), (W - 11, H - 11)], outline=(*GOLD_DIM, 80), width=1)

    # Gold accent lines at top and bottom
    draw.line([(20, 20), (W - 20, 20)], fill=GOLD, width=1)
    draw.line([(20, H - 20), (W - 20, H - 20)], fill=GOLD, width=1)

    # Bull idle sprite (left side)
    idle = Image.open(AVATAR / "bull_idle.png").convert("RGBA")
    sprite_h = H - 40
    sprite_w = int(idle.width * sprite_h / idle.height)
    idle = idle.resize((sprite_w, sprite_h), Image.LANCZOS)
    banner.paste(idle, (30, 20), idle)

    # Fonts
    font_title = get_font(48)
    font_sub = get_font(22)
    font_tag = get_font(16)

    # Title: "Orallexa"
    text_x = 30 + sprite_w + 40
    draw.text((text_x, 30), "Orallexa", fill=GOLD, font=font_title)

    # Subtitle: "AI Trading Agent"
    draw.text((text_x, 90), "AI Trading Agent", fill=WHITE, font=font_sub)

    # Tagline
    draw.text((text_x, 125), "Bull vs Bear Debate", fill=GOLD_DIM, font=font_tag)

    # Small decorative diamonds
    for dy in range(0, 20, 6):
        draw.rectangle(
            [(text_x + dy * 4, 160), (text_x + dy * 4 + 3, 163)],
            fill=GOLD,
        )

    # Save as PNG (flatten to RGB)
    out_path = ASSETS / "hero_banner.png"
    rgb = Image.new("RGB", (W, H), BG_COLOR)
    rgb.paste(banner, mask=banner.split()[3])
    rgb.save(out_path)
    print(f"Saved hero banner -> {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    create_showcase_gif()
    create_hero_banner()
    print("Done.")
