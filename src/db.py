import os
import duckdb
import pandas as pd
from pathlib import Path
from typing import Optional
from datetime import datetime
from .models import Candle

class TradingDB:
    def __init__(self, db_path: Optional[str] = None, read_only: bool = False):
        if db_path is None:
            db_path = os.getenv("DUCKDB_PATH", "trading.db")
        self.db_path = db_path
        self.conn = duckdb.connect(db_path, read_only=read_only)
        if not read_only:
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
                chat_id BIGINT,
                exchange_id VARCHAR,
                symbol VARCHAR,
                timeframe VARCHAR,
                PRIMARY KEY (chat_id, exchange_id, symbol, timeframe)
            );
        """)

    def add_to_watchlist(self, chat_id: int, exchange_id: str, symbol: str, timeframe: str):
        self.conn.execute("INSERT OR IGNORE INTO watchlist VALUES (?, ?, ?, ?)", [chat_id, exchange_id, symbol, timeframe])

    def remove_from_watchlist(self, chat_id: int, exchange_id: str, symbol: str, timeframe: str):
        self.conn.execute("DELETE FROM watchlist WHERE chat_id = ? AND exchange_id = ? AND symbol = ? AND timeframe = ?", [chat_id, exchange_id, symbol, timeframe])

    def get_watchlist(self, chat_id: Optional[int] = None):
        if chat_id:
            return self.conn.execute("SELECT exchange_id, symbol, timeframe FROM watchlist WHERE chat_id = ?", [chat_id]).fetchall()
        return self.conn.execute("SELECT * FROM watchlist").fetchall()

    def get_unique_scanners(self):
        """Returns unique (exchange_id, symbol, timeframe) to run scanners for."""
        return self.conn.execute("SELECT DISTINCT exchange_id, symbol, timeframe FROM watchlist").fetchall()

    def get_subscribers(self, exchange_id: str, symbol: str, timeframe: str):
        """Returns all chat_ids subscribed to a specific scanner."""
        rows = self.conn.execute("SELECT chat_id FROM watchlist WHERE exchange_id = ? AND symbol = ? AND timeframe = ?", [exchange_id, symbol, timeframe]).fetchall()
        return [r[0] for r in rows]

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
