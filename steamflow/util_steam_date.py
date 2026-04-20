from datetime import datetime


MONTH_ABBREVIATIONS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def format_steam_last_played(unix_timestamp, now=None):
    try:
        played_at = datetime.fromtimestamp(int(unix_timestamp))
    except (OverflowError, TypeError, ValueError, OSError):
        return ""

    now = now or datetime.now()
    played_date = played_at.date()
    today = now.date()
    delta_days = (today - played_date).days

    if delta_days == 0:
        return "Today"
    if delta_days == 1:
        return "Yesterday"
    if 2 <= delta_days <= 7:
        return f"{delta_days} days ago"

    month = MONTH_ABBREVIATIONS[played_at.month - 1]
    if played_at.year == now.year:
        return f"{month} {played_at.day}"
    return f"{month} {played_at.day}, {played_at.year}"


def format_relative_minutes_ago(total_minutes):
    try:
        total_minutes = max(0, int(total_minutes))
    except (TypeError, ValueError):
        return ""

    if total_minutes < 60:
        return f"{total_minutes}m ago"

    total_hours = total_minutes // 60
    if total_hours < 24:
        return f"{total_hours}h ago"

    total_days = total_hours // 24
    return f"{total_days}d ago"


def format_wishlisted_date(unix_timestamp, now=None):
    try:
        wishlisted_at = datetime.fromtimestamp(int(unix_timestamp))
    except (OverflowError, TypeError, ValueError, OSError):
        return ""

    now = now or datetime.now()
    wishlisted_date = wishlisted_at.date()
    today = now.date()
    delta_days = (today - wishlisted_date).days

    if delta_days == 0:
        return "Today"
    if delta_days == 1:
        return "Yesterday"
    if 2 <= delta_days <= 7:
        return f"{delta_days}d ago"

    month = MONTH_ABBREVIATIONS[wishlisted_at.month - 1]
    if wishlisted_at.year == now.year:
        return f"{month} {wishlisted_at.day}"
    return f"{month} {wishlisted_at.day}, {wishlisted_at.year}"
