"""
desktop_agent/generate_avatar.py
──────────────────────────────────────────────────────────────────
Generates the cartoon Wall Street Bull avatar.
Chibi-style: big round head, tiny body, red Wall Street tie.

Run once to generate all assets:
    python desktop_agent/generate_avatar.py

Output:
    assets/avatar/bull_r_00.png … bull_r_05.png   (walk right, 6 frames)
    assets/avatar/bull_l_00.png … bull_l_05.png   (walk left, mirrored)
    assets/avatar/bull_idle.png                    (idle pose)
    assets/avatar/bull_walk.gif                    (preview GIF)
"""
from __future__ import annotations
from pathlib import Path
from PIL import Image, ImageDraw
import math

SIZE = 128        # canvas px per frame (app renders at this size)
N_FRAMES = 6      # walk cycle
OUT_DIR = Path(__file__).parent.parent / "assets" / "avatar"

# ── Colour palette ────────────────────────────────────────────────────────────
P = {
    "body":      (204, 140,  68),
    "hi":        (232, 180, 115),
    "sh":        (152,  92,  32),
    "ol":        ( 62,  36,   8),   # dark brown outline
    "horn":      (244, 222, 156),
    "horn_sh":   (188, 152,  72),
    "ear_in":    (225, 165, 120),
    "snout":     (228, 168, 128),
    "nostril":   ( 88,  50,  20),
    "eye_w":     (255, 255, 255),
    "eye_iris":  (110, 175, 215),   # blue-grey iris
    "eye_p":     ( 18,  12,   6),
    "tie_r":     (210,  28,  40),   # Wall Street red
    "tie_k":     (148,  14,  22),   # tie knot / tip
    "hoof":      ( 48,  28,  10),
    "white":     (255, 255, 255),
    "blush":     (240, 150, 130, 90),  # cheek blush (semi-transparent)
}


def _a(c, alpha: int = 255):
    if len(c) == 4:
        return c
    return (*c, alpha)


def _ell(d, cx, cy, rx, ry, fill=None, ol=None, lw=2):
    kw: dict = {}
    if fill: kw["fill"]    = _a(fill)
    if ol:   kw["outline"] = _a(ol); kw["width"] = lw
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], **kw)


def _poly(d, pts, fill=None, ol=None, lw=2):
    kw: dict = {}
    if fill: kw["fill"]    = _a(fill)
    if ol:   kw["outline"] = _a(ol); kw["width"] = lw
    d.polygon(pts, **kw)


def _rect(d, x0, y0, x1, y1, fill=None, ol=None, lw=2):
    kw: dict = {}
    if fill: kw["fill"]    = _a(fill)
    if ol:   kw["outline"] = _a(ol); kw["width"] = lw
    d.rectangle([x0, y0, x1, y1], **kw)


# ── Walk cycle ────────────────────────────────────────────────────────────────

def _walk(frame: int) -> tuple[float, float, float, float]:
    """Return (frontA, frontB, backA, backB) upward lifts in pixels."""
    t = (frame / N_FRAMES) * 2 * math.pi
    amp = 7.0
    fa = amp * max(0.0, math.sin(t))
    fb = amp * max(0.0, math.sin(t + math.pi))
    ba = amp * max(0.0, math.sin(t + math.pi))   # diagonal pair
    bb = amp * max(0.0, math.sin(t))
    return fa, fb, ba, bb


# ── Main drawing function ─────────────────────────────────────────────────────

def draw_bull(frame: int, idle: bool = False) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    fa, fb, ba, bb = (0, 0, 0, 0) if idle else _walk(frame)

    # Body bob (subtle bounce)
    t   = (frame / N_FRAMES) * 2 * math.pi if not idle else 0
    bob = 0 if idle else -round(1.5 * abs(math.sin(t)))

    # ── Anchor points  (character faces RIGHT) ───────────────────
    # Chibi: head ≈ 42 px Ø, body ≈ 50×32
    BX,  BY  = 54, 90 + bob        # body centre
    BRX, BRY = 26, 17              # body radii

    HX,  HY  = 86, 62 + bob        # head centre
    HR       = 22                  # head radius

    # ── 1. Tail ──────────────────────────────────────────────────
    tx, ty = BX - BRX + 1, BY - 6
    d.arc([tx - 13, ty - 9, tx + 3, ty + 15],
          start=25, end=265, fill=_a(P["ol"]), width=4)
    d.arc([tx - 11, ty - 7, tx + 1, ty + 13],
          start=25, end=265, fill=_a(P["body"]), width=2)
    _ell(d, tx - 11, ty - 1, 5, 4, P["sh"], P["ol"], 1)   # tail tuft

    # ── 2. Back legs ─────────────────────────────────────────────
    for lx, lift in [(BX - 8, ba), (BX + 6, bb)]:
        ly = BY + BRY - 5 - int(lift)
        _rect(d, lx - 5, ly,      lx + 5, ly + 13, P["sh"],   P["ol"], 2)
        _rect(d, lx - 4, ly + 12, lx + 4, ly + 22, P["body"], P["ol"], 2)
        _ell(d,  lx,     ly + 24, 6, 4, P["hoof"], P["ol"], 2)

    # ── 3. Body ───────────────────────────────────────────────────
    _ell(d, BX, BY, BRX, BRY, P["body"], P["ol"], 3)
    _ell(d, BX + 4, BY + 7,  BRX - 9, BRY - 6, P["sh"])         # belly shadow
    _ell(d, BX - 9, BY - 9,  BRX - 12, BRY - 8, P["hi"])        # back highlight

    # ── 4. Tie ───────────────────────────────────────────────────
    tx2 = HX - 18
    ty2 = HY + 12 + bob
    # Knot
    _poly(d, [(tx2 - 5, ty2 - 3), (tx2 + 5, ty2 - 3),
              (tx2 + 4, ty2 + 5), (tx2 - 4, ty2 + 5)],
          P["tie_k"], P["ol"], 1)
    # Tie body
    _poly(d, [(tx2 - 4, ty2 + 5),  (tx2 + 4, ty2 + 5),
              (tx2 + 3, ty2 + 17), (tx2 - 3, ty2 + 17)],
          P["tie_r"], P["ol"], 1)
    # Tip
    _poly(d, [(tx2 - 3, ty2 + 17), (tx2 + 3, ty2 + 17), (tx2, ty2 + 22)],
          P["tie_k"])

    # ── 5. Front legs ─────────────────────────────────────────────
    for lx, lift in [(HX - 10, fa), (HX + 4, fb)]:
        ly = HY + HR - 3 - int(lift)
        _rect(d, lx - 5, ly,      lx + 5, ly + 13, P["body"], P["ol"], 2)
        _rect(d, lx - 4, ly + 12, lx + 4, ly + 22, P["sh"],   P["ol"], 2)
        _ell(d,  lx,     ly + 24, 6, 4, P["hoof"], P["ol"], 2)

    # ── 6. Ear ────────────────────────────────────────────────────
    _ell(d, HX - 19, HY - 11, 9, 8,  P["body"],  P["ol"], 2)
    _ell(d, HX - 19, HY - 11, 5, 4,  P["ear_in"])

    # ── 7. Head ───────────────────────────────────────────────────
    _ell(d, HX, HY, HR, HR, P["body"], P["ol"], 3)
    _ell(d, HX - 10, HY - 12, HR // 3 + 2, HR // 4 + 1, P["hi"])   # highlight

    # ── 8. Horn ───────────────────────────────────────────────────
    hbx, hby = HX - 2, HY - HR + 2
    _poly(d, [
        (hbx - 8,  hby + 2),
        (hbx + 6,  hby),
        (hbx + 9,  hby - 20),
        (hbx + 1,  hby - 23),
        (hbx - 10, hby - 12),
    ], P["horn"], P["ol"], 2)
    # Horn shadow (right face)
    _poly(d, [
        (hbx + 6,  hby),
        (hbx + 9,  hby - 20),
        (hbx + 3,  hby - 18),
        (hbx + 2,  hby - 2),
    ], P["horn_sh"])

    # ── 9. Muzzle / Snout ─────────────────────────────────────────
    SX, SY = HX + HR - 4, HY + 9
    _ell(d, SX, SY, 13, 9, P["snout"], P["ol"], 2)
    # Nostrils
    _ell(d, SX - 5, SY + 2, 3, 3, P["nostril"])
    _ell(d, SX + 5, SY + 2, 3, 3, P["nostril"])
    # Smile
    d.arc([SX - 7, SY + 2, SX + 7, SY + 9],
          start=15, end=165, fill=_a(P["nostril"]), width=2)

    # ── 10. Cheek blush ───────────────────────────────────────────
    _ell(d, HX + 10, HY + 8, 7, 5, P["blush"])

    # ── 11. Eye ───────────────────────────────────────────────────
    EX, EY = HX + 7, HY - 5
    _ell(d, EX, EY, 8, 8,  P["eye_w"],    P["ol"], 2)  # white
    _ell(d, EX + 2, EY + 1, 5, 5, P["eye_iris"])       # iris
    _ell(d, EX + 2, EY + 1, 3, 3, P["eye_p"])          # pupil
    _ell(d, EX,     EY - 2, 2, 2, P["white"])           # shine top
    _ell(d, EX + 3, EY + 2, 1, 1, P["white"])           # shine bottom

    # ── 12. Eyebrow (determined look) ─────────────────────────────
    d.line([(EX - 6, EY - 10), (EX + 5, EY - 8)],
           fill=_a(P["ol"]), width=3)

    return img


# ── GIF helper ────────────────────────────────────────────────────────────────

def _frames_to_gif(frames: list[Image.Image], path: Path, duration: int = 110):
    """Save RGBA frames as animated GIF (white background)."""
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
    """Apply a translucent colour tint to an RGBA image."""
    overlay = Image.new("RGBA", img.size, (*color, alpha))
    out = img.copy()
    out = Image.alpha_composite(out, overlay)
    # Restore original alpha channel so background stays transparent
    out.putalpha(img.split()[3])
    return out


def _add_glow(img: Image.Image, color: tuple, radius: int = 6) -> Image.Image:
    """Add a subtle glow around the non-transparent pixels."""
    from PIL import ImageFilter
    alpha = img.split()[3]
    glow_mask = alpha.filter(ImageFilter.GaussianBlur(radius))
    glow = Image.new("RGBA", img.size, (*color, 0))
    glow.putalpha(glow_mask)
    out = Image.alpha_composite(glow, img)
    return out


def _draw_ear_indicator(img: Image.Image, color: tuple) -> Image.Image:
    """Draw a small status dot near the ear (top-left area of sprite)."""
    out = img.copy()
    d = ImageDraw.Draw(out)
    # Small glowing dot near the ear area
    _ell(d, 65, 30, 5, 5, (*color, 200))
    _ell(d, 65, 30, 3, 3, (*color[:3], 255))
    return out


STATE_CONFIGS = {
    "idle":      {"tint": None,           "glow": None,            "dot": None},
    "listening": {"tint": None,           "glow": (100, 180, 255), "dot": (100, 180, 255)},
    "thinking":  {"tint": (80, 120, 200), "glow": (80, 120, 200),  "dot": (80, 120, 200)},
    "confident": {"tint": (30, 180, 80),  "glow": (30, 180, 80),   "dot": (30, 180, 80)},
    "warning":   {"tint": (220, 60, 40),  "glow": (220, 60, 40),   "dot": (220, 60, 40)},
    "wait":      {"tint": (180, 140, 40), "glow": (180, 140, 40),  "dot": (180, 140, 40)},
}


def generate_state_sprite(state: str, base_img: Image.Image) -> Image.Image:
    """Generate a state-specific sprite from the base idle image."""
    cfg = STATE_CONFIGS.get(state, STATE_CONFIGS["idle"])
    img = base_img.copy()

    if cfg["tint"]:
        img = _tint(img, cfg["tint"], alpha=35)
    if cfg["glow"]:
        img = _add_glow(img, cfg["glow"], radius=4)
    if cfg["dot"]:
        img = _draw_ear_indicator(img, cfg["dot"])

    return img


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    right_frames = [draw_bull(i) for i in range(N_FRAMES)]
    left_frames  = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in right_frames]
    idle_frame   = draw_bull(0, idle=True)

    # Save PNG frames (used by the desktop app -- full RGBA)
    for i, f in enumerate(right_frames):
        f.save(OUT_DIR / f"bull_r_{i:02d}.png")
    for i, f in enumerate(left_frames):
        f.save(OUT_DIR / f"bull_l_{i:02d}.png")
    idle_frame.save(OUT_DIR / "bull_idle.png")

    # Save preview GIF (right-walking, white bg)
    _frames_to_gif(right_frames, OUT_DIR / "bull_walk.gif")

    # Generate state sprites
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
