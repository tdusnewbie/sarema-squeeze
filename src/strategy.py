import pandas as pd
from typing import Optional, Dict
from .models import SignalType, Signal
from datetime import datetime

class StrategyEngine:
    def __init__(self, watch_window: int = 5):
        self.watch_window = watch_window
        # State: {symbol: {"type": SignalType, "expiry": int}}
        self.watch_mode: Dict[str, Dict] = {}

    def _check_indicators(self, curr: pd.Series, prev: pd.Series) -> dict:
        return {
            "long_ema": (curr['ema5'] > curr['ema9'] > curr['ema100']),
            "short_ema": (curr['ema5'] < curr['ema9'] < curr['ema100']),
            
            "long_psar_flip": (curr['psar'] < curr['close']) and (prev['psar'] > prev['close']),
            "short_psar_flip": (curr['psar'] > curr['close']) and (prev['psar'] < prev['close']),
            
            "long_green": (curr['close'] > curr['open']),
            "short_red": (curr['close'] < curr['open']),
            
            "long_go_through": (curr['low'] < prev['psar']) and (curr['close'] > prev['psar']),
            "short_go_through": (curr['high'] > prev['psar']) and (curr['close'] < prev['psar']),
            
            "long_sqz": (curr['sqz_val'] > 0) and (curr['sqz_val'] > prev['sqz_val']),
            "short_sqz": (curr['sqz_val'] < 0) and (curr['sqz_val'] < prev['sqz_val'])
        }

    def evaluate(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Signal]:
        if len(df) < 102:
            return None

        # Last two rows
        prev = df.iloc[-2]
        curr = df.iloc[-1]
        
        cond = self._check_indicators(curr, prev)

        # 1. HARD SIGNAL (5/5)
        is_hard_long = cond["long_ema"] and cond["long_psar_flip"] and cond["long_green"] and cond["long_go_through"] and cond["long_sqz"]
        is_hard_short = cond["short_ema"] and cond["short_psar_flip"] and cond["short_red"] and cond["short_go_through"] and cond["short_sqz"]

        if is_hard_long:
            self.watch_mode[symbol] = None
            return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=SignalType.LONG, 
                          price=curr['close'], message="🔥 HARD LONG: 5/5 Match", is_hard=True)
        
        if is_hard_short:
            self.watch_mode[symbol] = None
            return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=SignalType.SHORT, 
                          price=curr['close'], message="🔥 HARD SHORT: 5/5 Match", is_hard=True)

        # 2. STATE MANAGEMENT (Watch Window)
        long_setup = sum([cond["long_ema"], cond["long_psar_flip"], cond["long_green"], cond["long_sqz"]]) >= 3
        short_setup = sum([cond["short_ema"], cond["short_psar_flip"], cond["short_red"], cond["short_sqz"]]) >= 3

        # Case A: Not in Watch Mode -> Enter if Setup matches
        if symbol not in self.watch_mode or self.watch_mode[symbol] is None:
            if long_setup:
                self.watch_mode[symbol] = {"type": SignalType.LONG, "expiry": self.watch_window}
            elif short_setup:
                self.watch_mode[symbol] = {"type": SignalType.SHORT, "expiry": self.watch_window}
        
        # Case B: Already in Watch Mode -> Decrement or Expire
        else:
            setup = self.watch_mode[symbol]
            setup["expiry"] -= 1
            if setup["expiry"] <= 0:
                self.watch_mode[symbol] = None

        return None
