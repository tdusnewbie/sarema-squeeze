import pytest
import polars as pl
from datetime import datetime, timedelta
from src.strategy import StrategyEngine
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
    return pl.DataFrame(data)

def test_hard_long_signal():
    engine = StrategyEngine()
    df = create_mock_df()
    
    # Setup for a perfect HARD LONG trigger on the last row (n-1):
    df = df.with_columns([
        # Current row (n-1): psar flips to BELOW price
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(90.0).otherwise(pl.col("psar")).alias("psar"),
        # price action (go through):
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(100.0).otherwise(pl.col("low")).alias("low"),
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(115.0).otherwise(pl.col("close")).alias("close"),
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(110.0).otherwise(pl.col("open")).alias("open"),
        # Squeeze: Increasing
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(2.0)
          .when(pl.int_range(0, pl.len()) == pl.len() - 2).then(1.0)
          .otherwise(pl.col("sqz_val")).alias("sqz_val")
    ])

    signal = engine.evaluate(df, "BTC/USDT", "15m")
    
    assert signal is not None
    assert signal.type == SignalType.LONG
    assert "HARD LONG" in signal.message

def test_soft_long_signal_sequential():
    engine = StrategyEngine(watch_window=5)
    df = create_mock_df()
    
    # 1. First Candle: Create a 3/4 Setup (EMA, Green, Squeeze - NO PSAR FLIP)
    # psar is ABOVE price (110) and stays above.
    df_setup = df.with_columns([
        pl.Series("psar", [110.0] * len(df)),
        pl.Series("psar_prev", [110.0] * len(df)),
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(2.0)
          .when(pl.int_range(0, pl.len()) == pl.len() - 2).then(1.0)
          .otherwise(pl.col("sqz_val")).alias("sqz_val")
    ])
    
    signal1 = engine.evaluate(df_setup, "BTC/USDT", "15m")
    assert signal1 is None
    assert engine.watch_mode.get("BTC/USDT") is not None

    # 2. Second Candle: Trigger the 5/5 HARD condition
    df_trigger = df_setup.with_columns([
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(90.0).otherwise(pl.col("psar")).alias("psar"),
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(100.0).otherwise(pl.col("low")).alias("low"),
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(115.0).otherwise(pl.col("close")).alias("close"),
    ])
    
    signal2 = engine.evaluate(df_trigger, "BTC/USDT", "15m")
    assert signal2 is not None
    assert "HARD" in signal2.message
    assert engine.watch_mode.get("BTC/USDT") is None

def test_watch_mode_expiry():
    engine = StrategyEngine(watch_window=2)
    df = create_mock_df()
    
    # 1. Enter watch mode (3/4 setup)
    # EMA is aligned, Green, Squeeze is growing
    df_setup = df.with_columns([
        pl.when(pl.int_range(0, pl.len()) == pl.len() - 1).then(2.0)
          .when(pl.int_range(0, pl.len()) == pl.len() - 2).then(1.0)
          .otherwise(pl.col("sqz_val")).alias("sqz_val")
    ])
    engine.evaluate(df_setup, "BTC/USDT", "15m")
    assert engine.watch_mode.get("BTC/USDT") is not None
    
    # 2. Candle passes (No signal)
    engine.evaluate(df_setup, "BTC/USDT", "15m")
    # 3. Candle passes (No signal) - Should expire
    engine.evaluate(df_setup, "BTC/USDT", "15m")
    
    assert engine.watch_mode.get("BTC/USDT") is None
