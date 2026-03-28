import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.services.strategy_service import StrategyEngine
from src.models import SignalType

def create_mock_df(n=110):
    """Creates a base DataFrame with 110 candles."""
    now = datetime.now()
    data = {
        "timestamp": [now + timedelta(minutes=15*i) for i in range(n)],
        "open": [100.0] * n,
        "high": [105.0] * n,
        "low": [95.0] * n,
        "close": [102.0] * n,
        "volume": [1000.0] * n,
        "ema5": [110.0] * n,
        "ema9": [105.0] * n,
        "ema100": [100.0] * n,
        "psar": [110.0] * n,      # PSAR starts ABOVE price
        "psar_prev": [110.0] * n, # PSAR was ABOVE price
        "sqz_val": [1.0] * n
    }
    return pd.DataFrame(data)

def test_hard_long_signal():
    engine = StrategyEngine()
    df = create_mock_df()
    
    # Setup for a perfect HARD LONG trigger on the last row (n-1):
    # Current row (n-1): psar flips to BELOW price
    df.loc[df.index[-1], "psar"] = 90.0
    # price action (go through):
    df.loc[df.index[-1], "low"] = 100.0
    df.loc[df.index[-1], "close"] = 115.0
    df.loc[df.index[-1], "open"] = 110.0
    # Squeeze: Increasing
    df.loc[df.index[-2], "sqz_val"] = 1.0
    df.loc[df.index[-1], "sqz_val"] = 2.0

    signal = engine.evaluate(df, "BTC/USDT", "15m")
    
    assert signal is not None
    assert signal.type == SignalType.LONG
    assert "HARD LONG" in signal.message

def test_soft_long_signal_sequential():
    engine = StrategyEngine(watch_window=5)
    df = create_mock_df()
    
    # 1. First Candle: Create a 3/4 Setup (EMA, Green, Squeeze - NO PSAR FLIP)
    # psar is ABOVE price (110) and stays above.
    df.loc[df.index[-2], "sqz_val"] = 1.0
    df.loc[df.index[-1], "sqz_val"] = 2.0
    
    signal1 = engine.evaluate(df, "BTC/USDT", "15m")
    assert signal1 is None
    assert engine.watch_mode.get("BTC/USDT") is not None

    # 2. Second Candle: Trigger the 5/5 HARD condition
    df_trigger = df.copy()
    df_trigger.loc[df_trigger.index[-1], "psar"] = 90.0
    df_trigger.loc[df_trigger.index[-1], "low"] = 100.0
    df_trigger.loc[df_trigger.index[-1], "close"] = 115.0
    
    signal2 = engine.evaluate(df_trigger, "BTC/USDT", "15m")
    assert signal2 is not None
    assert "SEQUENTIAL" in signal2.message
    assert engine.watch_mode.get("BTC/USDT") is None

def test_watch_mode_expiry():
    engine = StrategyEngine(watch_window=2)
    df = create_mock_df()
    
    # 1. Enter watch mode (3/4 setup)
    # EMA is aligned, Green, Squeeze is growing
    df.loc[df.index[-2], "sqz_val"] = 1.0
    df.loc[df.index[-1], "sqz_val"] = 2.0
    
    engine.evaluate(df, "BTC/USDT", "15m")
    assert engine.watch_mode.get("BTC/USDT") is not None
    
    # 2. Break the setup so it doesn't refresh (e.g. Squeeze goes down)
    df.loc[df.index[-1], "sqz_val"] = 0.5
    engine.evaluate(df, "BTC/USDT", "15m")
    assert engine.watch_mode.get("BTC/USDT")["expiry"] == 1
    
    # 3. Candle passes (No signal) - Should expire
    engine.evaluate(df, "BTC/USDT", "15m")
    
    assert engine.watch_mode.get("BTC/USDT") is None
