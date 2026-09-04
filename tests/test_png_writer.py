import unittest
import sys, os, tempfile, struct, zlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.png_writer import RGBCanvas
from qrforge.exceptions import PNGWriteError


class TestRGBCanvas(unittest.TestCase):
    def test_len_is_pixel_count(self):
        c = RGBCanvas(10, 5)
        self.assertEqual(len(c), 50)

    def test_default_background_white(self):
        c = RGBCanvas(3, 3)
        self.assertEqual(c[0, 0], (255, 255, 255))

    def test_setitem_getitem_roundtrip(self):
        c = RGBCanvas(5, 5)
        c[2, 2] = (10, 20, 30)
        self.assertEqual(c[2, 2], (10, 20, 30))

    def test_out_of_bounds_setitem_is_noop(self):
        c = RGBCanvas(2, 2)
        c[99, 99] = (1, 2, 3)  # should not raise

    def test_fill_rect(self):
        c = RGBCanvas(10, 10)
        c.fill_rect(2, 2, 5, 5, (0, 0, 0))
        self.assertEqual(c[3, 3], (0, 0, 0))
        self.assertEqual(c[8, 8], (255, 255, 255))

    def test_fill_circle_center_colored(self):
        c = RGBCanvas(20, 20)
        c.fill_circle(10, 10, 5, (1, 2, 3))
        self.assertEqual(c[10, 10], (1, 2, 3))

    def test_iter_yields_rows(self):
        c = RGBCanvas(4, 3)
        rows = list(c)
        self.assertEqual(len(rows), 3)


class TestPNGEncoding(unittest.TestCase):
    def test_png_signature(self):
        c = RGBCanvas(4, 4)
        data = c.to_png_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_ihdr_dimensions(self):
        c = RGBCanvas(16, 9)
        data = c.to_png_bytes()
        ihdr_start = data.index(b"IHDR") + 4
        width, height = struct.unpack(">II", data[ihdr_start:ihdr_start + 8])
        self.assertEqual((width, height), (16, 9))

    def test_idat_decompresses_to_expected_size(self):
        w, h = 5, 5
        c = RGBCanvas(w, h)
        data = c.to_png_bytes()
        idat_tag_pos = data.index(b"IDAT")
        idat_len = struct.unpack(">I", data[idat_tag_pos - 4:idat_tag_pos])[0]
        idat = data[idat_tag_pos + 4:idat_tag_pos + 4 + idat_len]
        raw = zlib.decompress(idat)
        self.assertEqual(len(raw), h * (1 + w * 3))  # filter byte + RGB per row

    def test_save_writes_readable_file(self):
        c = RGBCanvas(8, 8)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.png")
            c.save(path)
            with open(path, "rb") as f:
                self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")

    def test_save_to_invalid_path_raises_typed_error(self):
        c = RGBCanvas(4, 4)
        with self.assertRaises(PNGWriteError):
            c.save("/nonexistent_dir_xyz/out.png")


if __name__ == "__main__":
    unittest.main()
