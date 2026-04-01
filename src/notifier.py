import requests
import os
from .models import Signal
import typer

class TelegramNotifier:
    def __init__(self, token: str, tz_offset: int = 0):
        self.token = token
        self.tz_offset = tz_offset
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    def send_signal(self, signal: Signal, chat_ids: list[int]):
        """Send a formatted trading signal to a list of Telegram chat IDs."""
        from datetime import timedelta
        # Convert to pydatetime if it's a pandas Timestamp to avoid pandas 3.0.1 bug in astimezone()
        ts = signal.timestamp
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()
        
        # Apply timezone offset
        ts_local = ts + timedelta(hours=self.tz_offset)
            
        type_emoji = "🟢 LONG" if signal.type == "LONG" else "🔴 SHORT"
        
        message = (
            f"{type_emoji} **{signal.symbol}** ({signal.timeframe})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Price:** {signal.price}\n"
            f"⏰ **Time:** {ts_local.strftime('%Y-%m-%d %H:%M:%S')} (UTC{'+' if self.tz_offset >= 0 else ''}{self.tz_offset})\n"
            f"📝 **Message:** {signal.message}\n"
            f"⚡ **Strict Mode:** {'Yes' if signal.is_hard else 'No'}"
        )

        for chat_id in chat_ids:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }

            try:
                response = requests.post(self.base_url, json=payload)
                response.raise_for_status()
                typer.echo(f"📨 Telegram alert sent to {chat_id}")
            except Exception as e:
                typer.echo(f"❌ Failed to send Telegram alert to {chat_id}: {e}", err=True)
