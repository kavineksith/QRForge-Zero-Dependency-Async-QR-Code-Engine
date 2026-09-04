"""
png_writer.py
=============
A minimal, correct, dependency-free PNG (RGB, 8-bit, non-interlaced)
encoder built entirely on stdlib `struct` and `zlib`. This is what lets
QRForge render styled, colored QR images without Pillow.
"""

from __future__ import annotations
import struct
import zlib
from typing import List, Tuple

from .exceptions import ErrorCode, PNGWriteError

RGB = Tuple[int, int, int]


class RGBCanvas:
    """
    A simple in-memory RGB raster. Dunder-rich: `__len__` gives pixel
    count, `__getitem__`/`__setitem__` give (x, y) pixel access, and
    `__iter__` streams rows -- consistent with the rest of QRForge.
    """

    __slots__ = ("width", "height", "_pixels")

    def __init__(self, width: int, height: int, background: RGB = (255, 255, 255)) -> None:
        self.width = width
        self.height = height
        self._pixels: List[bytearray] = [
            bytearray(background * width) for _ in range(height)
        ]

    def __len__(self) -> int:
        return self.width * self.height

    def __iter__(self):
        yield from self._pixels

    def __getitem__(self, coord: Tuple[int, int]) -> RGB:
        x, y = coord
        row = self._pixels[y]
        i = x * 3
        return (row[i], row[i + 1], row[i + 2])

    def __setitem__(self, coord: Tuple[int, int], color: RGB) -> None:
        x, y = coord
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        row = self._pixels[y]
        i = x * 3
        row[i], row[i + 1], row[i + 2] = color

    def fill_rect(self, x0: int, y0: int, x1: int, y1: int, color: RGB) -> None:
        for y in range(max(0, y0), min(self.height, y1)):
            row = self._pixels[y]
            for x in range(max(0, x0), min(self.width, x1)):
                i = x * 3
                row[i], row[i + 1], row[i + 2] = color

    def fill_circle(self, cx: float, cy: float, radius: float, color: RGB) -> None:
        r2 = radius * radius
        x0, x1 = int(cx - radius), int(cx + radius) + 1
        y0, y1 = int(cy - radius), int(cy + radius) + 1
        for y in range(max(0, y0), min(self.height, y1)):
            for x in range(max(0, x0), min(self.width, x1)):
                if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r2:
                    self[x, y] = color

    def to_png_bytes(self) -> bytes:
        raw = bytearray()
        for row in self._pixels:
            raw.append(0)  # filter type 0 (none) per scanline
            raw.extend(row)
        compressed = zlib.compress(bytes(raw), level=9)

        def chunk(tag: bytes, payload: bytes) -> bytes:
            return (
                struct.pack(">I", len(payload))
                + tag
                + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
            )

        signature = b"\x89PNG\r\n\x1a\n"
        ihdr = struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)
        return (
            signature
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", compressed)
            + chunk(b"IEND", b"")
        )

    def save(self, path: str) -> None:
        try:
            with open(path, "wb") as f:
                f.write(self.to_png_bytes())
        except OSError as exc:
            raise PNGWriteError(
                f"Failed to write PNG to {path}: {exc}",
                code=ErrorCode.PNG_WRITE_FAILED,
                path=path,
            ) from exc
