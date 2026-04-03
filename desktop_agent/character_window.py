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
CHAR_W       = 96
CHAR_H       = 108
WALK_SPEED   = 2
FPS_MOVE     = 40
FPS_SPRITE   = 8
N_FRAMES     = 6
PAUSE_MIN    = 3.0
PAUSE_MAX    = 9.0
TASKBAR_H    = 48

# ── Idle animation (Claude Buddy inspired) ───────────────────────────────────
# Indices map to walk frames; -1 = blink (use idle sprite briefly)
# Mostly resting (0), occasional fidget (1-2), rare blink (-1)
IDLE_SEQUENCE  = [0, 0, 0, 0, 0, 1, 0, 0, 0, -1, 0, 0, 2, 0, 0, 0, 0, 0, -1, 0]
IDLE_TICK_MS   = 500  # ms per idle frame

# ── Bubble animation ─────────────────────────────────────────────────────────
BUBBLE_SHOW_TICKS = 16   # ~8s at 500ms tick
BUBBLE_FADE_TICKS = 4    # last ~2s the bubble dims before hiding

# ── Pet interaction (hearts on click) ─────────────────────────────────────────
PET_HEARTS = ["♥", "♥ ♥", "♥  ♥  ♥", "♥   ♥", "·  ·"]
PET_BURST_MS = 2500

# ── Idle tips (random wisdom while idle) ──────────────────────────────────────
IDLE_TIPS_EN = [
    "Don't chase the market...", "Volume confirms trend", "Patience is alpha",
    "Risk/reward > win rate", "Cut losses, let winners run", "The trend is your friend",
    "Buy the fear, sell the greed", "No setup = no trade", "Position size matters",
    "Markets are never wrong", "Plan the trade, trade the plan",
]
IDLE_TIPS_ZH = [
    "别追涨杀跌...", "成交量确认趋势", "耐心就是超额收益",
    "风险收益比 > 胜率", "截断亏损，让利润奔跑", "趋势是你的朋友",
    "别人恐惧我贪婪", "没信号 = 不交易", "仓位管理很重要",
    "市场永远是对的", "计划你的交易，交易你的计划",
]
IDLE_TIP_INTERVAL = (30, 90)  # seconds between random tips

# ── Edge snapping ─────────────────────────────────────────────────────────────
SNAP_DISTANCE = 20   # pixels — snap to edge when within this distance
EDGE_MARGIN   = 4    # pixels — gap from screen edge when snapped

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
    "idle":      "#D4AF37",   # gold — neutral pixel bull
    "listening": "#64A0DC",   # blue — listening pixel bull
    "thinking":  "#9678C8",   # purple — thinking pixel bull
    "confident": "#DC3C3C",   # red — bullish/buy (中国红=涨)
    "warning":   "#32AA5A",   # green — bearish/sell (绿=跌)
    "wait":      "#D4AF37",   # gold — neutral
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

def _make_bubble(text: str, accent: str = "#D4AF37",
                 max_width: int = 220) -> ImageTk.PhotoImage:
    """Render an Art Deco speech bubble with sharp corners and diamond accent.

    Design: 0px radius (Art Deco), gold accent border, diamond arrow,
    stepped corner ornaments at top corners.
    """
    pad = 10
    font_size = 11

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
    bh = th + pad * 2 + 14  # extra space for diamond arrow

    img = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)

    ac = accent.lstrip("#")
    ar, ag, ab = int(ac[:2], 16), int(ac[2:4], 16), int(ac[4:6], 16)

    body_h = bh - 12
    body_color = (10, 10, 15, 240)      # #0A0A0F near-black (matching bg-deep)
    border_color = (ar, ag, ab, 180)

    # Sharp rectangle body (0px radius — Art Deco signature)
    d.rectangle([0, 0, bw - 1, body_h], fill=body_color, outline=border_color, width=2)

    # Gold accent line at top (brand gradient effect)
    d.line([(2, 2), (bw - 3, 2)], fill=(212, 175, 55, 200), width=1)

    # Stepped corner ornaments (tiny, Art Deco)
    for cx_corner, cy_corner in [(3, 3), (bw - 4, 3)]:
        d.line([(cx_corner, cy_corner), (cx_corner + (6 if cx_corner < bw // 2 else -6), cy_corner)],
               fill=(ar, ag, ab, 120), width=1)
        d.line([(cx_corner, cy_corner), (cx_corner, cy_corner + 6)],
               fill=(ar, ag, ab, 120), width=1)

    # Diamond arrow at bottom (instead of triangle)
    cx = bw // 2
    d.polygon([(cx - 6, body_h - 1), (cx, body_h + 10), (cx + 6, body_h - 1)],
              fill=body_color, outline=border_color, width=1)
    # Clean up the join
    d.line([(cx - 5, body_h), (cx + 5, body_h)], fill=body_color, width=2)

    # Text in champagne (#F5E6CA)
    d.multiline_text((pad, pad + 1), display, fill=(245, 230, 202, 255), font=font)

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

        # Idle animation state (Claude Buddy inspired)
        self._idle_seq_idx = 0
        self._idle_tick_count = 0

        # Bubble auto-hide timer
        self._bubble_ticks_left = 0
        self._bubble_fading = False

        # Pet interaction
        self._pet_active = False
        self._pet_tick = 0

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
        # Drag to move
        self._drag_data = {"x": 0, "y": 0, "dragging": False}
        self._canvas.bind("<ButtonPress-3>", self._drag_start)
        self._canvas.bind("<B3-Motion>", self._drag_motion)
        self._canvas.bind("<ButtonRelease-3>", self._drag_end)
        # Right-click context menu (Shift+Right or double-click)
        self._canvas.bind("<Double-Button-1>", self._show_context_menu)
        self._context_menu = tk.Menu(self._win, tearoff=0,
                                      bg="#1A1A2E", fg="#F5E6CA",
                                      activebackground="#D4AF37", activeforeground="#0A0A0F",
                                      font=("Segoe UI", 9))
        self._context_menu.add_command(label="Analyze NVDA", command=lambda: self._quick_action("NVDA"))
        self._context_menu.add_command(label="Analyze TSLA", command=lambda: self._quick_action("TSLA"))
        self._context_menu.add_command(label="Analyze QQQ", command=lambda: self._quick_action("QQQ"))
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Voice (K)", command=lambda: self._quick_action("voice"))
        self._context_menu.add_command(label="Screenshot", command=lambda: self._quick_action("screenshot"))
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Hide Bull", command=self._toggle_visibility)

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

        # ── Heart overlay (pet interaction) ───────────────────────
        self._heart_item: int | None = None

        # ── Mood memory (tracks recent analysis results) ──────────
        self._mood_history: list[dict] = []  # [{ticker, decision, confidence, ts}]
        self._mood_streak = 0  # positive = consecutive bulls, negative = bears

        # ── Quick action callback (set by main.py) ────────────────
        self._quick_action_cb = None

        # ── Start loops ───────────────────────────────────────────
        self._pick_target()
        self._move_loop()
        self._sprite_loop()
        self._idle_tick_loop()
        self._bubble_tick_loop()
        self._idle_tip_loop()

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
        margin = CHAR_W + EDGE_MARGIN
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
            # Idle animation: use IDLE_SEQUENCE for subtle fidget/blink
            frame_idx = IDLE_SEQUENCE[self._idle_seq_idx % len(IDLE_SEQUENCE)]
            if frame_idx == -1:
                # Blink: briefly show a walk frame then back to idle
                photo = self._frames_r[0]
            elif frame_idx > 0:
                # Fidget: show a walk frame
                frames = self._frames_r if self._direction == 1 else self._frames_l
                photo = frames[min(frame_idx, len(frames) - 1)]
            else:
                photo = self._idle
        else:
            frames = self._frames_r if self._direction == 1 else self._frames_l
            self._sprite_idx = (self._sprite_idx + 1) % N_FRAMES
            photo = frames[self._sprite_idx]

        self._canvas.itemconfig(self._img_item, image=photo)
        self._win.after(1000 // FPS_SPRITE, self._sprite_loop)

    def _idle_tick_loop(self) -> None:
        """Advance idle animation sequence at IDLE_TICK_MS interval."""
        if self._paused and self._state == "idle":
            self._idle_seq_idx = (self._idle_seq_idx + 1) % len(IDLE_SEQUENCE)
        self._win.after(IDLE_TICK_MS, self._idle_tick_loop)

    def _bubble_tick_loop(self) -> None:
        """Auto-hide bubble after BUBBLE_SHOW_TICKS. Fade in last BUBBLE_FADE_TICKS."""
        if self._bubble_visible and self._bubble_ticks_left > 0:
            self._bubble_ticks_left -= 1
            if self._bubble_ticks_left <= BUBBLE_FADE_TICKS and not self._bubble_fading:
                self._bubble_fading = True
                # Start fading: reduce bubble window opacity
                try:
                    self._bwin.wm_attributes("-alpha", 0.5)
                except tk.TclError:
                    pass
            if self._bubble_ticks_left <= 0:
                self._hide_bubble()
        self._win.after(IDLE_TICK_MS, self._bubble_tick_loop)

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
        self._bubble_ticks_left = BUBBLE_SHOW_TICKS
        self._bubble_fading = False

        bw = photo.width()
        bh = photo.height()

        self._bcanvas.config(width=bw, height=bh)
        if self._bimg_item is not None:
            self._bcanvas.itemconfig(self._bimg_item, image=photo)
        else:
            self._bimg_item = self._bcanvas.create_image(0, 0, anchor="nw",
                                                         image=photo)
        self._update_bubble_pos()
        try:
            self._bwin.wm_attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self._bwin.deiconify()

    def _hide_bubble(self) -> None:
        self._bubble_visible = False
        self._bubble_fading = False
        self._bubble_ticks_left = 0
        try:
            self._bwin.wm_attributes("-alpha", 1.0)
        except tk.TclError:
            pass
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

    # ── Drag to move ───────────────────────────────────────────────────────

    def _drag_start(self, event) -> None:
        self._drag_data["x"] = event.x_root - self._x
        self._drag_data["y"] = event.y_root - self._y
        self._drag_data["dragging"] = True
        self._paused = True
        self._pause_until = time.time() + 999

    def _drag_motion(self, event) -> None:
        if not self._drag_data["dragging"]:
            return
        self._x = event.x_root - self._drag_data["x"]
        self._y = event.y_root - self._drag_data["y"]
        self._x = max(0, min(self._sw - CHAR_W, self._x))
        self._y = max(0, min(self._sh - CHAR_H, self._y))
        self._win.geometry(f"{CHAR_W}x{CHAR_H}+{self._x}+{self._y}")
        self._update_bubble_pos()

    def _drag_end(self, _event) -> None:
        self._drag_data["dragging"] = False
        self._snap_to_edge()
        self._pause_until = time.time() + random.uniform(PAUSE_MIN, PAUSE_MAX)

    def _snap_to_edge(self) -> None:
        """Snap bull to nearest screen edge if within SNAP_DISTANCE."""
        snapped = False
        # Left edge
        if self._x < SNAP_DISTANCE:
            self._x = EDGE_MARGIN
            snapped = True
        # Right edge
        if self._x > self._sw - CHAR_W - SNAP_DISTANCE:
            self._x = self._sw - CHAR_W - EDGE_MARGIN
            snapped = True
        # Top edge
        if self._y < SNAP_DISTANCE:
            self._y = EDGE_MARGIN
            snapped = True
        # Bottom edge (above taskbar)
        if self._y > self._sh - CHAR_H - TASKBAR_H - SNAP_DISTANCE:
            self._y = self._sh - CHAR_H - TASKBAR_H
            snapped = True
        if snapped:
            self._win.geometry(f"{CHAR_W}x{CHAR_H}+{self._x}+{self._y}")
            self._update_bubble_pos()

    # ── Context menu ─────────────────────────────────────────────────────

    def _show_context_menu(self, event) -> None:
        try:
            self._context_menu.tk_popup(
                self._x + event.x, self._y + event.y - 120)
        finally:
            self._context_menu.grab_release()

    def _quick_action(self, action: str) -> None:
        if self._quick_action_cb:
            self._quick_action_cb(action)
        else:
            self.flash_state("thinking", f"Analyzing {action}..." if action not in ("voice", "screenshot") else action.title())

    def _toggle_visibility(self) -> None:
        self._win.withdraw()
        self._bwin.withdraw()
        # Re-show after 30 seconds
        self._win.after(30000, self._win.deiconify)

    def set_quick_action_callback(self, cb) -> None:
        """Set callback for context menu quick actions. cb(action: str)."""
        self._quick_action_cb = cb

    # ── Idle tips ────────────────────────────────────────────────────────

    def _idle_tip_loop(self) -> None:
        """Show random trading wisdom when idle for a while."""
        if self._state == "idle" and self._paused and not self._bubble_visible:
            lang = get_lang()
            tips = IDLE_TIPS_ZH if lang == "zh" else IDLE_TIPS_EN
            # Mood-aware tips
            if self._mood_streak >= 3:
                tip = random.choice(["On a roll! 🐂", "连胜中！保持冷静"] if lang == "zh" else ["On a roll! 🐂", "Stay disciplined on streaks"])
            elif self._mood_streak <= -3:
                tip = random.choice(["别气馁，回顾策略", "Tough streak. Review your plan."])
            else:
                tip = random.choice(tips)
            self._show_bubble(tip, accent="#C5A255")
        interval = random.randint(IDLE_TIP_INTERVAL[0], IDLE_TIP_INTERVAL[1]) * 1000
        self._win.after(interval, self._idle_tip_loop)

    # ── Mood memory ──────────────────────────────────────────────────────

    def record_analysis(self, ticker: str, decision: str, confidence: float) -> None:
        """Record an analysis result for mood tracking."""
        self._mood_history.append({
            "ticker": ticker, "decision": decision,
            "confidence": confidence, "ts": time.time(),
        })
        # Keep last 20
        if len(self._mood_history) > 20:
            self._mood_history = self._mood_history[-20:]
        # Update streak
        if decision == "BUY":
            self._mood_streak = max(1, self._mood_streak + 1)
        elif decision == "SELL":
            self._mood_streak = min(-1, self._mood_streak - 1)
        else:
            self._mood_streak = 0

    def get_mood_summary(self) -> str:
        """Get a mood summary string for display."""
        if not self._mood_history:
            return "No analyses yet"
        recent = self._mood_history[-5:]
        buys = sum(1 for r in recent if r["decision"] == "BUY")
        sells = sum(1 for r in recent if r["decision"] == "SELL")
        if buys > sells:
            return f"Bullish mood ({buys}/{len(recent)} buys)"
        elif sells > buys:
            return f"Bearish mood ({sells}/{len(recent)} sells)"
        return f"Mixed signals ({len(recent)} recent)"

    # ── Sound feedback ────────────────────────────────────────────────────

    @staticmethod
    def play_notification(kind: str = "complete") -> None:
        """Play a short notification sound. Non-blocking, best-effort.

        Kinds: complete (ding), alert (warning beep), error (low beep)
        Uses Windows system sounds via winsound, falls back to bell char.
        """
        import threading

        def _play():
            try:
                import winsound
                if kind == "complete":
                    winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
                elif kind == "alert":
                    winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
                elif kind == "error":
                    winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
                else:
                    winsound.MessageBeep()
            except Exception:
                # Fallback: terminal bell
                print("\a", end="", flush=True)

        threading.Thread(target=_play, daemon=True).start()

    # ── Click ─────────────────────────────────────────────────────────────

    def _handle_click(self, _event) -> None:
        # Pet interaction: show floating hearts
        if self._state == "idle" and not self._pet_active:
            self._start_pet_burst()
        if self._on_click:
            self._on_click(self._x + CHAR_W // 2, self._y)

    def _start_pet_burst(self) -> None:
        """Show floating hearts above the bull (Claude Buddy pet interaction)."""
        self._pet_active = True
        self._pet_tick = 0
        # Show a happy bubble
        self._show_bubble(random.choice(["Moo~ ♥", "嘿嘿~", "Bull happy!", "摸摸~"]),
                          accent="#DC3C3C")
        self._pet_hearts_loop()

    def _pet_hearts_loop(self) -> None:
        """Animate floating hearts above the character."""
        if not self._pet_active:
            return
        if self._pet_tick >= len(PET_HEARTS):
            self._pet_active = False
            if self._heart_item is not None:
                self._canvas.delete(self._heart_item)
                self._heart_item = None
            return

        heart_text = PET_HEARTS[self._pet_tick]
        if self._heart_item is not None:
            self._canvas.delete(self._heart_item)
        # Draw hearts above the bull, floating upward
        y_offset = 20 - self._pet_tick * 4
        self._heart_item = self._canvas.create_text(
            CHAR_W // 2, max(2, y_offset),
            text=heart_text, fill="#DC3C3C",
            font=("Segoe UI", 10))
        self._pet_tick += 1
        self._win.after(PET_BURST_MS // len(PET_HEARTS), self._pet_hearts_loop)


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
