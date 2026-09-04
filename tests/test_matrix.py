import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.encoder import build_bitstream, interleave_with_ecc, select_mode, select_version
from qrforge.exceptions import InvalidStyleOptionError
from qrforge.matrix import QRMatrix, build_matrix, format_info_bits


class TestQRMatrixConstruction(unittest.TestCase):
    def test_size_formula(self):
        for version, expected_size in ((1, 21), (2, 25), (10, 57), (40, 177)):
            self.assertEqual(QRMatrix(version, "L").size, expected_size)

    def test_len_matches_size(self):
        m = QRMatrix(3, "M")
        self.assertEqual(len(m), m.size)

    def test_finder_patterns_present(self):
        m = QRMatrix(1, "L")
        # Top-left finder pattern outer ring must be all dark.
        for i in range(7):
            self.assertEqual(m.modules[0][i], 1)
            self.assertEqual(m.modules[i][0], 1)

    def test_getitem_and_contains(self):
        m = QRMatrix(1, "L")
        self.assertEqual(m[(0, 0)], 1)
        self.assertIn((0, 0), m)
        self.assertNotIn((-1, 0), m)

    def test_repr(self):
        m = QRMatrix(2, "Q")
        r = repr(m)
        self.assertIn("version=2", r)
        self.assertIn("Q", r)

    def test_dark_module_always_set(self):
        for version in (1, 2, 7):
            m = QRMatrix(version, "L")
            self.assertEqual(m.modules[m.size - 8][8], 1)


class TestFormatInfo(unittest.TestCase):
    def test_length_is_15_bits(self):
        self.assertEqual(len(format_info_bits("L", 0)), 15)

    def test_differs_by_mask(self):
        a = format_info_bits("L", 0)
        b = format_info_bits("L", 1)
        self.assertNotEqual(a, b)

    def test_differs_by_ecc_level(self):
        a = format_info_bits("L", 0)
        b = format_info_bits("H", 0)
        self.assertNotEqual(a, b)


class TestBuildMatrix(unittest.TestCase):
    def _matrix_for(self, text, ecc="L"):
        data = text.encode("utf-8")
        mode = select_mode(data)
        version = select_version(data, ecc, mode)
        codewords = build_bitstream(data, version, ecc, mode)
        interleaved = interleave_with_ecc(codewords, version, ecc)
        return build_matrix(interleaved, version, ecc)

    def test_returns_matrix_and_valid_mask_index(self):
        matrix, mask = self._matrix_for("HELLO WORLD")
        self.assertIsInstance(matrix, QRMatrix)
        self.assertIn(mask, range(8))

    def test_no_unset_modules_remain(self):
        matrix, _ = self._matrix_for("Test payload 12345")
        for row in matrix.modules:
            self.assertNotIn(-1, row)

    def test_penalty_score_is_non_negative(self):
        matrix, _ = self._matrix_for("Another test string")
        self.assertGreaterEqual(matrix.penalty_score(), 0)

    def test_chosen_mask_has_lowest_or_equal_penalty(self):
        data = b"Portfolio grade QR encoder"
        mode = select_mode(data)
        version = select_version(data, "M", mode)
        codewords = build_bitstream(data, version, "M", mode)
        interleaved = interleave_with_ecc(codewords, version, "M")
        base = QRMatrix(version, "M")
        base.place_data(interleaved)
        scores = []
        for pattern in range(8):
            candidate = base.apply_mask(pattern)
            candidate.write_format_info(pattern)
            scores.append(candidate.penalty_score())
        best_matrix, best_pattern = build_matrix(interleaved, version, "M")
        self.assertEqual(scores[best_pattern], min(scores))


class TestIsFunctionModule(unittest.TestCase):
    def test_finder_pattern_is_function_module(self):
        m = QRMatrix(1, "L")
        self.assertTrue(m.is_function_module(0, 0))

    def test_typical_data_area_not_function_module(self):
        m = QRMatrix(1, "L")
        # Row 12, col 12 lies in the data area for a version-1 (21x21) symbol.
        self.assertFalse(m.is_function_module(12, 12))


if __name__ == "__main__":
    unittest.main()
