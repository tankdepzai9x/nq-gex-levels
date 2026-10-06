import io
import unittest

from gex.fetch import URL, fetch_json


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FetchTests(unittest.TestCase):
    def test_returns_parsed_json_and_sets_a_user_agent(self):
        seen = {}

        def opener(request, timeout):
            seen["url"] = request.full_url
            seen["ua"] = request.get_header("User-agent")
            return FakeResponse(b'{"ok": 1}')

        self.assertEqual(fetch_json("QQQ", opener=opener, sleep=lambda s: None), {"ok": 1})
        self.assertEqual(seen["url"], URL.format("QQQ"))
        self.assertIn("nq-gex-levels", seen["ua"])

    def test_retries_then_succeeds(self):
        calls = []

        def opener(request, timeout):
            calls.append(1)
            if len(calls) < 3:
                raise OSError("boom")
            return FakeResponse(b'{"ok": 2}')

        waits = []
        self.assertEqual(fetch_json("_NDX", opener=opener, sleep=waits.append), {"ok": 2})
        self.assertEqual(len(calls), 3)
        self.assertEqual(waits, [5.0, 10.0])

    def test_gives_up_loudly(self):
        def opener(request, timeout):
            raise OSError("down")

        with self.assertRaises(RuntimeError) as ctx:
            fetch_json("_NDX", opener=opener, sleep=lambda s: None)
        self.assertIn("_NDX", str(ctx.exception))

    def test_bad_json_counts_as_a_failure(self):
        with self.assertRaises(RuntimeError):
            fetch_json("QQQ", tries=1, opener=lambda r, timeout: FakeResponse(b"<html>"), sleep=lambda s: None)


if __name__ == "__main__":
    unittest.main()
