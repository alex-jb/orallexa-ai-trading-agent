"""
desktop_agent/chat_popover.py
──────────────────────────────────────────────────────────────────
Product-level floating chat window for the AI trading coach.

UX upgrades applied:
  Phase 1: Ticker field, mode toggles, clear chat, TTS stop
  Phase 2: Min 8pt fonts, timestamps, friendly errors
  Phase 3: Empty-state hints, last-result recall
"""
from __future__ import annotations

import json
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import Optional

from desktop_agent.i18n import t, set_lang, get_lang
from desktop_agent.fonts import load_fonts, FONT_HEADING, FONT_BODY, FONT_MONO as _FONT_MONO

load_fonts()

# ── Font config ───────────────────────────────────────────────────────────────
FONT       = FONT_BODY       # Lato (body text, chat messages)
FONT_HEAD  = FONT_HEADING    # Josefin Sans (labels, headers, uppercase)
FONT_MONO  = _FONT_MONO      # DM Mono (prices, data, metrics)
MIN_PT     = 10    # accessibility: WCAG AA minimum (was 8, too small)

# ── Colours: Desktop Pet palette — matching Figma design ─────────────────────
BG          = "#0F0F16"     # dark pet background
BG_CARD     = "#161623"     # card surface
BG_METRIC   = "#12111A"     # metric cell
BG_INPUT    = "#161623"     # input row (same as card)
BG_TOOLBAR  = "#0F0F16"     # same as bg
FG          = "#F5E6CA"     # --champagne (primary text)
FG_DIM      = "#C5A255"     # --gold-muted
FG_MUTED    = "#6B6E76"     # --text-muted
FG_HINT     = "#4A4D55"     # --text-dim

COL_BUY     = "#DC3C3C"     # red = bullish (中国红=涨)
COL_BUY_DIM = "#1E1010"     # dark red bg
COL_SELL    = "#32AA5A"     # green = bearish (绿=跌)
COL_SELL_DIM= "#101E14"     # dark green bg
COL_WAIT    = "#D4AF37"     # --gold (wait/neutral)
COL_WAIT_DIM= "#1A1608"     # dark gold bg
COL_ACTIVE  = "#D4AF37"     # --gold

ACCENT      = "#D4AF37"     # --gold
ACCENT_BRIGHT = "#FFD700"   # --gold-bright
ACCENT_DIM  = "#161623"     # --bg-card
BTN_MIC     = "#D4AF37"
BTN_MIC_REC = "#DC3C3C"     # red
BTN_SEND    = "#D4AF37"
BTN_STOP    = "#DC3C3C"
BTN_HOVER   = "#2A2A3E"     # --bg-input
BTN_ACTIVE  = "#C5A255"     # --gold-muted
BORDER      = "#2A2A3E"     # --border
BORDER_GOLD = "#3D3520"     # approx for Tkinter

# Pixel accent size (for decorative pixel dots)
PX_DOT = 3

W, H = 340, 580


_CHAT_HISTORY_PATH = Path(__file__).parent.parent / "memory_data" / "chat_history.json"


class ChatPopover:
    def __init__(self, brain_bridge, voice_handler, tts_handler) -> None:
        self._bb   = brain_bridge
        self._vh   = voice_handler
        self._tts  = tts_handler
        self._lang = "en"
        self._busy = False
        self._last_result = None
        self._analysis_history: list[dict] = []  # [{ticker, decision, confidence, ts}]
        self._chat_log: list[dict] = []          # persistent chat history

        # Voice & language controls
        self._voice_on = True                         # TTS toggle
        self._lang_mode = "auto"                      # "auto" | "en" | "zh"

        # Typing indicator
        self._typing_dots = 0
        self._typing_active = False

        self._win: Optional[tk.Toplevel] = None
        self._root: Optional[tk.Tk]      = None
        self._on_state_change = None

    # ── Public ────────────────────────────────────────────────────────────────

    def build(self, root: tk.Tk, on_state_change=None) -> None:
        self._root = root
        self._on_state_change = on_state_change
        self._win  = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.wm_attributes("-topmost", True)
        self._win.configure(bg=BG)
        self._win.withdraw()
        self._build_ui()
        self._load_chat_history()

    def show(self, anchor_x: int, anchor_y: int) -> None:
        if self._win is None:
            return
        sw = self._win.winfo_screenwidth()
        px = max(4, min(anchor_x - W // 2, sw - W - 4))
        py = max(4, anchor_y - H - 10)
        self._win.geometry(f"{W}x{H}+{px}+{py}")
        self._win.deiconify()
        self._win.lift()
        self._update_header()

    def hide(self) -> None:
        if self._win:
            self._save_chat_history()
            self._win.withdraw()

    def is_visible(self) -> bool:
        if self._win is None:
            return False
        return self._win.state() != "withdrawn"

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        win = self._win

        # ── Gold gradient accent line at top ──────────────────────
        gold_line = tk.Frame(win, bg=ACCENT, height=3)
        gold_line.pack(fill="x", side="top")

        # ── Title bar (compact, matching Figma) ──────────────────
        title_bar = tk.Frame(win, bg=BG_CARD, height=34)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)

        self._title_lbl = tk.Label(
            title_bar, text="ORALLEXA", bg=BG_CARD, fg=ACCENT,
            font=(FONT_HEAD, 10, "bold"), anchor="w", padx=10)
        self._title_lbl.pack(side="left", fill="y")

        # Green online dot (decorative, 8pt minimum)
        tk.Label(title_bar, text="\u25CF", bg=BG_CARD, fg="#32AA5A",
                 font=(FONT, 8), padx=2).pack(side="left")

        close_btn = tk.Button(
            title_bar, text="\u2715", bg=BG_CARD, fg=FG_MUTED,
            font=(FONT, 10), bd=0, padx=8,
            activebackground=BTN_HOVER, activeforeground=FG,
            command=self.hide, cursor="hand2")
        close_btn.pack(side="right", fill="y")

        quit_btn = tk.Button(
            title_bar, text=t("tray_quit"), bg=BG_CARD, fg="#DC3C3C",
            font=(FONT, 8), bd=0, padx=6,
            activebackground="#1E1010", activeforeground="#FF6666",
            command=self._quit_app, cursor="hand2")
        quit_btn.pack(side="right", fill="y")

        clear_btn = tk.Button(
            title_bar, text=t("clear"), bg=BG_CARD, fg=FG_MUTED,
            font=(FONT, 8), bd=0, padx=6,
            activebackground=BTN_HOVER, activeforeground=FG,
            command=self._clear_chat, cursor="hand2")
        clear_btn.pack(side="right", fill="y")

        # ── Welcome section ──────────────────────────────────────
        welcome_frame = tk.Frame(win, bg=BG, pady=10)
        welcome_frame.pack(fill="x")
        tk.Label(welcome_frame, text=t("welcome_back"),
                 bg=BG, fg=ACCENT_BRIGHT,
                 font=(FONT, 12, "bold")).pack()

        self._market_status = tk.Label(welcome_frame, text="",
                 bg=BG, fg=FG_MUTED, font=(FONT, MIN_PT))
        self._market_status.pack(pady=(2, 0))

        # Pixel dot divider
        px_div = tk.Frame(win, bg=BG, height=8)
        px_div.pack(fill="x")
        # Three tiny gold squares as pixel diamond
        for i, offset in enumerate([-6, 0, 6]):
            dot = tk.Frame(px_div, bg=ACCENT if i == 1 else FG_DIM,
                          width=PX_DOT, height=PX_DOT)
            dot.place(relx=0.5, rely=0.5, x=offset, anchor="center")

        # ── Toolbar: ticker + mode toggles (Phase 1) ─────────────
        toolbar = tk.Frame(win, bg=BG_TOOLBAR, pady=4, padx=8)
        toolbar.pack(fill="x")

        # Ticker entry
        tk.Label(toolbar, text=t("ticker"), bg=BG_TOOLBAR, fg=FG_MUTED,
                 font=(FONT_HEAD, MIN_PT)).pack(side="left", padx=(0, 4))
        self._ticker_entry = tk.Entry(
            toolbar, bg=BG, fg=FG, insertbackground=FG,
            font=(FONT_MONO, 9, "bold"), width=6, relief="flat", bd=2,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT)
        self._ticker_entry.insert(0, self._bb.ticker)
        self._ticker_entry.pack(side="left", padx=(0, 8))
        self._ticker_entry.bind("<Return>", self._on_ticker_change)
        self._ticker_entry.bind("<FocusOut>", self._on_ticker_change)

        # Mode toggles (pill buttons)
        self._mode_btns: dict[str, tk.Button] = {}
        for mode_key, mode_label in [("scalp", t("scalp")), ("intraday", t("intra")),
                                      ("swing", t("swing"))]:
            btn = tk.Button(
                toolbar, text=mode_label, bd=0, padx=8, pady=2,
                font=(FONT_HEAD, MIN_PT), cursor="hand2",
                command=lambda m=mode_key: self._on_mode_click(m))
            btn.pack(side="left", padx=2)
            self._mode_btns[mode_key] = btn
        self._refresh_mode_btns()

        # Last result button
        self._last_btn = tk.Button(
            toolbar, text=t("last"), bg=BG_TOOLBAR, fg=FG_MUTED,
            font=(FONT, MIN_PT), bd=0, padx=6, cursor="hand2",
            activebackground=BG_TOOLBAR, activeforeground=FG,
            command=self._show_last_result, state="disabled")
        self._last_btn.pack(side="right")

        # ── Control row: voice + language ─────────────────────────
        ctrl_row = tk.Frame(win, bg=BG_INPUT, pady=4, padx=8)
        ctrl_row.pack(fill="x")

        # Voice ON/OFF toggle
        self._voice_btn = tk.Button(
            ctrl_row, text=t("voice_on"), bd=0, padx=8, pady=2,
            font=(FONT, MIN_PT), cursor="hand2",
            bg=COL_ACTIVE, fg="white",
            activebackground=COL_ACTIVE,
            command=self._toggle_voice)
        self._voice_btn.pack(side="left", padx=(0, 6))

        # Language mode pills
        tk.Label(ctrl_row, text=t("lang_label"), bg=BG_INPUT, fg=FG_MUTED,
                 font=(FONT, MIN_PT)).pack(side="left", padx=(0, 3))
        self._lang_btns: dict[str, tk.Button] = {}
        for lang_key, lang_label in [("auto", "Auto"), ("en", "EN"), ("zh", "ZH")]:
            btn = tk.Button(
                ctrl_row, text=lang_label, bd=0, padx=6, pady=2,
                font=(FONT, MIN_PT), cursor="hand2",
                command=lambda lk=lang_key: self._on_lang_click(lk))
            btn.pack(side="left", padx=1)
            self._lang_btns[lang_key] = btn
        self._refresh_lang_btns()

        # ── Sub-header: dynamic display label ─────────────────────
        subbar = tk.Frame(win, bg=BG_INPUT, height=24)
        subbar.pack(fill="x")
        subbar.pack_propagate(False)

        self._status_lbl = tk.Label(
            subbar, text="", bg=BG_INPUT, fg=FG_DIM,
            font=(FONT, MIN_PT), anchor="w", padx=10)
        self._status_lbl.pack(side="left", fill="both", expand=True)

        # ── Decision card (hidden until analysis) ─────────────────
        self._card_frame = tk.Frame(win, bg=BG_CARD, padx=0, pady=0)

        self._card_top = tk.Frame(self._card_frame, bg=BG_CARD, padx=12, pady=8)
        self._card_top.pack(fill="x")

        badge_row = tk.Frame(self._card_top, bg=BG_CARD)
        badge_row.pack(fill="x")

        self._dec_badge = tk.Label(
            badge_row, text="", bg=COL_BUY_DIM, fg=COL_BUY,
            font=(FONT_HEAD, 12, "bold"), padx=12, pady=2)
        self._dec_badge.pack(side="left")

        self._dec_context = tk.Label(
            badge_row, text="", bg=BG_CARD, fg=FG_MUTED,
            font=(FONT, MIN_PT), anchor="e")
        self._dec_context.pack(side="right", fill="y")

        self._rec_label = tk.Label(
            self._card_top, text="", bg=BG_CARD, fg=FG,
            font=(FONT, 9), anchor="w",
            wraplength=W - 36, justify="left")
        self._rec_label.pack(anchor="w", pady=(6, 0))

        tk.Frame(self._card_frame, bg=BORDER, height=1).pack(fill="x")

        self._metrics_frame = tk.Frame(self._card_frame, bg=BG_CARD, padx=8, pady=6)
        self._metrics_frame.pack(fill="x")

        self._sig_cell  = self._make_metric_cell(self._metrics_frame, t("signal"), "\u2014", "\u2014")
        self._conf_cell = self._make_metric_cell(self._metrics_frame, t("confidence"), "\u2014", "\u2014")
        self._risk_cell = self._make_metric_cell(self._metrics_frame, t("risk"), "\u2014", "\u2014")

        tk.Frame(self._card_frame, bg=BORDER, height=1).pack(fill="x")

        self._expand_frame = tk.Frame(self._card_frame, bg=BG_CARD, padx=12, pady=4)
        self._expand_frame.pack(fill="x")

        self._why_btn = tk.Button(
            self._expand_frame, text=f"\u25B6  {t('why')}", bg=BG_CARD,
            fg=FG_DIM, font=(FONT_HEAD, MIN_PT, "bold"), bd=0, anchor="w",
            activebackground=BG_CARD, activeforeground=FG,
            cursor="hand2", command=self._toggle_why)
        self._why_btn.pack(anchor="w", pady=(2, 0))

        self._why_text = tk.Text(
            self._expand_frame, bg=BG_METRIC, fg=FG_DIM,
            font=(FONT, MIN_PT), height=0, wrap="word",
            relief="flat", bd=0, padx=8, pady=6, state="disabled")

        self._tech_btn = tk.Button(
            self._expand_frame, text=f"\u25B6  {t('tech_details')}", bg=BG_CARD,
            fg=FG_MUTED, font=(FONT_HEAD, MIN_PT), bd=0, anchor="w",
            activebackground=BG_CARD, activeforeground=FG_DIM,
            cursor="hand2", command=self._toggle_tech)
        self._tech_btn.pack(anchor="w", pady=(2, 0))

        self._tech_text = tk.Text(
            self._expand_frame, bg=BG_METRIC, fg=FG_MUTED,
            font=(FONT_MONO, MIN_PT), height=0, wrap="word",
            relief="flat", bd=0, padx=8, pady=6, state="disabled")

        # ── Risk management row (hidden until populated) ─────────
        self._risk_frame = tk.Frame(self._card_frame, bg=BG_CARD, padx=12, pady=6)
        # Will be packed by _show_risk_mgmt()

        self._risk_entry_lbl = tk.Label(self._risk_frame, text="", bg=BG_CARD,
                                        fg=FG_DIM, font=(FONT, MIN_PT))
        self._risk_entry_lbl.pack(side="left", padx=(0, 12))
        self._risk_stop_lbl = tk.Label(self._risk_frame, text="", bg=BG_CARD,
                                       fg=COL_SELL, font=(FONT, MIN_PT))
        self._risk_stop_lbl.pack(side="left", padx=(0, 12))
        self._risk_target_lbl = tk.Label(self._risk_frame, text="", bg=BG_CARD,
                                         fg=COL_BUY, font=(FONT, MIN_PT))
        self._risk_target_lbl.pack(side="left", padx=(0, 12))
        self._risk_rr_lbl = tk.Label(self._risk_frame, text="", bg=BG_CARD,
                                     fg=FG, font=(FONT, MIN_PT, "bold"))
        self._risk_rr_lbl.pack(side="right")

        tk.Frame(self._card_frame, bg=BORDER, height=1).pack(fill="x")

        # ── Input row (pack FIRST at bottom so it never gets pushed out) ──
        input_frame = tk.Frame(win, bg=BG_INPUT, pady=6, padx=8)
        input_frame.pack(fill="x", side="bottom")

        # ── Message area (fills remaining space between card and input) ──
        msg_frame = tk.Frame(win, bg=BG)
        msg_frame.pack(fill="both", expand=True, padx=0, pady=0)

        scrollbar = tk.Scrollbar(msg_frame, bg=BG, troughcolor=BG,
                                 highlightthickness=0, bd=0)
        scrollbar.pack(side="right", fill="y")

        self._msg_text = tk.Text(
            msg_frame, bg=BG, fg=FG, insertbackground=FG,
            font=(FONT, 10), wrap="word",
            relief="flat", bd=0, padx=12, pady=8,
            state="disabled", cursor="arrow",
            yscrollcommand=scrollbar.set,
            selectbackground=BG_METRIC)
        self._msg_text.pack(fill="both", expand=True)
        scrollbar.config(command=self._msg_text.yview)

        self._msg_text.tag_config("user_name", foreground=ACCENT,
                                  font=(FONT_HEAD, MIN_PT, "bold"))
        self._msg_text.tag_config("user_msg",  foreground=FG,
                                  font=(FONT, 10), lmargin1=12, lmargin2=12)
        self._msg_text.tag_config("bot_name",  foreground=ACCENT_BRIGHT,
                                  font=(FONT_HEAD, MIN_PT, "bold"))
        self._msg_text.tag_config("bot_msg",   foreground=FG,
                                  font=(FONT, 10))
        self._msg_text.tag_config("dim",       foreground=FG_MUTED,
                                  font=(FONT, MIN_PT))
        self._msg_text.tag_config("ts",        foreground=FG_HINT,
                                  font=(FONT, MIN_PT))

        # Phase 3: Empty state with hints
        self._add_message("bull", t("hint"), init=True)

        # Mic button
        self._mic_btn = tk.Button(
            input_frame, text="\U0001F3A4", bg=BTN_MIC, fg="white",
            font=(FONT, 11), bd=0, padx=6, pady=3,
            activebackground=BTN_MIC_REC,
            relief="flat", cursor="hand2")
        self._mic_btn.pack(side="left", padx=(0, 4))
        self._mic_btn.bind("<ButtonPress-1>",   self._mic_press)
        self._mic_btn.bind("<ButtonRelease-1>", self._mic_release)

        # TTS stop button (Phase 3)
        self._stop_btn = tk.Button(
            input_frame, text="\u25A0", bg=BG_INPUT, fg=FG_MUTED,
            font=(FONT, 10), bd=0, padx=4, pady=3,
            activebackground=BTN_STOP, activeforeground="white",
            relief="flat", cursor="hand2",
            command=self._stop_tts)
        self._stop_btn.pack(side="left", padx=(0, 4))

        # Text entry
        self._entry = tk.Entry(
            input_frame, bg=BG, fg=FG, insertbackground=FG,
            font=(FONT, 10), relief="flat", bd=4,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=ACCENT)
        self._entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self._entry.bind("<Return>", lambda _: self._send_text())

        # Send button
        self._send_btn = tk.Button(
            input_frame, text="\u2192", bg=BTN_SEND, fg="white",
            font=(FONT, 11, "bold"), bd=0, padx=10, pady=3,
            activebackground=BTN_ACTIVE, relief="flat", cursor="hand2",
            command=self._send_text)
        self._send_btn.pack(side="right")

        # Drag
        title_bar.bind("<ButtonPress-1>",   self._drag_start)
        title_bar.bind("<B1-Motion>",       self._drag_move)

    def _make_metric_cell(self, parent, label: str, value: str,
                          sub: str) -> dict:
        """Metric cell: header (tiny) → human label (large) → number (small)."""
        frame = tk.Frame(parent, bg=BG_METRIC, padx=8, pady=5)
        frame.pack(side="left", fill="x", expand=True, padx=2)

        lbl = tk.Label(frame, text=label, bg=BG_METRIC, fg=FG_MUTED,
                       font=(FONT_HEAD, MIN_PT, "bold"))
        lbl.pack(anchor="w")
        # Human label (primary — what user reads first)
        val = tk.Label(frame, text=value, bg=BG_METRIC, fg=FG,
                       font=(FONT, 10, "bold"))
        val.pack(anchor="w")
        # Numeric detail (secondary — glanceable)
        sublbl = tk.Label(frame, text=sub, bg=BG_METRIC, fg=FG_MUTED,
                          font=(FONT_MONO, MIN_PT))
        sublbl.pack(anchor="w")
        return {"frame": frame, "value": val, "sub": sublbl}

    # ── Toolbar actions (Phase 1) ─────────────────────────────────────────────

    def _on_ticker_change(self, _event=None) -> None:
        new_val = self._ticker_entry.get().strip().upper()
        if new_val and new_val != self._bb.ticker:
            self._bb.update_ticker(new_val)
            self._update_header()
            self._add_status(f"[ticker -> {new_val}]")

    def _on_mode_click(self, mode: str) -> None:
        tf_defaults = {"scalp": "5m", "intraday": "15m", "swing": "1D"}
        self._bb.update_mode(mode, tf_defaults.get(mode, "15m"))
        self._refresh_mode_btns()
        self._update_header()
        self._add_status(f"[mode -> {mode}]")

    def _refresh_mode_btns(self) -> None:
        for key, btn in self._mode_btns.items():
            if key == self._bb.mode:
                btn.config(bg=COL_ACTIVE, fg="white")
            else:
                btn.config(bg=BG_TOOLBAR, fg=FG_MUTED)

    def _clear_chat(self) -> None:
        self._msg_text.config(state="normal")
        self._msg_text.delete("1.0", "end")
        self._msg_text.config(state="disabled")
        self._hide_decision_card()
        self._add_message("bull", t("chat_cleared"), init=True)

    def _quit_app(self) -> None:
        """Exit the entire desktop agent application."""
        try:
            self._tts.stop()
        except Exception:
            pass
        self._root.quit()
        self._root.destroy()

    def _stop_tts(self) -> None:
        self._tts.stop()
        self._stop_btn.config(fg=FG_HINT)

    def _toggle_voice(self) -> None:
        self._voice_on = not self._voice_on
        if self._voice_on:
            self._voice_btn.config(text=t("voice_on"), bg=COL_ACTIVE, fg="white")
        else:
            self._voice_btn.config(text=t("voice_off"), bg=BG_INPUT, fg=FG_MUTED)
            self._tts.stop()

    def show_voice_status(self, recording: bool) -> None:
        """Update mic button to reflect external voice toggle (K key)."""
        if recording:
            self._mic_btn.config(bg=BTN_MIC_REC, text="\u23F9")
            self._add_status("[K] Voice recording...")
        else:
            self._mic_btn.config(bg=BTN_MIC, text="\U0001F3A4")

    def _on_lang_click(self, lang_key: str) -> None:
        self._lang_mode = lang_key
        if lang_key != "auto":
            self._lang = lang_key
            set_lang(lang_key)
        self._refresh_lang_btns()

    def _refresh_lang_btns(self) -> None:
        for key, btn in self._lang_btns.items():
            if key == self._lang_mode:
                btn.config(bg=COL_ACTIVE, fg="white")
            else:
                btn.config(bg=BG_INPUT, fg=FG_MUTED)

    def _effective_lang(self, detected: str = "") -> str:
        """Return the language to use: forced mode overrides auto-detection."""
        if self._lang_mode == "auto":
            return detected or self._lang
        return self._lang_mode

    def _show_last_result(self) -> None:
        if self._last_result:
            self._show_decision_card(self._last_result)

    # ── Decision card ─────────────────────────────────────────────────────────

    def _show_decision_card(self, result) -> None:
        from models.card_formatter import (
            humanize_reasoning, signal_label, confidence_label,
            risk_description, decision_subtitle,
        )

        dec  = result.decision
        conf = result.confidence
        risk = result.risk_level
        sig  = getattr(result, "signal_strength", 0.0)
        rec  = getattr(result, "recommendation", "")
        reasoning = result.reasoning

        # Store for recall
        self._last_result = result
        self._last_btn.config(state="normal")

        color_map = {
            "BUY":  (COL_BUY, COL_BUY_DIM),
            "SELL": (COL_SELL, COL_SELL_DIM),
            "WAIT": (COL_WAIT, COL_WAIT_DIM),
        }
        fg_col, bg_col = color_map.get(dec, (FG_DIM, BG_METRIC))
        # Pixel-pet style decision icons
        _dec_icons = {"BUY": "\u25B2", "SELL": "\u25BC", "WAIT": "\u25C6"}
        _icon = _dec_icons.get(dec, "")
        self._dec_badge.config(text=f" {_icon} {dec} ", fg=fg_col, bg=bg_col)
        self._dec_context.config(text=self._bb.display_label)
        self._rec_label.config(text=rec or t("analysis_complete"))

        # Metrics: human label first (large), number second (small)
        self._sig_cell["value"].config(text=signal_label(sig))
        self._sig_cell["sub"].config(text=f"{sig:.0f}/100")

        self._conf_cell["value"].config(text=confidence_label(conf))
        self._conf_cell["sub"].config(text=f"{conf:.0f}%")

        risk_fg = {"LOW": COL_BUY, "MEDIUM": COL_WAIT, "HIGH": COL_SELL}.get(risk, FG)
        self._risk_cell["value"].config(text=risk_description(risk), fg=risk_fg)
        self._risk_cell["sub"].config(text=risk)

        self._human_reasons = humanize_reasoning(reasoning, max_bullets=4)
        self._raw_reasons   = reasoning
        self._why_expanded  = False
        self._tech_expanded = False
        self._why_btn.config(text=f"\u25B6  {t('why')}")
        self._tech_btn.config(text=f"\u25B6  {t('tech_details')}")
        self._why_text.pack_forget()
        self._tech_text.pack_forget()

        self._card_frame.pack(fill="x", before=self._msg_text.master)

        if self._on_state_change:
            self._on_state_change(dec, risk)

    def _hide_decision_card(self) -> None:
        self._card_frame.pack_forget()
        self._risk_frame.pack_forget()

    def _show_risk_mgmt(self, entry: float, stop: float, target: float,
                        rr: str = "") -> None:
        """Show risk management row below the decision card."""
        self._risk_entry_lbl.config(text=f"Entry: ${entry:.2f}")
        self._risk_stop_lbl.config(text=f"Stop: ${stop:.2f}")
        self._risk_target_lbl.config(text=f"Target: ${target:.2f}")
        self._risk_rr_lbl.config(text=f"R:R {rr}" if rr else "")
        self._risk_frame.pack(fill="x", before=self._msg_text.master)

    def _toggle_why(self) -> None:
        if self._why_expanded:
            self._why_text.pack_forget()
            self._why_btn.config(text=f"\u25B6  {t('why')}")
            self._why_expanded = False
        else:
            lines = getattr(self, "_human_reasons", [t("analysis_complete")])
            self._why_text.config(state="normal",
                                  height=min(6, max(2, len(lines) + 1)))
            self._why_text.delete("1.0", "end")
            for line in lines:
                self._why_text.insert("end", f"\u2022 {line}\n")
            self._why_text.config(state="disabled")
            self._why_text.pack(fill="x", pady=(2, 4))
            self._why_btn.config(text=f"\u25BC  {t('why')}")
            self._why_expanded = True

    def _toggle_tech(self) -> None:
        if self._tech_expanded:
            self._tech_text.pack_forget()
            self._tech_btn.config(text=f"\u25B6  {t('tech_details')}")
            self._tech_expanded = False
        else:
            lines = getattr(self, "_raw_reasons", [])
            self._tech_text.config(state="normal",
                                   height=min(8, max(3, len(lines))))
            self._tech_text.delete("1.0", "end")
            for line in lines:
                self._tech_text.insert("end", f"{line}\n")
            self._tech_text.config(state="disabled")
            self._tech_text.pack(fill="x", pady=(2, 4))
            self._tech_btn.config(text=f"\u25BC  {t('tech_details')}")
            self._tech_expanded = True

    # ── Messaging ─────────────────────────────────────────────────────────────

    def _add_message(self, role: str, text: str, init: bool = False) -> None:
        tw = self._msg_text
        tw.config(state="normal")
        if not init:
            tw.insert("end", "\n")
        # Phase 2: timestamp
        ts = datetime.now().strftime("%H:%M")
        if role == "user":
            tw.insert("end", f"{t('you')}  {ts}\n", "user_name")
            tw.insert("end", text + "\n", "user_msg")
        else:
            tw.insert("end", f"{t('bull_coach')}  {ts}\n", "bot_name")
            tw.insert("end", text + "\n", "bot_msg")
        tw.config(state="disabled")
        tw.see("end")
        # Track for persistence (skip if restoring from disk)
        if not init:
            self._chat_log.append({"role": role, "text": text, "ts": ts})
            if len(self._chat_log) > 50:
                self._chat_log = self._chat_log[-50:]

    def _save_chat_history(self) -> None:
        """Save recent chat messages to disk."""
        try:
            _CHAT_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(_CHAT_HISTORY_PATH, "w", encoding="utf-8") as f:
                json.dump(self._chat_log[-50:], f, ensure_ascii=False)
        except Exception:
            pass

    def _load_chat_history(self) -> None:
        """Restore chat messages from last session."""
        try:
            if _CHAT_HISTORY_PATH.exists():
                with open(_CHAT_HISTORY_PATH, "r", encoding="utf-8") as f:
                    self._chat_log = json.load(f)
                for msg in self._chat_log[-20:]:
                    self._add_message(msg["role"], msg["text"], init=True)
        except Exception:
            self._chat_log = []

    def _add_status(self, text: str) -> None:
        tw = self._msg_text
        tw.config(state="normal")
        tw.insert("end", f"\n{text}\n", "dim")
        tw.config(state="disabled")
        tw.see("end")

    def _update_header(self) -> None:
        self._status_lbl.config(text=self._bb.display_label)
        # Sync ticker entry if changed externally
        current = self._ticker_entry.get().strip().upper()
        if current != self._bb.ticker:
            self._ticker_entry.delete(0, "end")
            self._ticker_entry.insert(0, self._bb.ticker)
        self._refresh_mode_btns()

    def update_market_status(self, text: str) -> None:
        """Update the market status line in the welcome section."""
        if hasattr(self, "_market_status"):
            self._market_status.config(text=text)

    def _notify_changes(self) -> None:
        changes = self._bb.last_changes
        if changes:
            self._add_status(f"[{', '.join(changes)}]")

    # ── Send / reply ──────────────────────────────────────────────────────────

    def _send_text(self) -> None:
        text = self._entry.get().strip()
        if not text or self._busy:
            return
        self._entry.delete(0, "end")
        # Auto-detect language from text content
        detected = self._detect_lang(text)
        self._process_input(text, self._effective_lang(detected))

    @staticmethod
    def _detect_lang(text: str) -> str:
        """Detect language from text — check for CJK characters."""
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                return "zh"
        return "en"

    def _process_input(self, text: str, lang: str) -> None:
        self._lang = lang
        self._add_message("user", text)
        self._busy = True
        # Disable input while processing
        self._send_btn.config(state="disabled")
        self._entry.config(state="disabled")
        self._add_status(t("thinking"))

        if self._on_state_change:
            self._on_state_change("THINKING", "")

        threading.Thread(target=self._get_reply, args=(text, lang),
                         daemon=True).start()

    def _get_reply(self, text: str, lang: str) -> None:
        try:
            reply, action = self._bb.route_and_respond(text, lang=lang)
        except Exception as exc:
            from core.logger import get_logger
            get_logger("chat_popover").error("route_and_respond failed: %s", exc)
            reply = ("AI 暂时无法回复，请检查网络和API密钥。" if lang == "zh"
                     else f"Error: {exc}")
            action = "none"

        decision_result = None
        try:
            if action == "analysis":
                try:
                    from core.brain import OrallexaBrain
                    brain = OrallexaBrain(self._bb.ticker)
                    decision_result = brain.run_for_mode(
                        mode=self._bb.mode,
                        timeframe=self._bb.timeframe,
                        use_claude=False,
                    )
                except Exception as exc:
                    from core.logger import get_logger
                    get_logger("chat_popover").warning(
                        "Analysis failed for %s: %s", self._bb.ticker, exc)
            elif action == "screenshot":
                decision_result = getattr(self._bb, "last_chart_result", None)
        except Exception:
            pass

        self._root.after(0, self._show_reply, reply, lang, action, decision_result)

    def _show_reply(self, reply: str, lang: str, action: str,
                    decision_result=None) -> None:
        try:
            # Remove "thinking..." status
            tw = self._msg_text
            tw.config(state="normal")
            content = tw.get("1.0", "end")
            thinking_str = t("thinking")
            idx = content.rfind(f"\n{thinking_str}\n")
            if idx >= 0:
                tw.delete(f"1.0 + {idx} chars",
                          f"1.0 + {idx + len(chr(10) + thinking_str + chr(10))} chars")
            tw.config(state="disabled")

            if decision_result is not None:
                self._show_decision_card(decision_result)
            elif self._on_state_change:
                self._on_state_change("WAIT", "")

            self._notify_changes()
            self._add_message("bull", reply if reply else "[no response]")
            self._update_header()

            # TTS (gated on voice toggle)
            if reply and self._voice_on:
                self._stop_btn.config(fg=BTN_STOP)
                threading.Thread(target=self._tts.speak,
                                 args=(reply, self._effective_lang(lang)),
                                 daemon=True).start()
        except Exception as exc:
            from core.logger import get_logger
            get_logger("chat_popover").error("_show_reply error: %s", exc)
        finally:
            self._busy = False
            # Re-enable input
            self._send_btn.config(state="normal")
            self._entry.config(state="normal")
            self._entry.focus_set()

    # ── Voice ─────────────────────────────────────────────────────────────────

    def _mic_press(self, _event) -> None:
        if self._busy:
            return
        try:
            self._vh.start_recording()
            self._mic_btn.config(bg=BTN_MIC_REC, text="\u23F9")
            if self._on_state_change:
                self._on_state_change("LISTENING", "")
        except Exception as exc:
            self._add_status(f"[Mic error: {exc}]")

    def _mic_release(self, _event) -> None:
        self._mic_btn.config(bg=BTN_MIC, text="\U0001F3A4")
        if not self._vh.is_recording:
            return
        self._add_status(t("transcribing"))
        threading.Thread(target=self._finish_voice, daemon=True).start()

    def _finish_voice(self) -> None:
        try:
            text, lang = self._vh.stop_and_transcribe()
        except Exception as exc:
            self._root.after(0, lambda: self._add_status(f"[Transcribe error: {exc}]"))
            return
        self._root.after(0, self._on_voice_done, text, lang)

    def _on_voice_done(self, text: str, lang: str) -> None:
        tw = self._msg_text
        tw.config(state="normal")
        content = tw.get("1.0", "end")
        transcribing_str = t("transcribing")
        idx = content.rfind(f"\n{transcribing_str}\n")
        if idx >= 0:
            tw.delete(f"1.0 + {idx} chars",
                      f"1.0 + {idx + len(chr(10) + transcribing_str + chr(10))} chars")
        tw.config(state="disabled")

        if text:
            effective = self._effective_lang(lang)
            self._lang = effective
            self._process_input(text, effective)
        else:
            self._add_status(t("no_speech"))
            if self._on_state_change:
                self._on_state_change("WAIT", "")

    # ── Drag ──────────────────────────────────────────────────────────────────

    def _drag_start(self, event) -> None:
        self._dx = event.x
        self._dy = event.y

    def _drag_move(self, event) -> None:
        x = self._win.winfo_x() + event.x - self._dx
        y = self._win.winfo_y() + event.y - self._dy
        self._win.geometry(f"+{x}+{y}")
