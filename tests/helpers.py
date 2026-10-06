"""Builders for small, fully known Cboe-style option chains used by the tests."""
from gex.bs import black76_price


def make_option(root, expiry, kind, strike, fwd, T, sigma, oi, rate=0.04, half_spread=0.5):
    """One option dict priced with Black-76 so put-call parity recovers `fwd` exactly."""
    price = black76_price(fwd, strike, T, sigma, rate, kind)
    return {
        "option": f"{root}{expiry:%y%m%d}{kind}{int(round(strike * 1000)):08d}",
        "bid": max(round(price - half_spread, 4), 0.0),
        "ask": round(price + half_spread, 4),
        "iv": sigma,
        "open_interest": float(oi),
        "volume": 0.0,
        "delta": 0.0,
        "gamma": 0.0,
    }


def make_chain(root, expiry, days, fwd, strikes, oi_for, sigma=0.2, rate=0.04, half_spread=0.5):
    """Calls and puts at every strike. oi_for(kind, strike) gives the open interest."""
    T = days / 365.0
    out = []
    for k in strikes:
        for kind in ("C", "P"):
            out.append(make_option(root, expiry, kind, k, fwd, T, sigma, oi_for(kind, k), rate, half_spread))
    return out


def make_file(symbol, spot, last_trade, file_ts, options, iv30=18.0):
    """Wrap options in the same envelope Cboe uses."""
    return {
        "timestamp": file_ts,
        "symbol": symbol,
        "data": {"symbol": symbol, "current_price": spot, "iv30": iv30,
                 "last_trade_time": last_trade, "options": options},
    }
