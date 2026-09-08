import typer
from typing import Optional
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = typer.Typer(help="TradingView Alert Bot - High Performance Pure Python Bot.")

@app.command()
def run(split: bool = typer.Option(False, "--split", "-s", help="Run in split mode (Bot only)")):
    """
    Start the interactive Telegram bot. 
    Manage your scanners directly via /add and /remove commands.
    """
    from .telegram_bot import TradingTelegramBot
    import os

    token = os.getenv("TELEGRAM_BOT_TOKEN")

    if not token:
        typer.echo("❌ Missing TELEGRAM_BOT_TOKEN in .env file", err=True)
        raise typer.Exit(1)

    bot = TradingTelegramBot(split_mode=split)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        typer.echo("\n👋 Bot stopped by user.")

@app.command()
def worker(
    poll: int = typer.Option(30, "--poll", "-p", help="Poll interval in seconds"),
    tz: Optional[str] = typer.Option(None, "--tz", help="Timezone name or offset (e.g. Asia/Ho_Chi_Minh, UTC+7, 7)"),
):
    """
    Start the background scanner worker.
    """
    import asyncio
    from .runner import ScannersManager
    from .data.db import TradingDB
    import os

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        typer.echo("❌ Missing TELEGRAM_BOT_TOKEN", err=True)
        raise typer.Exit(1)

    manager = ScannersManager(token, read_only=True, tz=tz)
    
    try:
        asyncio.run(manager.run_worker(poll_interval=poll))
    except KeyboardInterrupt:
        typer.echo("\n👷 Worker stopped by user.")

@app.command()
def fetch_history(
    exchange_id: str = typer.Option("binance", "--exchange", "-e"),
    symbol: str = typer.Option("BTC/USDT:USDT", "--symbol", "-s"),
    timeframe: str = typer.Option("15m", "--timeframe", "-t"),
    limit: int = typer.Option(1000, "--limit", "-l", help="Number of candles to fetch"),
    output: Path = typer.Option("live_history.csv", "--output", "-o")
):
    """
    Download historical data from an exchange and save to CSV.
    """
    import ccxt
    import pandas as pd
    
    typer.echo(f"🌐 Connecting to {exchange_id}...")
    # Use the pro futures exchange for perpetuals if needed
    exchange = getattr(ccxt, exchange_id)()
    
    typer.echo(f"📥 Fetching {limit} candles for {symbol} ({timeframe})...")
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    # Convert ms to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    df.to_csv(output, index=False)
    typer.echo(f"✅ Saved {len(df)} candles to {output}")

@app.command()
def scan(
    file: Path = typer.Option(..., "--file", "-f", exists=True, readable=True, help="Historical CSV file to scan"),
    symbol: str = typer.Option("BTC/USDT", "--symbol", "-s", help="Symbol for the data in CSV"),
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="Timeframe of the CSV data"),
    tz: Optional[str] = typer.Option(None, "--tz", help="Timezone name or offset (e.g. Asia/Ho_Chi_Minh, UTC+7)"),
    tz_offset: Optional[int] = typer.Option(None, "--tz-offset", help="Timezone offset in hours (e.g. 7 for UTC+7)"),
    output_log: Optional[Path] = typer.Option(None, "--output-log", "-ol", help="File to save scan results")
):
    """
    Scan a historical CSV file for signals (Backtester).
    """
    from .data.db import TradingDB
    from .notifier import parse_timezone
    from .services.indicator_service import IndicatorEngine
    from .services.strategy_service import StrategyEngine
    import pandas as pd
    import numpy as np
    from datetime import timezone

    target_tz = parse_timezone(tz if tz is not None else tz_offset)

    typer.echo(f"🔍 Scanning historical data from: {file}")
    
    # 1. Load CSV using Pandas
    df = pd.read_csv(file)
    
    # Standardize column names (TradingView exports often use 'time' instead of 'timestamp')
    if "time" in df.columns:
        df = df.rename(columns={"time": "timestamp"})
    
    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        # Check if it looks like unix seconds (e.g. > 1e9)
        sample_ts = df["timestamp"].iloc[0]
        if isinstance(sample_ts, (int, float, np.integer)) and sample_ts > 1e9:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit='s')
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    typer.echo(f"📈 Loaded {len(df)} candles. Scanning for signals...")
    
    # 2. Scan for Signals
    strategy = StrategyEngine()
    signals_found = []
    
    results = []

    def log_and_collect(msg: str):
        typer.echo(msg)
        results.append(msg)

    # Iterate through candles (starting from 101 to have enough history)
    for i in range(101, len(df)):
        window_df = df.iloc[:i + 1]
        
        # DEBUG: Check for setup count
        if i < 1: continue
        curr = df.iloc[i]
        
        ts_val = curr['timestamp']
        if hasattr(ts_val, "to_pydatetime"):
            ts_val = ts_val.to_pydatetime()
        if ts_val.tzinfo is None:
            ts_val = ts_val.replace(tzinfo=timezone.utc)
        ts_adjusted = ts_val.astimezone(target_tz)
        
        signal, status = strategy.evaluate(window_df, symbol, timeframe)
        
        # Log Condition Status if we have any interesting score (>=3) or if we are watching
        score = sum(status.values()) if status else 0
        is_watching = symbol in strategy.watch_mode and strategy.watch_mode[symbol] is not None
        
        if score >= 3 or is_watching:
            status_str = " ".join([f"{k}:{'✅' if v else '❌'}" for k, v in status.items()])
            prefix = "⏳ SETUP" if not is_watching else f"👀 WATCH ({strategy.watch_mode[symbol]['type']}, {strategy.watch_mode[symbol]['expiry']} left)"
            log_and_collect(f"{prefix} [{ts_adjusted}] {status_str}")

        if signal:
            signals_found.append(signal)
            sig_ts = signal.timestamp
            if hasattr(sig_ts, "to_pydatetime"):
                sig_ts = sig_ts.to_pydatetime()
            if sig_ts.tzinfo is None:
                sig_ts = sig_ts.replace(tzinfo=timezone.utc)
            ts_adjusted = sig_ts.astimezone(target_tz)
            log_and_collect(f"🎯 [{ts_adjusted.strftime('%Y-%m-%d %H:%M:%S')}] {signal.type} @ {signal.price} - {signal.message}")

    summary = f"✅ Scan complete. Found {len(signals_found)} signals."
    typer.echo(summary)
    results.append(summary)

    if output_log:
        with open(output_log, "w") as f:
            f.write("\n".join(results))
        typer.echo(f"📁 Results saved to {output_log}")

if __name__ == "__main__":
    app()
