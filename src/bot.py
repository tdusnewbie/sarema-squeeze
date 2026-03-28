import typer
from typing import Optional
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = typer.Typer(help="TradingView Alert Bot - High Performance Pure Python Bot.")

@app.command()
def run():
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

    bot = TradingTelegramBot()
    
    try:
        bot.run()
    except KeyboardInterrupt:
        typer.echo("\n👋 Bot stopped by user.")

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
    timeframe: str = typer.Option("1h", "--timeframe", "-t", help="Timeframe of the CSV data")
):
    """
    Scan a historical CSV file for signals (Backtester).
    """
    from .db import TradingDB
    from .engine import IndicatorEngine
    from .strategy import StrategyEngine
    import pandas as pd

    typer.echo(f"🔍 Scanning historical data from: {file}")
    
    # 1. Load CSV using Pandas
    df = pd.read_csv(file)
    
    # Standardize column names (TradingView exports often use 'time' instead of 'timestamp')
    if "time" in df.columns:
        df = df.rename(columns={"time": "timestamp"})
    
    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(df["timestamp"]):
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    
    typer.echo(f"📈 Loaded {len(df)} candles. Calculating indicators...")
    
    # 2. Add Indicators
    df = IndicatorEngine.add_indicators(df)
    
    # 3. Scan for Signals
    strategy = StrategyEngine()
    signals_found = []
    
    # Iterate through candles (starting from 101 to have enough history)
    for i in range(101, len(df)):
        window_df = df.iloc[:i + 1]
        
        # DEBUG: Check for setup count
        if i < 1: continue
        prev = df.iloc[i-1]
        curr = df.iloc[i]
        
        # Quick manual check for logging
        long_setup = sum([
            (curr['ema5'] > curr['ema9'] > curr['ema100']),
            (curr['psar'] < curr['close']) and (prev['psar'] > prev['close']),
            (curr['close'] > curr['open']),
            (curr['sqz_val'] > 0) and (curr['sqz_val'] > prev['sqz_val'])
        ])
        
        if long_setup >= 3:
            ema_ok = "✅" if (curr['ema5'] > curr['ema9'] > curr['ema100']) else "❌"
            psar_ok = "✅" if (curr['psar'] < curr['close']) and (prev['psar'] > prev['close']) else "❌"
            color_ok = "✅" if (curr['close'] > curr['open']) else "❌"
            sqz_ok = "✅" if (curr['sqz_val'] > 0) and (curr['sqz_val'] > prev['sqz_val']) else "❌"
            thru_ok = "✅" if (curr['low'] < prev['psar']) and (curr['close'] > prev['psar']) else "❌"
            
            typer.echo(f"⏳ [{curr['timestamp']}] SETUP: EMA:{ema_ok} PSAR:{psar_ok} Color:{color_ok} SQZ:{sqz_ok} THRU:{thru_ok}")

        signal = strategy.evaluate(window_df, symbol, timeframe)
        if signal:
            signals_found.append(signal)
            local_time = signal.timestamp.astimezone()
            typer.echo(f"🎯 [{local_time.strftime('%Y-%m-%d %H:%M:%S')}] {signal.type} @ {signal.price} - {signal.message}")

    typer.echo(f"✅ Scan complete. Found {len(signals_found)} signals.")

if __name__ == "__main__":
    app()
