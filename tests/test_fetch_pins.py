"""Extra checks for gex.fetch. Nothing here touches the network: every download goes through a fake opener."""
import unittest

from gex.fetch import URL, fetch_json
from tests.test_fetch import FakeResponse


class FetchPinTests(unittest.TestCase):
    def test_a_download_that_always_fails_is_tried_exactly_three_times(self):
        calls = []

        def opener(request, timeout):
            calls.append(1)
            raise OSError("down")

        with self.assertRaises(RuntimeError):
            fetch_json("_NDX", opener=opener, sleep=lambda s: None)
        self.assertEqual(len(calls), 3)

    def test_the_urls_are_the_real_cboe_ones(self):
        # test_fetch compares against URL itself, so a typo in URL would be invisible there
        self.assertEqual(URL.format("_NDX"), "https://cdn.cboe.com/api/global/delayed_quotes/options/_NDX.json")
        self.assertEqual(URL.format("QQQ"), "https://cdn.cboe.com/api/global/delayed_quotes/options/QQQ.json")

    def test_each_symbol_is_requested_from_its_own_url(self):
        seen = []

        def opener(request, timeout):
            seen.append(request.full_url)
            return FakeResponse(b"{}")

        fetch_json("_NDX", opener=opener, sleep=lambda s: None)
        fetch_json("QQQ", opener=opener, sleep=lambda s: None)
        self.assertEqual(seen, ["https://cdn.cboe.com/api/global/delayed_quotes/options/_NDX.json",
                                "https://cdn.cboe.com/api/global/delayed_quotes/options/QQQ.json"])

    def test_the_timeout_is_sixty_seconds(self):
        seen = {}

        def opener(request, timeout):
            seen["timeout"] = timeout
            return FakeResponse(b"{}")

        fetch_json("QQQ", opener=opener, sleep=lambda s: None)
        self.assertEqual(seen["timeout"], 60)

    def test_the_last_error_reaches_the_message(self):
        def opener(request, timeout):
            raise OSError("HTTP 403 forbidden")

        with self.assertRaises(RuntimeError) as ctx:
            fetch_json("QQQ", opener=opener, sleep=lambda s: None)
        self.assertIn("403", str(ctx.exception))

    def test_the_body_is_read_as_utf8(self):
        body = b'{"name": "caf\xc3\xa9"}'          # the two bytes C3 A9 are one accented e in UTF-8
        out = fetch_json("QQQ", opener=lambda r, timeout: FakeResponse(body), sleep=lambda s: None)
        self.assertEqual(out["name"], "caf" + chr(233))


if __name__ == "__main__":
    unittest.main()
