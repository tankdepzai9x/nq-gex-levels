"""Break the Python code on purpose and confirm the tests notice. Run from the repo root:

    python tools/mutation_check.py

First the tests run once on an unmutated copy; if they fail there, nothing else is run (a red suite would make every
mutation look "caught"). Then each line below changes one thing in a temporary copy of the repo.
"CAUGHT" is good: a test failed (or ran past the time limit). "SURVIVED" means no test noticed, so a test is missing.
"PATTERN MISSING" means the text to change is no longer in the code; "BROKEN PATTERN" means the changed file no longer
compiles, so the failure would say nothing about the tests. Both count as problems, like a survivor.
"""
import os
import shutil
import subprocess
import sys
import tempfile

TIMEOUT = 300    # seconds allowed for one run of the whole test suite

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


def run_tests(cwd):
    """Run the whole suite in `cwd`. Returns (finished, result): finished is False if it ran past TIMEOUT."""
    try:
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                                cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, None
    return True, result


def copy_repo(root, work):
    shutil.copytree(root, work, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".tmp"))


def main():
    root = os.getcwd()

    with tempfile.TemporaryDirectory() as tmp:
        work = os.path.join(tmp, "repo")
        copy_repo(root, work)
        finished, result = run_tests(work)
    if not finished:
        print(f"BASELINE FAILED: the unmutated tests ran longer than {TIMEOUT} s. Nothing else was run.")
        return 2
    if result.returncode != 0:
        print("BASELINE FAILED: the tests do not pass on the unmutated code, so the results below would mean nothing.")
        print("Run this from the repo root, and fix the tests first. Last lines of their output:")
        print("\n".join((result.stderr or result.stdout).strip().splitlines()[-15:]))
        return 2
    print("baseline: tests pass on the unmutated code")

    survivors = 0
    for path, old, new, why in MUTATIONS:
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.join(tmp, "repo")
            copy_repo(root, work)
            target = os.path.join(work, path)
            with open(target, encoding="utf-8") as fh:
                text = fh.read()
            if old not in text:
                print(f"PATTERN MISSING in {path}: {why}")
                survivors += 1
                continue
            mutated = text.replace(old, new, 1)
            try:
                compile(mutated, target, "exec")
            except (SyntaxError, ValueError) as exc:
                print(f"BROKEN PATTERN in {path}: {why} (the changed file does not compile: {exc})")
                survivors += 1
                continue
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(mutated)
            finished, result = run_tests(work)
            if not finished:
                print(f"CAUGHT   {why} (the tests ran past {TIMEOUT} s)")
            else:
                caught = result.returncode != 0
                print(("CAUGHT   " if caught else "SURVIVED ") + why)
                survivors += 0 if caught else 1
    print(f"survivors or missing patterns: {survivors}")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
