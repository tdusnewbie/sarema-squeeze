import pandas as pd
import talib
import numpy as np

class IndicatorEngine:
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

        # 2. Parabolic SAR
        psar = talib.SAR(high, low, acceleration=0.02, maximum=0.2)

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
        # Shift PSAR by 1 to get "previous PSAR dot" level
        df['psar_prev'] = df['psar'].shift(1)
        
        return df
