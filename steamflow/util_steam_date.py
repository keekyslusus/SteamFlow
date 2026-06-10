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


def _tr(translator, key, default, **values):
    if callable(translator):
        try:
            return translator(key, **values)
        except Exception:
            pass
    if values:
        try:
            return default.format(**values)
        except Exception:
            return default
    return default


def _month_abbreviation(month, tr=None):
    try:
        month = int(month)
    except (TypeError, ValueError):
        month = 1
    if 1 <= month <= 12:
        default = MONTH_ABBREVIATIONS[month - 1]
    else:
        default = ""
    return _tr(tr, f"date.month.short.{month}", default)


def _format_absolute_date(date_value, now, tr=None):
    month = _month_abbreviation(date_value.month, tr=tr)
    if date_value.year == now.year:
        return _tr(
            tr,
            "date.format.short",
            "{month} {day}",
            month=month,
            day=date_value.day,
        )
    return _tr(
        tr,
        "date.format.short_with_year",
        "{month} {day}, {year}",
        month=month,
        day=date_value.day,
        year=date_value.year,
    )


def format_steam_last_played(unix_timestamp, now=None, tr=None):
    try:
        played_at = datetime.fromtimestamp(int(unix_timestamp))
    except (OverflowError, TypeError, ValueError, OSError):
        return ""

    now = now or datetime.now()
    played_date = played_at.date()
    today = now.date()
    delta_days = (today - played_date).days

    if delta_days == 0:
        return _tr(tr, "relative.today", "Today")
    if delta_days == 1:
        return _tr(tr, "relative.yesterday", "Yesterday")
    if 2 <= delta_days <= 7:
        return _tr(tr, "relative.days_ago", "{count} days ago", count=delta_days)

    return _format_absolute_date(played_at, now, tr=tr)


def format_relative_minutes_ago(total_minutes, tr=None):
    try:
        total_minutes = max(0, int(total_minutes))
    except (TypeError, ValueError):
        return ""

    if total_minutes < 60:
        return _tr(tr, "relative.minutes_short_ago", "{count}m ago", count=total_minutes)

    total_hours = total_minutes // 60
    if total_hours < 24:
        return _tr(tr, "relative.hours_short_ago", "{count}h ago", count=total_hours)

    total_days = total_hours // 24
    return _tr(tr, "relative.days_short_ago", "{count}d ago", count=total_days)


def format_wishlisted_date(unix_timestamp, now=None, tr=None):
    try:
        wishlisted_at = datetime.fromtimestamp(int(unix_timestamp))
    except (OverflowError, TypeError, ValueError, OSError):
        return ""

    now = now or datetime.now()
    wishlisted_date = wishlisted_at.date()
    today = now.date()
    delta_days = (today - wishlisted_date).days

    if delta_days == 0:
        return _tr(tr, "relative.today", "Today")
    if delta_days == 1:
        return _tr(tr, "relative.yesterday", "Yesterday")
    if 2 <= delta_days <= 7:
        return _tr(tr, "relative.days_short_ago", "{count}d ago", count=delta_days)

    return _format_absolute_date(wishlisted_at, now, tr=tr)
