"""Extra checks for gex.run: skip-if-fresh branches, file writing, the real-clock path, download order, and a
snapshot of build_paste. Nothing here touches the network (downloads are files or a patched fetch_json) and every
file is written inside a temporary directory."""
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from io import StringIO
from unittest import mock

from gex.encode import decode
from gex.run import build_paste, main
from gex.timeutil import to_ms
from tests.helpers import make_chain, make_file
from tests.test_run import ndx_obj, qqq_obj


def rich_chains():
    """The test_run chains plus: an NDX 20-day expiry (call spike at 31500), an NDX 102-day expiry (put spike at
    30800, beyond both windows), and a QQQ put spike at 745 so QQQ's own strikes show up in the numbers."""
    ndx = ndx_obj()
    ndx["data"]["options"] += make_chain("NDXP", date(2026, 10, 25), 20, 31040.0, range(30000, 32001, 100),
                                         lambda k, s: 9000 if (k, s) == ("C", 31500) else 100)
    ndx["data"]["options"] += make_chain("NDX", date(2027, 1, 15), 102, 31200.0, range(30000, 32001, 100),
                                         lambda k, s: 90000 if (k, s) == ("P", 30800) else 100)
    qqq = make_file("QQQ", 756.0, "2026-10-05T15:59:59", "2026-10-06 03:55:36",
                    make_chain("QQQ", date(2026, 10, 8), 3, 756.25, range(700, 801, 5),
                               lambda k, s: 30000 if (k, s) == ("P", 745) else 200, sigma=0.2), iv30=18.9)
    return ndx, qqq


# This is a SNAPSHOT of what build_paste printed when the test was written, not an independent oracle. Its job is to
# pin the Task 3 argument order (ratio into build_records, NDX price level into compute_levels), the NEAR (7 days)
# and WIDE (45 days) windows, and how QQQ and NDX records are combined. What I checked by hand:
#   cw 300 and pw -300 in both sets: the NDX call spike at 31300 and put spike at 30700 sit 290 and 310 points from
#     the 31010 forward, which fall in the 300 and -300 buckets (25-point buckets);
#   em 352: 31000 (the NDX price level) x 0.18 / sqrt(252) = 351.5 (it would print 0 if the QQQ ratio were passed);
#   the 450 bucket in WIDE only: the 20-day call spike at 31500 is 460 points above its 31040 forward;
#   the -450 bucket: QQQ's 745 put is (745 - 756.25) x 41.005 = -461 NQ points;
#   nothing from the 102-day expiry (beyond 45 days) appears in either set.
# The dollar values, flip, and top lists are not hand-derived; they follow from the code at that time.
GOLDEN = """GEX1
gen 1791290700000
slot am
anchor 1791230400000
next 1791327600000
set NEAR
reg N
flip 130
cw 300
pw -300
top -1000:+ -900:+ -450:- -300:- 300:+
em 352
prof -450:-349594 -300:-3434037 300:2943038
set WIDE
reg P
flip -211
cw 300
pw -300
top -1000:+ -450:- -300:- 300:+ 450:+
em 352
prof -450:-349594 -300:-3434037 300:2943038 450:2251679
"""


class BuildPasteSnapshotTests(unittest.TestCase):
    def test_numbers_on_a_chain_with_several_expiries_and_a_heavy_qqq_put(self):
        ndx, qqq = rich_chains()
        self.assertEqual(build_paste(ndx, qqq, datetime(2026, 10, 6, 12, 45), "am")[0], GOLDEN)

    def test_an_expiry_exactly_seven_days_out_is_in_the_near_set(self):
        opts = make_chain("NDXP", date(2026, 10, 12), 7, 31010.0, range(30000, 32001, 100),
                          lambda k, s: 5000 if (k, s) == ("C", 31300) else 100)
        ndx = make_file("_NDX", 31000.0, "2026-10-05T16:14:59", "2026-10-06 03:44:52", opts, iv30=18.0)
        out = decode(build_paste(ndx, qqq_obj(), datetime(2026, 10, 6, 12, 45), "am")[0])
        self.assertEqual(out["sets"]["NEAR"]["cw"], 300.0)

    def test_an_expiry_exactly_forty_five_days_out_is_in_the_wide_set_only(self):
        ndx = ndx_obj()
        ndx["data"]["options"] += make_chain("NDX", date(2026, 11, 19), 45, 31100.0, range(30000, 32001, 100),
                                             lambda k, s: 80000 if (k, s) == ("P", 30500) else 100)
        out = decode(build_paste(ndx, qqq_obj(), datetime(2026, 10, 6, 12, 45), "am")[0])
        self.assertIn(-600.0, dict(out["sets"]["WIDE"]["prof"]))        # 30500 is 600 below that expiry's 31100 forward
        self.assertNotIn(-600.0, dict(out["sets"]["NEAR"]["prof"]))


class MainPinTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        for name, obj in (("ndx.json", ndx_obj()), ("qqq.json", qqq_obj())):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8") as fh:
                json.dump(obj, fh)
        self.out = os.path.join(self.dir, "levels", "levels.txt")
        self.hist = os.path.join(self.dir, "levels", "history")

    def argv(self, *extra):
        return ["--ndx-file", os.path.join(self.dir, "ndx.json"), "--qqq-file", os.path.join(self.dir, "qqq.json"),
                "--out", self.out, "--history", self.hist, *extra]

    def run_main(self, now, *extra):
        buf = StringIO()
        with redirect_stdout(buf):
            code = main(self.argv("--now-utc", now, *extra))
        return code, buf.getvalue()

    def read_out(self):
        with open(self.out, encoding="utf-8") as fh:
            return fh.read()

    def put_out(self, text):
        os.makedirs(os.path.dirname(self.out), exist_ok=True)
        with open(self.out, "w", encoding="utf-8") as fh:
            fh.write(text)

    # --- skip-if-fresh logic and its branches

    def test_without_the_flag_a_repeat_run_writes_again(self):
        self.run_main("2026-10-06T12:45:00")
        self.run_main("2026-10-06T13:45:00")
        self.assertEqual(decode(self.read_out())["gen"], to_ms(datetime(2026, 10, 6, 13, 45)))

    def test_another_slots_file_made_inside_this_window_does_not_make_it_skip(self):
        self.run_main("2026-10-06T12:45:00", "--slot", "pm")      # by hand, labelled pm, made inside the am window
        _, said = self.run_main("2026-10-06T12:50:00", "--skip-if-fresh")
        self.assertNotIn("skipping", said)
        self.assertEqual(decode(self.read_out())["slot"], "am")

    def test_a_file_without_a_gen_line_is_regenerated(self):
        self.put_out("GEX1\nslot am\n")
        self.run_main("2026-10-06T12:45:00", "--skip-if-fresh")
        self.assertEqual(decode(self.read_out())["gen"], to_ms(datetime(2026, 10, 6, 12, 45)))

    def test_a_junk_file_is_regenerated(self):
        self.put_out("junk")
        self.run_main("2026-10-06T12:45:00", "--skip-if-fresh")
        self.assertEqual(decode(self.read_out())["slot"], "am")

    def test_same_data_after_an_early_manual_run_is_not_rewritten(self):
        self.run_main("2026-10-06T11:00:00", "--slot", "am")      # 07:00 ET, before the am window opens
        before = self.read_out()
        _, said = self.run_main("2026-10-06T12:45:00", "--skip-if-fresh")
        self.assertIn("already this slot's result", said)
        self.assertEqual(self.read_out(), before)

    # --- writing files

    def test_a_failure_while_replacing_keeps_the_old_file(self):
        self.put_out("OLD")
        with mock.patch("gex.run.os.replace", side_effect=OSError("disk full")), redirect_stdout(StringIO()):
            with self.assertRaises(OSError):
                main(self.argv("--now-utc", "2026-10-06T12:45:00"))
        self.assertEqual(self.read_out(), "OLD")

    def test_the_files_use_unix_newlines(self):
        self.run_main("2026-10-06T12:45:00")
        for path in (self.out, os.path.join(self.hist, "2026-10-06_am.txt")):
            with open(path, "rb") as fh:
                self.assertNotIn(b"\r", fh.read())

    def test_the_history_file_is_named_by_the_eastern_date(self):
        self.run_main("2026-10-07T00:15:00")                       # 20:15 ET on the 6th, inside the pm window
        self.assertTrue(os.path.exists(os.path.join(self.hist, "2026-10-06_pm.txt")))

    # --- the clock and the downloads

    def test_the_real_clock_path_gives_naive_utc_without_microseconds(self):
        class FakeDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 6, 12, 45, 7, 999, tzinfo=tz)

        with mock.patch("gex.run.datetime", FakeDatetime), redirect_stdout(StringIO()):
            main(self.argv())                                      # no --now-utc
        self.assertEqual(decode(self.read_out())["gen"], to_ms(datetime(2026, 10, 6, 12, 45, 7)))

    def test_ndx_is_downloaded_first_and_qqq_second(self):
        files = {"_NDX": ndx_obj(), "QQQ": qqq_obj()}
        buf = StringIO()
        with mock.patch("gex.run.fetch_json", side_effect=lambda symbol: files[symbol]) as fetch, redirect_stdout(buf):
            main(["--out", self.out, "--history", self.hist, "--now-utc", "2026-10-06T12:45:00"])
        self.assertEqual([c.args[0] for c in fetch.call_args_list], ["_NDX", "QQQ"])
        self.assertIn("NDX 31000.00, QQQ 756.00", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
