"""VV_RATE_LIMIT knob: mirror console rate budget is operator-settable.

Run from meta code new 2.0 root:  python backend/tests/test_rate_limit_env.py
Default 120/min per client address stands; browser suites and
multi-viewer proxied demos share one egress bucket and need a
raised budget without code edits.
"""

import os
import sys
import unittest
from unittest.mock import patch

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, BASE)

from backend.config import load_settings  # noqa: E402


class TestRateLimitEnv(unittest.TestCase):
    def _load(self, env):
        base = {"APP_ENV": "development", "APP_SECRET": "x" * 40}
        base.update(env)
        with patch.dict(os.environ, base, clear=True):
            return load_settings()

    def test_default_is_120(self):
        self.assertEqual(self._load({}).rate_limit, 120)

    def test_override_applies(self):
        self.assertEqual(self._load({"VV_RATE_LIMIT": "600"}).rate_limit, 600)

    def test_invalid_falls_back(self):
        for bad in ("nope", "", "0", "-5", "12.5"):
            with self.subTest(bad=bad):
                self.assertEqual(
                    self._load({"VV_RATE_LIMIT": bad}).rate_limit, 120)


if __name__ == "__main__":
    unittest.main(verbosity=2)
