import asyncio
import ccxt.async_support as ccxt
import typer
import pandas as pd
from datetime import datetime
from .data.db import TradingDB
from .services.indicator_service import IndicatorEngine
from .services.strategy_service import StrategyEngine
from .notifier import TelegramNotifier

class AsyncLiveRunner:
    def __init__(self, exchange_id: str, symbol: str, timeframe: str, notifier: TelegramNotifier, db: TradingDB):
        self.exchange_id = exchange_id
        self.symbol = symbol
        self.timeframe = timeframe
        self.notifier = notifier
        self.db = db
        self.exchange = getattr(ccxt, exchange_id)()
        self.strategy = StrategyEngine()
        
        # Convert timeframe to seconds (e.g. 15m -> 900s)
        self.timeframe_secs = self.exchange.parse_timeframe(timeframe)

    async def _wait_for_next_candle(self):
        """Calculates time until the next candle close and sleeps."""
        now = datetime.now().timestamp()
        wait_time = self.timeframe_secs - (now % self.timeframe_secs) + 5 # Add 5s buffer for exchange data
        typer.echo(f"💤 [{self.symbol} {self.timeframe}] Waiting {int(wait_time)}s for next candle close...")
        await asyncio.sleep(wait_time)

    async def run(self):
        """Main infinite loop."""
        typer.echo(f"🏁 Async Runner started for {self.symbol} on {self.timeframe}")
        
        try:
            while True:
                # 1. Wait for candle close
                await self._wait_for_next_candle()
                
                typer.echo(f"🔔 [{self.symbol} {self.timeframe}] Checking for signals...")
                
                try:
                    # 2. Fetch latest candles (200 for enough history)
                    ohlcv = await self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
                    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    
                    # 3. Calculate Indicators
                    df = IndicatorEngine.add_indicators(df)
                    
                    # 4. Evaluate Strategy
                    signal, status = self.strategy.evaluate(df, self.symbol, self.timeframe)

                    if signal:
                        typer.echo(f"🎯 SIGNAL FOUND: {signal.type.value} for {self.symbol}")
                        # Get subscribers from DB
                        subscribers = self.db.get_subscribers(self.exchange_id, self.symbol, self.timeframe)
                        if subscribers:
                            # Ensure timestamp is standard datetime for notifier
                            if hasattr(signal.timestamp, "to_pydatetime"):
                                signal.timestamp = signal.timestamp.to_pydatetime()
                            self.notifier.send_signal(signal, subscribers)
                    else:
                        typer.echo(f"☁️ [{self.symbol} {self.timeframe}] No signal this candle.")
                except Exception as e:
                    typer.echo(f"⚠️ [{self.symbol} {self.timeframe}] Error in loop: {e}. Retrying in 30s...", err=True)
                    await asyncio.sleep(30)
        finally:
            await self.exchange.close()

class ScannersManager:
    def __init__(self, token: str, read_only: bool = False, tz_offset: int = 0):
        self.token = token
        self.tz_offset = tz_offset
        self.notifier = TelegramNotifier(token, tz_offset=tz_offset)
        self.db = TradingDB(read_only=read_only)
        self.active_tasks = {} # {(exchange, symbol, tf): asyncio.Task}

    async def start_all(self):
        """Starts all unique scanners from the watchlist."""
        unique_scanners = self.db.get_unique_scanners()
        for ex, sym, tf in unique_scanners:
            await self.start_scanner(ex, sym, tf)

    async def start_scanner(self, ex: str, sym: str, tf: str):
        key = (ex, sym, tf)
        if key in self.active_tasks:
            return
        
        runner = AsyncLiveRunner(ex, sym, tf, self.notifier, self.db)
        task = asyncio.create_task(runner.run())
        self.active_tasks[key] = task
        typer.echo(f"🚀 Started scanner for {key}")

    async def stop_scanner(self, ex: str, sym: str, tf: str):
        key = (ex, sym, tf)
        if key in self.active_tasks:
            # Check if anyone else is still subscribed
            subscribers = self.db.get_subscribers(ex, sym, tf)
            if not subscribers:
                self.active_tasks[key].cancel()
                del self.active_tasks[key]
                typer.echo(f"🛑 Stopped scanner for {key}")

    async def run_worker(self, poll_interval: int = 30):
        """Background loop that watches the DB and starts/stops scanners automatically."""
        typer.echo(f"👷 Scanner Worker started. Polling every {poll_interval}s...")
        
        try:
            while True:
                # 1. Get desired state from DB
                unique_scanners = self.db.get_unique_scanners()
                desired_keys = set(unique_scanners)
                current_keys = set(self.active_tasks.keys())
                
                # 2. Start new scanners
                for key in desired_keys - current_keys:
                    await self.start_scanner(*key)
                    
                # 3. Stop removed scanners
                for key in current_keys - desired_keys:
                    self.active_tasks[key].cancel()
                    del self.active_tasks[key]
                    typer.echo(f"🛑 Stopped scanner for {key}")
                
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            await self.stop_all()

    async def stop_all(self):
        for task in self.active_tasks.values():
            task.cancel()
        await asyncio.gather(*self.active_tasks.values(), return_exceptions=True)
        self.active_tasks.clear()
