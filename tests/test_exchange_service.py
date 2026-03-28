import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.exchange_service import ExchangeService

@pytest.mark.asyncio
async def test_search_symbols_direct_match():
    service = ExchangeService()
    
    mock_markets = {
        "BTC/USDT": {"type": "spot"},
        "ETH/USDT": {"type": "spot"},
    }
    
    with patch('ccxt.async_support.binance') as mock_binance:
        instance = mock_binance.return_value
        instance.load_markets = AsyncMock(return_value=mock_markets)
        instance.close = AsyncMock()
        
        ex, matches = await service.search_symbols("BTCUSDT")
        
        assert ex == "binance"
        assert "BTC/USDT" in matches

@pytest.mark.asyncio
async def test_search_symbols_with_exchange_prefix():
    service = ExchangeService()
    
    mock_markets = {
        "BTC/USDT:USDT": {"type": "swap"},
    }
    
    with patch('ccxt.async_support.bybit') as mock_bybit:
        instance = mock_bybit.return_value
        instance.load_markets = AsyncMock(return_value=mock_markets)
        instance.close = AsyncMock()
        
        ex, matches = await service.search_symbols("BYBIT:BTCUSDT")
        
        assert ex == "bybit"
        assert "BTC/USDT:USDT" in matches

@pytest.mark.asyncio
async def test_search_symbols_perp_logic():
    service = ExchangeService()
    
    # Mocking markets where one is spot and one is swap
    mock_markets = {
        "BTC/USDT": {"type": "spot"},
        "BTC/USDT:USDT": {"type": "swap"},
    }
    
    with patch('ccxt.async_support.binance') as mock_binance:
        instance = mock_binance.return_value
        instance.load_markets = AsyncMock(return_value=mock_markets)
        instance.close = AsyncMock()
        
        # Searching for PERP should prioritize the swap
        ex, matches = await service.search_symbols("BTCUSDTPERP")
        
        assert "BTC/USDT:USDT" in matches
        # In our logic, if it's a perp request, we only return perp matches if found
        assert "BTC/USDT" not in matches

@pytest.mark.asyncio
async def test_search_symbols_fallback():
    service = ExchangeService()
    
    # 1. Mock Binance to return NOTHING
    # 2. Mock Bybit to return MATCH
    
    with patch('ccxt.async_support.binance') as mock_binance, \
         patch('ccxt.async_support.bybit') as mock_bybit:
        
        binance_inst = mock_binance.return_value
        binance_inst.load_markets = AsyncMock(return_value={})
        binance_inst.close = AsyncMock()
        
        bybit_inst = mock_bybit.return_value
        bybit_inst.load_markets = AsyncMock(return_value={"BTC/USDT:USDT": {"type": "swap"}})
        bybit_inst.close = AsyncMock()
        
        ex, matches = await service.search_symbols("BTCUSDT")
        
        assert ex == "bybit"
        assert "BTC/USDT:USDT" in matches
