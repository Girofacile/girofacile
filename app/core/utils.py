from datetime import datetime
from zoneinfo import ZoneInfo

from .config import LOCAL_TIMEZONE

try:
    LOCAL_TZ = ZoneInfo(LOCAL_TIMEZONE)
except Exception:
    LOCAL_TZ = ZoneInfo("Europe/Rome")


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def local_today():
    return local_now().date()


def local_today_iso() -> str:
    return local_today().isoformat()



from datetime import date, time


def parse_date_value(value):
    """Converte stringhe ISO o oggetti date/datetime in date.

    Mantiene il frontend libero di inviare YYYY-MM-DD, mentre il database può
    salvare un vero tipo DATE.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def parse_time_value(value):
    """Converte HH:MM / HH:MM:SS / time/datetime in time."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0)
    if isinstance(value, time):
        return value.replace(microsecond=0)
    text = str(value).strip()
    if not text:
        return None
    try:
        parts = text.split(":")
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        ss = int(float(parts[2])) if len(parts) > 2 and parts[2] != "" else 0
        if 0 <= hh <= 23 and 0 <= mm <= 59 and 0 <= ss <= 59:
            return time(hh, mm, ss)
    except Exception:
        pass
    return None


def date_to_iso(value):
    parsed = parse_date_value(value)
    return parsed.isoformat() if parsed else None


def time_to_hhmm(value):
    parsed = parse_time_value(value)
    if not parsed:
        return None
    return f"{parsed.hour:02d}:{parsed.minute:02d}"


def minutes_from_hhmm(value) -> int | None:
    parsed = parse_time_value(value)
    if not parsed:
        return None
    return parsed.hour * 60 + parsed.minute
