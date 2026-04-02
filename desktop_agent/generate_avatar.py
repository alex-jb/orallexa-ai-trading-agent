"""
desktop_agent/generate_avatar.py
──────────────────────────────────────────────────────────────────
Generates the Art Deco Wall Street Bull avatar — v2 redesign.

Design concept:
  - Diamond-framed geometric bull matching the Orallexa SVG logo
  - OpenClaw-style cuteness: big round head, oversized expressive eyes
  - Wall Street Charging Bull: powerful golden bull, iconic silhouette
  - Great Gatsby Art Deco: gold palette, top hat, monocle, geometric patterns
  - New: stepped corner ornaments, diamond accents, gold gradient effects

Run once to generate all assets:
    python desktop_agent/generate_avatar.py

Output:
    assets/avatar/bull_r_00.png … bull_r_05.png   (walk right, 6 frames)
    assets/avatar/bull_l_00.png … bull_l_05.png   (walk left, mirrored)
    assets/avatar/bull_idle.png                    (idle pose)
    assets/avatar/bull_walk.gif                    (preview GIF)
    assets/avatar/bull_state_*.png                 (state sprites)
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw
import math

SIZE = 128        # canvas px per frame
N_FRAMES = 6      # walk cycle
OUT_DIR = Path(__file__).parent.parent / "assets" / "avatar"

# ── Art Deco Gold Palette v2 ────────────────────────────────────────────────
# Aligned with DESIGN.md tokens: gold #D4AF37, gold-bright #FFD700, gold-muted #C5A255
P = {
    # Body — warm antique gold (richer, matching logo gradients)
    "body":      (212, 175,  55),    # #D4AF37 — primary gold
    "hi":        (255, 215,   0),    # #FFD700 — gold-bright highlight
    "sh":        (148, 105,  15),    # deep bronze shadow
    "mid":       (197, 162,  85),    # #C5A255 — gold-muted
    "ol":        ( 10,  10,  15),    # near-black outline (#0A0A0F)

    # Horns — polished gold with brighter tips
    "horn":      (255, 215,   0),    # #FFD700 — bright gold
    "horn_sh":   (197, 162,  85),    # #C5A255 — shadow gold

    # Facial features
    "ear_in":    (225, 185,  75),
    "snout":     (230, 190,  90),    # lighter gold muzzle
    "nostril":   ( 10,  10,  15),

    # Eye — big, expressive (OpenClaw style) with richer contrast
    "eye_w":     (245, 230, 202),    # #F5E6CA champagne (matching text color)
    "eye_iris":  (  0, 107,  63),    # #006B3F emerald (matching bull/buy color)
    "eye_p":     ( 10,  10,  15),    # near-black pupil
    "eye_shine": (255, 255, 255),
    "eye_shine2": (255, 215,  0),    # gold secondary shine (brand accent)

    # Monocle — brighter gold
    "monocle":   (255, 215,   0),    # #FFD700 bright gold rim
    "monocle_ch": (212, 175,  55),   # chain gold

    # Bowtie — gold with dark accent
    "bow_main":  (255, 215,   0),
    "bow_dark":  (148, 105,  15),
    "bow_knot":  ( 10,  10,  15),

    # Top hat — dark with gold band (sharper contrast)
    "hat_main":  ( 16,  16,  24),    # near-black, matches bg-card
    "hat_band":  (255, 215,   0),    # #FFD700
    "hat_hi":    ( 38,  38,  50),
    "hat_band_detail": (212, 175, 55),  # #D4AF37

    # Hooves — dark
    "hoof":      ( 26,  26,  46),    # matches bg-card

    "white":     (255, 255, 255),
    "blush":     (255, 180, 100, 40),  # warm gold blush

    # Art Deco frame elements (new)
    "frame_gold":  (212, 175,  55, 100),  # semi-transparent gold
    "frame_bright": (255, 215,  0, 140),  # brighter frame accent
}


def _a(c: tuple, alpha: int = 255) -> tuple:
    if len(c) == 4:
        return c
    return (*c, alpha)


def _ell(d: ImageDraw.ImageDraw, cx: int, cy: int,
         rx: int, ry: int, fill: tuple | None = None,
         ol: tuple | None = None, lw: int = 2) -> None:
    kw: dict = {}
    if fill: kw["fill"]    = _a(fill)
    if ol:   kw["outline"] = _a(ol); kw["width"] = lw
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], **kw)


def _poly(d: ImageDraw.ImageDraw, pts: list[tuple],
          fill: tuple | None = None, ol: tuple | None = None,
          lw: int = 2) -> None:
    kw: dict = {}
    if fill: kw["fill"]    = _a(fill)
    if ol:   kw["outline"] = _a(ol); kw["width"] = lw
    d.polygon(pts, **kw)


def _rect(d: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int,
          fill: tuple | None = None, ol: tuple | None = None,
          lw: int = 2) -> None:
    kw: dict = {}
    if fill: kw["fill"]    = _a(fill)
    if ol:   kw["outline"] = _a(ol); kw["width"] = lw
    d.rectangle([x0, y0, x1, y1], **kw)


def _diamond(d: ImageDraw.ImageDraw, cx: int, cy: int, size: int,
             fill: tuple | None = None, ol: tuple | None = None,
             lw: int = 1) -> None:
    """Draw a diamond shape (Art Deco motif)."""
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    kw: dict = {}
    if fill: kw["fill"] = _a(fill)
    if ol:   kw["outline"] = _a(ol); kw["width"] = lw
    d.polygon(pts, **kw)


def _stepped_corner(d: ImageDraw.ImageDraw, x: int, y: int,
                    size: int, flip_h: bool = False, flip_v: bool = False,
                    color: tuple = (212, 175, 55, 80)) -> None:
    """Draw an L-shaped stepped corner ornament (Art Deco signature)."""
    dx = -1 if flip_h else 1
    dy = -1 if flip_v else 1
    s = size
    # Outer L
    d.line([(x, y), (x + dx * s, y)], fill=_a(color), width=1)
    d.line([(x, y), (x, y + dy * s)], fill=_a(color), width=1)
    # Inner step
    s2 = s // 2
    d.line([(x + dx * 3, y + dy * 3), (x + dx * s2, y + dy * 3)],
           fill=_a(color), width=1)
    d.line([(x + dx * 3, y + dy * 3), (x + dx * 3, y + dy * s2)],
           fill=_a(color), width=1)


# ── Walk cycle ────────────────────────────────────────────────────────────────

def _walk(frame: int) -> tuple[float, float, float, float]:
    """Return (frontA, frontB, backA, backB) upward lifts in pixels."""
    t = (frame / N_FRAMES) * 2 * math.pi
    amp = 5.0
    fa = amp * max(0.0, math.sin(t))
    fb = amp * max(0.0, math.sin(t + math.pi))
    ba = amp * max(0.0, math.sin(t + math.pi))
    bb = amp * max(0.0, math.sin(t))
    return fa, fb, ba, bb


# ── Main drawing function ─────────────────────────────────────────────────────

def draw_bull(frame: int, idle: bool = False) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    fa, fb, ba, bb = (0, 0, 0, 0) if idle else _walk(frame)

    # Body bob
    t_val = (frame / N_FRAMES) * 2 * math.pi if not idle else 0
    bob   = 0 if idle else -round(1.0 * abs(math.sin(t_val)))

    # ── Anchor points  (character faces RIGHT) ───────────────────
    BX,  BY  = 48, 92 + bob        # body centre
    BRX, BRY = 22, 15              # body radii (compact)

    HX,  HY  = 82, 60 + bob        # head centre
    HR       = 26                   # BIG head (cuter)

    # ── 0. Subtle diamond frame behind character (Art Deco logo motif) ──
    if idle:
        cx, cy = 64, 68
        _diamond(d, cx, cy, 52, ol=P["frame_gold"], lw=1)
        _diamond(d, cx, cy, 44, ol=(212, 175, 55, 50), lw=1)

    # ── 1. Tail ──────────────────────────────────────────────────
    tx, ty = BX - BRX - 1, BY - 5
    d.arc([tx - 12, ty - 8, tx + 4, ty + 12],
          start=25, end=280, fill=_a(P["ol"]), width=4)
    d.arc([tx - 10, ty - 6, tx + 2, ty + 10],
          start=25, end=280, fill=_a(P["body"]), width=3)
    # Gold tuft with bright tip
    _ell(d, tx - 10, ty, 4, 3, P["hi"], P["ol"], 1)

    # ── 2. Back legs (short, stubby — cute) ──────────────────────
    for lx, lift in [(BX - 7, ba), (BX + 5, bb)]:
        ly = BY + BRY - 4 - int(lift)
        _rect(d, lx - 4, ly,      lx + 4, ly + 10, P["body"], P["ol"], 2)
        _rect(d, lx - 3, ly + 9,  lx + 3, ly + 17, P["sh"],   P["ol"], 2)
        _ell(d,  lx,     ly + 19, 5, 3, P["hoof"], P["ol"], 2)

    # ── 3. Body (compact barrel) ─────────────────────────────────
    _ell(d, BX, BY, BRX, BRY, P["body"], P["ol"], 3)
    # Geometric highlight (Art Deco angular — brighter gold)
    _poly(d, [(BX - 14, BY - 8), (BX - 6, BY - 13),
              (BX + 2, BY - 7), (BX - 8, BY - 2)],
          P["hi"])
    # Belly shadow
    _ell(d, BX + 2, BY + 6, BRX - 10, BRY - 7, P["sh"])

    # ── 4. Gold Bowtie (Gatsby) — with diamond center ────────────
    btx = HX - 16
    bty = HY + 18 + bob
    # Left wing (geometric, Art Deco)
    _poly(d, [(btx - 1, bty), (btx - 10, bty - 6),
              (btx - 11, bty), (btx - 10, bty + 6)],
          P["bow_main"], P["ol"], 1)
    # Right wing
    _poly(d, [(btx + 1, bty), (btx + 10, bty - 6),
              (btx + 11, bty), (btx + 10, bty + 6)],
          P["bow_main"], P["ol"], 1)
    # Centre diamond (Art Deco motif — brighter)
    _diamond(d, btx, bty, 3, fill=P["ol"], ol=P["hi"], lw=1)

    # ── 5. Front legs (short, stubby) ────────────────────────────
    for lx, lift in [(HX - 10, fa), (HX + 2, fb)]:
        ly = HY + HR - 5 - int(lift)
        _rect(d, lx - 4, ly,      lx + 4, ly + 10, P["body"], P["ol"], 2)
        _rect(d, lx - 3, ly + 9,  lx + 3, ly + 17, P["sh"],   P["ol"], 2)
        _ell(d,  lx,     ly + 19, 5, 3, P["hoof"], P["ol"], 2)

    # ── 6. Ear ────────────────────────────────────────────────────
    _ell(d, HX - 22, HY - 8, 8, 7,  P["body"],  P["ol"], 2)
    _ell(d, HX - 22, HY - 8, 4, 3,  P["ear_in"])

    # ── 7. Head (BIG, round — OpenClaw cute proportions) ─────────
    _ell(d, HX, HY, HR, HR, P["body"], P["ol"], 3)
    # Forehead highlight (brighter gold)
    _ell(d, HX - 8, HY - 14, HR // 3, HR // 4, P["hi"])

    # ── 8. Top Hat (Gatsby gentleman — sharper) ──────────────────
    hat_cx = HX - 1
    hat_by = HY - HR + 3

    # Brim — wide, elegant
    _poly(d, [(hat_cx - 20, hat_by + 3), (hat_cx + 16, hat_by + 1),
              (hat_cx + 18, hat_by + 7), (hat_cx - 18, hat_by + 9)],
          P["hat_main"], P["ol"], 2)

    # Crown — tall, slightly tapered
    _poly(d, [(hat_cx - 14, hat_by + 3), (hat_cx + 12, hat_by + 1),
              (hat_cx + 10, hat_by - 20), (hat_cx - 12, hat_by - 20)],
          P["hat_main"], P["ol"], 2)

    # Top
    _rect(d, hat_cx - 12, hat_by - 22, hat_cx + 10, hat_by - 20,
          P["hat_main"], P["ol"], 2)

    # Gold band with Art Deco pattern (brighter gold)
    _rect(d, hat_cx - 14, hat_by - 1, hat_cx + 12, hat_by + 3,
          P["hat_band"], P["ol"], 1)

    # Art Deco diamonds on hat band (matching logo diamonds)
    for offset in [-8, -2, 4]:
        x = hat_cx + offset
        y = hat_by + 1
        _diamond(d, x, y, 2, fill=P["hat_band_detail"])

    # Hat highlight
    _poly(d, [(hat_cx - 10, hat_by - 18), (hat_cx - 6, hat_by - 18),
              (hat_cx - 6, hat_by - 4), (hat_cx - 10, hat_by - 4)],
          P["hat_hi"])

    # ── 9. Horn (Art Deco geometric, more angular) ───────────────
    hbx, hby = HX + 8, HY - HR + 6
    _poly(d, [
        (hbx, hby + 2),
        (hbx + 8, hby - 2),
        (hbx + 12, hby - 14),
        (hbx + 8, hby - 16),
        (hbx + 2, hby - 6),
    ], P["horn"], P["ol"], 2)
    # Shadow facet
    _poly(d, [
        (hbx + 8, hby - 2),
        (hbx + 12, hby - 14),
        (hbx + 9, hby - 12),
        (hbx + 6, hby - 1),
    ], P["horn_sh"])

    # ── 10. Muzzle / Snout ────────────────────────────────────────
    SX, SY = HX + HR - 5, HY + 10
    _ell(d, SX, SY, 12, 9, P["snout"], P["ol"], 2)
    # Nostrils
    _ell(d, SX - 4, SY + 2, 2, 2, P["nostril"])
    _ell(d, SX + 4, SY + 2, 2, 2, P["nostril"])
    # Happy smirk
    d.arc([SX - 6, SY + 2, SX + 6, SY + 8],
          start=10, end=170, fill=_a(P["nostril"]), width=2)

    # ── 11. Cheek blush (warm gold) ───────────────────────────────
    _ell(d, HX + 12, HY + 8, 6, 4, P["blush"])

    # ── 12. Eye (BIG, expressive — emerald iris matching brand) ──
    EX, EY = HX + 8, HY - 4
    # Big white (champagne tint)
    _ell(d, EX, EY, 10, 10, P["eye_w"], P["ol"], 2)
    # Large emerald iris
    _ell(d, EX + 2, EY + 1, 7, 7, P["eye_iris"])
    # Pupil
    _ell(d, EX + 2, EY + 1, 4, 4, P["eye_p"])
    # Big main shine (top-left)
    _ell(d, EX - 2, EY - 3, 3, 3, P["eye_shine"])
    # Gold secondary shine (brand accent)
    _ell(d, EX + 4, EY + 3, 2, 2, P["eye_shine2"])

    # ── 13. Monocle (bright gold rim) ────────────────────────────
    _ell(d, EX, EY, 13, 13, ol=P["monocle"], lw=2)
    # Chain hanging down with gold links
    chain_pts = [
        (EX - 11, EY + 7),
        (EX - 14, EY + 16),
        (EX - 15, EY + 22),
    ]
    for i in range(len(chain_pts) - 1):
        d.line([chain_pts[i], chain_pts[i + 1]],
               fill=_a(P["monocle_ch"]), width=1)
    # Diamond-shaped chain links (Art Deco detail)
    for pt in chain_pts[1:]:
        _diamond(d, pt[0], pt[1], 2, fill=P["monocle_ch"])

    # ── 14. Eyebrow (confident, slightly raised) ─────────────────
    d.line([(EX - 8, EY - 12), (EX + 7, EY - 11)],
           fill=_a(P["ol"]), width=3)

    # ── 15. Stepped corner ornaments (when idle, Art Deco frame) ─
    if idle:
        _stepped_corner(d, 4, 4, 16, color=(212, 175, 55, 60))
        _stepped_corner(d, SIZE - 5, 4, 16, flip_h=True, color=(212, 175, 55, 60))
        _stepped_corner(d, 4, SIZE - 5, 16, flip_v=True, color=(212, 175, 55, 60))
        _stepped_corner(d, SIZE - 5, SIZE - 5, 16, flip_h=True, flip_v=True,
                        color=(212, 175, 55, 60))

    return img


# ── GIF helper ────────────────────────────────────────────────────────────────

def _frames_to_gif(frames: list[Image.Image], path: Path,
                   duration: int = 110) -> None:
    out_frames = []
    for frame in frames:
        bg = Image.new("RGBA", frame.size, (255, 255, 255, 255))
        bg.alpha_composite(frame)
        out_frames.append(bg.convert("RGB").quantize(colors=128, dither=0))

    out_frames[0].save(
        str(path),
        save_all=True,
        append_images=out_frames[1:],
        duration=duration,
        loop=0,
        disposal=2,
    )


# ── State overlay tints ──────────────────────────────────────────────────────

def _tint(img: Image.Image, color: tuple, alpha: int = 50) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (*color, alpha))
    out = img.copy()
    out = Image.alpha_composite(out, overlay)
    out.putalpha(img.split()[3])
    return out


def _add_glow(img: Image.Image, color: tuple, radius: int = 6) -> Image.Image:
    from PIL import ImageFilter
    alpha = img.split()[3]
    glow_mask = alpha.filter(ImageFilter.GaussianBlur(radius))
    glow = Image.new("RGBA", img.size, (*color, 0))
    glow.putalpha(glow_mask)
    out = Image.alpha_composite(glow, img)
    return out


def _draw_hat_indicator(img: Image.Image, color: tuple) -> Image.Image:
    """Draw an Art Deco diamond status indicator near the hat."""
    out = img.copy()
    d = ImageDraw.Draw(out)
    cx, cy = 62, 24
    # Outer diamond (larger, matching logo aesthetic)
    _diamond(d, cx, cy, 7, fill=(*color[:3], 120), ol=(*color[:3], 200), lw=1)
    # Inner diamond (bright core)
    _diamond(d, cx, cy, 3, fill=(*color[:3], 255))
    return out


# ── State configs ────────────────────────────────────────────────────────────
# Colors updated to match DESIGN.md semantic palette
STATE_CONFIGS = {
    "idle":      {"tint": None,           "glow": None,            "dot": None},
    "listening": {"tint": None,           "glow": (100, 170, 220), "dot": (100, 170, 220)},
    "thinking":  {"tint": (80, 100, 160), "glow": (80, 100, 160),  "dot": (80, 100, 160)},
    "confident": {"tint": (  0, 107, 63), "glow": (  0, 107, 63),  "dot": (  0, 107, 63)},   # emerald
    "warning":   {"tint": (139,   0,  0), "glow": (139,   0,  0),  "dot": (139,   0,  0)},   # ruby
    "wait":      {"tint": (212, 175, 55), "glow": (212, 175, 55),  "dot": (212, 175, 55)},   # gold
}


def generate_state_sprite(state: str, base_img: Image.Image) -> Image.Image:
    cfg = STATE_CONFIGS.get(state, STATE_CONFIGS["idle"])
    img = base_img.copy()

    if cfg["tint"]:
        img = _tint(img, cfg["tint"], alpha=35)
    if cfg["glow"]:
        img = _add_glow(img, cfg["glow"], radius=4)
    if cfg["dot"]:
        img = _draw_hat_indicator(img, cfg["dot"])

    return img


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    right_frames = [draw_bull(i) for i in range(N_FRAMES)]
    left_frames  = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in right_frames]
    idle_frame   = draw_bull(0, idle=True)

    for i, f in enumerate(right_frames):
        f.save(OUT_DIR / f"bull_r_{i:02d}.png")
    for i, f in enumerate(left_frames):
        f.save(OUT_DIR / f"bull_l_{i:02d}.png")
    idle_frame.save(OUT_DIR / "bull_idle.png")

    _frames_to_gif(right_frames, OUT_DIR / "bull_walk.gif")

    for state in STATE_CONFIGS:
        state_img = generate_state_sprite(state, idle_frame)
        state_img.save(OUT_DIR / f"bull_state_{state}.png")

    total = N_FRAMES * 2 + 1 + len(STATE_CONFIGS)
    print(f"Generated {total} sprites  ->  {OUT_DIR}")
    print("Files:")
    for p in sorted(OUT_DIR.iterdir()):
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
