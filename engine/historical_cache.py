"""
engine/historical_cache.py
──────────────────────────────────────────────────────────────────
Cache layer for historical market data so walk-forward backtests of
the 8-source fusion can use REAL inputs instead of synthetic ones
(see scripts/backtest_fusion_partial.py for why we needed synthetic).

Schema lives at memory_data/historical_cache/<source>/<ticker>.parquet
(parquet for fast row-group reads + per-source isolation).

Sources covered today:
  - prices:       OHLCV daily bars from yfinance
  - earnings:     past earnings dates + EPS surprise from yfinance
  - options_flow: SNAPSHOT only — yfinance only returns current chains,
                  so backfill is point-in-time. Document this honestly
                  in the metadata so backtests can flag affected dates.

Sources NOT cacheable from public sources:
  - social_sentiment:   Reddit search API only returns recent posts.
                        We'd need to hit pushshift / commoncrawl to
                        backfill historical posts. Out of scope here.
  - prediction_markets: Polymarket Gamma returns current markets only.
                        Historical resolved markets would need a paid
                        API or direct on-chain reads. Out of scope.
  - news:               News provider RSS feeds drop articles after
                        ~7-30 days. Backfill needs paid news archive
                        APIs (Bloomberg, FT, etc).

The schema is built so adding the unsupported sources later is purely
additive — just create a new <source>/ subdirectory.

Usage:
    from engine.historical_cache import HistoricalCache
    cache = HistoricalCache()
    cache.populate_prices("NVDA", start="2024-01-01", end="2026-04-25")
    df = cache.load_prices("NVDA")            # pandas DataFrame
    earnings = cache.load_earnings("NVDA")    # list of dicts
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = _ROOT / "memory_data" / "historical_cache"
_METADATA_FILENAME = "_meta.json"


class HistoricalCache:
    """File-backed cache for historical market data."""

    def __init__(self, base_dir: Optional[Path] = None):
        self._base = base_dir or _CACHE_DIR
        self._base.mkdir(parents=True, exist_ok=True)

    # ── Paths ─────────────────────────────────────────────────────────────

    def _source_dir(self, source: str) -> Path:
        d = self._base / source
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _file_for(self, source: str, ticker: str, ext: str = "parquet") -> Path:
        return self._source_dir(source) / f"{ticker.upper()}.{ext}"

    def _meta_path(self) -> Path:
        return self._base / _METADATA_FILENAME

    # ── Metadata (per-source freshness ledger) ────────────────────────────

    def _load_meta(self) -> dict:
        path = self._meta_path()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_meta(self, meta: dict) -> None:
        try:
            self._meta_path().write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as e:
            logger.warning("Failed to save cache meta: %s", e)

    def _record_freshness(self, source: str, ticker: str, **fields) -> None:
        meta = self._load_meta()
        meta.setdefault(source, {})[ticker.upper()] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **fields,
        }
        self._save_meta(meta)

    # ── Prices (daily OHLCV) ──────────────────────────────────────────────

    def populate_prices(
        self,
        ticker: str,
        *,
        start: str,
        end: Optional[str] = None,
    ) -> int:
        """
        Pull daily OHLCV from yfinance for [start, end], store as parquet.
        Returns the number of bars cached.
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed — cannot populate prices")
            return 0
        end = end or datetime.now().strftime("%Y-%m-%d")
        try:
            df = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        except Exception as e:
            logger.warning("yfinance fetch failed for %s: %s", ticker, e)
            return 0
        if df.empty:
            return 0
        path = self._file_for("prices", ticker)
        try:
            df.to_parquet(path)
        except Exception as e:
            logger.warning("Parquet write failed (%s) — falling back to CSV", e)
            df.to_csv(path.with_suffix(".csv"))
        self._record_freshness("prices", ticker, start=start, end=end, bars=len(df))
        return len(df)

    def load_prices(self, ticker: str):
        """Return cached price DataFrame, or None if unavailable."""
        try:
            import pandas as pd
        except ImportError:
            return None
        path = self._file_for("prices", ticker)
        if path.exists():
            try:
                return pd.read_parquet(path)
            except Exception:
                pass
        csv_path = path.with_suffix(".csv")
        if csv_path.exists():
            try:
                return pd.read_csv(csv_path, index_col=0, parse_dates=True)
            except Exception:
                pass
        return None

    # ── Earnings ──────────────────────────────────────────────────────────

    def populate_earnings(self, ticker: str) -> int:
        """Cache the full earnings_dates DataFrame as JSON for ease of read."""
        try:
            import yfinance as yf
            import pandas as pd
        except ImportError:
            return 0
        try:
            ed = yf.Ticker(ticker).earnings_dates
        except Exception as e:
            logger.warning("Earnings fetch failed for %s: %s", ticker, e)
            return 0
        if ed is None or (hasattr(ed, "empty") and ed.empty):
            return 0
        rows = []
        for ts, row in ed.iterrows():
            rows.append({
                "date": str(ts),
                "eps_estimate": (
                    float(row.get("EPS Estimate"))
                    if row.get("EPS Estimate") is not None
                    and str(row.get("EPS Estimate")) != "nan" else None
                ),
                "reported_eps": (
                    float(row.get("Reported EPS"))
                    if row.get("Reported EPS") is not None
                    and str(row.get("Reported EPS")) != "nan" else None
                ),
                "surprise_pct": (
                    float(row.get("Surprise(%)"))
                    if row.get("Surprise(%)") is not None
                    and str(row.get("Surprise(%)")) != "nan" else None
                ),
            })
        path = self._file_for("earnings", ticker, ext="json")
        try:
            path.write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        except OSError as e:
            logger.warning("Earnings cache write failed: %s", e)
            return 0
        self._record_freshness("earnings", ticker, n_events=len(rows))
        return len(rows)

    def load_earnings(self, ticker: str) -> list[dict]:
        path = self._file_for("earnings", ticker, ext="json")
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []

    # ── Options snapshot (point-in-time only — see module docstring) ──────

    def populate_options_snapshot(self, ticker: str) -> bool:
        """Cache the current options chain. NOT a backfill — see docstring."""
        try:
            import yfinance as yf
            import pandas as pd  # noqa: F401
        except ImportError:
            return False
        try:
            tk = yf.Ticker(ticker)
            expirations = list(tk.options or [])
            if not expirations:
                return False
            chains = {}
            for exp in expirations[:5]:   # cap to avoid massive payloads
                try:
                    ch = tk.option_chain(exp)
                    chains[exp] = {
                        "calls": ch.calls.to_dict(orient="records"),
                        "puts": ch.puts.to_dict(orient="records"),
                    }
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Options snapshot failed for %s: %s", ticker, e)
            return False
        path = self._file_for("options_flow", ticker, ext="json")
        try:
            path.write_text(json.dumps(chains, default=str, indent=2),
                            encoding="utf-8")
        except OSError as e:
            logger.warning("Options snapshot write failed: %s", e)
            return False
        self._record_freshness(
            "options_flow", ticker,
            n_expirations=len(chains),
            note="snapshot only — yfinance does not provide historical chains",
        )
        return True

    # ── Cache-aware high-level fetchers ───────────────────────────────────
    # These are the methods production paths should call. They serve cache
    # when fresh + sufficient, else fall through to a yfinance round-trip
    # and write the result back. Returns the same shape yfinance would.

    def _is_fresh(self, source: str, ticker: str, max_age_hours: float) -> bool:
        meta = self._load_meta().get(source, {}).get(ticker.upper())
        if not meta or not meta.get("updated_at"):
            return False
        try:
            updated = datetime.fromisoformat(meta["updated_at"].replace("Z", "+00:00"))
        except ValueError:
            return False
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - updated).total_seconds()
        return age_seconds < max_age_hours * 3600

    def _covers_range(self, source: str, ticker: str, start: str, end: str) -> bool:
        """Is the cached range a superset of [start, end]?"""
        meta = self._load_meta().get(source, {}).get(ticker.upper())
        if not meta:
            return False
        cached_start = meta.get("start")
        cached_end = meta.get("end")
        if not (cached_start and cached_end):
            return False
        return cached_start <= start and cached_end >= end

    def get_prices(
        self,
        ticker: str,
        *,
        start: str,
        end: Optional[str] = None,
        max_age_hours: float = 24.0,
    ):
        """
        Cache-aware price fetch. Returns a pandas DataFrame or None.

        Serves the cached parquet when:
          (1) the cache is fresher than `max_age_hours`, AND
          (2) the cached range is a superset of [start, end].

        Otherwise fetches from yfinance, writes the result, then serves it.
        Failures (network, parquet) leak as None — callers should fall back
        to their existing path.
        """
        end = end or datetime.now().strftime("%Y-%m-%d")
        if self._is_fresh("prices", ticker, max_age_hours) and self._covers_range("prices", ticker, start, end):
            cached = self.load_prices(ticker)
            if cached is not None and not cached.empty:
                return cached
        n = self.populate_prices(ticker, start=start, end=end)
        if n == 0:
            return None
        return self.load_prices(ticker)

    def populate_earnings_dates_raw(self, ticker: str) -> int:
        """
        Cache the *raw* yfinance earnings_dates DataFrame. Different from
        populate_earnings (simplified JSON) — this preserves all columns
        (EPS Estimate, Reported EPS, Surprise(%)) and the DatetimeIndex,
        so downstream stats code can use it without reshaping.
        """
        try:
            import yfinance as yf
            import pandas as pd  # noqa: F401
        except ImportError:
            return 0
        try:
            ed = yf.Ticker(ticker).earnings_dates
        except Exception as e:
            logger.warning("earnings_dates fetch failed for %s: %s", ticker, e)
            return 0
        if ed is None or ed.empty:
            return 0
        path = self._file_for("earnings_raw", ticker)
        try:
            ed.to_parquet(path)
        except Exception as e:
            logger.warning("Parquet write failed (%s) — falling back to CSV", e)
            ed.to_csv(path.with_suffix(".csv"))
        self._record_freshness("earnings_raw", ticker, n_events=len(ed))
        return len(ed)

    def load_earnings_dates_raw(self, ticker: str):
        try:
            import pandas as pd
        except ImportError:
            return None
        path = self._file_for("earnings_raw", ticker)
        if path.exists():
            try:
                return pd.read_parquet(path)
            except Exception:
                pass
        csv_path = path.with_suffix(".csv")
        if csv_path.exists():
            try:
                return pd.read_csv(csv_path, index_col=0, parse_dates=True)
            except Exception:
                pass
        return None

    def get_earnings_dates(self, ticker: str, *, max_age_hours: float = 24.0):
        """
        Cache-aware earnings_dates fetch. Returns the raw yfinance DataFrame.

        Serves cache when fresher than `max_age_hours`. Earnings dates only
        change ~quarterly, so 24h is plenty conservative for most consumers.
        Returns None on all-source failure.
        """
        if self._is_fresh("earnings_raw", ticker, max_age_hours):
            cached = self.load_earnings_dates_raw(ticker)
            if cached is not None and not cached.empty:
                return cached
        if self.populate_earnings_dates_raw(ticker) == 0:
            return None
        return self.load_earnings_dates_raw(ticker)

    # ── Status / inspection ───────────────────────────────────────────────

    def status(self) -> dict:
        """Return a flat per-(source, ticker) summary of what's cached."""
        return self._load_meta()

    def has(self, source: str, ticker: str) -> bool:
        """Is there a cache entry for (source, ticker)?"""
        meta = self._load_meta()
        return (
            source in meta
            and ticker.upper() in meta[source]
        )


# ── Module-level convenience -------------------------------------------------
# A single shared instance is good enough for production (the cache is just a
# directory). Tests should construct their own instance with a tmp_path base.

_DEFAULT_INSTANCE: Optional[HistoricalCache] = None


def get_default_cache() -> HistoricalCache:
    """Module-level singleton for callers that don't want to manage state."""
    global _DEFAULT_INSTANCE
    if _DEFAULT_INSTANCE is None:
        _DEFAULT_INSTANCE = HistoricalCache()
    return _DEFAULT_INSTANCE


def cache_enabled() -> bool:
    """Read-time toggle. CI keeps cache off so tests stay deterministic."""
    import os
    return os.environ.get("ORALLEXA_USE_CACHE", "").lower() in ("1", "true", "yes")
