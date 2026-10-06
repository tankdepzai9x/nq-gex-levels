"""Break the Python code on purpose and confirm the tests notice. Run from the repo root:

    python tools/mutation_check.py

Each line below changes one thing in a temporary copy of the repo. "CAUGHT" is good: a test failed.
"SURVIVED" means no test noticed, so a test is missing.
"""
import os
import shutil
import subprocess
import sys
import tempfile

MUTATIONS = [
    ("gex/compute.py", "return total\n", "return -total\n", "net GEX sign flipped"),
    ("gex/compute.py", "(r.strike - r.fwd) * r.scale", "(r.strike - r.fwd)", "QQQ scale ignored"),
    ("gex/compute.py", "0 < b <= MAX_DIST", "0 < b", "call wall distance cap removed"),
    ("gex/compute.py", "if all(abs(b - c) >= min_sep for c in chosen):", "if True:", "top strikes may sit next to each other"),
    ("gex/forward.py", "k + math.exp(rate * T) * (calls[k] - puts[k])", "k + (puts[k] - calls[k])", "parity inverted"),
    ("gex/timeutil.py", "return 4 if start <= utc < end else 5", "return 5", "daylight saving ignored"),
    ("gex/timeutil.py", "while day.weekday() >= 5:", "while False:", "weekend skip removed"),
    ("gex/timeutil.py", "timedelta(hours=19)", "timedelta(hours=18)", "morning data due time changed"),
    ("gex/encode.py", "'+' if pos else '-'", "'-' if pos else '+'", "top-strike sign flipped"),
    ("gex/run.py", "min(ndx.last_trade_et, qqq.last_trade_et)", "max(ndx.last_trade_et, qqq.last_trade_et)", "anchor uses the later trade"),
    ("gex/run.py", "if args.skip_if_fresh and slot_ran_today(args.out, slot, now_utc):", "if False:", "duplicate runs download again"),
    ("gex/run.py", ' and slot_for(from_ms(old["gen"]), "auto") == slot', "", "a manual off-window run blocks the scheduled run"),
    ("gex/chain.py", "if not last_trade:", "if False:", "missing last_trade_time accepted"),
    ("gex/fetch.py", "if attempt < tries - 1:", "if False:", "no wait between retries"),
]


def main():
    root = os.getcwd()
    survivors = 0
    for path, old, new, why in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "repo")
            shutil.copytree(root, work, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".tmp"))
            target = os.path.join(work, path)
            with open(target, encoding="utf-8") as fh:
                text = fh.read()
            if old not in text:
                print(f"PATTERN MISSING in {path}: {why}")
                survivors += 1
                continue
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(text.replace(old, new, 1))
            result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                                    cwd=work, capture_output=True, text=True)
            caught = result.returncode != 0
            print(("CAUGHT   " if caught else "SURVIVED ") + why)
            survivors += 0 if caught else 1
    print(f"survivors or missing patterns: {survivors}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
