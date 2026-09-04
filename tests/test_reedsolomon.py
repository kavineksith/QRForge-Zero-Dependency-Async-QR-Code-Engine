import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.reedsolomon import GaloisField256, rs_encode, _generator_polynomial


class TestGaloisField256(unittest.TestCase):
    def setUp(self):
        self.gf = GaloisField256()

    def test_len_and_contains(self):
        self.assertEqual(len(self.gf), 256)
        self.assertIn(0, self.gf)
        self.assertIn(255, self.gf)
        self.assertNotIn(256, self.gf)
        self.assertNotIn(-1, self.gf)

    def test_repr(self):
        self.assertIn("GaloisField256", repr(self.gf))

    def test_multiply_by_zero(self):
        self.assertEqual(self.gf.multiply(0, 200), 0)
        self.assertEqual(self.gf.multiply(200, 0), 0)

    def test_multiply_identity(self):
        self.assertEqual(self.gf.multiply(1, 200), 200)

    def test_multiply_commutative(self):
        for a, b in [(5, 9), (200, 3), (17, 250)]:
            self.assertEqual(self.gf.multiply(a, b), self.gf.multiply(b, a))

    def test_exp_log_inverse(self):
        for i in range(1, 255):
            value = self.gf.exp(i)
            self.assertEqual(self.gf.log(value), i)


class TestGeneratorPolynomial(unittest.TestCase):
    def test_degree_matches_length(self):
        for degree in (7, 10, 13, 17, 30):
            poly = _generator_polynomial(degree)
            self.assertEqual(len(poly), degree + 1)

    def test_leading_and_trailing_coeff_nonzero(self):
        poly = _generator_polynomial(10)
        self.assertEqual(poly[0], 1)
        self.assertNotEqual(poly[-1], 0)


class TestRSEncode(unittest.TestCase):
    def test_output_length(self):
        data = [32, 65, 205, 69, 41, 220, 46, 128, 236]
        ec = rs_encode(data, 10)
        self.assertEqual(len(ec), 10)

    def test_known_vector(self):
        # Regression vector for the "HELLO WORLD" v1-L data block, cross-validated
        # against an independent QR encoder's Reed-Solomon output.
        data = [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236]
        ec = rs_encode(data, 10)
        expected = [122, 57, 137, 9, 58, 155, 238, 181, 73, 165]
        self.assertEqual(ec, expected)

    def test_deterministic(self):
        data = [1, 2, 3, 4, 5]
        self.assertEqual(rs_encode(data, 6), rs_encode(data, 6))

    def test_all_zero_data(self):
        ec = rs_encode([0] * 10, 8)
        self.assertEqual(ec, [0] * 8)


if __name__ == "__main__":
    unittest.main()
