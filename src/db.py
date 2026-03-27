import os
import duckdb
import pandas as pd
from pathlib import Path
from typing import Optional
from datetime import datetime
from .models import Candle

class TradingDB:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.getenv("DUCKDB_PATH", "trading.db")
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        self._init_db()

    def _init_db(self):
        """Create the candles and watchlist tables."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                symbol VARCHAR,
                timeframe VARCHAR,
                timestamp TIMESTAMP,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                PRIMARY KEY (symbol, timeframe, timestamp)
            );
            CREATE TABLE IF NOT EXISTS watchlist (
                exchange_id VARCHAR,
                symbol VARCHAR,
                timeframe VARCHAR,
                PRIMARY KEY (exchange_id, symbol, timeframe)
            );
        """)

    def add_to_watchlist(self, exchange_id: str, symbol: str, timeframe: str):
        self.conn.execute("INSERT OR IGNORE INTO watchlist VALUES (?, ?, ?)", [exchange_id, symbol, timeframe])

    def remove_from_watchlist(self, exchange_id: str, symbol: str, timeframe: str):
        self.conn.execute("DELETE FROM watchlist WHERE exchange_id = ? AND symbol = ? AND timeframe = ?", [exchange_id, symbol, timeframe])

    def get_watchlist(self):
        return self.conn.execute("SELECT * FROM watchlist").fetchall()

    def load_csv(self, file_path: Path, symbol: str, timeframe: str):
        """Ingest a historical CSV file into the database."""
        self.conn.execute(f"""
            INSERT OR IGNORE INTO candles
            SELECT '{symbol}', '{timeframe}', * FROM read_csv_auto('{file_path}')
        """)
        return self.conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]

    def save_candles(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Save a Pandas DataFrame of candles into the database."""
        self.conn.execute(f"""
            INSERT OR IGNORE INTO candles (symbol, timeframe, timestamp, open, high, low, close, volume)
            SELECT '{symbol}', '{timeframe}', * FROM df
        """)

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """Fetch the most recent candles as a Pandas DataFrame."""
        query = f"""
            SELECT timestamp, open, high, low, close, volume 
            FROM candles 
            WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        return self.conn.execute(query).df()
