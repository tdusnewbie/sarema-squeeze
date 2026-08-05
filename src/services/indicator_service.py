import pandas as pd
import talib
import numpy as np
from typing import Optional

class IndicatorEngine:
    @staticmethod
    def _calc_psar(
        high: np.ndarray,
        low: np.ndarray,
        start: float = 0.02,
        step: float = 0.02,
        maximum: float = 0.2,
    ) -> np.ndarray:
        """
        Custom Parabolic SAR that matches TradingView's ta.sar() behavior.

        The key difference from TA-Lib's SAR: on a reversal bar, TradingView
        immediately emits the new SAR value (set to the extreme point of the
        prior trend), so the dot is already on the correct side of price on
        the SAME bar as the flip. TA-Lib delays this by one bar, causing
        signals to appear one candle later than expected.

        Clamping rules (identical to TradingView):
          Bull: SAR[i] <= min(low[i-1], low[i-2])
          Bear: SAR[i] >= max(high[i-1], high[i-2])
        """
        n = len(high)
        sar = np.full(n, np.nan)
        if n < 2:
            return sar

        # Initialise: treat the very first bar as bullish
        bull = True
        af = start
        ep = high[0]          # Extreme point tracks highest high (bull) / lowest low (bear)
        sar[0] = low[0]       # Initial SAR is below the first bar (bullish assumption)

        for i in range(1, n):
            prev_sar = sar[i - 1]

            if bull:
                # Advance SAR toward the extreme point
                new_sar = prev_sar + af * (ep - prev_sar)
                # Clamp: must stay below the previous two lows
                new_sar = min(new_sar, low[i - 1])
                if i >= 2:
                    new_sar = min(new_sar, low[i - 2])

                if low[i] < new_sar:
                    # --- Reversal to bearish on THIS bar ---
                    bull = False
                    new_sar = ep   # Jump SAR to the highest point of the bull run
                    ep = low[i]
                    af = start
                else:
                    # Continue bullish; update EP and AF on new highs
                    if high[i] > ep:
                        ep = high[i]
                        af = min(af + step, maximum)
            else:
                # Advance SAR toward the extreme point (negative direction)
                new_sar = prev_sar + af * (ep - prev_sar)
                # Clamp: must stay above the previous two highs
                new_sar = max(new_sar, high[i - 1])
                if i >= 2:
                    new_sar = max(new_sar, high[i - 2])

                if high[i] > new_sar:
                    # --- Reversal to bullish on THIS bar ---
                    bull = True
                    new_sar = ep   # Jump SAR to the lowest point of the bear run
                    ep = high[i]
                    af = start
                else:
                    # Continue bearish; update EP and AF on new lows
                    if low[i] < ep:
                        ep = low[i]
                        af = min(af + step, maximum)

            sar[i] = new_sar

        return sar

    @staticmethod
    def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculates all required indicators for the 5-of-5 strategy.
        Input: Pandas DataFrame with columns [timestamp, open, high, low, close, volume]
        """
        # TA-Lib accepts numpy arrays
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values

        # 1. EMAs (5, 9, 100)
        ema5 = talib.EMA(close, timeperiod=5)
        ema9 = talib.EMA(close, timeperiod=9)
        ema100 = talib.EMA(close, timeperiod=100)

        # 2. Parabolic SAR (custom implementation matching TradingView)
        psar = IndicatorEngine._calc_psar(high, low, start=0.02, step=0.02, maximum=0.2)

        # 3. Squeeze Momentum (LazyBear Logic)
        length = 20
        mult_bb = 2.0
        mult_kc = 1.5

        # Bollinger Bands
        basis = talib.SMA(close, timeperiod=length)
        dev = mult_bb * talib.STDDEV(close, timeperiod=length)
        upperBB = basis + dev
        lowerBB = basis - dev

        # Keltner Channels
        ma = talib.SMA(close, timeperiod=length)
        tr = talib.TRANGE(high, low, close)
        range_ma = talib.SMA(tr, timeperiod=length)
        upperKC = ma + range_ma * mult_kc
        lowerKC = ma - range_ma * mult_kc

        # Squeeze Value (Linear Regression)
        highest_high = talib.MAX(high, timeperiod=length)
        lowest_low = talib.MIN(low, timeperiod=length)
        avg_price = (highest_high + lowest_low) / 2
        avg_combined = (avg_price + basis) / 2

        sqz_val = talib.LINEARREG(close - avg_combined, timeperiod=length)

        # Add columns back to the DataFrame
        df['ema5'] = ema5
        df['ema9'] = ema9
        df['ema100'] = ema100
        df['psar'] = psar
        df['sqz_val'] = sqz_val
        # Keep psar_prev for any downstream consumers
        df['psar_prev'] = df['psar'].shift(1)

        return df
