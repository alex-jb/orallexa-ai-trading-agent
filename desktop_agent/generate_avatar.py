"""
desktop_agent/generate_avatar.py
──────────────────────────────────────────────────────────────────
Generates the Art Deco Wall Street Bull avatar.

Design concept:
  - OpenClaw-style cuteness: big round head, oversized expressive eyes
  - Wall Street Charging Bull: powerful golden bull, iconic silhouette
  - Great Gatsby Art Deco: gold palette, top hat, monocle, geometric patterns

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

# ── Art Deco Gold Palette ────────────────────────────────────────────────────
P = {
    # Body — warm antique gold
    "body":      (198, 150,  42),    # rich gold
    "hi":        (232, 195,  90),    # bright gold highlight
    "sh":        (148, 105,  15),    # deep bronze shadow
    "ol":        ( 22,  18,  10),    # near-black outline

    # Horns — polished gold
    "horn":      (225, 190,  70),    # bright gold
    "horn_sh":   (170, 135,  30),    # shadow gold

    # Facial features
    "ear_in":    (210, 165,  70),
    "snout":     (215, 170,  80),    # lighter gold muzzle
    "nostril":   ( 40,  28,  10),

    # Eye — big, expressive (OpenClaw style)
    "eye_w":     (250, 245, 235),    # warm ivory white
    "eye_iris":  ( 55,  75, 115),    # deep navy blue (distinguished)
    "eye_p":     ( 12,  10,   6),    # near-black pupil
    "eye_shine": (255, 255, 255),
    "eye_shine2": (255, 248, 220),   # warm secondary shine

    # Monocle
    "monocle":   (225, 190,  70),    # gold rim
    "monocle_ch": (190, 155,  45),   # chain gold

    # Bowtie — gold with dark accent
    "bow_main":  (225, 190,  70),
    "bow_dark":  (148, 105,  15),
    "bow_knot":  ( 22,  18,  10),

    # Top hat — classic black with gold band
    "hat_main":  ( 28,  22,  16),
    "hat_band":  (225, 190,  70),
    "hat_hi":    ( 50,  42,  32),
    "hat_band_detail": (198, 150, 42),

    # Hooves
    "hoof":      ( 38,  26,  10),

    "white":     (255, 255, 255),
    "blush":     (235, 170, 100, 50),  # subtle warm blush
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
    # OpenClaw-style proportions: huge head, tiny body
    BX,  BY  = 48, 92 + bob        # body centre
    BRX, BRY = 22, 15              # body radii (compact)

    HX,  HY  = 82, 60 + bob        # head centre
    HR       = 26                   # BIG head (cuter)

    # ── 1. Tail ──────────────────────────────────────────────────
    tx, ty = BX - BRX - 1, BY - 5
    # Curly tail with gold tip
    d.arc([tx - 12, ty - 8, tx + 4, ty + 12],
          start=25, end=280, fill=_a(P["ol"]), width=4)
    d.arc([tx - 10, ty - 6, tx + 2, ty + 10],
          start=25, end=280, fill=_a(P["body"]), width=3)
    # Gold tuft
    _ell(d, tx - 10, ty, 4, 3, P["hi"], P["ol"], 1)

    # ── 2. Back legs (short, stubby — cute) ──────────────────────
    for lx, lift in [(BX - 7, ba), (BX + 5, bb)]:
        ly = BY + BRY - 4 - int(lift)
        _rect(d, lx - 4, ly,      lx + 4, ly + 10, P["body"], P["ol"], 2)
        _rect(d, lx - 3, ly + 9,  lx + 3, ly + 17, P["sh"],   P["ol"], 2)
        _ell(d,  lx,     ly + 19, 5, 3, P["hoof"], P["ol"], 2)

    # ── 3. Body (compact barrel) ─────────────────────────────────
    _ell(d, BX, BY, BRX, BRY, P["body"], P["ol"], 3)
    # Geometric highlight (Art Deco angular)
    _poly(d, [(BX - 14, BY - 8), (BX - 6, BY - 13),
              (BX + 2, BY - 7), (BX - 8, BY - 2)],
          P["hi"])
    # Belly shadow
    _ell(d, BX + 2, BY + 6, BRX - 10, BRY - 7, P["sh"])

    # ── 4. Gold Bowtie (Gatsby) ──────────────────────────────────
    btx = HX - 16
    bty = HY + 18 + bob
    # Left wing (geometric, Art Deco)
    _poly(d, [(btx - 1, bty), (btx - 9, bty - 5),
              (btx - 10, bty), (btx - 9, bty + 5)],
          P["bow_main"], P["ol"], 1)
    # Right wing
    _poly(d, [(btx + 1, bty), (btx + 9, bty - 5),
              (btx + 10, bty), (btx + 9, bty + 5)],
          P["bow_main"], P["ol"], 1)
    # Centre diamond (Art Deco motif)
    _poly(d, [(btx, bty - 3), (btx + 3, bty),
              (btx, bty + 3), (btx - 3, bty)],
          P["bow_knot"], P["ol"], 1)
    # Gold dot in centre
    _ell(d, btx, bty, 1, 1, P["hi"])

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
    # Forehead highlight (rounded, warm)
    _ell(d, HX - 8, HY - 14, HR // 3, HR // 4, P["hi"])

    # ── 8. Top Hat (Gatsby gentleman) ────────────────────────────
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

    # Gold band with Art Deco pattern
    _rect(d, hat_cx - 14, hat_by - 1, hat_cx + 12, hat_by + 3,
          P["hat_band"], P["ol"], 1)

    # Art Deco diamonds on hat band
    for offset in [-8, -2, 4]:
        x = hat_cx + offset
        y = hat_by + 1
        _poly(d, [(x, y - 2), (x + 2, y), (x, y + 2), (x - 2, y)],
              P["hat_band_detail"])

    # Hat highlight
    _poly(d, [(hat_cx - 10, hat_by - 18), (hat_cx - 6, hat_by - 18),
              (hat_cx - 6, hat_by - 4), (hat_cx - 10, hat_by - 4)],
          P["hat_hi"])

    # ── 9. Horn (Art Deco geometric, visible behind hat) ─────────
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

    # ── 11. Cheek blush (warm, subtle) ────────────────────────────
    _ell(d, HX + 12, HY + 8, 6, 4, P["blush"])

    # ── 12. Eye (BIG, expressive — OpenClaw-inspired) ────────────
    EX, EY = HX + 8, HY - 4
    # Big white
    _ell(d, EX, EY, 10, 10, P["eye_w"], P["ol"], 2)
    # Large iris
    _ell(d, EX + 2, EY + 1, 7, 7, P["eye_iris"])
    # Pupil
    _ell(d, EX + 2, EY + 1, 4, 4, P["eye_p"])
    # Big main shine (top-left)
    _ell(d, EX - 2, EY - 3, 3, 3, P["eye_shine"])
    # Smaller warm shine (bottom-right)
    _ell(d, EX + 4, EY + 3, 2, 2, P["eye_shine2"])

    # ── 13. Monocle (gold rim around right eye) ──────────────────
    _ell(d, EX, EY, 13, 13, ol=P["monocle"], lw=2)
    # Chain hanging down
    chain_pts = [
        (EX - 11, EY + 7),
        (EX - 14, EY + 16),
        (EX - 15, EY + 22),
    ]
    for i in range(len(chain_pts) - 1):
        d.line([chain_pts[i], chain_pts[i + 1]],
               fill=_a(P["monocle_ch"]), width=1)
    for pt in chain_pts[1:]:
        _ell(d, pt[0], pt[1], 1, 1, P["monocle_ch"])

    # ── 14. Eyebrow (confident, slightly raised) ─────────────────
    d.line([(EX - 8, EY - 12), (EX + 7, EY - 11)],
           fill=_a(P["ol"]), width=3)

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
    sz = 6
    # Outer diamond
    _poly(d, [(cx, cy - sz), (cx + sz, cy),
              (cx, cy + sz), (cx - sz, cy)],
          (*color, 180))
    # Inner diamond (brighter)
    _poly(d, [(cx, cy - 3), (cx + 3, cy),
              (cx, cy + 3), (cx - 3, cy)],
          (*color[:3], 255))
    return out


# ── State configs ────────────────────────────────────────────────────────────
STATE_CONFIGS = {
    "idle":      {"tint": None,           "glow": None,            "dot": None},
    "listening": {"tint": None,           "glow": (100, 170, 220), "dot": (100, 170, 220)},
    "thinking":  {"tint": (80, 100, 160), "glow": (80, 100, 160),  "dot": (80, 100, 160)},
    "confident": {"tint": (40, 160, 80),  "glow": (40, 160, 80),   "dot": (40, 160, 80)},
    "warning":   {"tint": (200, 60, 40),  "glow": (200, 60, 40),   "dot": (200, 60, 40)},
    "wait":      {"tint": (180, 150, 50), "glow": (180, 150, 50),  "dot": (180, 150, 50)},
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
