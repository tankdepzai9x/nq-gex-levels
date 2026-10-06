"""Find out when Cboe's open interest changes.

    python -m gex.probe             append one row per symbol to probe/oi_probe.csv (run every 30 minutes for 2 days)
    python -m gex.probe --analyze   print every moment total open interest changed, in Eastern time
"""
import argparse
import csv
import os
import sys
from datetime import datetime, timezone

from .chain import load_snapshot
from .fetch import fetch_json
from .timeutil import utc_to_et

FIELDS = ["utc", "symbol", "file_utc", "last_trade_et", "spot", "contracts", "total_oi"]
SYMBOLS = ("_NDX", "QQQ")


def row_for(symbol, obj, now_utc):
    snap = load_snapshot(obj)
    return {
        "utc": now_utc.isoformat(timespec="seconds"),
        "symbol": symbol,
        "file_utc": snap.file_utc.isoformat(sep=" "),
        "last_trade_et": snap.last_trade_et.isoformat(),
        "spot": snap.spot,
        "contracts": len(snap.contracts),
        "total_oi": int(sum(c.oi for c in snap.contracts)),
    }


def append_rows(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    new_file = not os.path.exists(path)
    with open(path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        if new_file:
            writer.writeheader()
        writer.writerows(rows)


def changes(path):
    """[(symbol, eastern time string, old total OI, new total OI)] for every row whose total OI differs from the last."""
    last, out = {}, []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            sym, oi = row["symbol"], int(row["total_oi"])
            if sym in last and oi != last[sym]:
                et = utc_to_et(datetime.fromisoformat(row["utc"]))
                out.append((sym, et.strftime("%a %Y-%m-%d %H:%M ET"), last[sym], oi))
            last[sym] = oi
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="probe/oi_probe.csv")
    ap.add_argument("--analyze", action="store_true")
    args = ap.parse_args(argv)
    if args.analyze:
        for sym, when, old, new in changes(args.csv):
            print(f"{sym:5s} {when}  total OI {old:,} -> {new:,}")
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    append_rows(args.csv, [row_for(s, fetch_json(s), now) for s in SYMBOLS])
    print(f"logged {len(SYMBOLS)} rows at {now} UTC")
    return 0


if __name__ == "__main__":
    sys.exit(main())
