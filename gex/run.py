"""Command-line entry: download NDX + QQQ, compute levels, write the paste file.

    python -m gex.run --slot auto --out levels/levels.txt --history levels/history --skip-if-fresh
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from .chain import load_snapshot
from .compute import build_records, compute_levels
from .encode import decode, encode
from .fetch import fetch_json
from .timeutil import et_to_utc, from_ms, next_session_ms, round_minute, slot_for, to_ms, utc_to_et

RATE = 0.04                       # rough risk-free rate; only used for put-call parity and discounting
SETS = {"NEAR": 7, "WIDE": 45}    # expiry windows, calendar days after the as-of date


def build_paste(ndx_obj, qqq_obj, now_utc, slot, rate=RATE):
    """Returns (paste_text, notes). Raises RuntimeError if either expiry set has no usable contracts."""
    ndx, qqq = load_snapshot(ndx_obj), load_snapshot(qqq_obj)
    anchor_et = round_minute(min(ndx.last_trade_et, qqq.last_trade_et))
    ratio = ndx.spot / qqq.spot
    max_days = max(SETS.values())
    recs_ndx, notes_ndx = build_records(ndx, anchor_et, max_days, rate, 1.0)
    recs_qqq, notes_qqq = build_records(qqq, anchor_et, max_days, rate, ratio)
    recs = recs_ndx + recs_qqq
    notes = [f"as-of {anchor_et} ET, NDX {ndx.spot:.2f}, QQQ {qqq.spot:.2f}, ratio {ratio:.3f}",
             f"unparsed symbols: NDX {ndx.skipped}, QQQ {qqq.skipped}"] + notes_ndx + notes_qqq
    sets = {}
    for name, days in SETS.items():
        subset = [r for r in recs if r.days <= days]
        levels = compute_levels(subset, ndx.iv30, ndx.spot, rate)
        if levels is None:
            raise RuntimeError(f"no usable contracts for expiry set {name}")
        sets[name] = levels
        notes.append(f"{name}: {len(subset)} contracts, regime {levels.reg}")
    text = encode(to_ms(now_utc), slot, to_ms(et_to_utc(anchor_et)), next_session_ms(slot, now_utc), sets)
    return text, notes


def already_fresh(existing_text, new_text):
    """True if the file on disk is the same slot, same as-of moment and same Eastern date as the new result."""
    try:
        old, new = decode(existing_text), decode(new_text)
    except ValueError:
        return False
    if not old["gen"] or not new["gen"]:
        return False
    same_day = utc_to_et(from_ms(old["gen"])).date() == utc_to_et(from_ms(new["gen"])).date()
    return old["slot"] == new["slot"] and old["anchor"] == new["anchor"] and same_day


def slot_ran_today(path, slot, now_utc):
    """True if the file at `path` already holds this slot's result from today (Eastern date), made inside the slot's own window."""
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8") as fh:
        try:
            old = decode(fh.read())
        except ValueError:
            return False
    return (bool(old["gen"]) and old["slot"] == slot and slot_for(from_ms(old["gen"]), "auto") == slot
            and utc_to_et(from_ms(old["gen"])).date() == utc_to_et(now_utc).date())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", default="auto", choices=["auto", "am", "mid", "pm"])
    ap.add_argument("--out", default="levels/levels.txt")
    ap.add_argument("--history", default="levels/history")
    ap.add_argument("--ndx-file", help="read NDX JSON from this file instead of downloading (tests)")
    ap.add_argument("--qqq-file", help="read QQQ JSON from this file instead of downloading (tests)")
    ap.add_argument("--now-utc", help="pretend it is this UTC time, ISO format (tests)")
    ap.add_argument("--skip-if-fresh", action="store_true")
    args = ap.parse_args(argv)

    now_utc = datetime.fromisoformat(args.now_utc) if args.now_utc else datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    slot = slot_for(now_utc, args.slot)
    if slot is None:
        print(f"{now_utc} UTC is outside the run windows; nothing to do.")
        return 0

    if args.skip_if_fresh and slot_ran_today(args.out, slot, now_utc):
        print(f"{args.out} already holds today's {slot} run; skipping (nothing downloaded).")
        return 0

    def load(path, symbol):
        if path:
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        return fetch_json(symbol)

    text, notes = build_paste(load(args.ndx_file, "_NDX"), load(args.qqq_file, "QQQ"), now_utc, slot)
    for line in notes:
        print(line)

    if args.skip_if_fresh and os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as fh:
            if already_fresh(fh.read(), text):
                print("Existing file is already this slot's result; skipping.")
                return 0

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, args.out)

    os.makedirs(args.history, exist_ok=True)
    et_day = utc_to_et(now_utc).date().isoformat()
    with open(os.path.join(args.history, f"{et_day}_{slot}.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"wrote {args.out} ({slot} slot)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
