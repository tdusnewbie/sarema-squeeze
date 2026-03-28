import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from .db import TradingDB
from .runner import ScannersManager

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

class TradingTelegramBot:
    def __init__(self, split_mode: bool = False):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.split_mode = split_mode
        # Bot is always the WRITER if it needs to update the watchlist
        self.db = TradingDB(read_only=False)
        self.manager = None if split_mode else ScannersManager(self.token)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("👋 Welcome! Use /add <ex> <sym> <tf> to start a scanner.\nExample: /add binance BTC/USDT:USDT 15m")

    async def add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            ex, sym, tf = context.args
            chat_id = update.effective_chat.id
            self.db.add_to_watchlist(chat_id, ex, sym, tf)
            if self.manager:
                await self.manager.start_scanner(ex, sym, tf)
            await update.message.reply_text(f"✅ Added {sym} ({tf}) on {ex}. You will be notified of signals!")
        except Exception as e:
            await update.message.reply_text("❌ Format: /add <exchange> <symbol> <timeframe>\nExample: /add binance BTC/USDT:USDT 15m")

    async def remove_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            ex, sym, tf = context.args
            chat_id = update.effective_chat.id
            self.db.remove_from_watchlist(chat_id, ex, sym, tf)
            if self.manager:
                await self.manager.stop_scanner(ex, sym, tf)
            await update.message.reply_text(f"🗑️ Removed {sym} ({tf}). Monitoring stopped for you.")
        except:
            await update.message.reply_text("❌ Format: /remove <exchange> <symbol> <timeframe>")

    async def list_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        items = self.db.get_watchlist(chat_id)
        if not items:
            await update.message.reply_text("📜 Your watchlist is empty.")
            return
        
        msg = "📋 **Your Watchlist:**\n"
        for ex, sym, tf in items:
            # Status display logic
            status = "🟢" if (not self.split_mode and self.manager and (ex, sym, tf) in self.manager.active_tasks) else "🟡"
            msg += f"{status} {ex.upper()}: {sym} [{tf}]\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def run_bot(self):
        # 1. Start all existing items from DB (only if NOT in split mode)
        if not self.split_mode:
            await self.manager.start_all()

        # 2. Start Telegram Application
        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("add", self.add_command))
        app.add_handler(CommandHandler("remove", self.remove_command))
        app.add_handler(CommandHandler("list", self.list_command))
        
        print("🚀 Telegram Bot is live and listening for commands...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        
        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit, asyncio.CancelledError):
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
            if self.manager:
                await self.manager.stop_all()

    def run(self):
        """Entry point for the bot."""
        asyncio.run(self.run_bot())
