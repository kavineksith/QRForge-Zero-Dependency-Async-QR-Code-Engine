import unittest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qrforge.encoder import build_bitstream, interleave_with_ecc, select_mode, select_version
from qrforge.exceptions import InvalidStyleOptionError
from qrforge.matrix import build_matrix
from qrforge.renderer import parse_color, render


def _sample_matrix(text="HELLO WORLD", ecc="L"):
    data = text.encode("utf-8")
    mode = select_mode(data)
    version = select_version(data, ecc, mode)
    codewords = build_bitstream(data, version, ecc, mode)
    interleaved = interleave_with_ecc(codewords, version, ecc)
    matrix, _ = build_matrix(interleaved, version, ecc)
    return matrix


class TestParseColor(unittest.TestCase):
    def test_named_color(self):
        self.assertEqual(parse_color("black"), (0, 0, 0))
        self.assertEqual(parse_color("white"), (255, 255, 255))

    def test_hex_with_hash(self):
        self.assertEqual(parse_color("#FF0000"), (255, 0, 0))

    def test_hex_without_hash(self):
        self.assertEqual(parse_color("00FF00"), (0, 255, 0))

    def test_case_insensitive_name(self):
        self.assertEqual(parse_color("BLACK"), (0, 0, 0))

    def test_invalid_color_raises(self):
        with self.assertRaises(InvalidStyleOptionError):
            parse_color("not_a_color")


class TestRender(unittest.TestCase):
    def test_output_dimensions_match_box_size_and_border(self):
        matrix = _sample_matrix()
        canvas = render(matrix, box_size=4, border=2)
        expected = matrix.size * 4 + 2 * 2 * 4
        self.assertEqual(canvas.width, expected)
        self.assertEqual(canvas.height, expected)

    def test_unstyled_uses_plain_black_on_white(self):
        matrix = _sample_matrix()
        canvas = render(matrix, box_size=3, border=1)
        # A finder-pattern corner module (just inside the quiet zone) must render as black.
        self.assertEqual(canvas[3, 3], (0, 0, 0))

    def test_styled_with_custom_colors(self):
        matrix = _sample_matrix()
        canvas = render(matrix, box_size=3, border=1, styled=True, drawer_style="square",
                         color_mask="solid", foreground="#0000FF", background="white")
        self.assertEqual(canvas[3, 3], (0, 0, 255))

    def test_invalid_drawer_style_raises(self):
        matrix = _sample_matrix()
        with self.assertRaises(InvalidStyleOptionError):
            render(matrix, styled=True, drawer_style="hexagon")

    def test_invalid_color_mask_raises(self):
        matrix = _sample_matrix()
        with self.assertRaises(InvalidStyleOptionError):
            render(matrix, styled=True, color_mask="rainbow")

    def test_function_modules_stay_solid_under_gradient(self):
        matrix = _sample_matrix()
        canvas = render(matrix, box_size=3, border=1, styled=True, drawer_style="circle",
                         color_mask="radial", foreground="black", background="white")
        # Top-left finder pattern corner must remain full foreground, never faded.
        self.assertEqual(canvas[3, 3], (0, 0, 0))

    def test_all_drawer_styles_run_without_error(self):
        matrix = _sample_matrix()
        for style in ("square", "rounded", "gapped", "circle", "vertical", "horizontal"):
            render(matrix, box_size=4, border=1, styled=True, drawer_style=style)

    def test_all_color_masks_run_without_error(self):
        matrix = _sample_matrix()
        for mask in ("solid", "radial", "square", "horizontal", "vertical"):
            render(matrix, box_size=4, border=1, styled=True, color_mask=mask)


if __name__ == "__main__":
    unittest.main()
