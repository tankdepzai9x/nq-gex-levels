"""Turn option chains into NQ-relative GEX levels.

Every level is a DISTANCE in NQ points from NQ's price at the data's as-of moment (positive = above).
The Pine indicator adds the chart's own NQ price at that moment, so this code never needs an NQ price.
"""
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import List, Optional, Tuple

from .bs import dollar_gamma_per_pct
from .forward import estimate_forward

CONTRACT_SIZE = 100.0
BUCKET = 25.0                                   # NQ points per strike bucket
MAX_DIST = 1000.0                               # walls and top strikes are only taken within +/- this many NQ points
MIN_SEP = 50.0                                  # top strikes must be at least this many NQ points apart
GRID = [i / 1000.0 for i in range(-50, 51)]     # -5.0% .. +5.0% in 0.1% steps


@dataclass(frozen=True)
class Rec:
    kind: str       # 'C' or 'P'
    strike: float   # native strike (index points for NDX, dollars for QQQ)
    fwd: float      # that expiry's forward, native units
    T: float        # years to expiry
    days: int       # calendar days to expiry
    iv: float
    oi: float
    scale: float    # converts native distance to NQ points (1 for NDX, NDX/QQQ ratio for QQQ)


@dataclass
class Levels:
    reg: str                                    # 'P' positive gamma or 'N' negative
    flip: Optional[float] = None                # NQ-point distance, None if net GEX never changes sign
    cw: Optional[float] = None                  # call wall distance
    pw: Optional[float] = None                  # put wall distance
    top: List[Tuple[float, bool]] = field(default_factory=list)   # (distance, net GEX positive?)
    em: float = 0.0                             # 1-day expected move, NQ points (one-sided)
    profile: List[Tuple[float, float]] = field(default_factory=list)   # (distance, net GEX $ per 1%) for every bucket within MAX_DIST


def years_to_expiry(expiry, anchor_et):
    """Years from the as-of moment to that expiry's 16:00 ET close (fractional for same-day 0DTE contracts)."""
    close = datetime.combine(expiry, time(16, 0))
    return (close - anchor_et).total_seconds() / (365.0 * 86400.0)


def build_records(snap, anchor_et, max_days, rate, scale):
    """Usable contracts (open interest and IV present) with each expiry's own forward. Returns (records, notes).

    anchor_et is the as-of moment (US Eastern, naive). Contracts that have already expired at that moment are dropped.
    """
    groups = defaultdict(list)
    for c in snap.contracts:
        days = (c.expiry - anchor_et.date()).days
        if days <= max_days and years_to_expiry(c.expiry, anchor_et) > 0:
            groups[(c.root, c.expiry)].append(c)
    recs, notes = [], []
    for (root, expiry), contracts in sorted(groups.items()):
        days = (expiry - anchor_et.date()).days
        T = years_to_expiry(expiry, anchor_et)
        fwd = estimate_forward(contracts, T, rate, snap.spot)
        if fwd is None:
            notes.append(f"{root} {expiry}: no strike with both a call and a put quote; skipped")
            continue
        if fwd <= 0:
            notes.append(f"{root} {expiry}: put-call parity gives a non-positive forward ({fwd:.2f}); skipped")
            continue
        for c in contracts:
            if c.oi > 0 and c.iv > 0 and c.strike > 0:
                recs.append(Rec(c.kind, c.strike, fwd, T, days, c.iv, c.oi, scale))
    return recs, notes


def net_gex_at(recs, x, rate):
    """Net dealer GEX in dollars per 1% move if the underlying were `x` (e.g. -0.01) away from now.

    Calls count positive, puts negative (the usual dealer-positioning assumption).
    """
    total = 0.0
    for r in recs:
        g = dollar_gamma_per_pct(r.fwd * (1.0 + x), r.strike, r.T, r.iv, rate) * r.oi * CONTRACT_SIZE
        total += g if r.kind == "C" else -g
    return total


def flip_x(curve):
    """Where a [(x, net_gex), ...] curve crosses zero, nearest to x=0 (linear interpolation). None if it never does."""
    crossings = []
    for (x0, g0), (x1, g1) in zip(curve, curve[1:]):
        if g0 == 0:
            crossings.append(x0)
        elif g0 * g1 < 0:
            crossings.append(x0 + (x1 - x0) * g0 / (g0 - g1))
    if curve and curve[-1][1] == 0:
        crossings.append(curve[-1][0])
    return min(crossings, key=abs) if crossings else None


def bucket_of(distance):
    return math.floor(distance / BUCKET + 0.5) * BUCKET


def pick_top(net, buckets, top_n, min_sep=MIN_SEP):
    """The top_n buckets by absolute net GEX, skipping any bucket closer than min_sep points to one already chosen."""
    chosen = []
    for b in sorted(buckets, key=lambda b: (-abs(net[b]), b)):
        if all(abs(b - c) >= min_sep for c in chosen):
            chosen.append(b)
        if len(chosen) == top_n:
            break
    return chosen


def compute_levels(recs, iv30, nq_scale, rate, top_n=5):
    """Levels for one expiry set. Returns None if there are no records."""
    if not recs:
        return None
    calls, puts = defaultdict(float), defaultdict(float)
    for r in recs:
        g = dollar_gamma_per_pct(r.fwd, r.strike, r.T, r.iv, rate) * r.oi * CONTRACT_SIZE
        b = bucket_of((r.strike - r.fwd) * r.scale)
        (calls if r.kind == "C" else puts)[b] += g
    net = {b: calls.get(b, 0.0) - puts.get(b, 0.0) for b in set(calls) | set(puts)}
    above = {b: g for b, g in calls.items() if 0 < b <= MAX_DIST}
    below = {b: g for b, g in puts.items() if -MAX_DIST <= b < 0}
    near_buckets = [b for b in net if abs(b) <= MAX_DIST]
    top = pick_top(net, near_buckets, top_n)
    curve = [(x, net_gex_at(recs, x, rate)) for x in GRID]
    fx = flip_x(curve)
    return Levels(
        reg="P" if net_gex_at(recs, 0.0, rate) >= 0 else "N",
        flip=None if fx is None else fx * nq_scale,
        cw=max(above, key=lambda b: (above[b], -b)) if above else None,
        pw=min(below, key=lambda b: (-below[b], b)) if below else None,
        top=[(b, net[b] >= 0) for b in sorted(top)],
        em=nq_scale * (iv30 / 100.0) * math.sqrt(1.0 / 252.0),
        profile=sorted((b, net[b]) for b in near_buckets),
    )
