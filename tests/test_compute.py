import unittest
from datetime import date, datetime

from gex.chain import load_snapshot
from gex.compute import (MAX_DIST, MIN_SEP, bucket_of, build_records, compute_levels, flip_x, net_gex_at, pick_top,
                         years_to_expiry)
from tests.helpers import make_chain, make_file, make_option

ASOF = datetime(2026, 10, 5, 16, 0)   # the as-of moment: the 16:00 ET close
EXPIRY = date(2026, 10, 8)            # exactly 3 days after ASOF
FWD = 31010.0
STRIKES = list(range(30000, 32001, 100))


def synthetic_snapshot(oi_for, expiry=EXPIRY, days=3, extra=None):
    opts = make_chain("NDXP", expiry, days, FWD, STRIKES, oi_for) + (extra or [])
    return load_snapshot(make_file("_NDX", 31000.0, "2026-10-05T16:00:00", "2026-10-06 03:44:52", opts))


def big_call_and_put(kind, strike):
    if kind == "C" and strike == 31300:
        return 5000
    if kind == "P" and strike == 30700:
        return 6000
    return 100


class PickTopTests(unittest.TestCase):
    def test_skips_buckets_too_close_to_a_stronger_one(self):
        net = {0.0: 10.0, 25.0: -9.0, 50.0: 8.0, 100.0: -7.0, 200.0: 1.0}
        self.assertEqual(pick_top(net, list(net), 3, 50.0), [0.0, 50.0, 100.0])

    def test_returns_fewer_when_there_are_not_enough(self):
        net = {0.0: 1.0, 25.0: 2.0}
        self.assertEqual(pick_top(net, list(net), 5, 50.0), [25.0])


class HelperTests(unittest.TestCase):
    def test_bucket_of_rounds_half_up_to_25(self):
        self.assertEqual(bucket_of(290.0), 300.0)
        self.assertEqual(bucket_of(-310.0), -300.0)
        self.assertEqual(bucket_of(12.4), 0.0)
        self.assertEqual(bucket_of(12.5), 25.0)
        self.assertEqual(bucket_of(-12.5), 0.0)

    def test_flip_x_interpolates_the_zero_crossing(self):
        curve = [(-0.02, -5.0), (-0.01, -1.0), (0.0, 3.0), (0.01, 4.0)]
        self.assertAlmostEqual(flip_x(curve), -0.0075, places=12)

    def test_flip_x_none_when_it_never_crosses(self):
        self.assertIsNone(flip_x([(-0.01, 2.0), (0.0, 3.0), (0.01, 4.0)]))
        self.assertIsNone(flip_x([]))

    def test_flip_x_picks_the_crossing_nearest_zero(self):
        curve = [(-0.04, -1.0), (-0.03, 1.0), (0.0, 1.0), (0.01, -1.0), (0.02, -1.0)]
        self.assertAlmostEqual(flip_x(curve), 0.005, places=12)


class YearsToExpiryTests(unittest.TestCase):
    def test_whole_days_from_the_close(self):
        self.assertAlmostEqual(years_to_expiry(EXPIRY, ASOF), 3 / 365.0, places=12)

    def test_same_day_expiry_is_a_fraction_of_a_day(self):
        ten_am = datetime(2026, 10, 5, 10, 0)
        self.assertAlmostEqual(years_to_expiry(date(2026, 10, 5), ten_am), 6 / (365.0 * 24), places=12)

    def test_already_expired_is_not_positive(self):
        self.assertLessEqual(years_to_expiry(date(2026, 10, 5), ASOF), 0)


class BuildRecordsTests(unittest.TestCase):
    def test_intraday_same_day_contracts_are_kept_with_fractional_time(self):
        ten_am = datetime(2026, 10, 5, 10, 0)
        snap = synthetic_snapshot(lambda k, s: 100, expiry=date(2026, 10, 5), days=1)
        recs, _ = build_records(snap, ten_am, 45, 0.04, 1.0)
        self.assertTrue(recs)
        self.assertTrue(all(r.days == 0 and abs(r.T - 6 / (365.0 * 24)) < 1e-12 for r in recs))

    def test_keeps_only_usable_contracts(self):
        snap = synthetic_snapshot(lambda k, s: 0 if s == 31500 else 100)
        recs, notes = build_records(snap, ASOF, 45, 0.04, 1.0)
        strikes = {r.strike for r in recs}
        self.assertNotIn(31500.0, strikes)          # zero open interest dropped
        self.assertIn(31000.0, strikes)
        self.assertEqual(notes, [])
        self.assertTrue(all(r.days == 3 and abs(r.fwd - FWD) < 0.05 for r in recs))

    def test_drops_expired_and_too_far_expiries(self):
        snap = synthetic_snapshot(lambda k, s: 100, expiry=date(2026, 10, 5), days=1)  # expires on the as-of date
        self.assertEqual(build_records(snap, ASOF, 45, 0.04, 1.0)[0], [])
        far = synthetic_snapshot(lambda k, s: 100, expiry=date(2026, 12, 18), days=74)
        self.assertEqual(build_records(far, ASOF, 45, 0.04, 1.0)[0], [])

    def test_expiry_without_a_parity_pair_is_skipped_with_a_note(self):
        calls_only = [make_option("NDXP", EXPIRY, "C", 31000.0, FWD, 3 / 365.0, 0.2, 100)]
        snap = load_snapshot(make_file("_NDX", 31000.0, "2026-10-05T16:00:00", "2026-10-06 03:44:52", calls_only))
        recs, notes = build_records(snap, ASOF, 45, 0.04, 1.0)
        self.assertEqual(recs, [])
        self.assertEqual(len(notes), 1)
        self.assertIn("skipped", notes[0])

    def test_zero_iv_contracts_are_ignored(self):
        opts = make_chain("NDXP", EXPIRY, 3, FWD, STRIKES, lambda k, s: 100)
        for o in opts:
            if o["option"].endswith("31200000"):
                o["iv"] = 0.0
        snap = load_snapshot(make_file("_NDX", 31000.0, "2026-10-05T16:00:00", "2026-10-06 03:44:52", opts))
        recs, _ = build_records(snap, ASOF, 45, 0.04, 1.0)
        self.assertNotIn(31200.0, {r.strike for r in recs})


class LevelsTests(unittest.TestCase):
    def levels(self, oi_for=big_call_and_put, **kw):
        recs, _ = build_records(synthetic_snapshot(oi_for), ASOF, 45, 0.04, 1.0)
        return compute_levels(recs, 18.0, 31000.0, 0.04, **kw)

    def test_walls_land_on_the_big_open_interest(self):
        lv = self.levels()
        # call strike 31300 is 290 above the forward -> bucket 300; put strike 30700 is 310 below -> bucket -300
        self.assertEqual(lv.cw, 300.0)
        self.assertEqual(lv.pw, -300.0)

    def test_top_strikes_include_both_walls_with_the_right_sign(self):
        lv = self.levels()
        self.assertIn((300.0, True), lv.top)
        self.assertIn((-300.0, False), lv.top)
        self.assertLessEqual(len(lv.top), 5)
        self.assertEqual(lv.top, sorted(lv.top))
        distances = [d for d, _ in lv.top]
        self.assertTrue(all(b - a >= MIN_SEP for a, b in zip(distances, distances[1:])))

    def test_regime_follows_the_bigger_side(self):
        calls_heavy = self.levels(lambda k, s: 5000 if k == "C" else 100)
        puts_heavy = self.levels(lambda k, s: 5000 if k == "P" else 100)
        self.assertEqual(calls_heavy.reg, "P")
        self.assertEqual(puts_heavy.reg, "N")

    def test_flip_exists_when_the_book_changes_sign(self):
        lv = self.levels(lambda k, s: 5000 if (k == "C" and s >= 31000) or (k == "P" and s < 31000) else 10)
        # calls above and puts below: net GEX is positive near price and turns negative as price moves away
        self.assertIsNotNone(lv.flip)

    def test_profile_covers_the_buckets_and_keeps_the_sign(self):
        lv = self.levels()
        profile = dict(lv.profile)
        self.assertGreater(profile[300.0], 0)       # big calls
        self.assertLess(profile[-300.0], 0)         # big puts
        self.assertTrue(all(abs(d) <= MAX_DIST for d in profile))
        self.assertEqual([d for d, _ in lv.profile], sorted(profile))

    def test_expected_move_matches_the_formula(self):
        lv = self.levels()
        self.assertAlmostEqual(lv.em, 31000.0 * 0.18 * (1 / 252) ** 0.5, places=6)

    def test_walls_ignore_strikes_beyond_the_distance_cap(self):
        extra = make_chain("NDXP", EXPIRY, 3, FWD, [32200], lambda k, s: 1_000_000)   # +1190 away, huge open interest
        recs, _ = build_records(synthetic_snapshot(big_call_and_put, extra=extra), ASOF, 45, 0.04, 1.0)
        lv = compute_levels(recs, 18.0, 31000.0, 0.04)
        self.assertEqual(lv.cw, 300.0)
        self.assertGreater(32200 - FWD, MAX_DIST)       # the extra strike really is beyond the cap

    def test_qqq_distances_are_scaled_to_nq_points(self):
        opts = make_chain("QQQ", EXPIRY, 3, 756.25, range(700, 801, 5),
                          lambda k, s: 5000 if (k, s) == ("C", 770) else 50, sigma=0.2)
        snap = load_snapshot(make_file("QQQ", 756.0, "2026-10-05T15:59:59", "2026-10-06 03:55:36", opts))
        recs, _ = build_records(snap, ASOF, 45, 0.04, 41.0)
        lv = compute_levels(recs, 18.0, 31000.0, 0.04)
        # strike 770 is 13.75 dollars above the forward = 563.75 NQ points -> bucket 575
        self.assertEqual(lv.cw, 575.0)

    def test_no_records_gives_none(self):
        self.assertIsNone(compute_levels([], 18.0, 31000.0, 0.04))

    def test_net_gex_sign_convention(self):
        recs, _ = build_records(synthetic_snapshot(lambda k, s: 100 if k == "C" else 0), ASOF, 45, 0.04, 1.0)
        self.assertGreater(net_gex_at(recs, 0.0, 0.04), 0)   # only calls -> positive


if __name__ == "__main__":
    unittest.main()
