import unittest
from datetime import date

from gex.occ import parse_occ


class OccTests(unittest.TestCase):
    def test_etf_option(self):
        self.assertEqual(parse_occ("QQQ261130C00620000"), ("QQQ", date(2026, 11, 30), "C", 620.0))

    def test_index_weekly_put(self):
        self.assertEqual(parse_occ("NDXP261009P31625000"), ("NDXP", date(2026, 10, 9), "P", 31625.0))

    def test_fractional_strike(self):
        self.assertEqual(parse_occ("QQQ261016C00612500")[3], 612.5)

    def test_rejects_nonstandard_symbols(self):
        for bad in ("QQQ1", "", None, "QQQ261399C00100000", "QQQ1261016C00612500", "qqq261016c00612500"):
            self.assertIsNone(parse_occ(bad), bad)


if __name__ == "__main__":
    unittest.main()
