import os
import tempfile
import unittest
from datetime import date, datetime

from gex.probe import append_rows, changes, row_for
from tests.helpers import make_chain, make_file


class ProbeTests(unittest.TestCase):
    def test_row_for_sums_open_interest(self):
        opts = make_chain("NDXP", date(2026, 10, 8), 3, 31010.0, [31000, 31100], lambda k, s: 10)
        obj = make_file("_NDX", 31000.0, "2026-10-05T16:14:59", "2026-10-06 03:44:52", opts)
        row = row_for("_NDX", obj, datetime(2026, 10, 6, 12, 0))
        self.assertEqual(row["total_oi"], 40)
        self.assertEqual(row["contracts"], 4)
        self.assertEqual(row["utc"], "2026-10-06T12:00:00")

    def test_changes_reports_when_total_oi_moves(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "p.csv")
            base = {"symbol": "QQQ", "file_utc": "x", "last_trade_et": "y", "spot": 1.0, "contracts": 1}
            append_rows(path, [dict(base, utc="2026-10-06T10:00:00", total_oi=100)])
            append_rows(path, [dict(base, utc="2026-10-06T10:30:00", total_oi=100)])
            append_rows(path, [dict(base, utc="2026-10-06T11:00:00", total_oi=150)])   # 07:00 ET
            self.assertEqual(changes(path), [("QQQ", "Tue 2026-10-06 07:00 ET", 100, 150)])


if __name__ == "__main__":
    unittest.main()
