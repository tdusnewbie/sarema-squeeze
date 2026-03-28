import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from src.data.db import TradingDB
from src.runner import ScannersManager, AsyncLiveRunner
from src.notifier import TelegramNotifier
from src.models import Signal
from datetime import datetime

@pytest.fixture
def mock_db():
    with patch('src.data.db.TradingDB') as mock:
        yield mock.return_value

@pytest.fixture
def mock_notifier():
    return MagicMock(spec=TelegramNotifier)

@pytest.mark.asyncio
async def test_scanners_manager_deduplication(mock_db):
    # Setup mock DB to return unique scanners
    mock_db.get_unique_scanners.return_value = [("binance", "BTC/USDT", "15m")]
    
    manager = ScannersManager(token="fake_token", read_only=True)
    manager.db = mock_db
    
    # Mock AsyncLiveRunner to avoid actual network calls
    with patch('src.runner.AsyncLiveRunner') as mock_runner:
        mock_runner_instance = mock_runner.return_value
        mock_runner_instance.run = AsyncMock()
        
        # Start all scanners
        await manager.start_all()
        
        # Verify only one scanner started for the unique pair
        assert len(manager.active_tasks) == 1
        assert ("binance", "BTC/USDT", "15m") in manager.active_tasks
        
        # Try starting the same scanner again
        await manager.start_scanner("binance", "BTC/USDT", "15m")
        assert len(manager.active_tasks) == 1 # Still 1

@pytest.mark.asyncio
async def test_scanners_manager_stop_logic(mock_db):
    manager = ScannersManager(token="fake_token", read_only=True)
    manager.db = mock_db
    
    key = ("binance", "BTC/USDT", "15m")
    mock_task = MagicMock(spec=asyncio.Task)
    manager.active_tasks[key] = mock_task
    
    # If subscribers still exist, don't stop
    mock_db.get_subscribers.return_value = [12345]
    await manager.stop_scanner(*key)
    assert key in manager.active_tasks
    mock_task.cancel.assert_not_called()
    
    # If no subscribers left, stop
    mock_db.get_subscribers.return_value = []
    await manager.stop_scanner(*key)
    assert key not in manager.active_tasks
    mock_task.cancel.assert_called_once()

@pytest.mark.asyncio
async def test_async_live_runner_signals_all_subscribers(mock_db, mock_notifier):
    # Setup runner
    runner = AsyncLiveRunner("binance", "BTC/USDT", "15m", mock_notifier, mock_db)
    runner.db = mock_db
    
    # Mock exchange and strategy
    runner.exchange = AsyncMock()
    runner.exchange.fetch_ohlcv = AsyncMock(return_value=[])
    runner.exchange.parse_timeframe = MagicMock(return_value=900)
    runner.exchange.close = AsyncMock()
    
    runner.strategy = MagicMock()
    mock_signal = Signal(symbol="BTC/USDT", timeframe="15m", type="LONG", price=50000.0, timestamp=datetime.now(), message="Test", is_hard=True)
    runner.strategy.evaluate.return_value = mock_signal
    
    # Mock subscribers
    subscribers = [111, 222, 333]
    mock_db.get_subscribers.return_value = subscribers
    
    # We want to run one iteration of the loop
    # Patch _wait_for_next_candle and asyncio.sleep to return immediately
    mock_wait = AsyncMock()
    mock_wait.side_effect = [None, Exception("Break Loop")]
    
    with patch.object(AsyncLiveRunner, '_wait_for_next_candle', mock_wait), \
         patch('asyncio.sleep', new_callable=AsyncMock):
        # Let's mock the whole run method's logic or just the part we need
        with patch('src.runner.IndicatorEngine.add_indicators', return_value=MagicMock()):
            # Use a timeout to avoid infinite loop if something goes wrong
            try:
                await runner.run()
            except Exception as e:
                if str(e) != "Break Loop":
                    raise e
                    
    # Verify notifier was called with the correct list of subscribers
    mock_notifier.send_signal.assert_called_once_with(mock_signal, subscribers)
