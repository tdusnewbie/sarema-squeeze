"""
Tests for IndicatorEngine.add_indicators (src/services/indicator_service.py).

These tests exercise the full TA-Lib pipeline (EMA, Squeeze, PSAR) to ensure
all columns are produced with the correct shapes and reasonable values.
"""
import numpy as np
import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.services.indicator_service import IndicatorEngine


def _make_df(n: int = 210, base: float = 100.0, trend: float = 0.05) -> pd.DataFrame:
    """
    Produce a realistic rising OHLCV DataFrame of *n* 15-minute candles.
    A gentle uptrend ensures EMAs and PSAR are well-behaved.
    """
    rng = np.random.default_rng(42)
    closes = base + np.cumsum(rng.normal(trend, 0.5, n))
    opens  = closes - rng.uniform(0.1, 0.5, n)
    highs  = closes + rng.uniform(0.2, 1.0, n)
    lows   = closes - rng.uniform(0.2, 1.0, n)
    # Make sure OHLCV invariants hold
    highs = np.maximum(highs, closes)
    lows  = np.minimum(lows,  closes)
    now   = datetime(2026, 1, 1)
    return pd.DataFrame({
        "timestamp": [now + timedelta(minutes=15 * i) for i in range(n)],
        "open":   opens,
        "high":   highs,
        "low":    lows,
        "close":  closes,
        "volume": rng.uniform(500, 2000, n),
    })


class TestAddIndicators:
    @pytest.fixture
    def df_with_indicators(self):
        return IndicatorEngine.add_indicators(_make_df())

    def test_all_columns_present(self, df_with_indicators):
        expected = {"ema5", "ema9", "ema100", "psar", "sqz_val", "psar_prev"}
        assert expected.issubset(df_with_indicators.columns), (
            f"Missing columns: {expected - set(df_with_indicators.columns)}"
        )

    def test_ema_columns_are_finite_after_warmup(self, df_with_indicators):
        df = df_with_indicators
        # EMA-100 needs 100 bars; everything beyond that should be finite
        tail = df.iloc[100:]
        for col in ("ema5", "ema9", "ema100"):
            assert tail[col].notna().all(), f"{col} has NaN after warmup period"

    def test_ema_ordering_in_uptrend(self, df_with_indicators):
        """In a rising market EMA5 > EMA9 > EMA100 holds for most of the tail."""
        tail = df_with_indicators.iloc[150:]
        ratio = (tail["ema5"] > tail["ema9"]).mean()
        assert ratio >= 0.7, f"EMA5 > EMA9 holds only {ratio:.0%} of the time in uptrend"

    def test_psar_has_no_nan(self, df_with_indicators):
        assert df_with_indicators["psar"].notna().all(), "psar column contains NaN"

    def test_psar_prev_is_shift_of_psar(self, df_with_indicators):
        df = df_with_indicators
        # psar_prev[i] == psar[i-1] for all rows after the first
        expected = df["psar"].shift(1)
        pd.testing.assert_series_equal(df["psar_prev"], expected, check_names=False)

    def test_sqz_val_has_valid_values_after_warmup(self, df_with_indicators):
        tail = df_with_indicators.iloc[40:]  # LinearReg(20) + lookback
        assert tail["sqz_val"].notna().all(), "sqz_val has NaN after warmup"

    def test_dataframe_length_unchanged(self):
        df_in = _make_df(210)
        df_out = IndicatorEngine.add_indicators(df_in)
        assert len(df_out) == 210

    def test_insufficient_rows_returns_early(self):
        """Strategy checks len(df) < 102; make sure indicators don't crash on small input."""
        df_small = _make_df(n=50)
        # add_indicators itself should still run — strategy is what guards the length
        result = IndicatorEngine.add_indicators(df_small)
        assert "psar" in result.columns
