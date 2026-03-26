import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from .db import TradingDB
from .runner import LiveRunner
from .notifier import TelegramNotifier

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

class TradingTelegramBot:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.db = TradingDB()
        self.active_tasks = {} # {(exchange, symbol, tf): asyncio.Task}

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("👋 Welcome! Use /add <ex> <sym> <tf> to start a scanner.\nExample: /add binance BTC/USDT:USDT 15m")

    async def add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            ex, sym, tf = context.args
            self.db.add_to_watchlist(ex, sym, tf)
            self._start_scanner(ex, sym, tf)
            await update.message.reply_text(f"✅ Added {sym} ({tf}) on {ex}. Monitoring started!")
        except Exception as e:
            await update.message.reply_text("❌ Format: /add <exchange> <symbol> <timeframe>\nExample: /add binance BTC/USDT:USDT 15m")

    async def remove_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            ex, sym, tf = context.args
            self.db.remove_from_watchlist(ex, sym, tf)
            key = (ex, sym, tf)
            if key in self.active_tasks:
                self.active_tasks[key].cancel()
                del self.active_tasks[key]
            await update.message.reply_text(f"🗑️ Removed {sym} ({tf}). Monitoring stopped.")
        except:
            await update.message.reply_text("❌ Format: /remove <exchange> <symbol> <timeframe>")

    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        items = self.db.get_watchlist()
        if not items:
            await update.message.reply_text("📜 Watchlist is empty.")
            return
        
        msg = "📋 **Current Watchlist:**\n"
        for ex, sym, tf in items:
            status = "🟢" if (ex, sym, tf) in self.active_tasks else "🟡"
            msg += f"{status} {ex.upper()}: {sym} [{tf}]\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

    def _start_scanner(self, ex, sym, tf):
        key = (ex, sym, tf)
        if key in self.active_tasks:
            return # Already running
        
        notifier = TelegramNotifier(self.token, self.chat_id)
        # We need a new non-blocking runner or wrap existing one
        runner = LiveRunner(ex, sym, tf, notifier)
        
        # Wrap the runner.run() into an async task
        loop = asyncio.get_event_loop()
        task = loop.run_in_executor(None, runner.run)
        self.active_tasks[key] = task

    def run(self):
        # 1. Start all existing items from DB
        for ex, sym, tf in self.db.get_watchlist():
            self._start_scanner(ex, sym, tf)

        # 2. Start Telegram Application
        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("add", self.add_command))
        app.add_handler(CommandHandler("remove", self.remove_command))
        app.add_handler(CommandHandler("list", self.list_command))
        
        print("🚀 Telegram Bot is live and listening for commands...")
        app.run_polling()
