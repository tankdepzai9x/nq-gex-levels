"""Pins for the paste format (gex/encode.py), beyond the first tests in test_encode.py.

The format is the contract between the Python writer and the Pine parser, so its edge cases are pinned here:
rounding to the nearest whole number, no "-0", levels at distance 0, the meaning of the top flag, no empty prof
line, the order of the sets, and what decode tolerates.
"""
import unittest

from gex.compute import Levels
from gex.encode import decode, encode
from tests.test_encode import sample_levels


def body(**kw):
    """The lines a set writes after its 'set A' and 'reg P' lines."""
    return encode(1, "am", 2, 3, {"A": Levels(reg="P", **kw)}).splitlines()[7:]


class EncodePinTests(unittest.TestCase):
    def test_rounds_to_nearest_not_down(self):
        # fractions of .6 (and .4), so truncating or flooring a distance or a thousand would give another answer
        self.assertEqual(
            body(flip=-312.6, cw=650.6, pw=-425.4, top=[(-200.6, True)], em=365.7,
                 profile=[(-99.6, -4_200_600.0), (50.4, 12_000_400.0)]),
            ["flip -313", "cw 651", "pw -425", "top -201:+", "em 366", "prof -100:-4201 50:12000"])

    def test_small_distances_never_print_minus_zero(self):
        self.assertEqual(body(cw=-0.4, pw=0.4, em=0.2, profile=[(-0.4, 5_000_000.0)]),
                         ["cw 0", "pw 0", "em 0", "prof 0:5000"])

    def test_levels_at_the_anchor_price_are_kept(self):
        # a distance of exactly 0 is still a level, and an expected move of 0 is still written
        self.assertEqual(body(flip=0.0, cw=0.0, pw=0.0, em=0.0), ["flip 0", "cw 0", "pw 0", "em 0"])

    def test_top_flag_follows_net_gex_not_the_side_of_the_price(self):
        # in test_encode.py's sample the flag and the side of the price happen to agree; here they do not
        self.assertEqual(body(top=[(-200.0, True), (100.0, False)], em=1.0), ["top -200:+ 100:-", "em 1"])
        self.assertEqual(body(top=[(50.0, True)], em=1.0), ["top 50:+", "em 1"])

    def test_no_prof_line_when_nothing_survives_rounding(self):
        self.assertEqual(body(em=50.0), ["em 50"])
        self.assertEqual(body(em=50.0, profile=[(0.0, 300.0), (25.0, -499.0)]), ["em 50"])

    def test_sets_come_out_in_the_order_given(self):
        text = encode(1, "am", 2, 3, {"WIDE": Levels(reg="N", em=1.0), "NEAR": Levels(reg="P", em=2.0)})
        self.assertEqual([ln for ln in text.splitlines() if ln.startswith("set ")], ["set WIDE", "set NEAR"])


class DecodePinTests(unittest.TestCase):
    def setUp(self):
        self.text = encode(1, "am", 2, 3, {"NEAR": sample_levels()})

    def test_blank_lines_before_the_header_are_ignored(self):
        self.assertEqual(decode("\n\r\n  \n" + self.text), decode(self.text))

    def test_spaces_and_tabs_around_lines_are_ignored(self):
        messy = "".join("  " + ln + " \t\n" for ln in self.text.splitlines())
        self.assertEqual(decode(messy), decode(self.text))

    def test_time_fields_decode_as_integers(self):
        out = decode(self.text)
        for key in ("gen", "anchor", "next"):
            self.assertIsInstance(out[key], int)


if __name__ == "__main__":
    unittest.main()
