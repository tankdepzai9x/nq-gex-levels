import unittest
from datetime import date, datetime

from gex.chain import Contract, load_snapshot
from gex.forward import estimate_forward, mid_price
from tests.helpers import make_chain, make_file

EXPIRY = date(2026, 10, 8)


def snapshot_obj(options, **overrides):
    obj = make_file("_NDX", 31000.0, "2026-10-05T16:14:59", "2026-10-06 03:44:52", options)
    obj.update(overrides)
    return obj


class ChainTests(unittest.TestCase):
    def test_loads_fields_and_timestamps(self):
        opts = make_chain("NDXP", EXPIRY, 3, 31010.0, [30900, 31000, 31100], lambda k, s: 100)
        snap = load_snapshot(snapshot_obj(opts))
        self.assertEqual(snap.symbol, "_NDX")
        self.assertEqual(snap.spot, 31000.0)
        self.assertEqual(snap.last_trade_et, datetime(2026, 10, 5, 16, 14, 59))
        self.assertEqual(snap.file_utc, datetime(2026, 10, 6, 3, 44, 52))
        self.assertEqual(len(snap.contracts), 6)
        c = snap.contracts[0]
        self.assertEqual((c.root, c.expiry, c.kind, c.strike, c.oi, c.iv), ("NDXP", EXPIRY, "C", 30900.0, 100.0, 0.2))

    def test_counts_unparseable_symbols_instead_of_crashing(self):
        opts = [{"option": "WEIRD123", "iv": 0.2, "open_interest": 5}] + \
            make_chain("NDXP", EXPIRY, 3, 31010.0, [31000], lambda k, s: 1)
        snap = load_snapshot(snapshot_obj(opts))
        self.assertEqual(snap.skipped, 1)
        self.assertEqual(len(snap.contracts), 2)

    def test_null_numbers_become_zero(self):
        opts = [{"option": "NDXP261008C31000000", "iv": None, "open_interest": None, "bid": None, "ask": None}]
        c = load_snapshot(snapshot_obj(opts)).contracts[0]
        self.assertEqual((c.iv, c.oi, c.bid, c.ask), (0.0, 0.0, 0.0, 0.0))

    def test_missing_pieces_raise_a_clear_error(self):
        with self.assertRaises(ValueError):
            load_snapshot({"timestamp": "2026-10-06 03:44:52"})
        obj = snapshot_obj([])
        obj["data"]["last_trade_time"] = None
        with self.assertRaises(ValueError):
            load_snapshot(obj)


class ForwardTests(unittest.TestCase):
    def contracts(self, fwd, half_spread=0.5):
        opts = make_chain("NDXP", EXPIRY, 3, fwd, [30800, 30900, 31000, 31100, 31200], lambda k, s: 100,
                          half_spread=half_spread)
        return load_snapshot(snapshot_obj(opts)).contracts

    def test_recovers_the_forward_from_parity(self):
        for fwd in (31010.0, 30950.5):
            est = estimate_forward(self.contracts(fwd), 3 / 365.0, 0.04, 31000.0)
            self.assertAlmostEqual(est, fwd, delta=0.05)

    def test_returns_none_without_two_sided_quotes(self):
        dead = [Contract("NDXP", EXPIRY, "C", 31000.0, 0.2, 10, 0.0, 0.0),
                Contract("NDXP", EXPIRY, "P", 31000.0, 0.2, 10, 0.0, 0.0)]
        self.assertIsNone(estimate_forward(dead, 3 / 365.0, 0.04, 31000.0))
        self.assertIsNone(estimate_forward([], 3 / 365.0, 0.04, 31000.0))

    def test_mid_price(self):
        self.assertEqual(mid_price(Contract("X", EXPIRY, "C", 1.0, 0.2, 1, 10.0, 12.0)), 11.0)
        self.assertIsNone(mid_price(Contract("X", EXPIRY, "C", 1.0, 0.2, 1, 0.0, 12.0)))
        self.assertIsNone(mid_price(Contract("X", EXPIRY, "C", 1.0, 0.2, 1, 12.0, 10.0)))


if __name__ == "__main__":
    unittest.main()
