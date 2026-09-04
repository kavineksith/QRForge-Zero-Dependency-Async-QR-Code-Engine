import unittest
import sys, os, json, tempfile, shutil, asyncio
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.audit_logger import AuditLogger, Severity, Timer


class TestAuditLogger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.tmpdir, "audit.jsonl")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _read_lines(self):
        with open(self.log_path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def test_info_writes_jsonl_record(self):
        logger = AuditLogger(path=self.log_path, level=Severity.INFO, console=False)
        logger.info("test_event", foo="bar")
        records = self._read_lines()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "test_event")
        self.assertEqual(records[0]["foo"], "bar")
        self.assertEqual(records[0]["severity"], "INFO")

    def test_debug_filtered_below_threshold(self):
        logger = AuditLogger(path=self.log_path, level=Severity.INFO, console=False)
        logger.debug("hidden_event")
        self.assertFalse(os.path.exists(self.log_path))

    def test_audit_always_bypasses_filter(self):
        logger = AuditLogger(path=self.log_path, level=Severity.CRITICAL, console=False)
        logger.debug("hidden")
        logger.audit("always_logged")
        records = self._read_lines()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"], "always_logged")
        self.assertEqual(records[0]["severity"], "AUDIT")

    def test_context_manager_logs_exception_on_exit(self):
        try:
            with AuditLogger(path=self.log_path, console=False) as logger:
                raise ValueError("boom")
        except ValueError:
            pass
        records = self._read_lines()
        self.assertTrue(any(r["event"] == "logger_context_exit_with_exception" for r in records))

    def test_rotation_creates_backup_file(self):
        logger = AuditLogger(path=self.log_path, level=Severity.INFO, max_bytes=200, backup_count=2, console=False)
        for i in range(50):
            logger.info("bulk_event", n=i, filler="x" * 20)
        directory_files = os.listdir(self.tmpdir)
        rotated = [f for f in directory_files if f.startswith("audit.jsonl.")]
        self.assertGreater(len(rotated), 0)

    def test_rotation_respects_backup_count(self):
        logger = AuditLogger(path=self.log_path, level=Severity.INFO, max_bytes=100, backup_count=1, console=False)
        for i in range(200):
            logger.info("bulk_event", n=i, filler="x" * 20)
        rotated = [f for f in os.listdir(self.tmpdir) if f.startswith("audit.jsonl.")]
        self.assertLessEqual(len(rotated), 1)

    def test_async_audit_writes_record(self):
        logger = AuditLogger(path=self.log_path, console=False)

        async def go():
            await logger.async_audit("async_event", n=1)

        asyncio.run(go())
        records = self._read_lines()
        self.assertEqual(records[0]["event"], "async_event")

    def test_timer_records_duration_and_status(self):
        logger = AuditLogger(path=self.log_path, console=False)
        with Timer(logger, "operation", label="x"):
            pass
        records = self._read_lines()
        self.assertTrue(any(r["event"] == "operation_completed" for r in records))
        self.assertIn("duration_ms", records[0])

    def test_timer_marks_failed_on_exception(self):
        logger = AuditLogger(path=self.log_path, console=False)
        try:
            with Timer(logger, "operation", label="x"):
                raise RuntimeError("fail")
        except RuntimeError:
            pass
        records = self._read_lines()
        self.assertTrue(any(r["event"] == "operation_failed" for r in records))

    def test_repr(self):
        logger = AuditLogger(path=self.log_path)
        self.assertIn("AuditLogger", repr(logger))


if __name__ == "__main__":
    unittest.main()
