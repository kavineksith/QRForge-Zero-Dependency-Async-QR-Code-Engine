import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.encoder import (
    BitBuffer, MODE_ALPHANUMERIC, MODE_BYTE, MODE_NUMERIC,
    build_bitstream, data_capacity_bits, interleave_with_ecc,
    select_mode, select_version,
)
from qrforge.exceptions import DataTooLargeError


class TestBitBuffer(unittest.TestCase):
    def test_len_tracks_bits_written(self):
        buf = BitBuffer()
        buf.put(0b101, 3)
        self.assertEqual(len(buf), 3)

    def test_put_is_chainable(self):
        buf = BitBuffer().put(1, 1).put(0, 1)
        self.assertEqual(len(buf), 2)

    def test_to_bytes_pads_with_zero_bits(self):
        buf = BitBuffer()
        buf.put(0b1, 1)
        self.assertEqual(buf.to_bytes(), [0b10000000])

    def test_iter_yields_bits_in_order(self):
        buf = BitBuffer()
        buf.put(0b1010, 4)
        self.assertEqual(list(buf), [1, 0, 1, 0])


class TestSelectMode(unittest.TestCase):
    def test_numeric(self):
        self.assertEqual(select_mode(b"0123456789"), MODE_NUMERIC)

    def test_alphanumeric(self):
        self.assertEqual(select_mode(b"HELLO WORLD 123"), MODE_ALPHANUMERIC)

    def test_byte_for_lowercase(self):
        self.assertEqual(select_mode(b"hello"), MODE_BYTE)

    def test_byte_for_utf8(self):
        self.assertEqual(select_mode("日本語".encode("utf-8")), MODE_BYTE)

    def test_byte_for_symbols_outside_alphanumeric_set(self):
        self.assertEqual(select_mode(b"user@example.com"), MODE_BYTE)


class TestSelectVersion(unittest.TestCase):
    def test_small_payload_picks_version_1(self):
        version = select_version(b"HI", "L", MODE_ALPHANUMERIC)
        self.assertEqual(version, 1)

    def test_larger_payload_needs_larger_version(self):
        version = select_version(b"A" * 100, "H", MODE_BYTE)
        self.assertGreater(version, 1)

    def test_higher_ecc_needs_larger_or_equal_version(self):
        v_low = select_version(b"A" * 60, "L", MODE_BYTE)
        v_high = select_version(b"A" * 60, "H", MODE_BYTE)
        self.assertGreaterEqual(v_high, v_low)

    def test_oversized_payload_raises(self):
        with self.assertRaises(DataTooLargeError):
            select_version(b"X" * 5000, "H", MODE_BYTE)

    def test_min_version_respected(self):
        version = select_version(b"HI", "L", MODE_ALPHANUMERIC, min_version=5)
        self.assertGreaterEqual(version, 5)


class TestBuildBitstream(unittest.TestCase):
    def test_output_length_matches_capacity(self):
        version, ecc = 1, "L"
        codewords = build_bitstream(b"HELLO WORLD", version, ecc, MODE_ALPHANUMERIC)
        self.assertEqual(len(codewords), data_capacity_bits(version, ecc) // 8)

    def test_padding_uses_standard_pad_bytes(self):
        codewords = build_bitstream(b"HI", 1, "L", MODE_ALPHANUMERIC)
        tail = codewords[-4:]
        # Standard QR padding alternates 0xEC, 0x11.
        for i, b in enumerate(tail):
            self.assertIn(b, (0xEC, 0x11))


class TestInterleaveWithEcc(unittest.TestCase):
    def test_single_block_length(self):
        version, ecc = 1, "L"
        codewords = build_bitstream(b"HI", version, ecc, MODE_ALPHANUMERIC)
        interleaved = interleave_with_ecc(codewords, version, ecc)
        # version 1-L: 19 data + 7 ec = 26 total codewords, single block.
        self.assertEqual(len(interleaved), 26)

    def test_multi_block_length(self):
        version, ecc = 5, "Q"
        codewords = build_bitstream(b"A" * 60, version, ecc, MODE_BYTE)
        interleaved = interleave_with_ecc(codewords, version, ecc)
        # version 5-Q: 2 blocks of 15 data + 2 blocks of 16 data, 18 ec codewords/block.
        self.assertEqual(len(interleaved), (2 * 15 + 2 * 16) + 18 * 4)


if __name__ == "__main__":
    unittest.main()
