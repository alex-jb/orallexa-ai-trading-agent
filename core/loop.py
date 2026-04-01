import os
import json
import copy


class StrategyLoop:
    def __init__(self, brain):
        self.brain = brain

    def run(
        self,
        iterations=5,
        save_prefix=None,
        train_ratio=0.7,
        wf_train_ratio=0.6,
        wf_test_ratio=0.2,
        wf_step_ratio=0.1,
        transaction_cost=0.001,   # ← added (was missing before)
        slippage=0.001,            # ← added (was missing before)
    ):
        history = []

        params = {
            "rsi_min":    30,
            "rsi_max":    65,
            "stop_loss":  0.04,
            "take_profit":0.10
        }

        best_params        = copy.deepcopy(params)
        best_train_sharpe  = float("-inf")
        best_result        = None

        for i in range(iterations):
            print(f"\n=== Iteration {i + 1} ===")

            summary, train_metrics, _ = self.brain.run(
                params=params,
                train_ratio=train_ratio
            )

            train_sharpe = train_metrics.get("sharpe", 0.0)

            if train_sharpe > best_train_sharpe:
                best_train_sharpe = train_sharpe

                _, test_metrics = self.brain.evaluate_test(
                    params=params,
                    train_ratio=train_ratio,
                    transaction_cost=transaction_cost,
                    slippage=slippage,
                )

                wf_metrics = self.brain.evaluate_walk_forward(
                    params=params,
                    train_ratio=wf_train_ratio,
                    test_ratio=wf_test_ratio,
                    step_ratio=wf_step_ratio,
                    transaction_cost=transaction_cost,
                    slippage=slippage,
                )

                best_params = copy.deepcopy(params)
                best_result = {
                    "iteration":           i + 1,
                    "summary":             summary,
                    "train_metrics":       train_metrics,
                    "test_metrics":        test_metrics,
                    "walk_forward_metrics":wf_metrics,
                }

            history.append({
                "iteration":    i + 1,
                "train_metrics":train_metrics,
                "params":       copy.deepcopy(params)
            })

        # ── NEW: run all 6 strategies and find the best ──────────────────────
        print(f"\n=== Multi-Strategy Analysis for {self.brain.ticker} ===")
        try:
            multi_strategy_result = self.brain.evaluate_multi_strategy(
                train_ratio=train_ratio,
                transaction_cost=transaction_cost,
                slippage=slippage,
            )
            best_strategy_name = multi_strategy_result.get("best_strategy", "N/A")
            best_strategy_sharpe = multi_strategy_result.get("test_metrics", {}).get("sharpe", 0.0)
            print(f"Best strategy: {best_strategy_name} (test Sharpe: {best_strategy_sharpe:.3f})")

            # Print ranking
            for name, sharpe in multi_strategy_result.get("ranking", []):
                print(f"  {name:25s}  {sharpe:+.3f}")

        except Exception as e:
            print(f"Multi-strategy analysis failed: {e}")
            multi_strategy_result = {}
        # ─────────────────────────────────────────────────────────────────────

        # ── NEW: ML signal analysis ─────────────────────────────────────────
        print(f"\n=== ML Signal Analysis for {self.brain.ticker} ===")
        try:
            ml_result = self.brain.evaluate_ml(
                train_ratio=train_ratio,
                transaction_cost=transaction_cost,
                slippage=slippage,
            )
            best_ml = ml_result.get("best_model", "N/A")
            best_ml_sharpe = ml_result.get("best_metrics", {}).get("sharpe", 0.0)
            print(f"Best ML model: {best_ml} (test Sharpe: {best_ml_sharpe:.3f})")
        except Exception as e:
            print(f"ML analysis failed: {e}")
            ml_result = {}
        # ─────────────────────────────────────────────────────────────────────

        # ── NEW: Sentiment analysis ──────────────────────────────────────────
        print(f"\n=== Sentiment Analysis for {self.brain.ticker} ===")
        try:
            sentiment_result = self.brain.evaluate_sentiment()
            print(f"Sentiment: {sentiment_result.get('sentiment_label','N/A')} "
                  f"(score: {sentiment_result.get('avg_compound',0):.3f})")
        except Exception as e:
            print(f"Sentiment analysis failed: {e}")
            sentiment_result = {}
        # ─────────────────────────────────────────────────────────────────────

        result_package = {
            "ticker":             self.brain.ticker,
            "best_train_sharpe":  best_train_sharpe,
            "best_params":        best_params,
            "best_result":        best_result,
            "history":            history,
            "multi_strategy":     multi_strategy_result,
            "ml_analysis":        ml_result,        # ← new
            "sentiment":          sentiment_result,  # ← new
        }

        if save_prefix:
            os.makedirs("results", exist_ok=True)
            path = f"results/{save_prefix}_{self.brain.ticker}.json"
            # multi_strategy contains DataFrames — exclude from JSON save
            save_package = {k: v for k, v in result_package.items()
                            if k != "multi_strategy"}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(save_package, f, indent=2)

        return result_package
