"""
renderer.py
===========
Rasterizes a QRMatrix into a styled RGBCanvas: module drawer shapes
(square/rounded/gapped/circle/vertical/horizontal bars) and color masks
(solid/radial/square/horizontal/vertical gradient), then hands off to the
pure-stdlib PNG writer.
"""

from __future__ import annotations
import math
import re
from typing import Callable, Tuple

from .exceptions import ErrorCode, InvalidStyleOptionError
from .matrix import QRMatrix
from .png_writer import RGBCanvas, RGB

_NAMED_COLORS = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (220, 38, 38),
    "green": (22, 163, 74), "blue": (37, 99, 235), "yellow": (234, 179, 8),
    "orange": (234, 88, 12), "purple": (147, 51, 234), "cyan": (8, 145, 178),
    "magenta": (219, 39, 119), "gray": (107, 114, 128), "grey": (107, 114, 128),
    "navy": (30, 58, 138), "teal": (13, 148, 136), "indigo": (79, 70, 229),
    "maroon": (127, 29, 29), "gold": (202, 138, 4),
}
_HEX_RE = re.compile(r"^#?([0-9A-Fa-f]{6})$")


def parse_color(value: str) -> RGB:
    if value.lower() in _NAMED_COLORS:
        return _NAMED_COLORS[value.lower()]
    match = _HEX_RE.match(value.strip())
    if match:
        h = match.group(1)
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    raise InvalidStyleOptionError(
        f"Unrecognized color: {value!r}. Use a name ({sorted(_NAMED_COLORS)}) or hex (#RRGGBB).",
        code=ErrorCode.INVALID_COLOR,
        value=value,
    )


_MAX_GRADIENT_FADE = 0.55  # cap how far a data module can fade toward the background color


def _lerp(a: RGB, b: RGB, t: float) -> RGB:
    t = max(0.0, min(_MAX_GRADIENT_FADE, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _color_mask_fn(name: str, fg: RGB, bg: RGB, size: int) -> Callable[[int, int], RGB]:
    if name == "solid":
        return lambda r, c: fg
    if name == "horizontal":
        return lambda r, c: _lerp(fg, bg, c / max(1, size - 1))
    if name == "vertical":
        return lambda r, c: _lerp(fg, bg, r / max(1, size - 1))
    if name == "square":
        center = (size - 1) / 2
        max_d = max(center, 1)
        return lambda r, c: _lerp(fg, bg, max(abs(r - center), abs(c - center)) / max_d)
    if name == "radial":
        center = (size - 1) / 2
        max_d = math.hypot(center, center) or 1
        return lambda r, c: _lerp(fg, bg, math.hypot(r - center, c - center) / max_d)
    raise InvalidStyleOptionError(
        f"Unknown color mask: {name!r}. Options: solid, radial, square, horizontal, vertical.",
        code=ErrorCode.INVALID_STYLE_OPTION,
        value=name,
    )


DRAWER_STYLES = ("square", "rounded", "gapped", "circle", "vertical", "horizontal")


def _draw_module(canvas: RGBCanvas, drawer: str, x0: int, y0: int, box: int, color: RGB) -> None:
    if drawer == "square":
        canvas.fill_rect(x0, y0, x0 + box, y0 + box, color)
    elif drawer == "gapped":
        pad = max(1, box // 6)
        canvas.fill_rect(x0 + pad, y0 + pad, x0 + box - pad, y0 + box - pad, color)
    elif drawer == "circle":
        r = box / 2
        canvas.fill_circle(x0 + r, y0 + r, r * 0.95, color)
    elif drawer == "rounded":
        pad = max(1, box // 5)
        canvas.fill_rect(x0 + pad, y0, x0 + box - pad, y0 + box, color)
        canvas.fill_rect(x0, y0 + pad, x0 + box, y0 + box - pad, color)
        r = (box - 2 * pad) / 2 + pad * 0.4
        for cx, cy in ((x0 + pad, y0 + pad), (x0 + box - pad, y0 + pad),
                       (x0 + pad, y0 + box - pad), (x0 + box - pad, y0 + box - pad)):
            canvas.fill_circle(cx, cy, r, color)
    elif drawer == "vertical":
        pad = max(1, box // 4)
        canvas.fill_rect(x0 + pad, y0, x0 + box - pad, y0 + box, color)
    elif drawer == "horizontal":
        pad = max(1, box // 4)
        canvas.fill_rect(x0, y0 + pad, x0 + box, y0 + box - pad, color)
    else:
        raise InvalidStyleOptionError(
            f"Unknown module drawer style: {drawer!r}. Options: {DRAWER_STYLES}",
            code=ErrorCode.INVALID_STYLE_OPTION,
            value=drawer,
        )


def render(
    matrix: QRMatrix,
    box_size: int = 10,
    border: int = 4,
    styled: bool = False,
    drawer_style: str = "square",
    color_mask: str = "solid",
    foreground: str = "black",
    background: str = "white",
) -> RGBCanvas:
    """Rasterize a finished QRMatrix into an RGBCanvas ready to save as PNG."""
    fg = parse_color(foreground)
    bg = parse_color(background)
    quiet = border * box_size
    dimension = matrix.size * box_size + 2 * quiet
    canvas = RGBCanvas(dimension, dimension, background=bg)

    gradient_fn = _color_mask_fn(color_mask, fg, bg, matrix.size) if styled else (lambda r, c: fg)
    drawer = drawer_style if styled else "square"

    for r in range(matrix.size):
        for c in range(matrix.size):
            if not matrix.modules[r][c]:
                continue
            # Function patterns (finder/timing/alignment/format/version) always render
            # solid and as plain squares -- fading or reshaping them breaks scannability.
            if matrix.is_function_module(r, c):
                color, shape = fg, "square"
            else:
                color, shape = gradient_fn(r, c), drawer
            x0 = quiet + c * box_size
            y0 = quiet + r * box_size
            _draw_module(canvas, shape, x0, y0, box_size, color)
    return canvas
