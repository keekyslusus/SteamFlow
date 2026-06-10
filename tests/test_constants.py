import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIB_PATH = PROJECT_ROOT / "lib"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(LIB_PATH) not in sys.path:
    sys.path.insert(0, str(LIB_PATH))

from steamflow.constants import STEAMFLOW_CONFIG


class ConstantsTests(unittest.TestCase):
    def test_all_visible_store_results_can_fetch_appdetails_price_format(self):
        self.assertGreaterEqual(
            STEAMFLOW_CONFIG.query.store_cold_metric_fetch_limit,
            STEAMFLOW_CONFIG.query.max_results,
        )


if __name__ == "__main__":
    unittest.main()
