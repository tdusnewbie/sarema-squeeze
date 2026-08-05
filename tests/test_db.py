"""
Tests for TradingDB (src/data/db.py).

All tests use ':memory:' so they never touch the real trading.db file.
"""
import pandas as pd
import pytest
from datetime import datetime, timedelta

from src.data.db import TradingDB


@pytest.fixture
def db(tmp_path):
    """Fresh in-memory DB for each test (tmp_path keeps isolation)."""
    return TradingDB(db_path=str(tmp_path / "test.db"))


# ---------------------------------------------------------------------------
# Watchlist CRUD
# ---------------------------------------------------------------------------

class TestWatchlistCRUD:
    def test_add_and_get(self, db):
        db.add_to_watchlist(111, "binance", "BTC/USDT", "15m")
        rows = db.get_watchlist(chat_id=111)
        assert len(rows) == 1
        assert rows[0] == ("binance", "BTC/USDT", "15m")

    def test_add_duplicate_is_ignored(self, db):
        db.add_to_watchlist(111, "binance", "BTC/USDT", "15m")
        db.add_to_watchlist(111, "binance", "BTC/USDT", "15m")  # duplicate
        assert len(db.get_watchlist(chat_id=111)) == 1

    def test_remove_from_watchlist(self, db):
        db.add_to_watchlist(111, "binance", "BTC/USDT", "15m")
        db.remove_from_watchlist(111, "binance", "BTC/USDT", "15m")
        assert db.get_watchlist(chat_id=111) == []

    def test_get_watchlist_all(self, db):
        db.add_to_watchlist(111, "binance", "BTC/USDT", "15m")
        db.add_to_watchlist(222, "binance", "ETH/USDT", "1h")
        all_rows = db.get_watchlist()
        assert len(all_rows) == 2

    def test_get_watchlist_filtered_by_chat_id(self, db):
        db.add_to_watchlist(111, "binance", "BTC/USDT", "15m")
        db.add_to_watchlist(222, "binance", "ETH/USDT", "1h")
        rows = db.get_watchlist(chat_id=111)
        assert len(rows) == 1
        assert rows[0][1] == "BTC/USDT"


# ---------------------------------------------------------------------------
# Scanners / subscribers
# ---------------------------------------------------------------------------

class TestScannersAndSubscribers:
    def test_get_unique_scanners_deduplicates(self, db):
        db.add_to_watchlist(111, "binance", "BTC/USDT", "15m")
        db.add_to_watchlist(222, "binance", "BTC/USDT", "15m")  # same scanner, diff user
        db.add_to_watchlist(111, "binance", "ETH/USDT", "15m")
        scanners = db.get_unique_scanners()
        assert len(scanners) == 2

    def test_get_subscribers_returns_chat_ids(self, db):
        db.add_to_watchlist(111, "binance", "BTC/USDT", "15m")
        db.add_to_watchlist(222, "binance", "BTC/USDT", "15m")
        subs = db.get_subscribers("binance", "BTC/USDT", "15m")
        assert sorted(subs) == [111, 222]

    def test_get_subscribers_empty_when_none(self, db):
        subs = db.get_subscribers("binance", "BTC/USDT", "15m")
        assert subs == []


# ---------------------------------------------------------------------------
# Candle persistence
# ---------------------------------------------------------------------------

class TestCandles:
    def _make_df(self, n=5):
        now = datetime(2026, 1, 1, 0, 0)
        return pd.DataFrame({
            "timestamp": [now + timedelta(minutes=15 * i) for i in range(n)],
            "open":   [100.0 + i for i in range(n)],
            "high":   [105.0 + i for i in range(n)],
            "low":    [95.0  + i for i in range(n)],
            "close":  [102.0 + i for i in range(n)],
            "volume": [1000.0]  * n,
        })

    def test_save_and_get_candles(self, db):
        df = self._make_df(5)
        db.save_candles("BTC/USDT", "15m", df)
        result = db.get_candles("BTC/USDT", "15m", limit=10)
        assert len(result) == 5

    def test_save_candles_ignores_duplicates(self, db):
        df = self._make_df(5)
        db.save_candles("BTC/USDT", "15m", df)
        db.save_candles("BTC/USDT", "15m", df)  # duplicate insert
        result = db.get_candles("BTC/USDT", "15m", limit=10)
        assert len(result) == 5

    def test_get_candles_limit(self, db):
        df = self._make_df(10)
        db.save_candles("BTC/USDT", "15m", df)
        result = db.get_candles("BTC/USDT", "15m", limit=3)
        assert len(result) == 3

    def test_get_candles_empty_when_none(self, db):
        result = db.get_candles("ETH/USDT", "15m")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Read-only mode
# ---------------------------------------------------------------------------

class TestReadOnly:
    def test_read_only_init_skips_schema_creation(self, tmp_path):
        """Read-only mode must not try to create tables (would raise on a fresh file)."""
        # First create a valid DB
        TradingDB(db_path=str(tmp_path / "ro.db"))
        # Then open it read-only — should not raise
        ro = TradingDB(db_path=str(tmp_path / "ro.db"), read_only=True)
        assert ro.read_only is True
