import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, datetime
from io import StringIO
from unittest import mock

from gex.encode import decode
from gex.run import already_fresh, build_paste, main
from gex.timeutil import to_ms
from tests.helpers import make_chain, make_file

EXPIRY = date(2026, 10, 8)


def ndx_obj():
    opts = make_chain("NDXP", EXPIRY, 3, 31010.0, range(30000, 32001, 100),
                      lambda k, s: 5000 if (k, s) == ("C", 31300) else 6000 if (k, s) == ("P", 30700) else 100)
    return make_file("_NDX", 31000.0, "2026-10-05T16:14:59", "2026-10-06 03:44:52", opts, iv30=18.0)


def qqq_obj():
    opts = make_chain("QQQ", EXPIRY, 3, 756.25, range(700, 801, 5), lambda k, s: 200, sigma=0.2)
    return make_file("QQQ", 756.0, "2026-10-05T15:59:59", "2026-10-06 03:55:36", opts, iv30=18.9)


class BuildPasteTests(unittest.TestCase):
    def test_header_and_sets(self):
        text, notes = build_paste(ndx_obj(), qqq_obj(), datetime(2026, 10, 6, 12, 45), "am")
        out = decode(text)
        self.assertEqual(out["slot"], "am")
        self.assertEqual(out["anchor"], to_ms(datetime(2026, 10, 5, 20, 0)))        # 16:00 ET close
        self.assertEqual(out["gen"], to_ms(datetime(2026, 10, 6, 12, 45)))
        self.assertEqual(out["next"], to_ms(datetime(2026, 10, 6, 23, 0)))          # due by 19:00 ET same day
        self.assertEqual(set(out["sets"]), {"NEAR", "WIDE"})
        self.assertIsNotNone(out["sets"]["NEAR"]["cw"])
        self.assertIsNotNone(out["sets"]["NEAR"]["pw"])
        self.assertTrue(any("as-of 2026-10-05 16:00:00 ET" in n for n in notes))

    def test_half_day_close_anchors_to_one_oclock(self):
        ndx, qqq = ndx_obj(), qqq_obj()
        ndx["data"]["last_trade_time"] = "2026-10-05T13:14:59"
        qqq["data"]["last_trade_time"] = "2026-10-05T12:59:59"
        out = decode(build_paste(ndx, qqq, datetime(2026, 10, 6, 21, 30), "pm")[0])
        self.assertEqual(out["anchor"], to_ms(datetime(2026, 10, 5, 17, 0)))        # 13:00 ET

    def test_fails_when_nothing_is_usable(self):
        ndx, qqq = ndx_obj(), qqq_obj()
        ndx["data"]["options"], qqq["data"]["options"] = [], []
        with self.assertRaises(RuntimeError):
            build_paste(ndx, qqq, datetime(2026, 10, 6, 12, 45), "am")


class MainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        self.write_chain(ndx_obj(), qqq_obj())
        self.out = os.path.join(self.dir, "levels", "levels.txt")
        self.hist = os.path.join(self.dir, "levels", "history")

    def write_chain(self, ndx, qqq):
        for name, obj in (("ndx.json", ndx), ("qqq.json", qqq)):
            with open(os.path.join(self.dir, name), "w", encoding="utf-8") as fh:
                json.dump(obj, fh)

    def run_main(self, now, *extra):
        argv = ["--ndx-file", os.path.join(self.dir, "ndx.json"), "--qqq-file", os.path.join(self.dir, "qqq.json"),
                "--out", self.out, "--history", self.hist, "--now-utc", now, *extra]
        buf = StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def test_writes_levels_and_history(self):
        code, _ = self.run_main("2026-10-06T12:45:00")
        self.assertEqual(code, 0)
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(decode(fh.read())["slot"], "am")
        self.assertTrue(os.path.exists(os.path.join(self.hist, "2026-10-06_am.txt")))

    def test_mid_morning_run_uses_the_mid_slot_and_its_own_anchor(self):
        ndx, qqq = ndx_obj(), qqq_obj()
        ndx["data"]["last_trade_time"] = "2026-10-06T10:00:00"
        qqq["data"]["last_trade_time"] = "2026-10-06T09:59:59"
        text, _ = build_paste(ndx, qqq, datetime(2026, 10, 6, 14, 15), "mid")
        out = decode(text)
        self.assertEqual(out["slot"], "mid")
        self.assertEqual(out["anchor"], to_ms(datetime(2026, 10, 6, 14, 0)))        # 10:00 ET
        self.assertEqual(out["next"], to_ms(datetime(2026, 10, 6, 23, 0)))          # due by 19:00 ET
        self.assertEqual(set(out["sets"]), {"NEAR", "WIDE"})

    def test_outside_the_windows_nothing_is_written(self):
        code, said = self.run_main("2026-10-06T16:00:00")      # 12:00 ET
        self.assertEqual(code, 0)
        self.assertIn("outside", said)
        self.assertFalse(os.path.exists(self.out))

    def test_skip_if_fresh_leaves_the_file_alone(self):
        self.run_main("2026-10-06T12:45:00", "--skip-if-fresh")
        with open(self.out, encoding="utf-8") as fh:
            first = fh.read()
        code, said = self.run_main("2026-10-06T13:45:00", "--skip-if-fresh")      # late duplicate cron, same slot
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), first)
        self.assertIn("skipping", said)

    def test_a_failed_download_keeps_the_old_file(self):
        self.run_main("2026-10-06T12:45:00")
        with open(self.out, encoding="utf-8") as fh:
            before = fh.read()
        os.remove(os.path.join(self.dir, "ndx.json"))
        with self.assertRaises(FileNotFoundError):
            self.run_main("2026-10-06T22:30:00")
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), before)

    def test_duplicate_cron_runs_do_not_download_anything(self):
        runs = [("2026-10-06T12:45:00", "2026-10-06T13:45:00"),    # am, then the late summer duplicate (09:45 ET)
                ("2026-10-06T14:15:00", "2026-10-06T15:15:00"),    # mid, then the duplicate (11:15 ET)
                ("2026-10-06T22:30:00", "2026-10-06T23:30:00")]    # pm, then the duplicate (19:30 ET)
        for first, again in runs:
            self.run_main(first, "--skip-if-fresh")
            with open(self.out, encoding="utf-8") as fh:
                before = fh.read()
            argv = ["--out", self.out, "--history", self.hist, "--now-utc", again, "--skip-if-fresh"]   # no files: a download would be needed
            buf = StringIO()
            with mock.patch("gex.run.fetch_json", side_effect=AssertionError("must not download")), redirect_stdout(buf):
                self.assertEqual(main(argv), 0)
            self.assertIn("nothing downloaded", buf.getvalue())
            with open(self.out, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), before)

    def test_next_days_run_is_not_skipped(self):
        self.run_main("2026-10-06T12:45:00", "--skip-if-fresh")                    # Tuesday morning
        _, said = self.run_main("2026-10-07T12:45:00", "--skip-if-fresh")          # Wednesday morning: same slot, new day
        self.assertNotIn("skipping", said)
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(decode(fh.read())["gen"], to_ms(datetime(2026, 10, 7, 12, 45)))

    def test_a_manual_run_outside_its_window_does_not_block_the_scheduled_run(self):
        ndx, qqq = ndx_obj(), qqq_obj()
        ndx["data"]["last_trade_time"], qqq["data"]["last_trade_time"] = "2026-10-06T13:45:00", "2026-10-06T13:44:59"
        self.write_chain(ndx, qqq)
        self.run_main("2026-10-06T18:00:00", "--slot", "pm")                    # by hand at 14:00 ET, data as of 13:45 ET
        ndx["data"]["last_trade_time"], qqq["data"]["last_trade_time"] = "2026-10-06T16:14:59", "2026-10-06T15:59:59"
        self.write_chain(ndx, qqq)                                              # the closing data arrives
        _, said = self.run_main("2026-10-06T22:30:00", "--skip-if-fresh")       # the real 18:30 ET run
        self.assertNotIn("skipping", said)
        with open(self.out, encoding="utf-8") as fh:
            self.assertEqual(decode(fh.read())["gen"], to_ms(datetime(2026, 10, 6, 22, 30)))

    def test_already_fresh_ignores_garbage(self):
        self.assertFalse(already_fresh("junk", "GEX1\ngen 1\nslot am\nanchor 2\nnext 3\n"))
        self.assertFalse(already_fresh("GEX1\nslot am\n", "GEX1\ngen 1\nslot am\nanchor 2\nnext 3\n"))   # no gen line
        self.assertFalse(already_fresh("GEX1\nslot am\n", "GEX1\ngen 1\nslot am\nanchor 2\nnext 3\n"))   # no gen line


if __name__ == "__main__":
    unittest.main()
