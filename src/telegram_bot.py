import os
import asyncio
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from .data.db import TradingDB
from .runner import ScannersManager
from .services.exchange_service import ExchangeService

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

class TradingTelegramBot:
    def __init__(self, split_mode: bool = False):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.split_mode = split_mode
        # Bot is always the WRITER if it needs to update the watchlist
        self.db = TradingDB(read_only=False)
        self.manager = None if split_mode else ScannersManager(self.token)
        self.exchange_service = ExchangeService()

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("👋 Welcome! Use /add <ex> <sym> <tf> to start a scanner.\nExample: /add binance BTC/USDT:USDT 15m")

    async def add_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            logging.info(f"Adding scanner: {context.args} from {update.effective_chat.id}")
            ex, sym, tf = context.args
            chat_id = update.effective_chat.id
            self.db.add_to_watchlist(chat_id, ex, sym, tf)
            if self.manager:
                await self.manager.start_scanner(ex, sym, tf)
            await update.message.reply_text(f"✅ Added {sym} ({tf}) on {ex}. You will be notified of signals!")
        except Exception as e:
            logging.error(f"Error in /add command: {e}", exc_info=True)
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

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "🤖 **sarema-squeeze bot Help**\n\n"
            "**/start** - Welcome message\n"
            "**/add <ex> <sym> <tf>** - Start monitoring a pair\n"
            "Example: `/add binance BTC/USDT:USDT 15m`\n\n"
            "**/search <name>** or **/search <ex> <name>** - Search for symbols\n"
            "Example: `/search BTCUSDTPERP` or `/search bybit BTCUSDT`\n\n"
            "**/remove <ex> <sym> <tf>** - Stop monitoring a pair\n"
            "Example: `/remove binance BTC/USDT:USDT 15m`\n\n"
            "**/list** - Show your active watchlist\n"
            "**/help** - Show this help message"
        )
        await update.message.reply_text(help_text, parse_mode="Markdown")

    async def search_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Usage: /search <TradingView_Name> or /search <exchange> <name>\nExample: /search BTCUSDTPERP or /search bybit BTCUSDT")
            return

        # Case 1: /search bybit BTCUSDT
        if len(context.args) >= 2:
            exchange_id = context.args[0].lower()
            query = context.args[1].upper()
        # Case 2: /search BYBIT:BTCUSDT
        else:
            query = context.args[0].upper()
            exchange_id = None # Let service parse EXCHANGE:SYMBOL or fallback

        await update.message.reply_text(f"🔍 Searching for **{query}**" + (f" on **{exchange_id}**" if exchange_id else "") + "...")

        try:
            target_exchange, matches = await self.exchange_service.search_symbols(query, exchange_id=exchange_id)
            
            if matches:
                msg = f"✅ Found matches on **{target_exchange.upper()}**:\n\n"
                for m_full in matches[:10]:
                    # m_full looks like "BTC/USDT:USDT (SWAP)"
                    m_symbol = m_full.split(" (")[0]
                    msg += f"`/add {target_exchange} {m_symbol} 15m` - {m_full}\n"
                if len(matches) > 10:
                    msg += f"\n...and {len(matches)-10} more."
                await update.message.reply_text(msg, parse_mode="Markdown")
            else:
                target_str = target_exchange.upper() if target_exchange else "common exchanges"
                await update.message.reply_text(f"❌ No matches found for '{query}' on {target_str}.")
        except Exception as e:
            logging.error(f"Search error: {e}")
            await update.message.reply_text(f"⚠️ Error during search: {str(e)}")

    async def run_bot(self):
        # 1. Start all existing items from DB (only if NOT in split mode)
        if not self.split_mode:
            await self.manager.start_all()

        # 2. Start Telegram Application
        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("add", self.add_command))
        app.add_handler(CommandHandler("search", self.search_command))
        app.add_handler(CommandHandler("remove", self.remove_command))
        app.add_handler(CommandHandler("list", self.list_command))
        app.add_handler(CommandHandler("help", self.help_command))
        
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
