"""tests/fixtures/golden_levels.txt is shared with the Pine checks (tools/pine_check.mjs), so it must stay exactly what the generator writes."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class GoldenFixtureTests(unittest.TestCase):
    def test_fixed_sample_is_byte_for_byte_the_golden_file(self):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_sample.py"), "--fixed"],
                             capture_output=True, check=True).stdout
        with open(os.path.join(ROOT, "tests", "fixtures", "golden_levels.txt"), "rb") as f:
            golden = f.read()
        self.assertEqual(out, golden)


if __name__ == "__main__":
    unittest.main()
