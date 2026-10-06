import unittest
from datetime import datetime

from gex.timeutil import (dst_bounds_utc, et_to_utc, from_ms, next_session_ms, round_minute, slot_for, to_ms,
                          utc_to_et)


class TimeUtilTests(unittest.TestCase):
    def test_to_ms_known_value(self):
        self.assertEqual(to_ms(datetime(2026, 1, 1)), 1767225600000)
        self.assertEqual(from_ms(1767225600000), datetime(2026, 1, 1))

    def test_dst_bounds_2026(self):
        start, end = dst_bounds_utc(2026)
        self.assertEqual(start, datetime(2026, 3, 8, 7, 0))
        self.assertEqual(end, datetime(2026, 11, 1, 6, 0))

    def test_et_to_utc_summer_and_winter(self):
        self.assertEqual(et_to_utc(datetime(2026, 10, 5, 16, 0)), datetime(2026, 10, 5, 20, 0))
        self.assertEqual(et_to_utc(datetime(2026, 12, 1, 16, 0)), datetime(2026, 12, 1, 21, 0))

    def test_utc_to_et_around_the_changes(self):
        self.assertEqual(utc_to_et(datetime(2026, 3, 8, 6, 59)), datetime(2026, 3, 8, 1, 59))   # still EST
        self.assertEqual(utc_to_et(datetime(2026, 3, 8, 7, 0)), datetime(2026, 3, 8, 3, 0))     # now EDT
        self.assertEqual(utc_to_et(datetime(2026, 11, 1, 5, 59)), datetime(2026, 11, 1, 1, 59))  # still EDT
        self.assertEqual(utc_to_et(datetime(2026, 11, 1, 6, 0)), datetime(2026, 11, 1, 1, 0))   # back to EST

    def test_round_minute(self):
        self.assertEqual(round_minute(datetime(2026, 10, 5, 15, 59, 59)), datetime(2026, 10, 5, 16, 0, 0))
        self.assertEqual(round_minute(datetime(2026, 10, 5, 16, 14, 29)), datetime(2026, 10, 5, 16, 14, 0))

    def test_next_paste_after_am_is_due_by_seven_pm(self):
        run = datetime(2026, 10, 6, 12, 45)  # 08:45 ET
        self.assertEqual(from_ms(next_session_ms("am", run)), datetime(2026, 10, 6, 23, 0))  # 19:00 ET

    def test_next_session_after_pm_skips_the_weekend(self):
        friday = datetime(2026, 10, 9, 22, 30)  # Friday 18:30 ET
        self.assertEqual(from_ms(next_session_ms("pm", friday)), datetime(2026, 10, 12, 13, 30))  # Monday 09:30 ET
        monday = datetime(2026, 10, 5, 22, 30)
        self.assertEqual(from_ms(next_session_ms("pm", monday)), datetime(2026, 10, 6, 13, 30))

    def test_next_session_rejects_unknown_slot(self):
        with self.assertRaises(ValueError):
            next_session_ms("noon", datetime(2026, 10, 6, 12, 0))

    def test_next_paste_after_mid_is_due_by_seven_pm(self):
        run = datetime(2026, 10, 6, 14, 15)  # 10:15 ET
        self.assertEqual(from_ms(next_session_ms("mid", run)), datetime(2026, 10, 6, 23, 0))  # 19:00 ET

    def test_slot_windows_in_summer(self):
        self.assertEqual(slot_for(datetime(2026, 10, 6, 12, 45), "auto"), "am")    # 08:45 ET
        self.assertEqual(slot_for(datetime(2026, 10, 6, 13, 45), "auto"), "am")    # 09:45 ET (late or duplicate cron)
        self.assertEqual(slot_for(datetime(2026, 10, 6, 14, 15), "auto"), "mid")   # 10:15 ET
        self.assertEqual(slot_for(datetime(2026, 10, 6, 21, 30), "auto"), None)    # 17:30 ET: before the evening window
        self.assertEqual(slot_for(datetime(2026, 10, 6, 22, 30), "auto"), "pm")    # 18:30 ET
        self.assertEqual(slot_for(datetime(2026, 10, 6, 23, 30), "auto"), "pm")    # 19:30 ET (late or duplicate cron)
        self.assertEqual(slot_for(datetime(2026, 10, 6, 16, 0), "auto"), None)     # 12:00 ET

    def test_wrong_season_cron_entries_do_nothing_or_repeat_a_slot(self):
        self.assertEqual(slot_for(datetime(2026, 12, 1, 12, 45), "auto"), None)    # 07:45 EST: too early
        self.assertEqual(slot_for(datetime(2026, 12, 1, 13, 45), "auto"), "am")    # 08:45 EST
        self.assertEqual(slot_for(datetime(2026, 12, 1, 14, 15), "auto"), "am")    # 09:15 EST: repeats the am slot
        self.assertEqual(slot_for(datetime(2026, 12, 1, 15, 15), "auto"), "mid")   # 10:15 EST
        self.assertEqual(slot_for(datetime(2026, 12, 1, 22, 30), "auto"), None)    # 17:30 EST: too early
        self.assertEqual(slot_for(datetime(2026, 12, 1, 23, 30), "auto"), "pm")    # 18:30 EST

    def test_forced_slot_ignores_the_clock(self):
        self.assertEqual(slot_for(datetime(2026, 10, 6, 3, 0), "pm"), "pm")


if __name__ == "__main__":
    unittest.main()
