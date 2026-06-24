import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.services.strategy_service import StrategyEngine
from src.models import SignalType

def create_mock_df(n=120):
    """Creates a base DataFrame with 120 candles."""
    now = datetime.now()
    data = {
        "timestamp": [now + timedelta(minutes=15*i) for i in range(n)],
        "open": [100.0] * n,
        "high": [105.0] * n,
        "low": [95.0] * n,
        "close": [102.0] * n,
        "volume": [1000.0] * n,
        "ema5": [100.0] * n,
        "ema9": [100.0] * n,
        "ema100": [100.0] * n,
        "psar": [115.0] * n,      # PSAR starts ABOVE price
        "sqz_val": [1.0] * n
    }
    return pd.DataFrame(data)

def test_hard_long_signal():
    engine = StrategyEngine()
    df = create_mock_df()
    
    # Setup for a perfect HARD LONG trigger on the last row (n-1):
    # n-2 (prev): psar=115, close=102 -> psar > close OK
    df.loc[df.index[-2], "psar"] = 115.0
    df.loc[df.index[-2], "close"] = 102.0
    
    # n-1 (curr): psar=110, close=120 -> psar < close OK (Flip!)
    df.loc[df.index[-1], "psar"] = 110.0
    # 2. EMA Alignment
    df.loc[df.index[-1], "ema5"] = 125.0
    df.loc[df.index[-1], "ema9"] = 115.0
    df.loc[df.index[-1], "ema100"] = 100.0 # psar(110) > ema100(100) -> OK
    # 3. Price action (go through): curr['close'] > prev['psar'] (115)
    df.loc[df.index[-1], "low"] = 105.0
    df.loc[df.index[-1], "high"] = 125.0
    df.loc[df.index[-1], "close"] = 120.0
    df.loc[df.index[-1], "open"] = 118.0 # Green
    # 4. Squeeze: Increasing
    df.loc[df.index[-2], "sqz_val"] = 1.0
    df.loc[df.index[-1], "sqz_val"] = 2.0

    signal, status = engine.evaluate(df, "BTC/USDT", "15m", add_indicators=False)
    
    assert signal is not None
    assert signal.type == SignalType.LONG
    assert "HARD LONG" in signal.message
    assert all(status.values())

def test_hard_short_signal():
    engine = StrategyEngine()
    df = create_mock_df()
    
    # PSAR starts BELOW price for short setup
    df["psar"] = 85.0
    # n-2 (prev): psar=85, close=102 -> psar < close OK
    df.loc[df.index[-2], "psar"] = 85.0
    df.loc[df.index[-2], "close"] = 102.0
    
    # n-1 (curr): psar=90, close=80 -> psar > close OK (Flip!)
    df.loc[df.index[-1], "psar"] = 90.0
    # 2. EMA Alignment
    df.loc[df.index[-1], "ema5"] = 75.0
    df.loc[df.index[-1], "ema9"] = 85.0
    df.loc[df.index[-1], "ema100"] = 100.0 # psar(90) < ema100(100) -> OK
    # 3. Price action (Red candle below psar): curr['close'] < prev['psar'] (85)
    df.loc[df.index[-1], "high"] = 95.0
    df.loc[df.index[-1], "low"] = 75.0
    df.loc[df.index[-1], "close"] = 80.0
    df.loc[df.index[-1], "open"] = 82.0 # Red
    # 4. Squeeze: Decreasing (more negative)
    df.loc[df.index[-2], "sqz_val"] = -1.0
    df.loc[df.index[-1], "sqz_val"] = -2.0

    signal, status = engine.evaluate(df, "BTC/USDT", "15m", add_indicators=False)
    
    assert signal is not None
    assert signal.type == SignalType.SHORT
    assert "HARD SHORT" in signal.message
    assert all(status.values())

def test_soft_long_signal_sequential():
    engine = StrategyEngine(watch_window=5)
    df = create_mock_df()
    
    # 1. First Candle: Create a Setup (PSAR Flip + EMA + SQZ + SAR_EMA - NO Price Action)
    # n-2: psar=115, close=102 -> OK
    df.loc[df.index[-2], "psar"] = 115.0
    df.loc[df.index[-2], "close"] = 102.0
    # n-1: psar=110, close=112 -> Flip OK! (psar 110 < close 112)
    # But Price Action False because 112 < LOCKED psar which is prev['psar'] = 115
    df.loc[df.index[-1], "psar"] = 110.0
    df.loc[df.index[-1], "close"] = 112.0
    # EMA Aligned
    df.loc[df.index[-1], "ema5"] = 125.0
    df.loc[df.index[-1], "ema9"] = 115.0
    df.loc[df.index[-1], "ema100"] = 100.0
    # Squeeze growing
    df.loc[df.index[-2], "sqz_val"] = 1.0
    df.loc[df.index[-1], "sqz_val"] = 2.0
    
    signal1, status1 = engine.evaluate(df, "BTC/USDT", "15m", add_indicators=False)
    assert signal1 is None
    assert engine.watch_mode.get("BTC/USDT") is not None
    assert status1["PSAR"] == True
    assert status1["Price"] == False
    assert status1["SAR_EMA"] == True

    # 2. Second Candle: Complete the setup (Price Action pierce locked PSAR 115)
    df_trigger = df.copy()
    new_row = df_trigger.iloc[-1].copy()
    new_row["timestamp"] += timedelta(minutes=15)
    # EMA stays aligned
    new_row["ema5"], new_row["ema9"], new_row["ema100"] = 125.0, 115.0, 100.0
    # Price Action: Pierce locked 115
    new_row["low"] = 100.0
    new_row["close"] = 120.0 
    new_row["open"] = 118.0  
    # SQZ stays growing
    df_trigger.loc[df_trigger.index[-1], "sqz_val"] = 2.0
    new_row["sqz_val"] = 3.0
    
    df_trigger = pd.concat([df_trigger, pd.DataFrame([new_row])], ignore_index=True)
    
    signal2, status2 = engine.evaluate(df_trigger, "BTC/USDT", "15m", add_indicators=False)
    assert signal2 is not None
    assert "SEQUENTIAL" in signal2.message
    assert engine.watch_mode.get("BTC/USDT") is None

def test_watch_mode_expiry():
    engine = StrategyEngine(watch_window=2)
    df = create_mock_df()
    
    # 1. Enter watch mode (PSAR Flip + EMA + SQZ + SAR_EMA)
    # n-2: psar=115, close=102 -> OK
    df.loc[df.index[-2], "psar"] = 115.0
    df.loc[df.index[-2], "close"] = 102.0
    # n-1: psar=110, close=112 -> Flip OK!
    df.loc[df.index[-1], "psar"] = 110.0
    df.loc[df.index[-1], "close"] = 112.0
    df.loc[df.index[-1], "ema5"], df.loc[df.index[-1], "ema9"], df.loc[df.index[-1], "ema100"] = 125.0, 115.0, 100.0
    df.loc[df.index[-2], "sqz_val"], df.loc[df.index[-1], "sqz_val"] = 1.0, 2.0
    
    engine.evaluate(df, "BTC/USDT", "15m", add_indicators=False)
    assert engine.watch_mode.get("BTC/USDT") is not None
    
    # 2. Candle passes (No signal)
    new_row = df.iloc[-1].copy()
    new_row["timestamp"] += timedelta(minutes=15)
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    engine.evaluate(df, "BTC/USDT", "15m", add_indicators=False)
    assert engine.watch_mode.get("BTC/USDT")["expiry"] == 1
    
    # 3. Candle passes (No signal) - Should expire
    new_row["timestamp"] += timedelta(minutes=15)
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    engine.evaluate(df, "BTC/USDT", "15m", add_indicators=False)
    
    assert engine.watch_mode.get("BTC/USDT") is None
