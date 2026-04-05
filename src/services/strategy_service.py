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
            
            "long_sar_ema": (curr['psar'] > curr['ema100']),
            "short_sar_ema": (curr['psar'] < curr['ema100']),
            
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
        
        # Define 5 groups (New logic: PSAR vs EMA100 check)
        # 1. PSAR Side (Relaxed Flip: Is price on the correct side?)
        psar_long = curr['psar'] < curr['close']
        psar_short = curr['psar'] > curr['close']
        
        # Fresh Flip (For HARD signal)
        psar_flip_long = psar_long and (prev['psar'] > prev['close'])
        psar_flip_short = psar_short and (prev['psar'] < prev['close'])
        
        # 2. EMA Alignment
        ema_long = cond["long_ema"]
        ema_short = cond["short_ema"]
        
        # 3. Squeeze
        sqz_long = cond["long_sqz"]
        sqz_short = cond["short_sqz"]

        # 4. SAR vs EMA100
        sar_ema_long = cond["long_sar_ema"]
        sar_ema_short = cond["short_sar_ema"]
        
        # 5. Price Action (Color + Position)
        # Position check: Is the candle on the correct side of the PSAR level?
        thru_long = (curr['close'] > prev['psar']) and (curr['close'] > curr['open'])
        thru_short = (curr['close'] < prev['psar']) and (curr['close'] < curr['open'])

        status_long = {"PSAR": psar_long, "EMA": ema_long, "Price": thru_long, "Sqz": sqz_long, "SAR_EMA": sar_ema_long}
        status_short = {"PSAR": psar_short, "EMA": ema_short, "Price": thru_short, "Sqz": sqz_short, "SAR_EMA": sar_ema_short}

        # Hard signal status must use fresh flip
        hard_status_long = status_long.copy()
        hard_status_long["PSAR"] = psar_flip_long
        
        hard_status_short = status_short.copy()
        hard_status_short["PSAR"] = psar_flip_short

        # 1. Check for HARD Signal (All 5 must be True)
        if all(hard_status_long.values()):
            self.watch_mode[symbol] = None
            return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=SignalType.LONG, 
                          price=curr['close'], message="🔥 HARD LONG: Match (SAR Filter OK)", is_hard=True), hard_status_long
        
        if all(hard_status_short.values()):
            self.watch_mode[symbol] = None
            return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=SignalType.SHORT, 
                          price=curr['close'], message="🔥 HARD SHORT: Match (SAR Filter OK)", is_hard=True), hard_status_short

        # 2. Check for SEQUENTIAL Completion (Watch Mode)
        if symbol in self.watch_mode and self.watch_mode[symbol] is not None:
            wm = self.watch_mode[symbol]
            st = status_long if wm["type"] == SignalType.LONG else status_short
            
            # Locked Price Action check: Does current candle pierce the LOCKED PSAR level?
            locked_psar = wm["locked_psar"]
            if wm["type"] == SignalType.LONG:
                price_ok = (curr['low'] < locked_psar) and (curr['close'] > locked_psar) and (curr['close'] > curr['open'])
            else:
                price_ok = (curr['high'] > locked_psar) and (curr['close'] < locked_psar) and (curr['close'] < locked_psar) and (curr['close'] < curr['open'])
            
            # Update status with the locked check for this candle
            st["Price"] = price_ok
            # PSAR is considered "Completed" if we are in watch mode
            st["PSAR"] = True 
            
            if all(st.values()):
                self.watch_mode[symbol] = None
                msg = f"🌊 SEQUENTIAL {wm['type']}: Completed (SAR Filter OK)"
                return Signal(timestamp=curr['timestamp'], symbol=symbol, timeframe=timeframe, type=wm["type"], 
                              price=curr['close'], message=msg, is_hard=False), st
            
            # Still watching: Decrement
            wm["expiry"] -= 1
            if wm["expiry"] <= 0:
                self.watch_mode[symbol] = None
            else:
                # Return current status for logging
                return None, st

        # 3. Check for Watch Mode ENTRY 
        # Mandatory: PSAR Flip AND SAR vs EMA100
        # Optional: 2 out of the other 3 (EMA Alignment, Price Action, Squeeze)
        if psar_flip_long and sar_ema_long and sum([ema_long, thru_long, sqz_long]) >= 2:
            self.watch_mode[symbol] = {"type": SignalType.LONG, "expiry": self.watch_window, "locked_psar": prev['psar']}
            return None, hard_status_long
        
        if psar_flip_short and sar_ema_short and sum([ema_short, thru_short, sqz_short]) >= 2:
            self.watch_mode[symbol] = {"type": SignalType.SHORT, "expiry": self.watch_window, "locked_psar": prev['psar']}
            return None, hard_status_short

        return None, {}
