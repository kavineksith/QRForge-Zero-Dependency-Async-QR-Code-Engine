import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.exceptions import (
    BatchProcessingError, DataTooLargeError, ErrorCode, FileSystemError,
    InputValidationError, InvalidStyleOptionError, MaskSelectionError,
    PermissionDeniedError, QRForgeError, ReportGenerationError,
)


class TestErrorCode(unittest.TestCase):
    def test_is_int_enum(self):
        self.assertEqual(int(ErrorCode.EMPTY_DATA), 1100)
        self.assertIsInstance(ErrorCode.EMPTY_DATA, int)

    def test_codes_are_unique(self):
        values = [e.value for e in ErrorCode]
        self.assertEqual(len(values), len(set(values)))


class TestQRForgeErrorBase(unittest.TestCase):
    def test_default_code_applied(self):
        err = InputValidationError("bad input")
        self.assertEqual(err.code, ErrorCode.EMPTY_DATA)

    def test_explicit_code_overrides_default(self):
        err = InputValidationError("bad version", code=ErrorCode.INVALID_VERSION)
        self.assertEqual(err.code, ErrorCode.INVALID_VERSION)

    def test_str_includes_code_name_and_message(self):
        err = DataTooLargeError("too big")
        s = str(err)
        self.assertIn("DATA_TOO_LARGE", s)
        self.assertIn("too big", s)

    def test_repr_includes_context(self):
        err = InvalidStyleOptionError("bad drawer", value="hexagon")
        r = repr(err)
        self.assertIn("InvalidStyleOptionError", r)
        self.assertIn("hexagon", r)

    def test_equality_by_code_and_message(self):
        a = FileSystemError("x")
        b = FileSystemError("x")
        c = FileSystemError("y")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_hashable(self):
        errors = {FileSystemError("x"), FileSystemError("x"), FileSystemError("y")}
        self.assertEqual(len(errors), 2)

    def test_to_dict_roundtrip_fields(self):
        err = BatchProcessingError("bad batch", path="in.csv")
        d = err.to_dict()
        self.assertEqual(d["code"], int(ErrorCode.BATCH_INPUT_INVALID))
        self.assertEqual(d["context"]["path"], "in.csv")

    def test_context_kwargs_stored(self):
        err = ReportGenerationError("failed", path="/tmp/report.xlsx")
        self.assertEqual(err.context["path"], "/tmp/report.xlsx")

    def test_is_exception_subclass(self):
        self.assertTrue(issubclass(InputValidationError, QRForgeError))
        self.assertTrue(issubclass(QRForgeError, Exception))

    def test_inheritance_chain(self):
        self.assertTrue(issubclass(MaskSelectionError, QRForgeError))
        self.assertTrue(issubclass(PermissionDeniedError, FileSystemError))


class TestFromCodeFactory(unittest.TestCase):
    def test_reconstructs_registered_subclass(self):
        rebuilt = QRForgeError.from_code(int(ErrorCode.DATA_TOO_LARGE), "payload too big")
        self.assertIsInstance(rebuilt, DataTooLargeError)
        self.assertEqual(rebuilt.message, "payload too big")

    def test_permission_denied_reconstruction(self):
        rebuilt = QRForgeError.from_code(int(ErrorCode.PERMISSION_DENIED), "no access")
        self.assertIsInstance(rebuilt, PermissionDeniedError)

    def test_unknown_code_falls_back_to_base(self):
        rebuilt = QRForgeError.from_code(999999, "mystery error")
        self.assertIs(type(rebuilt), QRForgeError)
        self.assertEqual(rebuilt.code, ErrorCode.UNKNOWN)

    def test_context_passed_through(self):
        rebuilt = QRForgeError.from_code(int(ErrorCode.BATCH_INPUT_INVALID), "bad", path="a.csv")
        self.assertEqual(rebuilt.context["path"], "a.csv")


if __name__ == "__main__":
    unittest.main()
