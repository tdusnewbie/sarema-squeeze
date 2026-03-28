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

    def evaluate(self, df: pd.DataFrame, symbol: str, timeframe: str) -> tuple[Optional[Signal], dict]:
        if len(df) < 102:
            return None, {}

        # Last two rows
        prev = df.iloc[-2]
        curr = df.iloc[-1]
        
        cond = self._check_indicators(curr, prev)
        
        # Define 4 groups
        # 1. PSAR Flip (Must have for Watch Mode)
        psar_flip_long = (curr['psar'] < curr['close']) and (prev['psar'] > prev['close'])
        psar_flip_short = (curr['psar'] > curr['close']) and (prev['psar'] < prev['close'])
        
        # 2. EMA Alignment
        ema_long = cond["long_ema"]
        ema_short = cond["short_ema"]
        
        # 3. Squeeze
        sqz_long = cond["long_sqz"]
        sqz_short = cond["short_sqz"]
        
        # 4. Price Action (Color + Thru)
        # Note: 'Thru' check for HARD signal uses current prev['psar']
        # but for WATCH mode we might use a locked level.
        thru_long = (curr['low'] < prev['psar']) and (curr['close'] > prev['psar']) and (curr['close'] > curr['open'])
        thru_short = (curr['high'] > prev['psar']) and (curr['close'] < prev['psar']) and (curr['close'] < curr['open'])

        status_long = {"PSAR": psar_flip_long, "EMA": ema_long, "Price": thru_long, "Sqz": sqz_long}
        status_short = {"PSAR": psar_flip_short, "EMA": ema_short, "Price": thru_short, "Sqz": sqz_short}

        # 1. Check for 4/4 HARD Signal
        if all(status_long.values()):
            self.watch_mode[symbol] = None
            return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=SignalType.LONG, 
                          price=curr['close'], message="🔥 HARD LONG: 4/4 Match", is_hard=True), status_long
        
        if all(status_short.values()):
            self.watch_mode[symbol] = None
            return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=SignalType.SHORT, 
                          price=curr['close'], message="🔥 HARD SHORT: 4/4 Match", is_hard=True), status_short

        # 2. Check for SEQUENTIAL Completion (Watch Mode)
        if symbol in self.watch_mode and self.watch_mode[symbol] is not None:
            wm = self.watch_mode[symbol]
            st = status_long if wm["type"] == SignalType.LONG else status_short
            
            # Locked Price Action check: Does current candle pierce the LOCKED PSAR level?
            locked_psar = wm["locked_psar"]
            if wm["type"] == SignalType.LONG:
                price_ok = (curr['low'] < locked_psar) and (curr['close'] > locked_psar) and (curr['close'] > curr['open'])
            else:
                price_ok = (curr['high'] > locked_psar) and (curr['close'] < locked_psar) and (curr['close'] < curr['open'])
            
            # Update status with the locked check for this candle
            st["Price"] = price_ok
            # PSAR is considered "Completed" if it flipped at the start
            st["PSAR"] = True 
            
            if all(st.values()):
                self.watch_mode[symbol] = None
                msg = f"🌊 SEQUENTIAL {wm['type']}: 4/4 Completed"
                return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=wm["type"], 
                              price=curr['close'], message=msg, is_hard=False), st
            
            # Still watching: Decrement
            wm["expiry"] -= 1
            if wm["expiry"] <= 0:
                self.watch_mode[symbol] = None
            else:
                # Return current status for logging
                return None, st

        # 3. Check for Watch Mode ENTRY (Must have PSAR Flip + 2 others)
        if psar_flip_long and sum([ema_long, thru_long, sqz_long]) >= 2:
            self.watch_mode[symbol] = {"type": SignalType.LONG, "expiry": self.watch_window, "locked_psar": prev['psar']}
            return None, status_long
        
        if psar_flip_short and sum([ema_short, thru_short, sqz_short]) >= 2:
            self.watch_mode[symbol] = {"type": SignalType.SHORT, "expiry": self.watch_window, "locked_psar": prev['psar']}
            return None, status_short

        return None, {}
