import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.models import QRJob, QRResult


class TestQRJob(unittest.TestCase):
    def test_len_is_data_length(self):
        job = QRJob(data="hello", output_path="out.png")
        self.assertEqual(len(job), 5)

    def test_contains_checks_substring(self):
        job = QRJob(data="hello world", output_path="out.png")
        self.assertIn("world", job)
        self.assertNotIn("xyz", job)

    def test_auto_label_from_data(self):
        data = "https://example.com/very/long/path"
        job = QRJob(data=data, output_path="out.png")
        self.assertEqual(job.label, data[:32])

    def test_explicit_label_preserved(self):
        job = QRJob(data="x", output_path="out.png", label="custom")
        self.assertEqual(job.label, "custom")

    def test_equality_by_data_and_path(self):
        a = QRJob(data="x", output_path="out.png")
        b = QRJob(data="x", output_path="out.png")
        c = QRJob(data="x", output_path="other.png")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_hashable_and_usable_in_set(self):
        jobs = {QRJob(data="x", output_path="a.png"), QRJob(data="x", output_path="a.png")}
        self.assertEqual(len(jobs), 1)

    def test_lt_orders_by_data_length(self):
        short = QRJob(data="a", output_path="a.png")
        long_ = QRJob(data="a" * 10, output_path="b.png")
        self.assertLess(short, long_)

    def test_str_contains_label_and_path(self):
        job = QRJob(data="x", output_path="out.png")
        s = str(job)
        self.assertIn("out.png", s)


class TestQRResult(unittest.TestCase):
    def test_bool_reflects_success(self):
        job = QRJob(data="x", output_path="out.png")
        ok = QRResult(job=job, success=True)
        fail = QRResult(job=job, success=False, error="boom")
        self.assertTrue(bool(ok))
        self.assertFalse(bool(fail))

    def test_str_success_includes_output_path(self):
        job = QRJob(data="x", output_path="out.png")
        result = QRResult(job=job, success=True, output_path="out.png", version=1, mode="byte")
        self.assertIn("out.png", str(result))

    def test_str_failure_includes_error(self):
        job = QRJob(data="x", output_path="out.png")
        result = QRResult(job=job, success=False, error="bad payload")
        self.assertIn("bad payload", str(result))

    def test_to_dict_has_expected_keys(self):
        job = QRJob(data="x", output_path="out.png")
        result = QRResult(job=job, success=True, output_path="out.png", version=2)
        d = result.to_dict()
        for key in ("label", "success", "output_path", "version", "duration_ms"):
            self.assertIn(key, d)

    def test_equality_and_hash(self):
        job = QRJob(data="x", output_path="out.png")
        a = QRResult(job=job, success=True)
        b = QRResult(job=job, success=True)
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))


if __name__ == "__main__":
    unittest.main()
