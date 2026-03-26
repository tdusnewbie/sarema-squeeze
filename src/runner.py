import time
import ccxt
import typer
from datetime import datetime, timedelta
from .db import TradingDB
from .engine import IndicatorEngine
from .strategy import StrategyEngine
from .notifier import TelegramNotifier
import polars as pl

class LiveRunner:
    def __init__(self, exchange_id: str, symbol: str, timeframe: str, notifier: TelegramNotifier):
        self.symbol = symbol
        self.timeframe = timeframe
        self.notifier = notifier
        self.exchange = getattr(ccxt, exchange_id)()
        self.db = TradingDB()
        self.strategy = StrategyEngine()
        
        # Convert timeframe to seconds (e.g. 15m -> 900s)
        self.timeframe_secs = self.exchange.parse_timeframe(timeframe)

    def _wait_for_next_candle(self):
        """Calculates time until the next candle close and sleeps."""
        now = time.time()
        wait_time = self.timeframe_secs - (now % self.timeframe_secs) + 5 # Add 5s buffer for exchange data
        typer.echo(f"💤 Waiting {int(wait_time)}s for next candle close...")
        time.sleep(wait_time)

    def run(self):
        """Main infinite loop."""
        typer.echo(f"🏁 Live Runner started for {self.symbol} on {self.timeframe}")
        
        while True:
            try:
                # 1. Wait for candle close
                self._wait_for_next_candle()
                
                typer.echo(f"🔔 [{datetime.now().strftime('%H:%M:%S')}] Checking for signals...")
                
                # 2. Fetch latest candles (200 for enough history)
                ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=200)
                df = pl.DataFrame(ohlcv, schema=["timestamp", "open", "high", "low", "close", "volume"])
                df = df.with_columns(pl.from_epoch("timestamp", time_unit="ms"))
                
                # 3. Calculate Indicators
                df = IndicatorEngine.add_indicators(df)
                
                # 4. Evaluate Strategy
                signal = self.strategy.evaluate(df, self.symbol, self.timeframe)
                
                if signal:
                    typer.echo(f"🎯 SIGNAL FOUND: {signal.type}")
                    self.notifier.send_signal(signal)
                else:
                    typer.echo("☁️ No signal this candle.")

            except Exception as e:
                typer.echo(f"⚠️ Error in main loop: {e}. Retrying in 30s...", err=True)
                time.sleep(30)
