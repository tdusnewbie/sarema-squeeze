import os
import duckdb
import pandas as pd
import typer
from pathlib import Path
from typing import Optional
from datetime import datetime
from .models import Candle

class TradingDB:
    def __init__(self, db_path: Optional[str] = None, read_only: bool = False):
        if db_path is None:
            db_path = os.getenv("DUCKDB_PATH", "trading.db")
        self.db_path = db_path
        self.read_only = read_only
        
        # Initialize DB if not read-only
        if not read_only:
            conn = duckdb.connect(self.db_path)
            self._init_db(conn)
            conn.close()

    def _get_conn(self):
        return duckdb.connect(self.db_path, read_only=self.read_only)

    def _init_db(self, conn):
        """Create the candles and watchlist tables."""
        conn.execute("""
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
        """)
        # Check if watchlist exists and what columns it has
        tables = conn.execute("SHOW TABLES").fetchall()
        if ('watchlist',) in tables:
            cols = conn.execute("PRAGMA table_info('watchlist')").fetchall()
            col_names = [c[1] for c in cols]
            if 'chat_id' not in col_names:
                typer.echo("🔄 Migrating watchlist table to include chat_id...")
                conn.execute("ALTER TABLE watchlist RENAME TO watchlist_old")
                conn.execute("""
                    CREATE TABLE watchlist (
                        chat_id BIGINT,
                        exchange_id VARCHAR,
                        symbol VARCHAR,
                        timeframe VARCHAR,
                        PRIMARY KEY (chat_id, exchange_id, symbol, timeframe)
                    )
                """)
                # Use current env chat_id as default for old records if available
                default_chat_id = os.getenv("TELEGRAM_CHAT_ID", "0")
                try:
                    conn.execute(f"INSERT INTO watchlist SELECT {default_chat_id}, * FROM watchlist_old")
                except:
                    pass
                conn.execute("DROP TABLE watchlist_old")
        
        # Ensure it exists with correct schema if not already there
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                chat_id BIGINT,
                exchange_id VARCHAR,
                symbol VARCHAR,
                timeframe VARCHAR,
                PRIMARY KEY (chat_id, exchange_id, symbol, timeframe)
            );
        """)

    def add_to_watchlist(self, chat_id: int, exchange_id: str, symbol: str, timeframe: str):
        with self._get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO watchlist VALUES (?, ?, ?, ?)", [chat_id, exchange_id, symbol, timeframe])

    def remove_from_watchlist(self, chat_id: int, exchange_id: str, symbol: str, timeframe: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM watchlist WHERE chat_id = ? AND exchange_id = ? AND symbol = ? AND timeframe = ?", [chat_id, exchange_id, symbol, timeframe])

    def get_watchlist(self, chat_id: Optional[int] = None):
        with self._get_conn() as conn:
            if chat_id:
                return conn.execute("SELECT exchange_id, symbol, timeframe FROM watchlist WHERE chat_id = ?", [chat_id]).fetchall()
            return conn.execute("SELECT * FROM watchlist").fetchall()

    def get_unique_scanners(self):
        """Returns unique (exchange_id, symbol, timeframe) to run scanners for."""
        with self._get_conn() as conn:
            return conn.execute("SELECT DISTINCT exchange_id, symbol, timeframe FROM watchlist").fetchall()

    def get_subscribers(self, exchange_id: str, symbol: str, timeframe: str):
        """Returns all chat_ids subscribed to a specific scanner."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT chat_id FROM watchlist WHERE exchange_id = ? AND symbol = ? AND timeframe = ?", [exchange_id, symbol, timeframe]).fetchall()
            return [r[0] for r in rows]

    def load_csv(self, file_path: Path, symbol: str, timeframe: str):
        """Ingest a historical CSV file into the database."""
        with self._get_conn() as conn:
            conn.execute(f"""
                INSERT OR IGNORE INTO candles
                SELECT '{symbol}', '{timeframe}', * FROM read_csv_auto('{file_path}')
            """)
            return conn.execute("SELECT COUNT(*) FROM candles").fetchone()[0]

    def save_candles(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Save a Pandas DataFrame of candles into the database."""
        with self._get_conn() as conn:
            conn.execute(f"""
                INSERT OR IGNORE INTO candles (symbol, timeframe, timestamp, open, high, low, close, volume)
                SELECT '{symbol}', '{timeframe}', * FROM df
            """)

    def get_candles(self, symbol: str, timeframe: str, limit: int = 200) -> pd.DataFrame:
        """Fetch the most recent candles as a Pandas DataFrame."""
        with self._get_conn() as conn:
            query = f"""
                SELECT timestamp, open, high, low, close, volume 
                FROM candles 
                WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
                ORDER BY timestamp DESC
                LIMIT {limit}
            """
            return conn.execute(query).df()
