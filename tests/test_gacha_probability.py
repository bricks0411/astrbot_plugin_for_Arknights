import sys
import unittest
from pathlib import Path

PLUGIN_PARENT = Path(__file__).resolve().parents[2]
if str(PLUGIN_PARENT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_PARENT))

from astrbot_plugin_for_Arknights.analysis.SixStarsAnalyser import (
    GachaHistoryAnalyser,
)


class SixStarProbabilityTests(unittest.TestCase):

    def test_probability_boundaries(self):
        boundary_rates = {
            0: 2.0,
            49: 2.0,
            50: 4.0,
            51: 6.0,
            97: 98.0,
            98: 100.0,
            99: 100.0,
            100: 100.0,
        }

        for pulls, expected_rate in boundary_rates.items():
            with self.subTest(pulls=pulls):
                self.assertEqual(
                    GachaHistoryAnalyser._next_six_star_rate(pulls),
                    expected_rate,
                )


if __name__ == "__main__":
    unittest.main()
