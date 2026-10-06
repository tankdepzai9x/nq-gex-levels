import unittest

from gex.compute import Levels
from gex.encode import decode, encode


def sample_levels():
    return Levels(reg="P", flip=-312.4, cw=650.0, pw=-425.0, top=[(-200.0, False), (100.0, True)], em=365.2,
                  profile=[(-200.0, -4_200_400.0), (-175.0, 300.0), (100.0, 12_000_000.0)])


class EncodeTests(unittest.TestCase):
    def test_exact_text_format(self):
        text = encode(1790000000000, "am", 1789990000000, 1790100000000, {"NEAR": sample_levels()})
        self.assertEqual(text, "\n".join([
            "GEX1", "gen 1790000000000", "slot am", "anchor 1789990000000", "next 1790100000000",
            "set NEAR", "reg P", "flip -312", "cw 650", "pw -425", "top -200:- 100:+", "em 365",
            "prof -200:-4200 100:12000", ""]))      # the -175 bucket rounds to 0 thousand and is left out

    def test_round_trip(self):
        text = encode(1, "pm", 2, 3, {"NEAR": sample_levels(), "WIDE": Levels(reg="N", em=100.0)})
        out = decode(text)
        self.assertEqual((out["gen"], out["slot"], out["anchor"], out["next"]), (1, "pm", 2, 3))
        near = out["sets"]["NEAR"]
        self.assertEqual((near["reg"], near["flip"], near["cw"], near["pw"], near["em"]),
                         ("P", -312.0, 650.0, -425.0, 365.0))
        self.assertEqual(near["top"], [(-200.0, False), (100.0, True)])
        self.assertEqual(near["prof"], [(-200.0, -4200.0), (100.0, 12000.0)])
        wide = out["sets"]["WIDE"]
        self.assertEqual((wide["reg"], wide["flip"], wide["cw"], wide["pw"], wide["top"], wide["prof"]),
                         ("N", None, None, None, [], []))

    def test_missing_levels_are_left_out(self):
        text = encode(1, "am", 2, 3, {"NEAR": Levels(reg="P", em=50.0)})
        self.assertNotIn("flip", text)
        self.assertNotIn("cw", text)
        self.assertNotIn("top", text)

    def test_decode_tolerates_windows_line_endings_bom_and_blank_lines(self):
        text = encode(1, "am", 2, 3, {"NEAR": sample_levels()})
        messy = "\ufeff" + text.replace("\n", "\r\n") + "\r\n\r\n"
        self.assertEqual(decode(messy), decode(text))

    def test_decode_rejects_other_text(self):
        for bad in ("", "hello", "GEX2\ngen 1"):
            with self.assertRaises(ValueError):
                decode(bad)


if __name__ == "__main__":
    unittest.main()
