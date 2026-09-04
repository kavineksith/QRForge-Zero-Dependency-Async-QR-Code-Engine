import unittest
import sys, os, tempfile, shutil, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.audit_logger import AuditLogger
from qrforge.exceptions import BatchProcessingError
from qrforge.pipeline import run_batch_sync, stream_jobs_from_file


class TestStreamJobsFromFile(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_streams_from_txt(self):
        path = os.path.join(self.tmpdir, "in.txt")
        with open(path, "w") as f:
            f.write("one\ntwo\n\nthree\n")
        jobs = list(stream_jobs_from_file(path, self.tmpdir))
        self.assertEqual([j.data for j in jobs], ["one", "two", "three"])

    def test_is_a_generator_not_a_list(self):
        path = os.path.join(self.tmpdir, "in.txt")
        with open(path, "w") as f:
            f.write("one\n")
        result = stream_jobs_from_file(path, self.tmpdir)
        self.assertTrue(hasattr(result, "__next__") or hasattr(result, "__iter__"))
        self.assertFalse(isinstance(result, list))

    def test_streams_from_csv_with_data_column(self):
        path = os.path.join(self.tmpdir, "in.csv")
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["data", "filename"])
            writer.writeheader()
            writer.writerow({"data": "payload1", "filename": "a.png"})
            writer.writerow({"data": "payload2", "filename": "b.png"})
        jobs = list(stream_jobs_from_file(path, self.tmpdir))
        self.assertEqual(len(jobs), 2)
        self.assertTrue(jobs[0].output_path.endswith("a.png"))

    def test_csv_missing_data_column_raises(self):
        path = os.path.join(self.tmpdir, "bad.csv")
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["payload"])
            writer.writeheader()
            writer.writerow({"payload": "x"})
        with self.assertRaises(BatchProcessingError):
            list(stream_jobs_from_file(path, self.tmpdir))

    def test_missing_file_raises(self):
        with self.assertRaises(BatchProcessingError):
            list(stream_jobs_from_file(os.path.join(self.tmpdir, "nope.txt"), self.tmpdir))


class TestRunBatchSync(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.logger = AuditLogger(path=os.path.join(self.tmpdir, "audit.jsonl"), console=False)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_processes_all_jobs(self):
        in_path = os.path.join(self.tmpdir, "in.txt")
        with open(in_path, "w") as f:
            f.write("https://a.com\nhttps://b.com\nhttps://c.com\n")
        out_dir = os.path.join(self.tmpdir, "out")
        jobs = stream_jobs_from_file(in_path, out_dir)
        results = run_batch_sync(jobs, self.logger, concurrency=2)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r.success for r in results))
        self.assertTrue(all(os.path.exists(r.output_path) for r in results))

    def test_empty_batch_returns_empty_list(self):
        results = run_batch_sync(iter([]), self.logger, concurrency=2)
        self.assertEqual(results, [])

    def test_mixed_success_and_failure(self):
        in_path = os.path.join(self.tmpdir, "in.txt")
        with open(in_path, "w") as f:
            f.write("good payload\n")
        out_dir = os.path.join(self.tmpdir, "out")
        jobs = list(stream_jobs_from_file(in_path, out_dir))
        jobs.append(__import__("qrforge.models", fromlist=["QRJob"]).QRJob(
            data="", output_path=os.path.join(out_dir, "bad.png")))
        results = run_batch_sync(jobs, self.logger, concurrency=2)
        self.assertEqual(sum(r.success for r in results), 1)
        self.assertEqual(sum(not r.success for r in results), 1)


if __name__ == "__main__":
    unittest.main()
