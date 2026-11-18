import unittest
from nvme_sentinel.monitor import evaluate_apst_status


class NvmeTests(unittest.TestCase):
    def test_apst_status_grading(self):
        self.assertEqual(evaluate_apst_status(5500, 42), "DEEP_PS4_OPTIMAL")
        self.assertEqual(evaluate_apst_status(2000, 40), "LIGHT_APST")
        self.assertEqual(evaluate_apst_status(0, 38), "APST_DISABLED")
        self.assertEqual(evaluate_apst_status(5500, 75), "THERMAL_WARN")


if __name__ == "__main__":
    unittest.main()
