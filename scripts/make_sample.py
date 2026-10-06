"""Print a sample GEX1 paste block for testing the indicator before the cloud job exists.

    python scripts/make_sample.py            sample as-of the most recent weekday 16:00 ET close
    python scripts/make_sample.py --fixed    the fixed sample used by the tests (as-of 2026-10-05 16:00 ET)

Paste the output into the indicator's "Paste levels" box on an NQ or MNQ chart. Distances are made up (they are not real
GEX), but the format is exactly what the cloud job writes.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gex.compute import Levels  # noqa: E402
from gex.encode import encode  # noqa: E402
from gex.timeutil import et_to_utc, next_session_ms, to_ms, utc_to_et  # noqa: E402


def last_close_et(now_utc):
    et = utc_to_et(now_utc)
    day = et.date() if et.hour >= 16 else et.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=16)


def sample_levels():
    profile = []
    for d in range(-300, 301, 25):
        sign = 1 if d >= -100 else -1
        profile.append((float(d), sign * (90e6 - abs(d) * 0.2e6)))
    return Levels(reg="P", flip=-120.0, cw=175.0, pw=-225.0, top=[(-100.0, True), (0.0, True), (175.0, True)],
                  em=365.0, profile=profile)


def build(now_utc, fixed=False):
    """fixed=True gives the byte-exact test fixture; otherwise the sample stays fresh for 12 hours."""
    anchor_ms = to_ms(et_to_utc(last_close_et(now_utc)))
    due_ms = next_session_ms("am", now_utc) if fixed else to_ms(now_utc) + 12 * 3600 * 1000
    sets = {"NEAR": sample_levels(), "WIDE": sample_levels()}
    return encode(to_ms(now_utc), "am", anchor_ms, due_ms, sets)


if __name__ == "__main__":
    sys.stdout.reconfigure(newline="\n")     # always plain LF, even on Windows
    fixed = "--fixed" in sys.argv
    now = datetime(2026, 10, 6, 12, 45) if fixed else datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    print(build(now, fixed), end="")
