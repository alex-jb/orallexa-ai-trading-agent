from core.logger import get_logger
from skills.market_data import MarketDataSkill

logger = get_logger("brain")
from skills.technical_analysis_v2 import TechnicalAnalysisSkillV2 as TechnicalAnalysisSkill
from engine.backtest import simple_backtest
from engine.evaluation import evaluate
from engine.multi_strategy import run_multi_strategy_analysis
from engine.ml_signal import run_ml_analysis
from engine.sentiment import analyze_ticker_sentiment
from llm.claude_client import real_llm_analysis


class OrallexaBrain:
    def __init__(self, ticker):
        self.ticker = ticker

    def _prepare_data(self):
        data = MarketDataSkill(self.ticker).execute()
        ta = TechnicalAnalysisSkill(data).add_indicators()
        ta = ta.dropna().copy()
        return ta

    def _single_split(self, df, train_ratio=0.7):
        split_idx = int(len(df) * train_ratio)
        train_df = df.iloc[:split_idx].copy()
        test_df = df.iloc[split_idx:].copy()
        return train_df, test_df

    def _safe_summary_from_df(self, df):
        latest = df.iloc[-1]
        close_col = "Close" if "Close" in df.columns else "Adj Close"

        def safe_float(x):
            try:
                if x != x:
                    return None
                return float(x)
            except Exception:
                return None

        close_val = safe_float(latest.get(close_col))
        prev_close = safe_float(df[close_col].iloc[-2]) if len(df) >= 2 else None
        change_pct = round((close_val / prev_close - 1) * 100, 2) if close_val and prev_close else None

        return {
            "close":        close_val,
            "change_pct":   change_pct,
            "ma20":         safe_float(latest.get("MA20")),
            "ma50":         safe_float(latest.get("MA50")),
            "rsi":          safe_float(latest.get("RSI")),
            "macd":         safe_float(latest.get("MACD")),
            "macd_hist":    safe_float(latest.get("MACD_Hist")),
            "bb_pct":       safe_float(latest.get("BB_Pct")),
            "bb_upper":     safe_float(latest.get("BB_Upper")),
            "bb_lower":     safe_float(latest.get("BB_Lower")),
            "atr_pct":      safe_float(latest.get("ATR_Pct")),
            "adx":          safe_float(latest.get("ADX")),
            "volume_ratio": safe_float(latest.get("Volume_Ratio")),
        }

    def run_train(self, params=None, train_ratio=0.7,
                  transaction_cost=0.001, slippage=0.001):
        ta = self._prepare_data()
        train_df, _ = self._single_split(ta, train_ratio=train_ratio)
        bt_train = simple_backtest(train_df, params=params, debug=True,
                                   transaction_cost=transaction_cost, slippage=slippage)
        train_metrics = evaluate(bt_train)
        summary = self._safe_summary_from_df(train_df)
        try:
            ai_output = real_llm_analysis(summary)
        except Exception as e:
            logger.error("LLM analysis failed for %s: %s", self.ticker, e)
            ai_output = f"LLM failed: {str(e)}"
        return summary, train_metrics, ai_output

    def evaluate_test(self, params=None, train_ratio=0.7,
                      transaction_cost=0.001, slippage=0.001):
        ta = self._prepare_data()
        _, test_df = self._single_split(ta, train_ratio=train_ratio)
        bt_test = simple_backtest(test_df, params=params, debug=False,
                                  transaction_cost=transaction_cost, slippage=slippage)
        return bt_test, evaluate(bt_test)

    def evaluate_walk_forward(self, params=None, train_ratio=0.6,
                              test_ratio=0.2, step_ratio=0.1,
                              transaction_cost=0.001, slippage=0.001):
        ta = self._prepare_data()
        n = len(ta)
        train_size = int(n * train_ratio)
        test_size  = int(n * test_ratio)
        step_size  = max(1, int(n * step_ratio))
        windows = []
        start = 0
        while start + train_size + test_size <= n:
            train_df = ta.iloc[start:start + train_size].copy()
            test_df  = ta.iloc[start + train_size:start + train_size + test_size].copy()
            bt_train = simple_backtest(train_df, params=params, debug=False,
                                       transaction_cost=transaction_cost, slippage=slippage)
            bt_test  = simple_backtest(test_df, params=params, debug=False,
                                       transaction_cost=transaction_cost, slippage=slippage)
            windows.append({
                "train_start": int(start), "train_end": int(start + train_size),
                "test_start":  int(start + train_size),
                "test_end":    int(start + train_size + test_size),
                "train_metrics": evaluate(bt_train),
                "test_metrics":  evaluate(bt_test),
            })
            start += step_size

        if not windows:
            return {"num_windows": 0, "avg_test_sharpe": 0.0,
                    "avg_test_return": 0.0, "avg_test_drawdown": 0.0,
                    "avg_test_trades": 0.0, "windows": []}

        avg = lambda key: sum(w["test_metrics"].get(key, 0.0) for w in windows) / len(windows)
        return {"num_windows": len(windows), "avg_test_sharpe": avg("sharpe"),
                "avg_test_return": avg("total_return"),
                "avg_test_drawdown": avg("max_drawdown"),
                "avg_test_trades": avg("num_trades"), "windows": windows}

    def evaluate_multi_strategy(self, train_ratio=0.7,
                                transaction_cost=0.001, slippage=0.001):
        """Run all 6 rule-based strategies and return comparison."""
        ta = self._prepare_data()
        train_df, test_df = self._single_split(ta, train_ratio=train_ratio)
        return run_multi_strategy_analysis(
            train_df=train_df, test_df=test_df, ticker=self.ticker,
            transaction_cost=transaction_cost, slippage=slippage)

    def evaluate_ml(self, train_ratio=0.7,
                    transaction_cost=0.001, slippage=0.001):
        """Run ML models (RF, XGBoost, LR) and return comparison vs buy-and-hold."""
        ta = self._prepare_data()
        train_df, test_df = self._single_split(ta, train_ratio=train_ratio)
        return run_ml_analysis(
            train_df=train_df, test_df=test_df, ticker=self.ticker,
            transaction_cost=transaction_cost, slippage=slippage)

    def evaluate_sentiment(self, rag_store=None, news_skill=None):
        """Score news sentiment for this ticker."""
        return analyze_ticker_sentiment(
            ticker=self.ticker, rag_store=rag_store, news_skill=news_skill)

    def run_for_mode(
        self,
        mode: str,
        timeframe: str = "",
        use_claude: bool = True,
        rag_context: str = "",
        use_debate: bool = False,
        use_langgraph: bool = False,
        portfolio: list | None = None,
        portfolio_value: float | None = None,
        recent_decisions: list | None = None,
        pm_rules: dict | None = None,
    ):
        """
        Unified entry point. Routes to the correct skill based on mode.

        mode:
          "scalp"    → ScalpingSkill  (1m / 5m)
          "intraday" → IntradaySkill  (15m / 1h)
          "swing"    → PredictionSkill (1D)

        use_debate: if True, runs a lightweight Bull/Bear debate after initial signal.
        use_langgraph: if True, uses LangGraph debate pipeline instead of direct calls.

        Portfolio Manager gate (opt-in): if `portfolio` + `portfolio_value` are
        provided, the final decision is run through engine.portfolio_manager
        (concentration, sector, streak, sizing). Rejections downgrade the
        decision to WAIT with a reason; warnings are appended to reasoning.

        Returns DecisionOutput.
        """
        from models.decision import DecisionOutput
        from models.confidence import guard_decision
        try:
            if mode == "scalp":
                result = self.run_scalping()
            elif mode == "intraday":
                tf = timeframe if timeframe in ("15m", "1h") else "15m"
                result = self.run_intraday(tf)
            elif mode == "swing":
                result = self.run_prediction(use_claude=use_claude, rag_context=rag_context)
            else:
                result = self.run_prediction(use_claude=use_claude, rag_context=rag_context)

            # Optional adversarial debate (skip if initial decision is WAIT)
            if use_debate and result.decision != "WAIT":
                try:
                    summary = self._safe_summary_from_df(self._prepare_data())
                    if use_langgraph:
                        from llm.debate_graph import run_debate_graph
                        result = run_debate_graph(
                            initial_decision=result,
                            summary=summary,
                            ticker=self.ticker,
                            rag_context=rag_context,
                        )
                    else:
                        from llm.debate import run_lightweight_debate
                        result = run_lightweight_debate(
                            initial_decision=result,
                            summary=summary,
                            ticker=self.ticker,
                            rag_context=rag_context,
                        )
                except Exception as e:
                    logger.warning("Debate skipped for %s: %s", self.ticker, e)

            result = guard_decision(result)

            # Portfolio Manager gate (opt-in final layer)
            if portfolio is not None and portfolio_value:
                result = self._apply_portfolio_manager(
                    result,
                    portfolio=portfolio,
                    portfolio_value=portfolio_value,
                    recent_decisions=recent_decisions or [],
                    rules=pm_rules,
                )

            return result
        except Exception as e:
            from models.confidence import make_recommendation
            return DecisionOutput(
                decision="WAIT",
                confidence=0.0,
                risk_level="HIGH",
                reasoning=[f"run_for_mode({mode}/{timeframe}) failed: {str(e)}"],
                probabilities={"up": 0.33, "down": 0.33, "neutral": 0.34},
                source=mode,
                signal_strength=0.0,
                recommendation=make_recommendation("WAIT", 0.0, "HIGH"),
            )

    def _apply_portfolio_manager(
        self,
        decision,
        *,
        portfolio: list,
        portfolio_value: float,
        recent_decisions: list,
        rules: dict | None = None,
    ):
        """
        Run the decision through engine.portfolio_manager. Mutates the
        DecisionOutput with the approval outcome — rejection downgrades to
        WAIT, warnings append to reasoning, scaled_position_pct is surfaced
        via the .extra dict so downstream consumers (API, UI) see it.
        """
        try:
            from engine.portfolio_manager import approve_decision
            verdict = approve_decision(
                ticker=self.ticker,
                decision={
                    "decision": decision.decision,
                    "confidence": int(decision.confidence * 100)
                        if decision.confidence <= 1 else int(decision.confidence),
                    "signal_strength": int(decision.signal_strength * 100)
                        if decision.signal_strength <= 1 else int(decision.signal_strength),
                },
                portfolio=portfolio,
                portfolio_value=portfolio_value,
                recent_decisions=recent_decisions,
                rules=rules,
            )
            if not verdict["approved"]:
                decision.decision = "WAIT"
                decision.reasoning = (decision.reasoning or []) + [
                    f"Portfolio Manager rejected: {verdict['reason']}"
                ]
            elif verdict.get("warnings"):
                decision.reasoning = (decision.reasoning or []) + [
                    f"PM warning: {w}" for w in verdict["warnings"]
                ]
            # Surface PM metadata
            if hasattr(decision, "extra") and isinstance(decision.extra, dict):
                decision.extra["portfolio_manager"] = verdict
        except Exception as e:
            logger.warning("Portfolio manager check failed for %s: %s", self.ticker, e)
        return decision

    def run_scalping(self):
        """Run 5-minute scalping analysis. Returns DecisionOutput."""
        from skills.scalping import ScalpingSkill
        from models.decision import DecisionOutput
        try:
            return ScalpingSkill(self.ticker).execute()
        except Exception as e:
            from models.confidence import make_recommendation
            return DecisionOutput(
                decision="WAIT",
                confidence=0.0,
                risk_level="HIGH",
                reasoning=[f"Scalping analysis failed: {str(e)}"],
                probabilities={"up": 0.33, "down": 0.33, "neutral": 0.34},
                source="scalping",
                signal_strength=0.0,
                recommendation=make_recommendation("WAIT", 0.0, "HIGH"),
            )

    def run_intraday(self, timeframe: str = "15m"):
        """Run 15m/1h intraday analysis. Returns DecisionOutput."""
        from skills.intraday import IntradaySkill
        from models.decision import DecisionOutput
        try:
            return IntradaySkill(self.ticker).execute(interval=timeframe)
        except Exception as e:
            from models.confidence import make_recommendation
            return DecisionOutput(
                decision="WAIT",
                confidence=0.0,
                risk_level="HIGH",
                reasoning=[f"Intraday analysis ({timeframe}) failed: {str(e)}"],
                probabilities={"up": 0.33, "down": 0.33, "neutral": 0.34},
                source="intraday",
                signal_strength=0.0,
                recommendation=make_recommendation("WAIT", 0.0, "HIGH"),
            )

    def run_prediction(
        self,
        use_claude: bool = True,
        rag_context: str = "",
        sentiment_score: float = None,
        mode: str = "swing",
    ):
        """Run probability-based prediction. Returns DecisionOutput."""
        from skills.prediction import PredictionSkill
        from models.decision import DecisionOutput
        try:
            return PredictionSkill(self.ticker).execute(
                use_claude=use_claude,
                rag_context=rag_context,
                sentiment_score=sentiment_score,
                mode=mode,
            )
        except Exception as e:
            from models.confidence import make_recommendation
            return DecisionOutput(
                decision="WAIT",
                confidence=0.0,
                risk_level="HIGH",
                reasoning=[f"Prediction failed: {str(e)}"],
                probabilities={"up": 0.33, "down": 0.33, "neutral": 0.34},
                source="prediction",
                signal_strength=0.0,
                recommendation=make_recommendation("WAIT", 0.0, "HIGH"),
            )

    def run_deep_analysis(
        self,
        trade_date: str = None,
        analysts: list = None,
        include_ml_evidence: bool = True,
    ):
        """
        Run multi-agent analysis pipeline (market + news + ML + debate + risk).
        Returns a MultiAgentResult whose .decision_output is a DecisionOutput.

        Fully self-contained — no external framework dependencies.
        """
        from engine.multi_agent_analysis import run_multi_agent_analysis

        return run_multi_agent_analysis(
            ticker=self.ticker,
            trade_date=trade_date,
            brain=self,
        )

    def run(self, params=None, train_ratio=0.7,
            transaction_cost=0.001, slippage=0.001):
        return self.run_train(params=params, train_ratio=train_ratio,
                              transaction_cost=transaction_cost, slippage=slippage)

