import unittest
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.core import generate_qr, validate_output_dir
from qrforge.exceptions import PermissionDeniedError
from qrforge.models import QRJob


class TestGenerateQR(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _job(self, **overrides):
        defaults = dict(data="https://example.com", output_path=os.path.join(self.tmpdir, "out.png"))
        defaults.update(overrides)
        return QRJob(**defaults)

    def test_successful_generation(self):
        result = generate_qr(self._job())
        self.assertTrue(result.success)
        self.assertTrue(os.path.exists(result.output_path))
        self.assertGreater(result.version, 0)

    def test_empty_data_fails_gracefully(self):
        result = generate_qr(self._job(data="   "))
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error_code)

    def test_invalid_ecc_level_fails_gracefully(self):
        result = generate_qr(self._job(ecc_level="Z"))
        self.assertFalse(result.success)

    def test_never_raises_on_bad_input(self):
        try:
            result = generate_qr(self._job(data="X" * 5000, ecc_level="H"))
        except Exception as exc:  # noqa: BLE001
            self.fail(f"generate_qr raised instead of returning a failed QRResult: {exc}")
        self.assertFalse(result.success)

    def test_styled_generation_succeeds(self):
        result = generate_qr(self._job(styled=True, drawer_style="circle", color_mask="radial"))
        self.assertTrue(result.success)

    def test_output_directory_auto_created(self):
        nested = os.path.join(self.tmpdir, "a", "b", "c", "out.png")
        result = generate_qr(self._job(output_path=nested))
        self.assertTrue(result.success)
        self.assertTrue(os.path.exists(nested))

    def test_explicit_version_too_small_fails(self):
        result = generate_qr(self._job(data="A" * 500, version=1, ecc_level="H"))
        self.assertFalse(result.success)

    def test_duration_recorded(self):
        result = generate_qr(self._job())
        self.assertGreaterEqual(result.duration_ms, 0)


class TestValidateOutputDir(unittest.TestCase):
    def test_creates_missing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "nested", "dir")
            validate_output_dir(target)
            self.assertTrue(os.path.isdir(target))

    @unittest.skipIf(os.name != "posix" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "permission bits are not enforced for the root user")
    def test_raises_on_unwritable_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            locked = os.path.join(tmp, "locked")
            os.makedirs(locked)
            os.chmod(locked, 0o500)
            try:
                with self.assertRaises(PermissionDeniedError):
                    validate_output_dir(os.path.join(locked, "sub"))
            finally:
                os.chmod(locked, 0o700)


if __name__ == "__main__":
    unittest.main()
