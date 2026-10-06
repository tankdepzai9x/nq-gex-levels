"""Load a Cboe delayed-quotes JSON file into plain Python objects."""
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List

from .occ import parse_occ


@dataclass(frozen=True)
class Contract:
    root: str
    expiry: date
    kind: str      # 'C' or 'P'
    strike: float
    iv: float      # implied vol as a fraction, e.g. 0.18
    oi: float      # open interest (prior-day figure)
    bid: float
    ask: float


@dataclass
class Snapshot:
    symbol: str
    spot: float
    iv30: float                 # 30-day implied vol in percent, e.g. 18.6
    last_trade_et: datetime     # underlying's last trade, US Eastern wall-clock (naive)
    file_utc: datetime          # when Cboe generated the file, UTC (naive)
    contracts: List[Contract] = field(default_factory=list)
    skipped: int = 0            # option symbols we could not parse


def load_snapshot(obj):
    """Build a Snapshot from the parsed JSON (dict). Raises ValueError if key fields are missing."""
    try:
        data = obj["data"]
        spot = float(data["current_price"])
        last_trade = data["last_trade_time"]
        file_ts = obj["timestamp"]
        options = data["options"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"unexpected Cboe file layout: missing {exc}") from exc
    if not last_trade:
        raise ValueError("Cboe file has no last_trade_time for the underlying")
    contracts, skipped = [], 0
    for o in options:
        parsed = parse_occ(o.get("option", ""))
        if parsed is None:
            skipped += 1
            continue
        root, expiry, kind, strike = parsed
        contracts.append(Contract(
            root=root, expiry=expiry, kind=kind, strike=strike,
            iv=float(o.get("iv") or 0.0), oi=float(o.get("open_interest") or 0.0),
            bid=float(o.get("bid") or 0.0), ask=float(o.get("ask") or 0.0)))
    return Snapshot(
        symbol=str(obj.get("symbol") or data.get("symbol") or ""),
        spot=spot, iv30=float(data.get("iv30") or 0.0),
        last_trade_et=datetime.fromisoformat(last_trade),
        file_utc=datetime.strptime(file_ts, "%Y-%m-%d %H:%M:%S"),
        contracts=contracts, skipped=skipped)
