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

    def test_wrong_types_in_key_fields_also_raise_a_clear_error(self):
        # A JSON array or null instead of an object, or a null price, make Python raise TypeError internally;
        # load_snapshot must report all of them as the one documented ValueError.
        for not_an_object in ([], None):
            with self.assertRaises(ValueError):
                load_snapshot(not_an_object)
        obj = snapshot_obj([])
        obj["data"]["current_price"] = None
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

    def test_recovers_the_forward_from_parity_on_a_long_expiry(self):
        # 180 days at 4%: exp(rT) is about 1.02, so a missing or inverted discount factor misses F by 0.2 to 1.9
        # points here. At 3 days the miss is under 0.04, below the delta of test_recovers_the_forward_from_parity,
        # which therefore cannot see it.
        long_expiry = date(2027, 4, 3)  # 180 days after the 2026-10-05 last trade in snapshot_obj
        for fwd in (31010.0, 30950.5):
            opts = make_chain("NDXP", long_expiry, 180, fwd, [30800, 30900, 31000, 31100, 31200], lambda k, s: 100)
            contracts = load_snapshot(snapshot_obj(opts)).contracts
            est = estimate_forward(contracts, 180 / 365.0, 0.04, 31000.0)
            self.assertAlmostEqual(est, fwd, delta=0.05)

    def test_takes_the_median_of_the_five_nearest_strikes(self):
        # Hand-built quotes whose put-call parity implies a different forward at every strike. Rate 0 keeps the
        # arithmetic exact: F = K + (C - P), with every price a multiple of 0.5. Each row is (strikes, forwards
        # implied at those strikes as offsets from 31000, expected median offset). Strikes are listed nearest first
        # to the 31000 reference and the last is 5000 points away, an outlier whose forward is 5000 off: above the
        # reference in `above`, below it in `below`. So the five lowest strikes are not the five nearest in every
        # row, and a sort key that is dropped or turned into the strike itself is caught. The offsets are ordered so
        # that any other count of strikes, the farthest five, the lowest or highest value, or a neighbour of the
        # middle value gives a different answer. Row 1 repeats a value, so only rows 2 and 3 can tell the middle
        # value from the one just below it.
        ref = 31000.0
        above = [31000.0, 31010.0, 30980.0, 31030.0, 30960.0, 36000.0]
        below = [31000.0, 30990.0, 31020.0, 30970.0, 31040.0, 26000.0]
        for strikes, offsets, median in ((above, [-10, 50, 10, 0, 0, 5000], 0), (above, [-10, 50, 10, 3, 0, 5000], 3),
                                         (below, [-10, 0, 10, 3, 50, -5000], 3)):
            with self.subTest(offsets=offsets):
                contracts = []
                for strike, offset in zip(strikes, offsets):
                    diff = ref + offset - strike  # C - P at this strike
                    call, put = (100.0 + diff, 100.0) if diff >= 0 else (100.0, 100.0 - diff)
                    contracts += [Contract("NDXP", EXPIRY, "C", strike, 0.2, 10, call - 0.5, call + 0.5),
                                  Contract("NDXP", EXPIRY, "P", strike, 0.2, 10, put - 0.5, put + 0.5)]
                self.assertEqual(estimate_forward(contracts, 3 / 365.0, 0.0, ref), ref + median)

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
