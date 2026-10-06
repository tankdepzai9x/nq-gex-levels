"""Estimate an expiry's forward price from put-call parity."""
import math


def mid_price(contract):
    """Mid of bid/ask, or None when there is no two-sided quote."""
    if contract.bid > 0 and contract.ask >= contract.bid:
        return (contract.bid + contract.ask) / 2.0
    return None


def estimate_forward(contracts, T, rate, ref, n=5):
    """Forward price F for ONE expiry, from the n strikes nearest `ref` that have both a call and a put quote.

    Parity: C - P = exp(-rT) * (F - K)  =>  F = K + exp(rT) * (C - P). Returns the median, or None if no strike
    has both quotes.
    """
    calls, puts = {}, {}
    for c in contracts:
        m = mid_price(c)
        if m is None:
            continue
        (calls if c.kind == "C" else puts)[c.strike] = m
    strikes = sorted((k for k in calls if k in puts), key=lambda k: abs(k - ref))[:n]
    if not strikes:
        return None
    ests = sorted(k + math.exp(rate * T) * (calls[k] - puts[k]) for k in strikes)
    return ests[len(ests) // 2]
