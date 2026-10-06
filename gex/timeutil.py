"""US Eastern time helpers with the daylight-saving rule built in.

No tzdata needed, so the tests pass on Windows as well as on the GitHub runner.
All datetimes here are naive: "utc" values are UTC, "et" values are US Eastern wall-clock.
"""
from datetime import date, datetime, timedelta

EPOCH = datetime(1970, 1, 1)


def _nth_sunday(year, month, n):
    first_of_month = date(year, month, 1)
    first_sunday = first_of_month + timedelta(days=(6 - first_of_month.weekday()) % 7)
    return first_sunday + timedelta(weeks=n - 1)


def dst_bounds_utc(year):
    """(start, end) of US daylight time as naive UTC datetimes.

    Starts 2nd Sunday of March at 02:00 EST (07:00 UTC); ends 1st Sunday of November at 02:00 EDT (06:00 UTC).
    """
    start = datetime.combine(_nth_sunday(year, 3, 2), datetime.min.time()) + timedelta(hours=7)
    end = datetime.combine(_nth_sunday(year, 11, 1), datetime.min.time()) + timedelta(hours=6)
    return start, end


def et_offset_hours(utc):
    """Hours Eastern is behind UTC at this UTC moment: 4 (EDT) or 5 (EST)."""
    start, end = dst_bounds_utc(utc.year)
    return 4 if start <= utc < end else 5


def utc_to_et(utc):
    return utc - timedelta(hours=et_offset_hours(utc))


def et_to_utc(et):
    for off in (4, 5):
        candidate = et + timedelta(hours=off)
        if et_offset_hours(candidate) == off:
            return candidate
    return et + timedelta(hours=5)


def to_ms(utc):
    return int((utc - EPOCH).total_seconds() * 1000)


def from_ms(ms):
    return EPOCH + timedelta(milliseconds=ms)


def round_minute(dt):
    """Round a datetime to the nearest whole minute (15:59:59 -> 16:00:00)."""
    return (dt + timedelta(seconds=30)).replace(second=0, microsecond=0)


def next_session_ms(slot, run_utc):
    """When the NEXT paste is due, as epoch ms (UTC).

    After the 'am' or 'mid' run the next paste is due by 19:00 ET the same day (the evening run is at 18:30 ET).
    After the 'pm' run it is the 09:30 ET session on the next weekday.
    """
    et = utc_to_et(run_utc)
    if slot in ("am", "mid"):
        target = datetime.combine(et.date(), datetime.min.time()) + timedelta(hours=19)
    elif slot == "pm":
        day = et.date() + timedelta(days=1)
        while day.weekday() >= 5:
            day += timedelta(days=1)
        target = datetime.combine(day, datetime.min.time()) + timedelta(hours=9, minutes=30)
    else:
        raise ValueError("slot must be 'am', 'mid' or 'pm'")
    return to_ms(et_to_utc(target))


def slot_for(run_utc, mode):
    """Which slot a run belongs to. mode: 'am' | 'mid' | 'pm' | 'auto'.

    'auto' returns None outside the windows (am 08:20-09:55 ET, mid 10:05-11:45 ET, pm 18:10-20:30 ET)
    so a run fired by the wrong-season cron entry either does nothing or is skipped as a duplicate.
    """
    if mode in ("am", "mid", "pm"):
        return mode
    et = utc_to_et(run_utc)
    minutes = et.hour * 60 + et.minute
    if 8 * 60 + 20 <= minutes <= 9 * 60 + 55:
        return "am"
    if 10 * 60 + 5 <= minutes <= 11 * 60 + 45:
        return "mid"
    if 18 * 60 + 10 <= minutes <= 20 * 60 + 30:
        return "pm"
    return None
