import unittest

from ..analysis.SixStarsAnalyser import GachaHistoryAnalyser


class SixStarProbabilityTests(unittest.TestCase):

    def test_probability_boundaries(self):
        boundary_rates = {
            49: 2.0,
            50: 4.0,
            51: 6.0,
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
