"""Parse OCC option symbols such as 'QQQ261130C00620000' or 'NDXP261009P31625000'."""
import re
from datetime import date

_OCC = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")


def parse_occ(symbol):
    """Return (root, expiry_date, 'C' or 'P', strike) or None if the symbol is not standard."""
    m = _OCC.match(symbol or "")
    if not m:
        return None
    root, yy, mm, dd, kind, strike = m.groups()
    try:
        expiry = date(2000 + int(yy), int(mm), int(dd))
    except ValueError:
        return None
    return root, expiry, kind, int(strike) / 1000.0
