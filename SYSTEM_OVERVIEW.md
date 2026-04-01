# OralleXa — System Overview

**AI Trading Decision Copilot with Desktop Assistant, Voice Interaction, and Multi-Agent Analysis**

---

## 1. System Overview

### What This System Is

OralleXa is an AI-powered trading decision copilot that combines real-time technical analysis, multi-agent reasoning, voice interaction, and a floating desktop assistant into a unified system. It analyzes stocks across multiple timeframes (scalping, intraday, swing) and produces structured BUY / SELL / WAIT decisions with separated signal strength, confidence, and risk metrics.

The system has two interfaces:
- **Streamlit Web App** (`app_ui.py`) — a 5-page trading cockpit with voice coaching, decision engine, backtesting, memory, and settings
- **Desktop Agent** (`desktop_agent/`) — a floating cartoon bull character with push-to-talk voice, chat popover, and system tray, always available on screen

### What Problem It Solves

Most retail traders face three problems:
1. **Information overload** — dozens of indicators, no clear action
2. **Emotional decision-making** — no structured framework to follow
3. **No learning loop** — repeating the same mistakes without feedback

OralleXa solves these by:
- Producing a single, structured decision (BUY/SELL/WAIT) with clear reasoning
- Separating *signal strength* (how clear the setup is) from *confidence* (how certain we are) from *risk* (how dangerous it is)
- Tracking trades, win/loss streaks, and adjusting aggressiveness over time
- Speaking in the user's language (English, Chinese, Japanese, etc.) via voice

### How It Differs from Typical Systems

| Typical Trading Bot | Typical LLM Tool | Typical Quant System | **OralleXa** |
|---|---|---|---|
| Executes trades blindly | Gives opinions with no data | Outputs metrics, not decisions | **Structured decisions with reasoning** |
| Single strategy | No technical analysis | No natural language | **Multi-skill + multi-agent + voice** |
| No explanation | Hallucination risk | Hard to interpret | **Step-by-step reasoning + recommendation** |
| No learning | No memory | Static parameters | **Behavior tracking + adaptive aggressiveness** |
| Text-only | Text-only | Terminal-only | **Desktop character + voice + web UI** |

---

## 2. Core Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        INTERFACE LAYER                           │
│                                                                  │
│  ┌──────────────┐  ┌───────────────┐  ┌────────────────────┐    │
│  │  app_ui.py   │  │   app.py      │  │  desktop_agent/    │    │
│  │  (2,273 L)   │  │   (644 L)     │  │  main.py           │    │
│  │              │  │              │  │                    │    │
│  │  5 pages:    │  │  3 modes:    │  │  BullCharacter     │    │
│  │  Home        │  │  scalp       │  │  ChatPopover       │    │
│  │  Today       │  │  predict     │  │  VoiceHandler      │    │
│  │  Memory      │  │  research    │  │  TTSHandler         │    │
│  │  Analysis    │  │              │  │  TrayIcon          │    │
│  │  Settings    │  │              │  │  BrainBridge       │    │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬──────────┘    │
│         │                 │                     │               │
└─────────┼─────────────────┼─────────────────────┼───────────────┘
          │                 │                     │
          ▼                 ▼                     ▼
┌──────────────────────────────────────────────────────────────────┐
│                     BRAIN / ROUTING LAYER                        │
│                                                                  │
│  core/brain.py — OrallexaBrain                                   │
│    run_for_mode(mode, timeframe)  → routes to correct skill      │
│    run_scalping()                 → ScalpingSkill                 │
│    run_intraday(tf)               → IntradaySkill                 │
│    run_prediction(use_claude)     → PredictionSkill               │
│    run_deep_analysis(date)        → TradingAgentsGraph            │
│                                                                  │
│  desktop_agent/brain_bridge.py — BrainBridge                     │
│    route_and_respond(text, lang)  → intent → handler → reply     │
│    Intents: "analysis" | "coach" | "dashboard" | "status"        │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                      SKILL LAYER (11 skills)                     │
│                                                                  │
│  Trading Decision Skills:                                        │
│    skills/scalping.py     — 5m breakout/pullback/volume          │
│    skills/intraday.py     — 15m/1h EMA+MACD+RSI+VWAP scoring    │
│    skills/prediction.py   — Daily swing + optional Claude overlay │
│    skills/chart_analysis.py — Claude vision (screenshot upload)  │
│                                                                  │
│  Risk & Filtering:                                               │
│    skills/risk_management.py — Position sizing, stop/target calc │
│    skills/trade_filter.py    — Mode-aware quality gate            │
│                                                                  │
│  Data & Indicators:                                              │
│    skills/market_data.py          — yfinance OHLCV               │
│    skills/technical_analysis_v2.py — 30+ indicators              │
│    skills/news.py                 — News article fetching         │
│                                                                  │
│  All decision skills output: DecisionOutput                      │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                     ENGINE LAYER (11 modules)                    │
│                                                                  │
│  Backtesting:     engine/backtest.py, engine/evaluation.py       │
│  Strategies:      engine/strategies.py (7 rule-based strategies) │
│  Multi-strategy:  engine/multi_strategy.py (parallel comparison) │
│  ML Signals:      engine/ml_signal.py (RandomForest + XGBoost)   │
│  Sentiment:       engine/sentiment.py (VADER + TextBlob)         │
│  Factors:         engine/factor_engine.py (6 alpha factors)      │
│  Multi-Agent:     engine/multi_agent_analysis.py (TradingAgents) │
│  Logging:         engine/decision_log.py (JSON persistence)      │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                  DATA & STATE LAYER                               │
│                                                                  │
│  Models:      models/decision.py    — DecisionOutput schema      │
│               models/confidence.py  — scale, risk, recommendation│
│  Bot:         bot/behavior.py       — trade tracking, streaks    │
│               bot/config.py         — user profile & preferences │
│               bot/arena.py          — 3-config comparison engine │
│  RAG:         rag/vector_store.py   — TF-IDF market notes        │
│  LLM:         llm/claude_client.py  — Claude API wrapper         │
│               llm/ui_analysis.py    — RAG-enhanced analysis      │
│  Persistence: memory_data/*.json    — sessions, voice, decisions │
│               bot/memory.json       — trade state                │
│               bot/config.json       — user preferences           │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│                    EXTERNAL SERVICES                              │
│                                                                  │
│  yfinance          — Market data (OHLCV, news, fundamentals)     │
│  Anthropic Claude  — AI reasoning, coaching, chart vision        │
│  OpenAI Whisper    — Speech-to-text transcription                │
│  OpenAI TTS-1-HD   — Text-to-speech response                    │
│  VADER / TextBlob  — Offline sentiment scoring                   │
│  TradingAgents     — Multi-agent debate framework (LangGraph)    │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow: Input to Decision

**Fast Analysis (Analyze button):**
```
User selects ticker + mode + timeframe
  → OrallexaBrain.run_for_mode()
    → ScalpingSkill / IntradaySkill / PredictionSkill
      → Fetch OHLCV via yfinance
      → Compute indicators (EMA, MACD, RSI, VWAP, ADX, Volume)
      → Score each dimension (trend, momentum, session, volume)
      → Apply quality filter
      → scale_confidence() caps at 82%
      → score_to_risk() derives risk from signal clarity
      → make_recommendation() generates action sentence
    → DecisionOutput returned
  → Render decision card in UI
```

**Deep Analysis (Multi-Agent button):**
```
User clicks Deep Analysis
  → OrallexaBrain.run_deep_analysis()
    → engine/multi_agent_analysis.py
      → TradingAgentsGraph.propagate(ticker, date)
        → Parallel: MarketAnalyst + NewsAnalyst + FundamentalsAnalyst
        → Bull vs Bear debate
        → Research Manager synthesis
        → Trader decision
        → Aggressive / Conservative / Neutral risk debate
        → Portfolio Manager final call
      → Signal: BUY / SELL / HOLD / OVERWEIGHT / UNDERWEIGHT
    → Map to DecisionOutput (BUY / SELL / WAIT)
    → scale_confidence() + make_recommendation()
  → Render decision card + 4 expandable report sections
```

**Voice Flow (Desktop Agent):**
```
User holds mic button → VoiceHandler captures audio (16kHz, 30s max)
  → User releases → Whisper transcribes → returns (text, language)
  → BrainBridge.route_and_respond(text, lang)
    → Keyword matching → intent: "analysis" | "coach" | "dashboard"
    → If analysis: OrallexaBrain.run_for_mode() → formatted reply
    → If coach: Claude API with conversation history → reply
    → If dashboard: open Streamlit in browser
  → TTSHandler.speak(reply, lang) → OpenAI TTS → audio playback
  → ChatPopover displays text + plays audio
```

---

## 3. Key Features Implemented

### Decision Engine
- **3 trading modes**: Scalping (5m), Intraday (15m/1h), Swing (1D)
- **Unified DecisionOutput schema** across all modes: decision, confidence, risk, signal_strength, recommendation, reasoning, probabilities
- **Confidence normalization**: linear cap at 82% (no analysis ever claims certainty)
- **Independent risk derivation**: risk is based on signal clarity + stale data, not confidence
- **Quality filter**: mode-aware gate that rejects low-quality setups before generating a decision
- **Actionable recommendation**: plain-English sentence on every decision ("Strong setup — trend, momentum, and volume aligned")

### Multi-Agent Deep Analysis
- **TradingAgents integration**: 3 parallel analysts (market, news, fundamentals) → Bull/Bear debate → Risk debate → final decision
- **LLM-powered**: Claude Sonnet + Claude Haiku via LangGraph pipeline
- **Full report output**: Market Report, News Report, Fundamentals Report, Investment Plan (each in expandable section)
- **Uses same data source** (yfinance) — no extra API keys for market data

### Desktop Floating Assistant
- **Cartoon bull character**: 128x128px chibi Wall Street bull, walks across screen bottom with 6-frame animation
- **Always-on-top**: transparent window, click to open chat
- **System tray**: right-click menu for mode switching, show/hide, quit
- **Chat popover**: dark-themed 340x480px floating window with message history

### Voice Interaction
- **Push-to-talk**: hold mic button → record → release → transcribe
- **Language auto-detection**: Whisper identifies language from speech
- **Language-matched response**: replies in the same language as the user (English, Chinese, etc.)
- **Text-to-speech**: OpenAI TTS-1-HD with language-specific voice selection (nova for Chinese, echo for English)

### Analysis Engine
- **7 rule-based strategies**: Double MA, MACD crossover, Bollinger breakout, RSI reversal, Trend momentum, Dual thrust, Alpha combo
- **ML models**: RandomForest + XGBoost trained on 33 technical features
- **6 alpha factors**: Momentum, Volatility, Volume, Trend, Reversal, Composite
- **Walk-forward validation**: expanding-window backtest for robustness
- **Sentiment analysis**: VADER + TextBlob with finance-specific lexicon

### Risk Management
- **Position sizing**: account-size-aware, risk-per-trade percentage
- **Stop-loss / take-profit**: ATR-based or percentage-based
- **Risk/reward ratio**: minimum 1.5:1 enforcement
- **Overtrading detection**: max trades per day limit
- **Bot arena**: 3-config comparison (Conservative / Moderate / Aggressive)

### Learning & Memory
- **Trade tracking**: BehaviorMemory records wins/losses/streaks
- **Adaptive aggressiveness**: +0.05 per 3-win streak, -0.05 per 2-loss streak (capped 0.0–1.0)
- **Bot profile**: user preferences for mode, timeframe, risk tolerance, skill weights
- **Session journal**: all interactions logged to memory_data/
- **Decision log**: every decision persisted with full metadata for future evaluation
- **RAG store**: TF-IDF vector store for market notes (manual or auto-added)

### Web UI (Streamlit)
- **Home**: 3-column cockpit with mode/TF selector, Decision/Chat/Chart tabs, bot profile panel
- **Today**: daily session entries + decision log review
- **Memory**: historical sessions, voice history, behavior insights
- **Analysis**: full multi-strategy backtest, ML comparison, factor decomposition, equity curves
- **Settings**: language, persona, voice, risk appetite, trading defaults

---

## 4. Decision System Design

This is the most important architectural piece. It ensures every analysis path produces the same structured output with clearly separated metrics.

### DecisionOutput Schema

```python
@dataclass
class DecisionOutput:
    decision:         "BUY" | "SELL" | "WAIT"
    confidence:       float    # 0.0–82.0%  (capped, never 100%)
    risk_level:       "LOW" | "MEDIUM" | "HIGH"
    reasoning:        list     # step-by-step explanation strings
    probabilities:    dict     # {"up": 0.6, "neutral": 0.2, "down": 0.2}
    source:           str      # "scalping", "intraday", "prediction", "multi_agent", "chart_analysis"
    signal_strength:  float    # 0–100  (raw composite score, unscaled)
    recommendation:   str      # "Strong setup — trend, momentum, and volume aligned"
```

### Three Separated Metrics

| Metric | What It Measures | Range | Derived From |
|---|---|---|---|
| **signal_strength** | How clear the technical picture is | 0–100 | Raw composite indicator score |
| **confidence** | How certain the system is about the outcome | 0–82% | `scale_confidence(signal_strength)` |
| **risk_level** | How dangerous the trade is | LOW / MEDIUM / HIGH | Signal clarity + stale data flag |

These are **independent**. A trade can have high signal strength (80/100) but HIGH risk (because market data is stale). Or moderate confidence (55%) with LOW risk (because the trend is clean even if not extreme).

### Confidence Scaling

```
scale_confidence(raw) = min(raw × 0.82, 82.0)

Examples:
  Raw 100 → 82.0%    (maximum possible — never shows 100%)
  Raw  75 → 61.5%
  Raw  50 → 41.0%
  Raw  25 → 20.5%
  Raw   0 →  0.0%
```

The 82% cap reflects a fundamental principle: **no technical analysis should claim certainty**. Even the strongest confluence of indicators cannot guarantee an outcome.

### Risk Derivation

```python
def score_to_risk(signal_strength, stale=False):
    if stale or signal_strength < 40:  return "HIGH"
    if signal_strength >= 68:          return "LOW"
    return "MEDIUM"
```

Risk is not the inverse of confidence. It answers: "How clear is the signal, and can I trust the data?" Stale data (market closed, delayed feed) always forces HIGH risk regardless of signal strength.

### Recommendation Generation

Every decision includes a plain-English action sentence:

| Scenario | Recommendation |
|---|---|
| BUY + LOW risk + high confidence | "Strong setup — trend, momentum, and volume aligned" |
| BUY + HIGH risk | "Weak setup — only consider with a very tight stop-loss" |
| BUY + moderate confidence | "Moderate setup — consider a half position with stop below support" |
| SELL + LOW risk | "Strong sell signal — trend and momentum bearish" |
| WAIT + low confidence | "No setup detected — stand aside" |
| WAIT + moderate confidence | "Conflicting signals — wait for a cleaner entry" |
| Any + stale data | "Market closed — verify signal at next open before acting" |

### Fast Analysis vs Deep Analysis

| Dimension | Fast Analysis (Analyze) | Deep Analysis (Multi-Agent) |
|---|---|---|
| **Time** | 2–5 seconds | 60–120 seconds |
| **Method** | Single skill (scalp/intraday/swing) | 3 parallel AI analysts + debate |
| **Indicators** | EMA, MACD, RSI, VWAP, ADX, Volume | + news, fundamentals, market structure |
| **LLM calls** | 0–1 (optional Claude overlay for swing) | 10+ (one per agent in the pipeline) |
| **Output** | DecisionOutput | DecisionOutput + 4 agent reports |
| **Best for** | Quick checks, active trading | Swing decisions, position evaluation |
| **Cost** | Free (technical) or ~$0.01 (with Claude) | ~$0.10–0.30 per analysis |

Both paths output the **same DecisionOutput schema**. The UI renders them identically — the decision card, probability bars, and recommendation look the same regardless of which button was clicked.

---

## 5. User Experience Flow

### Streamlit Web App

```
1. Open app → Home page loads with sidebar controls

2. User enters ticker (e.g., NVDA) and selects mode:
   └── Sidebar: Ticker input → Mode (scalp/intraday/swing) → Timeframe

3. User clicks "Analyze" or "Deep Analysis":
   ├── Analyze: 2-5 second spinner → decision card appears
   └── Deep Analysis: 60-120s spinner with info banner → decision card + reports

4. Decision card shows:
   ┌─────────────────────────────────────────────┐
   │ BUY                           NVDA · intraday/15m │
   │                                                    │
   │ "Strong setup — trend, momentum aligned"           │
   │                                                    │
   │ SIGNAL: 85/100  CONFIDENCE: 69%  RISK: LOW        │
   │                                                    │
   │ Up: ████████████████░░░░ 72%                       │
   │ Neutral: ████░░░░░░░░░░░░ 18%                     │
   │ Down: ██░░░░░░░░░░░░░░░░ 10%                      │
   │                                                    │
   │ ▸ Step-by-step reasoning                           │
   │ ▸ Risk Management (entry, stop, target, size)      │
   └────────────────────────────────────────────────────┘

5. User can switch to Coach Chat tab for conversational Q&A
6. User can upload a chart screenshot in Chart tab
7. User can speak via mic button (Whisper → Claude → TTS)
```

### Desktop Agent

```
1. Launch: python desktop_agent/main.py
   → Bull character appears at bottom of screen, walking left/right
   → System tray icon appears with right-click menu

2. User clicks the bull → Chat popover opens
   ├── Type a question → Send → Claude coach responds (text + TTS)
   └── Hold mic → speak → release → Whisper transcribes → Brain routes → response

3. Intent routing:
   ├── "Should I buy NVDA?" → analysis intent → OrallexaBrain → formatted result
   ├── "What is a stop loss?" → coach intent → Claude conversational reply
   └── "Open dashboard" → dashboard intent → opens Streamlit in browser

4. Responses are:
   ├── Displayed in chat popover (scrollable message history)
   └── Spoken aloud via TTS (language-matched: en→echo, zh→nova)

5. Tray menu allows: mode switching, show/hide, quit
```

---

## 6. Strengths of the Current System

### Compared to Typical Trading Bots
- **Doesn't execute trades** — it's a decision copilot, not an auto-trader. This is a feature: the human stays in the loop.
- **Explains every decision** with step-by-step reasoning. A bot just sends orders; OralleXa tells you *why*.
- **Adapts behavior** via trade tracking and aggressiveness adjustment. Most bots have static parameters.

### Compared to Simple LLM Tools
- **Grounded in real data** — every decision starts from actual OHLCV data with computed indicators, not LLM hallucination.
- **Structured output** — not free-form text. DecisionOutput is a standardized schema that can be rendered, logged, compared, and backtested.
- **Multi-modal input** — voice in any language, text, chart screenshots. Not just a chatbox.

### Compared to Quant Systems
- **Human-readable output** — no need to interpret Sharpe ratios or factor loadings. The system says "BUY, 69% confidence, low risk, trend and momentum aligned."
- **Multi-timeframe** — same system handles 5-minute scalps and daily swing trades, not just one strategy.
- **Voice-first** — can be used hands-free while watching charts. No terminal commands needed.
- **Multi-agent reasoning** — the Deep Analysis path runs 3 analysts + bull/bear debate + risk committee. This is closer to how a real trading desk operates than a single-model quant system.

### Technical Strengths
- **47 passing tests** with full coverage of the decision model, risk management, scalping skill, and behavior tracking
- **Unified schema** — every analysis path (scalp, intraday, swing, chart, multi-agent) returns the exact same DecisionOutput structure
- **Confidence cap at 82%** — the system never claims certainty, which is honest and prevents over-trading
- **Stale data detection** — automatically warns and adjusts risk when market data is old
- **Decision logging** — every decision is persisted with full metadata for future evaluation

---

## 7. Current Limitations / Gaps

### Data Limitations
- **No real-time streaming** — relies on yfinance polling, which has 15-30 minute delays for intraday data. During market hours, data can be stale.
- **No options / futures data** — equities only via yfinance. No support for derivatives analysis.
- **Sentiment is basic** — VADER + TextBlob with a custom lexicon. No social media scraping (Reddit, Twitter/X) beyond yfinance news.

### Decision System Gaps
- **Confidence heuristic is keyword-based** for Deep Analysis — `_estimate_confidence()` uses word matching ("strongly", "high confidence") rather than probabilistic calibration.
- **No backtesting of the decision engine itself** — the backtest system tests strategies (double MA, MACD crossover, etc.), but doesn't evaluate the intraday/scalping decision skill's historical accuracy.
- **Probabilities are estimates, not calibrated** — the up/neutral/down bars look precise but are computed from scoring heuristics, not from historical frequency data.

### UX Gaps
- **No mobile layout** — Streamlit's 3-column layout works on desktop but is cramped on tablets/phones.
- **Desktop agent is Windows-focused** — tested on Windows 11. macOS transparency and tkinter behavior may differ.
- **No real-time refresh** — the user must click "Analyze" each time. There is no auto-refresh or streaming update during market hours.
- **Chart analysis requires manual upload** — no automatic screenshot capture from broker platforms.

### Architecture Gaps
- **`app_ui.py` is 2,273 lines** — the main UI file is large. It works but is harder to navigate and modify.
- **No user authentication** — single-user system. The bot profile and memory are shared across all sessions.
- **RAG store is empty** — the infrastructure exists (TF-IDF retrieval), but `rag_data/market_notes.json` has no content by default.
- **Arena is not wired to the main UI** — `bot/arena.py` exists and works, but there's no "Arena" tab or comparison view in `app_ui.py`.
- **Decision log has no review UI** — decisions are logged to JSON but there's no interface to review historical accuracy or filter by ticker/mode.

### Production Readiness
- **No error retry logic** — if a yfinance call or Claude API call fails, the error is caught and displayed, but not retried.
- **No rate limiting** — repeated "Analyze" clicks send repeated API calls without throttling.
- **No API cost tracking** — Deep Analysis costs $0.10-0.30 per run. There's no visibility into accumulated cost.

---

## 8. Suggested Next Steps (Phased)

### Phase 1: Refinement (UX + Decision Clarity)

**Goal:** Make the existing system more polished and usable.

- [ ] Add auto-refresh during market hours (periodic re-analysis)
- [ ] Wire bot arena into the Home tab (show Conservative/Moderate/Aggressive side by side)
- [ ] Add a "Decision History" section to the Today tab (render `decision_log.json` as a table with filters)
- [ ] Improve intraday scoring: add time-of-day weighting (opening hour vs midday vs power hour)
- [ ] Add a loading progress indicator for Deep Analysis (estimated time remaining)

### Phase 2: Chart Analysis Enhancement

**Goal:** Make the chart upload feature more useful.

- [ ] Support multi-chart comparison (upload 2-3 timeframes of the same ticker)
- [ ] Add annotated chart output (Claude describes where support/resistance levels are)
- [ ] Connect chart analysis result to the decision card (same rendering pipeline)
- [ ] Consider browser extension or clipboard integration for faster chart capture

### Phase 3: User Memory + Personalization

**Goal:** The system should learn the user's patterns.

- [ ] Populate RAG store automatically from daily sessions (auto-add notes from each analysis)
- [ ] Track which recommendations the user acted on vs ignored
- [ ] Adjust confidence thresholds based on historical accuracy per mode
- [ ] Build a "Your Trading DNA" summary page (preferred setups, common mistakes, best/worst tickers)

### Phase 4: News + Context Integration

**Goal:** Enrich decisions with real-time news context.

- [ ] Auto-fetch news before every swing analysis (already partially wired)
- [ ] Add earnings calendar awareness (warn before earnings, adjust risk)
- [ ] Integrate macro indicators (VIX, DXY, yield curve) into swing mode scoring
- [ ] Show a "News Summary" badge on the decision card for swing mode

### Phase 5: Arena + Bot Comparison

**Goal:** Let the user evaluate different risk profiles against historical data.

- [ ] Build an Arena tab in `app_ui.py` showing 3 bot configs side by side
- [ ] Backtest each bot's decisions against historical data (using `decision_log.json`)
- [ ] Show cumulative P&L curves for each risk profile
- [ ] Allow custom bot profiles (not just the 3 presets)
- [ ] Implement `reflect_and_remember()` from TradingAgents to improve agent memory over time

---

## Appendix: Project Stats

| Metric | Value |
|---|---|
| Total Python files | 62 |
| Total lines of code | ~11,600 |
| Test functions | 47 (all passing) |
| Trading skills | 6 (scalp, intraday, prediction, chart, risk, filter) |
| Rule-based strategies | 7 |
| ML models | 2 (RandomForest, XGBoost) |
| Alpha factors | 6 |
| Technical indicators | 30+ |
| LLM integrations | Claude Sonnet (analysis, coaching, chart vision), Claude Haiku (multi-agent quick reasoning) |
| Voice support | Whisper (input) + TTS-1-HD (output), auto-detected language |
| Persistence files | 6 JSON files (sessions, voice, decisions, daily, bot memory, bot config) |
| Dependencies | 17 Python packages |
| API keys required | ANTHROPIC_API_KEY (required), OPENAI_API_KEY (voice features) |
| Max confidence | 82.0% (hard cap) |
| Stale data threshold | 30 min (scalp/intraday 15m), 90 min (intraday 1h) |
| Desktop agent sprites | 13 PNG frames + 1 GIF (128x128px cartoon bull) |

---

## Appendix: Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set API keys
export ANTHROPIC_API_KEY=your_key_here
export OPENAI_API_KEY=your_key_here    # for voice features

# Run web app
streamlit run app_ui.py

# Run desktop agent
python desktop_agent/main.py

# Run tests
python -m pytest tests/ -v
```

## Appendix: Environment Variables

| Variable | Required | Used By |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude analysis, coaching, chart vision, multi-agent |
| `OPENAI_API_KEY` | For voice | Whisper transcription, TTS-1-HD playback |
| `BULL_TICKER` | No (default: NVDA) | Desktop agent default ticker |
| `BULL_MODE` | No (default: intraday) | Desktop agent default mode |
| `BULL_TF` | No (default: 15m) | Desktop agent default timeframe |
