import pandas as pd
from typing import Optional, Dict
from ..models import SignalType, Signal
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

        # 1. Check for 5/5 Match Completion
        is_5_of_5_long = cond["long_ema"] and cond["long_psar_flip"] and cond["long_green"] and cond["long_go_through"] and cond["long_sqz"]
        is_5_of_5_short = cond["short_ema"] and cond["short_psar_flip"] and cond["short_red"] and cond["short_go_through"] and cond["short_sqz"]

        if is_5_of_5_long:
            # Check if we were already watching for this
            was_watching = symbol in self.watch_mode and self.watch_mode[symbol] is not None and self.watch_mode[symbol]["type"] == SignalType.LONG
            self.watch_mode[symbol] = None # Reset
            
            msg = "🔥 HARD LONG: 5/5 Match" if not was_watching else "🌊 SEQUENTIAL LONG: 5/5 Completed"
            return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=SignalType.LONG, 
                          price=curr['close'], message=msg, is_hard=not was_watching)
        
        if is_5_of_5_short:
            was_watching = symbol in self.watch_mode and self.watch_mode[symbol] is not None and self.watch_mode[symbol]["type"] == SignalType.SHORT
            self.watch_mode[symbol] = None # Reset
            
            msg = "🔥 HARD SHORT: 5/5 Match" if not was_watching else "🌊 SEQUENTIAL SHORT: 5/5 Completed"
            return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=SignalType.SHORT, 
                          price=curr['close'], message=msg, is_hard=not was_watching)

        # 2. STATE MANAGEMENT (Watch Window Setup)
        # Setup conditions: 3 out of 4 main indicators (EMA, PSAR Flip, Candle Color, Squeeze)
        long_setup = sum([cond["long_ema"], cond["long_psar_flip"], cond["long_green"], cond["long_sqz"]]) >= 3
        short_setup = sum([cond["short_ema"], cond["short_psar_flip"], cond["short_red"], cond["short_sqz"]]) >= 3

        # Case A: Handle Setup (Enter or Refresh)
        if long_setup:
            # If not watching, or watching SHORT, or just refreshing LONG
            self.watch_mode[symbol] = {"type": SignalType.LONG, "expiry": self.watch_window}
        elif short_setup:
            # If not watching, or watching LONG, or just refreshing SHORT
            self.watch_mode[symbol] = {"type": SignalType.SHORT, "expiry": self.watch_window}
        
        # Case B: No Setup this candle -> Decrement if already in Watch Mode
        elif symbol in self.watch_mode and self.watch_mode[symbol] is not None:
            setup = self.watch_mode[symbol]
            setup["expiry"] -= 1
            if setup["expiry"] <= 0:
                self.watch_mode[symbol] = None

        return None
