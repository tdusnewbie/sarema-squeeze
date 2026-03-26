import requests
import os
from .models import Signal
import typer

class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_signal(self, signal: Signal):
        """Send a formatted trading signal to Telegram."""
        emoji = "🚀" if signal.type == "LONG" else "td" # Typer doesn't like some emojis in code strings sometimes
        # Let's use standard strings
        type_emoji = "🟢 LONG" if signal.type == "LONG" else "🔴 SHORT"
        
        message = (
            f"{type_emoji} **{signal.symbol}** ({signal.timeframe})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Price:** {signal.price}\n"
            f"⏰ **Time:** {signal.timestamp.astimezone().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📝 **Message:** {signal.message}\n"
            f"⚡ **Strict Mode:** {'Yes' if signal.is_hard else 'No'}"
        )

        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }

        try:
            response = requests.post(self.base_url, json=payload)
            response.raise_for_status()
            typer.echo(f"📨 Telegram alert sent for {signal.type}")
        except Exception as e:
            typer.echo(f"❌ Failed to send Telegram alert: {e}", err=True)
