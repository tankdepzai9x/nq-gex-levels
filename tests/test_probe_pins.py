"""Pins for gex.probe: the probe decides the final run times, and its first cloud run cannot be repeated cheaply."""
import contextlib
import csv
import io
import os
import tempfile
import unittest
from datetime import date, datetime
from unittest import mock

import gex.probe as probe
from gex.probe import append_rows, changes, row_for
from tests.helpers import make_chain, make_file

HEADER = ["utc", "symbol", "file_utc", "last_trade_et", "spot", "contracts", "total_oi"]


def csv_row(utc, total_oi, symbol="QQQ"):
    return {"utc": utc, "symbol": symbol, "file_utc": "x", "last_trade_et": "y", "spot": 1.0,
            "contracts": 1, "total_oi": total_oi}


def read_rows(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


class _Clock(datetime):
    """now() answers with a fixed UTC time, and a different, wrong time if the caller forgets to ask for UTC."""

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return datetime(2026, 10, 6, 8, 0, 5, 123456)
        return datetime(2026, 10, 6, 12, 0, 5, 123456, tzinfo=tz)


def fake_fetch(calls, fail=None):
    """A stand-in for gex.probe.fetch_json: records the symbols asked for, never touches the network."""
    def fetch(symbol):
        calls.append(symbol)
        if symbol == fail:
            raise RuntimeError("could not download " + symbol)
        root, spot, oi = {"_NDX": ("NDXP", 31000.0, 10), "QQQ": ("QQQ", 520.0, 7)}[symbol]
        opts = make_chain(root, date(2026, 10, 8), 3, spot, [spot - 100, spot], lambda k, s: oi)
        return make_file(symbol, spot, "2026-10-06T16:00:00", "2026-10-06 20:05:00", opts)
    return fetch


class ChangesPins(unittest.TestCase):
    def csv_path(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = os.path.join(tmp.name, "p.csv")
        append_rows(path, rows)
        return path

    def test_a_drop_is_reported_as_well_as_a_rise(self):
        path = self.csv_path([csv_row("2026-10-06T17:00:00", 100), csv_row("2026-10-06T17:30:00", 80)])
        self.assertEqual(changes(path), [("QQQ", "Tue 2026-10-06 13:30 ET", 100, 80)])

    def test_each_row_is_compared_with_the_previous_row_not_the_first(self):
        rows = [csv_row("2026-10-06T14:00:00", 100), csv_row("2026-10-06T14:30:00", 150),
                csv_row("2026-10-06T15:00:00", 150), csv_row("2026-10-06T15:30:00", 200),
                csv_row("2026-10-06T16:00:00", 100)]
        self.assertEqual(changes(self.csv_path(rows)), [
            ("QQQ", "Tue 2026-10-06 10:30 ET", 100, 150),
            ("QQQ", "Tue 2026-10-06 11:30 ET", 150, 200),
            ("QQQ", "Tue 2026-10-06 12:00 ET", 200, 100)])

    def test_the_time_is_24_hour_eastern(self):
        rows = [csv_row("2026-10-06T16:00:00", 5), csv_row("2026-10-06T17:00:00", 6), csv_row("2026-10-06T19:00:00", 7)]
        self.assertEqual(changes(self.csv_path(rows)), [
            ("QQQ", "Tue 2026-10-06 13:00 ET", 5, 6),
            ("QQQ", "Tue 2026-10-06 15:00 ET", 6, 7)])

    def test_the_date_is_the_eastern_date_not_the_utc_date(self):
        rows = [csv_row("2026-10-07T01:00:00", 1), csv_row("2026-10-07T02:00:00", 2)]
        self.assertEqual(changes(self.csv_path(rows)), [("QQQ", "Tue 2026-10-06 22:00 ET", 1, 2)])

    def test_winter_time_is_five_hours_behind_utc(self):
        rows = [csv_row("2026-11-02T12:30:00", 1), csv_row("2026-11-02T13:30:00", 2)]
        self.assertEqual(changes(self.csv_path(rows)), [("QQQ", "Mon 2026-11-02 08:30 ET", 1, 2)])

    def test_each_symbol_is_followed_on_its_own_and_in_file_order(self):
        rows = [csv_row("2026-10-06T10:00:00", 10, "_NDX"), csv_row("2026-10-06T10:00:00", 20, "QQQ"),
                csv_row("2026-10-06T10:30:00", 10, "_NDX"), csv_row("2026-10-06T10:30:00", 25, "QQQ"),
                csv_row("2026-10-06T11:00:00", 12, "_NDX"), csv_row("2026-10-06T11:00:00", 25, "QQQ")]
        self.assertEqual(changes(self.csv_path(rows)), [
            ("QQQ", "Tue 2026-10-06 06:30 ET", 20, 25),
            ("_NDX", "Tue 2026-10-06 07:00 ET", 10, 12)])

    def test_no_change_and_a_single_row_report_nothing(self):
        self.assertEqual(changes(self.csv_path([csv_row("2026-10-06T10:00:00", 9)])), [])
        same = [csv_row("2026-10-06T10:00:00", 9), csv_row("2026-10-06T10:30:00", 9)]
        self.assertEqual(changes(self.csv_path(same)), [])


class RowForPins(unittest.TestCase):
    def obj(self, oi_for):
        opts = make_chain("NDXP", date(2026, 10, 8), 3, 31010.0, [31000, 31100], oi_for)
        return make_file("_NDX", 31000.0, "2026-10-05T16:14:59", "2026-10-06 03:44:52", opts, iv30=18.6)

    def test_every_field_of_the_row(self):
        row = row_for("QQQ", self.obj(lambda k, s: 10 if k == "C" else 5), datetime(2026, 10, 6, 12, 0, 5, 987654))
        self.assertEqual(row, {
            "utc": "2026-10-06T12:00:05",
            "symbol": "QQQ",
            "file_utc": "2026-10-06 03:44:52",
            "last_trade_et": "2026-10-05T16:14:59",
            "spot": 31000.0,
            "contracts": 4,
            "total_oi": 30,
        })
        self.assertIsInstance(row["total_oi"], int)

    def test_contracts_counts_zero_open_interest_and_the_total_ignores_it(self):
        row = row_for("_NDX", self.obj(lambda k, s: 10 if k == "C" else 0), datetime(2026, 10, 6, 12, 0))
        self.assertEqual((row["contracts"], row["total_oi"]), (4, 20))


class AppendRowsPins(unittest.TestCase):
    def test_creates_a_missing_directory_like_probe_on_the_first_cloud_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe", "deeper", "oi_probe.csv")
            self.assertFalse(os.path.exists(os.path.dirname(path)))
            append_rows(path, [csv_row("2026-10-06T10:00:00", 100)])
            self.assertTrue(os.path.isfile(path))

    def test_header_once_in_the_documented_order_and_rows_kept_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.csv")
            append_rows(path, [csv_row("2026-10-06T10:00:00", 100, "_NDX"), csv_row("2026-10-06T10:00:00", 7)])
            append_rows(path, [csv_row("2026-10-06T10:30:00", 101, "_NDX")])
            self.assertEqual(read_rows(path), [
                HEADER,
                ["2026-10-06T10:00:00", "_NDX", "x", "y", "1.0", "1", "100"],
                ["2026-10-06T10:00:00", "QQQ", "x", "y", "1.0", "1", "7"],
                ["2026-10-06T10:30:00", "_NDX", "x", "y", "1.0", "1", "101"]])


class MainPins(unittest.TestCase):
    def run_main(self, argv, fetch):
        out = io.StringIO()
        with mock.patch.object(probe, "fetch_json", fetch), mock.patch.object(probe, "datetime", _Clock), \
                contextlib.redirect_stdout(out):
            code = probe.main(argv)
        return code, out.getvalue()

    def test_one_run_logs_two_rows_for_the_two_symbols_in_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "probe", "oi_probe.csv")
            calls = []
            code, out = self.run_main(["--csv", path], fake_fetch(calls))
            self.assertEqual(code, 0)
            self.assertEqual(calls, ["_NDX", "QQQ"])
            self.assertEqual(out, "logged 2 rows at 2026-10-06 12:00:05 UTC\n")
            self.assertEqual(read_rows(path), [
                HEADER,
                ["2026-10-06T12:00:05", "_NDX", "2026-10-06 20:05:00", "2026-10-06T16:00:00", "31000.0", "4", "40"],
                ["2026-10-06T12:00:05", "QQQ", "2026-10-06 20:05:00", "2026-10-06T16:00:00", "520.0", "4", "28"]])

    def test_a_second_run_appends_two_more_rows_under_the_same_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "oi.csv")
            for _ in range(2):
                self.assertEqual(self.run_main(["--csv", path], fake_fetch([]))[0], 0)
            rows = read_rows(path)
            self.assertEqual(len(rows), 5)
            self.assertEqual(rows[0], HEADER)
            self.assertEqual([r[1] for r in rows[1:]], ["_NDX", "QQQ", "_NDX", "QQQ"])

    def test_default_csv_is_probe_oi_probe_csv_in_the_current_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            try:
                code, _ = self.run_main([], fake_fetch([]))
            finally:
                os.chdir(old)
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "probe", "oi_probe.csv")))

    def test_a_failed_download_fails_loudly_and_logs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "oi.csv")
            calls = []
            with self.assertRaises(RuntimeError):
                self.run_main(["--csv", path], fake_fetch(calls, fail="QQQ"))
            self.assertEqual(calls, ["_NDX", "QQQ"])
            self.assertFalse(os.path.exists(path))

    def test_analyze_prints_every_change_and_downloads_and_writes_nothing(self):
        def must_not_download(symbol):
            raise AssertionError("--analyze must not download " + symbol)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "oi.csv")
            append_rows(path, [
                csv_row("2026-10-06T10:00:00", 1234567, "_NDX"), csv_row("2026-10-06T10:00:00", 900000),
                csv_row("2026-10-06T11:00:00", 1301234, "_NDX"), csv_row("2026-10-06T11:00:00", 900000),
                csv_row("2026-10-06T12:00:00", 850500)])
            with open(path, "rb") as fh:
                before = fh.read()
            code, out = self.run_main(["--csv", path, "--analyze"], must_not_download)
            with open(path, "rb") as fh:
                after = fh.read()
        self.assertEqual(code, 0)
        self.assertEqual(out,
                         "_NDX  Tue 2026-10-06 07:00 ET  total OI 1,234,567 -> 1,301,234\n"
                         "QQQ   Tue 2026-10-06 08:00 ET  total OI 900,000 -> 850,500\n")
        self.assertEqual(after, before)

    def test_analyze_with_no_changes_prints_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "oi.csv")
            append_rows(path, [csv_row("2026-10-06T10:00:00", 5), csv_row("2026-10-06T10:30:00", 5)])
            code, out = self.run_main(["--csv", path, "--analyze"], fake_fetch([]))
        self.assertEqual((code, out), (0, ""))


if __name__ == "__main__":
    unittest.main()
