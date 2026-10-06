"""The paste format shared by the Python job and the Pine indicator.

    GEX1
    gen 1791230400000          when the job ran (epoch ms, UTC)
    slot am                    am, mid or pm
    anchor 1791230400000       the moment the option quotes are from (epoch ms, UTC): the indicator looks up NQ's price then
    next 1791273600000         when the next paste is due; the indicator turns red after this
    set NEAR                   a block of levels for one expiry set
    reg P                      P = positive gamma, N = negative
    flip -312                  distance in NQ points from the anchor price (omitted if there is no flip)
    cw 650
    pw -425
    top 100:+ -200:- 650:+     up to 5 strikes; + means net GEX is positive there
    em 365                     one-sided 1-day expected move
    prof -100:-4200 -75:350 0:12000   the bar column: distance in NQ points : net GEX in thousands of dollars per 1% move

The Pine script has its own copy of this parser; keep the two in step.
"""


def _n(value):
    return str(int(round(value)))


def encode(gen_ms, slot, anchor_ms, next_ms, sets):
    lines = ["GEX1", f"gen {gen_ms}", f"slot {slot}", f"anchor {anchor_ms}", f"next {next_ms}"]
    for name, lv in sets.items():
        lines += [f"set {name}", f"reg {lv.reg}"]
        if lv.flip is not None:
            lines.append(f"flip {_n(lv.flip)}")
        if lv.cw is not None:
            lines.append(f"cw {_n(lv.cw)}")
        if lv.pw is not None:
            lines.append(f"pw {_n(lv.pw)}")
        if lv.top:
            lines.append("top " + " ".join(f"{_n(d)}:{'+' if pos else '-'}" for d, pos in lv.top))
        lines.append(f"em {_n(lv.em)}")
        cells = [(d, round(v / 1000.0)) for d, v in lv.profile]
        cells = [f"{_n(d)}:{k}" for d, k in cells if k != 0]
        if cells:
            lines.append("prof " + " ".join(cells))
    return "\n".join(lines) + "\n"


def _top_cell(token):
    """One 'distance:+' or 'distance:-' token of a top line."""
    dist, _, flag = token.partition(":")
    if flag in ("+", "-"):
        try:
            return float(dist), flag == "+"
        except ValueError:
            pass
    raise ValueError(f"bad top token {token!r}: expected distance:+ or distance:-")


def _prof_cell(token):
    """One 'distance:thousands' token of a prof line."""
    dist, _, value = token.partition(":")
    try:
        return float(dist), float(value)
    except ValueError:
        raise ValueError(f"bad prof token {token!r}: expected distance:value") from None


def decode(text):
    """Reference parser. Returns {'gen','slot','anchor','next','sets':{name:{...}}}. Raises ValueError on bad input."""
    lines = [ln.strip() for ln in text.replace("\r", "").lstrip("\ufeff").split("\n") if ln.strip()]
    if not lines or lines[0] != "GEX1":
        raise ValueError("not a GEX1 levels block")
    out = {"gen": None, "slot": None, "anchor": None, "next": None, "sets": {}}
    cur = None
    for ln in lines[1:]:
        key, _, rest = ln.partition(" ")
        if key in ("gen", "anchor", "next"):
            out[key] = int(rest)
        elif key == "slot":
            out["slot"] = rest
        elif key == "set":
            cur = out["sets"].setdefault(
                rest, {"reg": None, "flip": None, "cw": None, "pw": None, "top": [], "em": None, "prof": []})
        elif cur is not None and key == "reg":
            cur["reg"] = rest
        elif cur is not None and key in ("flip", "cw", "pw", "em"):
            cur[key] = float(rest)
        elif cur is not None and key == "top":
            cur["top"] = [_top_cell(t) for t in rest.split()]
        elif cur is not None and key == "prof":
            cur["prof"] = [_prof_cell(t) for t in rest.split()]
    return out
