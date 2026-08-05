"""
Tests for the custom Parabolic SAR implementation in IndicatorEngine.

Focus: verify that PSAR flips are detected on the SAME bar as the reversal
(matching TradingView's behavior), not 1 candle later (TA-Lib behaviour).
"""
import numpy as np
import pytest
from src.services.indicator_service import IndicatorEngine


def _make_bull_run(n: int = 20, base: float = 100.0, step: float = 1.0):
    """Return (high, low) for a clean uptrend so PSAR settles as bullish."""
    high = np.array([base + i * step + 2 for i in range(n)], dtype=float)
    low  = np.array([base + i * step - 2 for i in range(n)], dtype=float)
    return high, low


def _make_bear_run(n: int = 20, base: float = 200.0, step: float = 1.0):
    """Return (high, low) for a clean downtrend so PSAR settles as bearish."""
    high = np.array([base - i * step + 2 for i in range(n)], dtype=float)
    low  = np.array([base - i * step - 2 for i in range(n)], dtype=float)
    return high, low


class TestCustomPSAR:
    """Validates _calc_psar output matches expected TradingView flip timing."""

    def test_flip_to_bearish_detected_on_same_bar(self):
        """
        After a bull run, when price drops below SAR the flip (SAR > close)
        must be visible on THAT bar, not the next one.
        """
        # 30 bars of uptrend to let PSAR settle, then 1 sharp reversal bar
        h_up, l_up = _make_bull_run(n=30, base=100.0)
        # Reversal bar: high below previous lows so SAR definitely gets crossed
        h_rev = np.array([80.0])
        l_rev = np.array([70.0])

        high = np.concatenate([h_up, h_rev])
        low  = np.concatenate([l_up, l_rev])

        sar = IndicatorEngine._calc_psar(high, low)

        reversal_idx = 30   # The reversal bar index
        # On the reversal bar itself, SAR must be ABOVE the high (bearish flip confirmed)
        assert sar[reversal_idx] > high[reversal_idx], (
            f"SAR ({sar[reversal_idx]:.4f}) should be above high ({high[reversal_idx]:.4f}) "
            f"on the reversal bar (idx={reversal_idx}). Got bearish flip 1 bar LATE."
        )

    def test_flip_to_bullish_detected_on_same_bar(self):
        """
        After a bear run, when price rises above SAR the flip (SAR < low)
        must be visible on THAT bar, not the next one.
        """
        # 30 bars of downtrend to let PSAR settle bearish, then 1 sharp rally bar
        h_dn, l_dn = _make_bear_run(n=30, base=200.0)
        # Reversal bar: low well above previous highs so SAR definitely gets crossed
        h_rev = np.array([250.0])
        l_rev = np.array([240.0])

        high = np.concatenate([h_dn, h_rev])
        low  = np.concatenate([l_dn, l_rev])

        sar = IndicatorEngine._calc_psar(high, low)

        reversal_idx = 30
        # On the reversal bar itself, SAR must be BELOW the low (bullish flip confirmed)
        assert sar[reversal_idx] < low[reversal_idx], (
            f"SAR ({sar[reversal_idx]:.4f}) should be below low ({low[reversal_idx]:.4f}) "
            f"on the reversal bar (idx={reversal_idx}). Got bullish flip 1 bar LATE."
        )

    def test_no_nan_after_first_bar(self):
        """PSAR should produce valid (non-NaN) values from bar index 1 onwards."""
        h, l = _make_bull_run(n=50)
        sar = IndicatorEngine._calc_psar(h, l)

        assert not np.isnan(sar[0]), "SAR[0] should be initialised (not NaN)"
        assert not np.any(np.isnan(sar[1:])), "SAR should have no NaN after bar 0"

    def test_bull_sar_stays_below_price(self):
        """During a clean uptrend, SAR must always be below the low of each bar."""
        h, l = _make_bull_run(n=50, base=100.0, step=2.0)
        sar = IndicatorEngine._calc_psar(h, l)

        # Skip first bar (initialisation may equal low[0])
        for i in range(1, len(h)):
            assert sar[i] <= l[i] or sar[i] > h[i], (
                f"Bar {i}: SAR={sar[i]:.4f} is neither below low={l[i]:.4f} "
                f"(bull) nor above high={h[i]:.4f} (bear after flip)"
            )

    def test_clamping_rule_respected(self):
        """
        In bull mode, SAR[i] must not exceed min(low[i-1], low[i-2]).
        Build a run where the SAR formula would push SAR too high without clamping.
        """
        # Flat-ish uptrend but very volatile lows → clamping will bite
        n = 40
        high = np.linspace(110, 140, n)
        low  = np.linspace(80, 110, n)   # lows well below highs → SAR would overshoot without clamp

        sar = IndicatorEngine._calc_psar(high, low)

        # In any bull bar, SAR[i] <= min(low[i-1], low[i-2])
        for i in range(3, n):
            if sar[i] < low[i]:   # still bullish (SAR below price)
                expected_max = min(low[i - 1], low[i - 2])
                assert sar[i] <= expected_max + 1e-9, (
                    f"Clamping violated at bar {i}: SAR={sar[i]:.4f} > "
                    f"min(low[i-1], low[i-2])={expected_max:.4f}"
                )
