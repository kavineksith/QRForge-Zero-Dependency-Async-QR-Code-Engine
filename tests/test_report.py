import unittest
import sys, os, tempfile, shutil, json, csv, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.models import QRJob, QRResult
from qrforge.report import to_csv, to_json, to_terminal, to_xlsx


def _sample_results():
    job1 = QRJob(data="https://a.com", output_path="a.png")
    job2 = QRJob(data="bad", output_path="b.png")
    return [
        QRResult(job=job1, success=True, output_path="a.png", version=2, mode="byte", mask_pattern=3),
        QRResult(job=job2, success=False, error="empty payload", error_code=1100),
    ]


class TestReportFormats(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.results = _sample_results()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_json_report_structure(self):
        path = os.path.join(self.tmpdir, "r.json")
        to_json(self.results, path)
        with open(path) as f:
            payload = json.load(f)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["succeeded"], 1)
        self.assertEqual(payload["failed"], 1)
        self.assertEqual(len(payload["results"]), 2)

    def test_csv_report_has_header_and_rows(self):
        path = os.path.join(self.tmpdir, "r.csv")
        to_csv(self.results, path)
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)
        self.assertIn("label", rows[0])

    def test_xlsx_report_is_valid_zip_with_sheet(self):
        path = os.path.join(self.tmpdir, "r.xlsx")
        to_xlsx(self.results, path)
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            self.assertIn("xl/worksheets/sheet1.xml", names)
            sheet_xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("a.png", sheet_xml)
            self.assertIn("empty payload", sheet_xml)

    def test_terminal_report_contains_summary_counts(self):
        text = to_terminal(self.results)
        self.assertIn("2 job(s)", text)
        self.assertIn("1 ok", text)
        self.assertIn("1 failed", text)

    def test_xlsx_escapes_special_characters(self):
        job = QRJob(data="<script>&\"'</script>", output_path="x.png")
        result = QRResult(job=job, success=True, output_path="x.png")
        path = os.path.join(self.tmpdir, "esc.xlsx")
        to_xlsx([result], path)  # must not raise, and must escape safely
        with zipfile.ZipFile(path) as z:
            sheet_xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertNotIn("<script>", sheet_xml)


if __name__ == "__main__":
    unittest.main()
