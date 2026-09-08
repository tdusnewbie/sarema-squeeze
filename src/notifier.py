import os
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import requests
import typer
from .models import Signal


def parse_timezone(tz_input: str | int | float | None = None) -> ZoneInfo | timezone:
    """
    Parses a timezone input into a ZoneInfo or timezone object.
    Supports:
      - IANA timezone strings (e.g. 'Asia/Ho_Chi_Minh', 'America/New_York', 'UTC')
      - Fixed offset numbers or strings (e.g. 7, -5, '+7', '-5', '+07:00', 'UTC+7', 'GMT-5')
      - Environment variables fallback (TZ, TIMEZONE, TIMEZONE_OFFSET, TZ_OFFSET)
    """
    if tz_input is None or str(tz_input).strip() == "":
        tz_input = (
            os.getenv("TZ")
            or os.getenv("TIMEZONE")
            or os.getenv("TIMEZONE_OFFSET")
            or os.getenv("TZ_OFFSET")
            or "UTC"
        )

    if isinstance(tz_input, (int, float)):
        return timezone(timedelta(hours=tz_input))

    tz_str = str(tz_input).strip()

    # Try numeric string (e.g. "7", "-5", "+7.5")
    try:
        val = float(tz_str)
        return timezone(timedelta(hours=val))
    except ValueError:
        pass

    # Check for UTC/GMT/Offset strings (e.g. "UTC+7", "+07:00", "-0500")
    match = re.match(r"^(?:UTC|GMT)?([+-])(\d{1,2})(?::?(\d{2}))?$", tz_str, re.IGNORECASE)
    if match:
        sign, hours, minutes = match.groups()
        h = int(hours)
        m = int(minutes) if minutes else 0
        delta = timedelta(hours=h, minutes=m)
        if sign == "-":
            delta = -delta
        return timezone(delta)

    try:
        return ZoneInfo(tz_str)
    except (ZoneInfoNotFoundError, Exception):
        return timezone.utc


def format_tz_offset(dt: datetime) -> str:
    """Formats the UTC offset of a datetime as UTC+H or UTC+HH:MM."""
    offset = dt.utcoffset()
    if offset is None:
        return "UTC+0"
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    abs_seconds = abs(total_seconds)
    hours = abs_seconds // 3600
    minutes = (abs_seconds % 3600) // 60
    if minutes == 0:
        return f"UTC{sign}{hours}"
    return f"UTC{sign}{hours:02d}:{minutes:02d}"


class TelegramNotifier:
    def __init__(self, token: str, tz: str | int | None = None, tz_offset: int | None = None):
        self.token = token
        tz_target = tz if tz is not None else tz_offset
        self._tz = parse_timezone(tz_target)
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    @property
    def tz(self) -> ZoneInfo | timezone:
        return self._tz

    @tz.setter
    def tz(self, value: str | int | float | ZoneInfo | timezone | None):
        if isinstance(value, (ZoneInfo, timezone)):
            self._tz = value
        else:
            self._tz = parse_timezone(value)

    @property
    def tz_offset(self) -> int:
        """Backward compatibility helper for reading integer offset in hours."""
        offset = datetime.now(timezone.utc).astimezone(self._tz).utcoffset()
        return int(offset.total_seconds() // 3600) if offset else 0

    @tz_offset.setter
    def tz_offset(self, value: int | None):
        if value is not None:
            self._tz = parse_timezone(value)

    def send_signal(self, signal: Signal, chat_ids: list[int]):
        """Send a formatted trading signal to a list of Telegram chat IDs."""
        ts = signal.timestamp
        if hasattr(ts, "to_pydatetime"):
            ts = ts.to_pydatetime()

        if ts.tzinfo is None:
            # Naive timestamps from exchange candle data are UTC
            ts_utc = ts.replace(tzinfo=timezone.utc)
        else:
            ts_utc = ts.astimezone(timezone.utc)

        ts_local = ts_utc.astimezone(self._tz)
        tz_label = format_tz_offset(ts_local)

        type_emoji = "🟢 LONG" if signal.type == "LONG" else "🔴 SHORT"

        message = (
            f"{type_emoji} **{signal.symbol}** ({signal.timeframe})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 **Price:** {signal.price}\n"
            f"⏰ **Time:** {ts_local.strftime('%Y-%m-%d %H:%M:%S')} ({tz_label})\n"
            f"📝 **Message:** {signal.message}\n"
            f"⚡ **Strict Mode:** {'Yes' if signal.is_hard else 'No'}"
        )

        for chat_id in chat_ids:
            payload = {
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "Markdown",
            }

            try:
                response = requests.post(self.base_url, json=payload)
                response.raise_for_status()
                typer.echo(f"📨 Telegram alert sent to {chat_id}")
            except Exception as e:
                typer.echo(f"❌ Failed to send Telegram alert to {chat_id}: {e}", err=True)
