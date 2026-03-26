from enum import Enum
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class SignalType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"

class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class Signal(BaseModel):
    timestamp: datetime
    symbol: str
    timeframe: str
    type: SignalType
    price: float
    message: str
    is_hard: bool = True  # True for Hard Condition, False for Soft/Sequential
