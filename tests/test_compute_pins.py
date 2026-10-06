"""Pins for behaviour that tests/test_compute.py cannot see.

Found with hand-made mutants of gex/compute.py: the value of the zero-gamma level, the distance caps on the put wall,
the top strikes and the profile, top_n, dollar sizes, one-sided books and the max_days boundary.
"""
import unittest
from datetime import timedelta

from gex.bs import dollar_gamma_per_pct
from gex.chain import load_snapshot
from gex.compute import MAX_DIST, MIN_SEP, build_records, compute_levels, flip_x, net_gex_at
from tests.helpers import make_chain, make_file
from tests.test_compute import ASOF, EXPIRY, FWD, STRIKES, big_call_and_put, synthetic_snapshot


def flip_book(kind, strike):
    """Calls at or above 31000 and puts below it carry the open interest, so net GEX turns negative below the price."""
    return 5000 if (kind == "C" and strike >= 31000) or (kind == "P" and strike < 31000) else 10


def far_both_sides(kind, strike):
    if (kind, strike) == ("C", 32200) or (kind, strike) == ("P", 29800):
        return 1_000_000                                    # huge open interest, 1190 above and 1210 below
    return big_call_and_put(kind, strike)


class FlipValueTests(unittest.TestCase):
    def setUp(self):
        self.recs, _ = build_records(synthetic_snapshot(flip_book), ASOF, 45, 0.04, 1.0)
        self.lv = compute_levels(self.recs, 18.0, 31000.0, 0.04)

    def test_flip_is_below_the_price_in_this_book_and_is_a_real_zero(self):
        self.assertLess(self.lv.flip, 0)
        self.assertAlmostEqual(self.lv.flip, -82.0, delta=1.0)          # measured: -81.996 NQ points
        at_flip = net_gex_at(self.recs, self.lv.flip / 31000.0, 0.04)
        self.assertLess(abs(at_flip), 0.001 * abs(net_gex_at(self.recs, 0.0, 0.04)))

    def test_flip_scales_with_the_nq_price(self):
        half = compute_levels(self.recs, 18.0, 15500.0, 0.04)
        self.assertAlmostEqual(half.flip, self.lv.flip / 2.0, places=9)


class CurveTests(unittest.TestCase):
    def test_flip_x_counts_an_exact_zero_in_the_middle_and_at_the_end(self):
        self.assertEqual(flip_x([(-0.01, -1.0), (0.0, 0.0), (0.01, 1.0)]), 0.0)
        self.assertEqual(flip_x([(-0.01, -1.0), (0.0, 0.0)]), 0.0)

    def test_net_gex_magnitude_is_the_plain_sum_of_signed_dollar_gamma(self):
        recs, _ = build_records(synthetic_snapshot(big_call_and_put), ASOF, 45, 0.04, 1.0)
        # the definition restated on purpose: it pins the contract size (100) and the rate
        expected = sum((1 if r.kind == "C" else -1) * dollar_gamma_per_pct(r.fwd, r.strike, r.T, r.iv, 0.04) * r.oi
                       * 100.0 for r in recs)
        self.assertAlmostEqual(net_gex_at(recs, 0.0, 0.04) / expected, 1.0, places=12)

    def test_profile_bucket_is_calls_minus_puts_in_dollars(self):
        recs, _ = build_records(synthetic_snapshot(big_call_and_put), ASOF, 45, 0.04, 1.0)
        lv = compute_levels(recs, 18.0, 31000.0, 0.04)
        # only strike 31300 falls in bucket 300
        expected = (5000 - 100) * 100.0 * dollar_gamma_per_pct(recs[0].fwd, 31300.0, 3 / 365.0, 0.2, 0.04)
        self.assertAlmostEqual(dict(lv.profile)[300.0] / expected, 1.0, places=9)


class CapTests(unittest.TestCase):
    def levels(self):
        strikes = STRIKES + [29800, 32200]
        opts = make_chain("NDXP", EXPIRY, 3, FWD, strikes, far_both_sides)
        snap = load_snapshot(make_file("_NDX", 31000.0, "2026-10-05T16:00:00", "2026-10-06 03:44:52", opts))
        recs, _ = build_records(snap, ASOF, 45, 0.04, 1.0)
        return compute_levels(recs, 18.0, 31000.0, 0.04)

    def test_far_strikes_are_ignored_on_both_sides(self):
        lv = self.levels()
        self.assertEqual((lv.cw, lv.pw), (300.0, -300.0))

    def test_far_strikes_stay_out_of_the_top_strikes_and_the_profile(self):
        lv = self.levels()
        self.assertTrue(all(abs(d) <= MAX_DIST for d, _ in lv.top))
        self.assertTrue(all(abs(d) <= MAX_DIST for d, _ in lv.profile))


class TopThroughComputeLevelsTests(unittest.TestCase):
    def test_top_n_is_passed_through(self):
        recs, _ = build_records(synthetic_snapshot(big_call_and_put), ASOF, 45, 0.04, 1.0)
        lv = compute_levels(recs, 18.0, 31000.0, 0.04, top_n=2)
        self.assertEqual(lv.top, [(-300.0, False), (300.0, True)])

    def test_default_top_n_is_five(self):
        recs, _ = build_records(synthetic_snapshot(big_call_and_put), ASOF, 45, 0.04, 1.0)
        self.assertEqual(len(compute_levels(recs, 18.0, 31000.0, 0.04).top), 5)

    def test_separation_binds_with_25_point_strike_spacing(self):
        # two adjacent heavy strikes 25 apart: only the stronger may be a top strike (MIN_SEP is 50)
        def oi_for(kind, strike):
            return {("C", 31300): 5000, ("C", 31325): 4900, ("P", 30700): 6000}.get((kind, strike), 100)
        strikes = list(range(30000, 32001, 25))
        opts = make_chain("NDXP", EXPIRY, 3, FWD, strikes, oi_for)
        snap = load_snapshot(make_file("_NDX", 31000.0, "2026-10-05T16:00:00", "2026-10-06 03:44:52", opts))
        recs, _ = build_records(snap, ASOF, 45, 0.04, 1.0)
        lv = compute_levels(recs, 18.0, 31000.0, 0.04)
        distances = [d for d, _ in lv.top]
        self.assertTrue(all(b - a >= MIN_SEP for a, b in zip(distances, distances[1:])), distances)


class OneSidedBookTests(unittest.TestCase):
    def test_no_calls_means_no_call_wall_and_no_puts_means_no_put_wall(self):
        puts_only, _ = build_records(synthetic_snapshot(lambda k, s: 100 if k == "P" else 0), ASOF, 45, 0.04, 1.0)
        lv = compute_levels(puts_only, 18.0, 31000.0, 0.04)
        self.assertIsNone(lv.cw)
        self.assertIsNotNone(lv.pw)
        calls_only, _ = build_records(synthetic_snapshot(lambda k, s: 100 if k == "C" else 0), ASOF, 45, 0.04, 1.0)
        lv = compute_levels(calls_only, 18.0, 31000.0, 0.04)
        self.assertIsNone(lv.pw)
        self.assertIsNotNone(lv.cw)


class MaxDaysBoundaryTests(unittest.TestCase):
    def test_an_expiry_exactly_max_days_away_is_kept_and_one_day_further_is_dropped(self):
        d45 = ASOF.date() + timedelta(days=45)
        kept = synthetic_snapshot(lambda k, s: 100, expiry=d45, days=45)
        self.assertTrue(build_records(kept, ASOF, 45, 0.04, 1.0)[0])
        d46 = ASOF.date() + timedelta(days=46)
        dropped = synthetic_snapshot(lambda k, s: 100, expiry=d46, days=46)
        self.assertEqual(build_records(dropped, ASOF, 45, 0.04, 1.0)[0], [])


if __name__ == "__main__":
    unittest.main()
