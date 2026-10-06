"""Black-76 pricing and gamma, written against the forward price so we never need a dividend yield."""
import math

_SQRT_2PI = math.sqrt(2.0 * math.pi)


def norm_pdf(x):
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1(F, K, T, sigma):
    sd = sigma * math.sqrt(T)
    return (math.log(F / K) + 0.5 * sd * sd) / sd, sd


def black76_price(F, K, T, sigma, r, kind):
    """Price of a European option on a forward F. kind is 'C' or 'P'."""
    d1, sd = _d1(F, K, T, sigma)
    d2 = d1 - sd
    df = math.exp(-r * T)
    if kind == "C":
        return df * (F * norm_cdf(d1) - K * norm_cdf(d2))
    return df * (K * norm_cdf(-d2) - F * norm_cdf(-d1))


def dollar_gamma_per_pct(F, K, T, sigma, r):
    """Gamma x F^2 x 1% for ONE option on ONE unit of the underlying (native dollars).

    gamma_F = exp(-rT) * phi(d1) / (F * sigma * sqrt(T)); multiplied by F^2 and by 0.01.
    Multiply by open interest and the contract size (100) to get the dollars of hedging per 1% move.
    """
    d1, sd = _d1(F, K, T, sigma)
    return math.exp(-r * T) * norm_pdf(d1) * F * 0.01 / sd
