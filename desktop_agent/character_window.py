"""
desktop_agent/character_window.py
──────────────────────────────────────────────────────────────────
Transparent always-on-top window with animated bull character and
state-driven visual feedback.

States:
    idle       — neutral, walking or paused
    listening  — mic active, blue glow
    thinking   — AI processing, blue pulse
    confident  — strong signal, green glow
    warning    — risk alert, red glow
    wait       — no action, amber glow

Usage (standalone test):
    python desktop_agent/character_window.py
"""
from __future__ import annotations

import random
import time
import tkinter as tk
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont, ImageTk

from desktop_agent.i18n import t, get_lang
from desktop_agent.fonts import load_fonts, FONT_BODY

load_fonts()

# ── Constants ─────────────────────────────────────────────────────────────────
ASSETS       = Path(__file__).parent.parent / "assets" / "avatar"
TRANS        = "#010101"
CHAR_W       = 128
CHAR_H       = 128
WALK_SPEED   = 2
FPS_MOVE     = 40
FPS_SPRITE   = 8
N_FRAMES     = 6
PAUSE_MIN    = 3.0
PAUSE_MAX    = 9.0
TASKBAR_H    = 48

# ── State definitions ─────────────────────────────────────────────────────────

StateName = Literal["idle", "listening", "thinking", "confident", "warning", "wait"]

def _state_bubbles(lang: str | None = None) -> dict[str, list[str]]:
    """Return state bubble texts in the current language."""
    return {
        "idle":      [],
        "listening": [t("listening", lang), t("go_ahead", lang), t("im_here", lang)],
        "thinking":  [t("analysing", lang), t("let_me_check", lang), t("one_sec", lang),
                      t("checking_charts", lang), t("thinking_bubble", lang)],
        "confident": [t("strong_signal", lang), t("looking_good", lang), t("setup_confirmed", lang)],
        "warning":   [t("careful_here", lang), t("risk_is_high", lang), t("watch_out", lang)],
        "wait":      [t("not_yet", lang), t("stand_aside", lang), t("no_setup", lang)],
    }

STATE_COLORS: dict[str, str] = {
    "idle":      "#A89F8B",   # champagne — Art Deco neutral
    "listening": "#7BA7CC",   # steel blue — 1920s art poster
    "thinking":  "#8B7EC8",   # muted lavender — Gatsby violet
    "confident": "#D4AF37",   # Art Deco gold — the money color
    "warning":   "#C44536",   # vintage crimson
    "wait":      "#B8860B",   # dark goldenrod
}


# ── Sprite loader ─────────────────────────────────────────────────────────────

def _load_frames(prefix: str) -> list[ImageTk.PhotoImage]:
    out = []
    for i in range(N_FRAMES):
        path = ASSETS / f"{prefix}_{i:02d}.png"
        img  = Image.open(path).convert("RGBA")
        out.append(_rgba_to_photo(img))
    return out


def _rgba_to_photo(img: Image.Image) -> ImageTk.PhotoImage:
    img = img.convert("RGBA")
    bg = Image.new("RGB", img.size, (1, 1, 1))
    bg.paste(img.convert("RGB"), mask=img.split()[3])
    return ImageTk.PhotoImage(bg)


def _load_state_sprite(state: str) -> ImageTk.PhotoImage | None:
    path = ASSETS / f"bull_state_{state}.png"
    if path.exists():
        return _rgba_to_photo(Image.open(path).convert("RGBA"))
    return None


# ── Speech bubble ─────────────────────────────────────────────────────────────

def _make_bubble(text: str, accent: str = "#94a3b8",
                 max_width: int = 220) -> ImageTk.PhotoImage:
    """Render a styled speech bubble with accent-colored border.

    Phase 2: min font 11pt (was 13), max width clamp, multiline support.
    Phase 3: bubble never exceeds max_width.
    """
    pad = 10
    radius = 14
    font_size = 11   # min 8pt for accessibility; 11pt for bubble readability

    tmp = Image.new("RGBA", (1, 1))
    td  = ImageDraw.Draw(tmp)
    _font_path = Path(__file__).parent.parent / "assets" / "fonts" / "Lato-Regular.ttf"
    try:
        font = ImageFont.truetype(str(_font_path), font_size) if _font_path.exists() else ImageFont.truetype("segoeui.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

    # Wrap text if wider than max_width
    lines = text.split("\n")
    wrapped: list[str] = []
    for line in lines:
        words = line.split()
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            bbox = td.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_width - pad * 2 and current:
                wrapped.append(current)
                current = word
            else:
                current = test
        if current:
            wrapped.append(current)
    display = "\n".join(wrapped) if wrapped else text

    bbox = td.multiline_textbbox((0, 0), display, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    bw = min(max(tw + pad * 2, 60), max_width)
    bh = th + pad * 2 + 10

    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    ac = accent.lstrip("#")
    ar, ag, ab = int(ac[:2], 16), int(ac[2:4], 16), int(ac[4:6], 16)

    body_h = bh - 10
    d.rounded_rectangle([0, 0, bw - 1, body_h], radius=radius,
                        fill=(26, 26, 46, 235),
                        outline=(ar, ag, ab, 200), width=2)
    cx = bw // 2
    d.polygon([(cx - 8, body_h - 1), (cx + 8, body_h - 1), (cx, bh - 1)],
              fill=(26, 26, 46, 235))

    d.multiline_text((pad, pad), display, fill=(226, 232, 240, 255), font=font)

    return _rgba_to_photo(img)


# ── Main character class ──────────────────────────────────────────────────────

class BullCharacter:
    """
    Walking bull character with state-driven visual feedback.

    States: idle, listening, thinking, confident, warning, wait
    """

    def __init__(self, on_click=None) -> None:
        self._on_click   = on_click
        self._direction  = 1
        self._sprite_idx = 0
        self._paused     = True
        self._pause_until = time.time() + 1.0
        self._state: StateName = "idle"

        # ── Main window (must exist before loading sprites) ───────
        self._win = tk.Tk()

        # Walk sprites
        self._frames_r = _load_frames("bull_r")
        self._frames_l = _load_frames("bull_l")
        self._idle     = _rgba_to_photo(
            Image.open(ASSETS / "bull_idle.png").convert("RGBA"))

        # State sprites (loaded lazily, cached)
        self._state_sprites: dict[str, ImageTk.PhotoImage] = {}

        # Bubble image ref
        self._bubble_photo: ImageTk.PhotoImage | None = None
        self._bubble_visible = False
        self._win.overrideredirect(True)
        self._win.wm_attributes("-topmost", True)
        self._win.wm_attributes("-transparentcolor", TRANS)
        self._win.configure(bg=TRANS)
        self._win.resizable(False, False)

        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        self._sw = sw
        self._sh = sh
        self._x  = sw // 4
        self._y  = sh - CHAR_H - TASKBAR_H

        self._win.geometry(f"{CHAR_W}x{CHAR_H}+{self._x}+{self._y}")

        self._canvas = tk.Canvas(self._win, width=CHAR_W, height=CHAR_H,
                                 bg=TRANS, highlightthickness=0)
        self._canvas.pack()
        self._img_item = self._canvas.create_image(0, 0, anchor="nw",
                                                   image=self._idle)
        self._canvas.bind("<Button-1>", self._handle_click)

        # ── Bubble window ─────────────────────────────────────────
        self._bwin = tk.Toplevel(self._win)
        self._bwin.overrideredirect(True)
        self._bwin.wm_attributes("-topmost", True)
        self._bwin.wm_attributes("-transparentcolor", TRANS)
        self._bwin.configure(bg=TRANS)
        self._bwin.withdraw()

        self._bcanvas = tk.Canvas(self._bwin, bg=TRANS, highlightthickness=0)
        self._bcanvas.pack()
        self._bimg_item: int | None = None

        # ── Start loops ───────────────────────────────────────────
        self._pick_target()
        self._move_loop()
        self._sprite_loop()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> StateName:
        return self._state

    def set_state(self, state: StateName, bubble_text: str = "") -> None:
        """
        Transition to a new state with optional custom bubble text.

        If no bubble_text is provided, a random phrase for the state is shown.
        If the state is 'idle', the bubble is hidden.
        """
        self._state = state

        if state == "idle":
            self._hide_bubble()
            return

        bubbles = _state_bubbles(get_lang())
        text = bubble_text or (
            random.choice(bubbles[state])
            if bubbles.get(state)
            else ""
        )
        if text:
            accent = STATE_COLORS.get(state, STATE_COLORS["idle"])
            self._show_bubble(text, accent)

    def set_state_from_decision(self, decision: str, risk: str) -> None:
        """
        Set character state based on a DecisionOutput's decision + risk.

        BUY + LOW/MEDIUM risk  -> confident
        BUY + HIGH risk        -> warning
        SELL                   -> warning
        WAIT                   -> wait
        """
        lang = get_lang()
        if decision == "BUY":
            if risk == "HIGH":
                self.set_state("warning", t("careful_high_risk", lang))
            else:
                self.set_state("confident", t("signal_looks_good", lang))
        elif decision == "SELL":
            self.set_state("warning", t("sell_watch_risk", lang))
        else:
            self.set_state("wait", t("no_clear_setup", lang))

    def flash_state(self, state: StateName, text: str = "",
                    duration_ms: int = 3000) -> None:
        """Show a state briefly, then return to idle."""
        self.set_state(state, text)
        self._win.after(duration_ms, lambda: self.set_state("idle"))

    # Backward-compatible aliases
    def set_thinking(self, active: bool, custom_text: str = "") -> None:
        if active:
            self.set_state("thinking", custom_text)
        else:
            self.set_state("idle")

    def show_done(self) -> None:
        self.flash_state("confident", t("ready", get_lang()), 2500)

    def run(self) -> None:
        self._win.mainloop()

    def destroy(self) -> None:
        self._win.destroy()

    # ── Walk logic ────────────────────────────────────────────────────────────

    def _pick_target(self) -> None:
        margin = CHAR_W + 20
        lo = margin
        hi = max(lo + 10, self._sw - CHAR_W - margin)
        self._target_x  = random.randint(lo, hi)
        self._direction = 1 if self._target_x > self._x else -1

    def _move_loop(self) -> None:
        now = time.time()

        if self._paused:
            if now >= self._pause_until:
                self._paused = False
                self._pick_target()
        else:
            diff = self._target_x - self._x
            if abs(diff) <= WALK_SPEED + 1:
                self._x = self._target_x
                self._paused     = True
                self._pause_until = now + random.uniform(PAUSE_MIN, PAUSE_MAX)
            else:
                self._direction = 1 if diff > 0 else -1
                ease = min(1.0, abs(diff) / 60.0)
                step = max(1, round(WALK_SPEED * ease))
                self._x += self._direction * step
                self._x = max(0, min(self._sw - CHAR_W, self._x))

            self._win.geometry(f"{CHAR_W}x{CHAR_H}+{self._x}+{self._y}")
            self._update_bubble_pos()

        self._win.after(1000 // FPS_MOVE, self._move_loop)

    def _sprite_loop(self) -> None:
        if self._state != "idle" and self._paused:
            # Show state sprite when paused and in a non-idle state
            photo = self._get_state_sprite(self._state)
        elif self._paused:
            photo = self._idle
        else:
            frames = self._frames_r if self._direction == 1 else self._frames_l
            self._sprite_idx = (self._sprite_idx + 1) % N_FRAMES
            photo = frames[self._sprite_idx]

        self._canvas.itemconfig(self._img_item, image=photo)
        self._win.after(1000 // FPS_SPRITE, self._sprite_loop)

    def _get_state_sprite(self, state: str) -> ImageTk.PhotoImage:
        """Load and cache state sprite. Falls back to idle."""
        if state not in self._state_sprites:
            sprite = _load_state_sprite(state)
            self._state_sprites[state] = sprite or self._idle
        return self._state_sprites[state]

    # ── Bubble ────────────────────────────────────────────────────────────────

    def _show_bubble(self, text: str, accent: str = "#94a3b8") -> None:
        photo = _make_bubble(text, accent=accent)
        self._bubble_photo = photo
        self._bubble_visible = True

        bw = photo.width()
        bh = photo.height()

        self._bcanvas.config(width=bw, height=bh)
        if self._bimg_item is not None:
            self._bcanvas.itemconfig(self._bimg_item, image=photo)
        else:
            self._bimg_item = self._bcanvas.create_image(0, 0, anchor="nw",
                                                         image=photo)
        self._update_bubble_pos()
        self._bwin.deiconify()

    def _hide_bubble(self) -> None:
        self._bubble_visible = False
        self._bwin.withdraw()

    def _update_bubble_pos(self) -> None:
        """Phase 3: Clamp bubble fully on-screen (no clipping)."""
        if not self._bubble_visible:
            return
        if self._bubble_photo is None:
            return
        bw = self._bubble_photo.width()
        bh = self._bubble_photo.height()
        bx = self._x + (CHAR_W - bw) // 2
        by = self._y - bh - 4
        # Clamp horizontal
        bx = max(4, min(self._sw - bw - 4, bx))
        # Clamp vertical (don't go above screen top)
        by = max(4, by)
        self._bwin.geometry(f"+{bx}+{by}")

    # ── Click ─────────────────────────────────────────────────────────────────

    def _handle_click(self, _event) -> None:
        if self._on_click:
            self._on_click(self._x + CHAR_W // 2, self._y)


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import itertools

    states = itertools.cycle(["listening", "thinking", "confident",
                              "warning", "wait", "idle"])

    def _clicked(x, y):
        s = next(states)
        print(f"state -> {s}")
        bull.set_state(s)

    bull = BullCharacter(on_click=_clicked)
    bull.run()
