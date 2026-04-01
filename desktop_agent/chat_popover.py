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

import threading
import time
import tkinter as tk
from datetime import datetime
from typing import Optional

from desktop_agent.i18n import t, set_lang, get_lang

# ── Font config ───────────────────────────────────────────────────────────────
FONT       = "Segoe UI"
FONT_MONO  = "Consolas"
MIN_PT     = 10    # accessibility: WCAG AA minimum (was 8, too small)

# ── Colours: Art Deco Gatsby palette ─────────────────────────────────────────
BG          = "#0A0A0F"     # deep noir background
BG_CARD     = "#12111A"     # card surface — midnight
BG_METRIC   = "#1A1820"     # metric cell — dark plum
BG_INPUT    = "#100F18"     # input row
BG_TOOLBAR  = "#08080D"     # toolbar — deepest
FG          = "#F5F0E1"     # warm ivory foreground
FG_DIM      = "#A89F8B"     # muted champagne
FG_MUTED    = "#7A7262"     # very dim (WCAG 5.0:1 on dark bg)
FG_HINT     = "#6B6355"     # hint / placeholder (WCAG 4.5:1+)

COL_BUY     = "#D4AF37"     # Art Deco gold — bullish
COL_BUY_DIM = "#2A2210"     # dark gold bg
COL_SELL    = "#C44536"     # vintage red — bearish
COL_SELL_DIM= "#3A1510"     # dark vintage red bg
COL_WAIT    = "#B8860B"     # dark goldenrod — wait
COL_WAIT_DIM= "#2E2108"     # dark amber bg
COL_ACTIVE  = "#D4AF37"     # gold active toggle

ACCENT      = "#D4AF37"     # Art Deco gold
ACCENT_DIM  = "#3D3115"     # dark gold
BTN_MIC     = "#D4AF37"
BTN_MIC_REC = "#C44536"
BTN_SEND    = "#D4AF37"
BTN_STOP    = "#C44536"
BTN_HOVER   = "#2A2520"     # hover — warm dark
BTN_ACTIVE  = "#B8860B"     # pressed — deep gold
BORDER      = "#3D3520"     # border — warm bronze line

W, H = 390, 580


class ChatPopover:
    def __init__(self, brain_bridge, voice_handler, tts_handler) -> None:
        self._bb   = brain_bridge
        self._vh   = voice_handler
        self._tts  = tts_handler
        self._lang = "en"
        self._busy = False
        self._last_result = None

        # Voice & language controls
        self._voice_on = True                         # TTS toggle
        self._lang_mode = "auto"                      # "auto" | "en" | "zh"

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
            self._win.withdraw()

    def is_visible(self) -> bool:
        if self._win is None:
            return False
        return self._win.state() != "withdrawn"

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        win = self._win

        # ── Title bar ────────────────────────────────────────────
        title_bar = tk.Frame(win, bg=ACCENT_DIM, height=36)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)

        self._title_lbl = tk.Label(
            title_bar, text=t("bull_coach"), bg=ACCENT_DIM, fg=FG,
            font=(FONT, 10, "bold"), anchor="w", padx=10)
        self._title_lbl.pack(side="left", fill="y")

        # Clear chat button (Phase 1)
        clear_btn = tk.Button(
            title_bar, text=t("clear"), bg=ACCENT_DIM, fg=FG_MUTED,
            font=(FONT, 8), bd=0, padx=6,
            activebackground=BTN_HOVER, activeforeground=FG,
            command=self._clear_chat, cursor="hand2")
        clear_btn.pack(side="right", fill="y")

        close_btn = tk.Button(
            title_bar, text="\u2715", bg=ACCENT_DIM, fg=FG_MUTED,
            font=(FONT, 10), bd=0, padx=8,
            activebackground=BTN_HOVER, activeforeground=FG,
            command=self.hide, cursor="hand2")
        close_btn.pack(side="right", fill="y")

        # ── Toolbar: ticker + mode toggles (Phase 1) ─────────────
        toolbar = tk.Frame(win, bg=BG_TOOLBAR, pady=4, padx=8)
        toolbar.pack(fill="x")

        # Ticker entry
        tk.Label(toolbar, text=t("ticker"), bg=BG_TOOLBAR, fg=FG_MUTED,
                 font=(FONT, MIN_PT)).pack(side="left", padx=(0, 4))
        self._ticker_entry = tk.Entry(
            toolbar, bg=BG, fg=FG, insertbackground=FG,
            font=(FONT, 9, "bold"), width=6, relief="flat", bd=2,
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
                font=(FONT, MIN_PT), cursor="hand2",
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
            font=(FONT, 12, "bold"), padx=12, pady=2)
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
            fg=FG_DIM, font=(FONT, MIN_PT, "bold"), bd=0, anchor="w",
            activebackground=BG_CARD, activeforeground=FG,
            cursor="hand2", command=self._toggle_why)
        self._why_btn.pack(anchor="w", pady=(2, 0))

        self._why_text = tk.Text(
            self._expand_frame, bg=BG_METRIC, fg=FG_DIM,
            font=(FONT, MIN_PT), height=0, wrap="word",
            relief="flat", bd=0, padx=8, pady=6, state="disabled")

        self._tech_btn = tk.Button(
            self._expand_frame, text=f"\u25B6  {t('tech_details')}", bg=BG_CARD,
            fg=FG_MUTED, font=(FONT, MIN_PT), bd=0, anchor="w",
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

        # ── Message area ─────────────────────────────────────────
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
                                  font=(FONT, MIN_PT, "bold"))
        self._msg_text.tag_config("user_msg",  foreground=FG,
                                  font=(FONT, 10), lmargin1=12, lmargin2=12)
        self._msg_text.tag_config("bot_name",  foreground=COL_BUY,
                                  font=(FONT, MIN_PT, "bold"))
        self._msg_text.tag_config("bot_msg",   foreground=FG,
                                  font=(FONT, 10))
        self._msg_text.tag_config("dim",       foreground=FG_MUTED,
                                  font=(FONT, MIN_PT))
        self._msg_text.tag_config("ts",        foreground=FG_HINT,
                                  font=(FONT, MIN_PT))

        # Phase 3: Empty state with hints
        self._add_message("bull", t("hint"), init=True)

        # ── Input row ─────────────────────────────────────────────
        input_frame = tk.Frame(win, bg=BG_INPUT, pady=6, padx=8)
        input_frame.pack(fill="x", side="bottom")

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
        send_btn = tk.Button(
            input_frame, text="\u2192", bg=BTN_SEND, fg="white",
            font=(FONT, 11, "bold"), bd=0, padx=10, pady=3,
            activebackground=BTN_ACTIVE, relief="flat", cursor="hand2",
            command=self._send_text)
        send_btn.pack(side="right")

        # Drag
        title_bar.bind("<ButtonPress-1>",   self._drag_start)
        title_bar.bind("<B1-Motion>",       self._drag_move)

    def _make_metric_cell(self, parent, label: str, value: str,
                          sub: str) -> dict:
        """Metric cell: header (tiny) → human label (large) → number (small)."""
        frame = tk.Frame(parent, bg=BG_METRIC, padx=8, pady=5)
        frame.pack(side="left", fill="x", expand=True, padx=2)

        lbl = tk.Label(frame, text=label, bg=BG_METRIC, fg=FG_MUTED,
                       font=(FONT, MIN_PT, "bold"))
        lbl.pack(anchor="w")
        # Human label (primary — what user reads first)
        val = tk.Label(frame, text=value, bg=BG_METRIC, fg=FG,
                       font=(FONT, 10, "bold"))
        val.pack(anchor="w")
        # Numeric detail (secondary — glanceable)
        sublbl = tk.Label(frame, text=sub, bg=BG_METRIC, fg=FG_MUTED,
                          font=(FONT, MIN_PT))
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
        _dec_icons = {"BUY": "\u25B2", "SELL": "\u25BC", "WAIT": "\u25CF"}
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
        self._process_input(text, self._effective_lang())

    def _process_input(self, text: str, lang: str) -> None:
        self._lang = lang
        self._add_message("user", text)
        self._busy = True
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
