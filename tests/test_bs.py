import math
import unittest

from gex.bs import black76_price, dollar_gamma_per_pct, norm_cdf, norm_pdf


class BlackScholesTests(unittest.TestCase):
    def test_normal_functions(self):
        self.assertAlmostEqual(norm_pdf(0.0), 0.3989422804, places=9)
        self.assertAlmostEqual(norm_cdf(0.0), 0.5, places=12)
        self.assertAlmostEqual(norm_cdf(1.96), 0.9750021049, places=8)

    def test_atm_price_matches_textbook(self):
        # F=K=100, T=1, vol 20%, no discounting: price = F * (2*N(0.1) - 1) = 7.9656...
        self.assertAlmostEqual(black76_price(100, 100, 1.0, 0.2, 0.0, "C"), 7.965567, places=5)

    def test_put_call_parity(self):
        c = black76_price(100, 95, 0.5, 0.25, 0.03, "C")
        p = black76_price(100, 95, 0.5, 0.25, 0.03, "P")
        self.assertAlmostEqual(c - p, math.exp(-0.03 * 0.5) * (100 - 95), places=9)

    def test_dollar_gamma_hand_worked_example(self):
        # F=K=100, T=0.25, vol 20%, r=0 -> sd=0.1, d1=0.05
        # gamma_F = phi(0.05)/(100*0.1) = 0.0398444; x F^2 x 0.01 = 3.98444
        self.assertAlmostEqual(dollar_gamma_per_pct(100, 100, 0.25, 0.2, 0.0), 3.984436, places=5)

    def test_gamma_is_highest_at_the_money(self):
        atm = dollar_gamma_per_pct(100, 100, 0.1, 0.2, 0.0)
        self.assertGreater(atm, dollar_gamma_per_pct(100, 110, 0.1, 0.2, 0.0))
        self.assertGreater(atm, dollar_gamma_per_pct(100, 90, 0.1, 0.2, 0.0))


if __name__ == "__main__":
    unittest.main()
