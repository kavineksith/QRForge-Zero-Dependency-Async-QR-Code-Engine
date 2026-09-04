"""
matrix.py
=========
Builds the final QR module matrix: finder/timing/alignment patterns,
format & version information (BCH-encoded), data placement in the
standard zigzag order, and penalty-driven selection of the best of the
8 standard data masks (ISO/IEC 18004 section 7.8).
"""

from __future__ import annotations
from typing import List, Optional, Tuple

from .exceptions import ErrorCode, MaskSelectionError
from .tables import ALIGNMENT_POSITIONS

_G15 = 0b10100110111
_G18 = 0b1111100100101
_G15_MASK = 0b101010000010010
_ECC_INDICATOR = {"L": 0b01, "M": 0b00, "Q": 0b11, "H": 0b10}

RESERVED = -1  # sentinel: reserved/function module, not data-writable


def _bch_digit(value: int) -> int:
    digit = 0
    while value:
        digit += 1
        value >>= 1
    return digit


def _bch_encode(data: int, generator: int) -> int:
    shifted = data << (_bch_digit(generator) - 1)
    d = shifted
    while _bch_digit(d) >= _bch_digit(generator):
        d ^= generator << (_bch_digit(d) - _bch_digit(generator))
    return shifted | d


def format_info_bits(ecc_level: str, mask_pattern: int) -> List[int]:
    data = (_ECC_INDICATOR[ecc_level] << 3) | mask_pattern
    bch = _bch_encode(data, _G15) ^ _G15_MASK
    return [(bch >> i) & 1 for i in range(14, -1, -1)]


def version_info_bits(version: int) -> Optional[List[int]]:
    if version < 7:
        return None
    bch = _bch_encode(version, _G18)
    return [(bch >> i) & 1 for i in range(17, -1, -1)]


_MASK_FUNCS = [
    lambda i, j: (i + j) % 2 == 0,
    lambda i, j: i % 2 == 0,
    lambda i, j: j % 3 == 0,
    lambda i, j: (i + j) % 3 == 0,
    lambda i, j: (i // 2 + j // 3) % 2 == 0,
    lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
    lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0,
    lambda i, j: ((i + j) % 2 + (i * j) % 3) % 2 == 0,
]


class QRMatrix:
    """
    The QR module grid. Supports `__len__` (side size), `__iter__` (row
    iteration), `__getitem__`/`__contains__` for coordinate-style access,
    matching the dunder-rich convention used across the portfolio.
    """

    __slots__ = ("size", "version", "ecc_level", "modules", "_reserved")

    def __init__(self, version: int, ecc_level: str) -> None:
        self.version = version
        self.ecc_level = ecc_level
        self.size = version * 4 + 17
        self.modules: List[List[int]] = [[RESERVED] * self.size for _ in range(self.size)]
        self._reserved: List[List[bool]] = [[False] * self.size for _ in range(self.size)]
        self._place_function_patterns()

    def __len__(self) -> int:
        return self.size

    def __iter__(self):
        yield from self.modules

    def __getitem__(self, coord: Tuple[int, int]) -> int:
        r, c = coord
        return self.modules[r][c]

    def __contains__(self, coord: Tuple[int, int]) -> bool:
        r, c = coord
        return 0 <= r < self.size and 0 <= c < self.size

    def __repr__(self) -> str:
        return f"QRMatrix(version={self.version}, ecc_level={self.ecc_level!r}, size={self.size})"

    def is_function_module(self, r: int, c: int) -> bool:
        """True for finder/timing/alignment/format/version modules (never gradient-faded)."""
        return self._reserved[r][c]

    # -- construction -----------------------------------------------------
    def _set(self, r: int, c: int, value: int, reserved: bool = True) -> None:
        self.modules[r][c] = value
        if reserved:
            self._reserved[r][c] = True

    def _place_finder(self, top: int, left: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = top + dr, left + dc
                if not (0 <= r < self.size and 0 <= c < self.size):
                    continue
                if 0 <= dr <= 6 and 0 <= dc <= 6 and (dr in (0, 6) or dc in (0, 6) or (2 <= dr <= 4 and 2 <= dc <= 4)):
                    self._set(r, c, 1)
                else:
                    self._set(r, c, 0)

    def _place_function_patterns(self) -> None:
        self._place_finder(0, 0)
        self._place_finder(0, self.size - 7)
        self._place_finder(self.size - 7, 0)

        for i in range(8, self.size - 8):
            self._set(6, i, 1 if i % 2 == 0 else 0)
            self._set(i, 6, 1 if i % 2 == 0 else 0)

        positions = ALIGNMENT_POSITIONS[self.version]
        for r in positions:
            for c in positions:
                if (r, c) in ((6, 6), (6, self.size - 7), (self.size - 7, 6)):
                    continue
                self._place_alignment(r, c)

        self._set(self.size - 8, 8, 1)  # dark module (set once more below after reservations)

        for i in range(9):
            if i != 6:
                self._set(8, i, RESERVED)
                self._set(i, 8, RESERVED)
        for i in range(self.size - 8, self.size):
            self._set(8, i, RESERVED)
            self._set(i, 8, RESERVED)

        self._set(self.size - 8, 8, 1)  # re-assert: the loop above may have cleared it

        if self.version >= 7:
            for r in range(6):
                for c in range(self.size - 11, self.size - 8):
                    self._set(r, c, RESERVED)
                    self._set(c, r, RESERVED)

    def _place_alignment(self, center_r: int, center_c: int) -> None:
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                r, c = center_r + dr, center_c + dc
                on = max(abs(dr), abs(dc)) != 1
                self._set(r, c, 1 if on else 0)

    def place_data(self, codewords: List[int]) -> None:
        """Place codeword bits into free modules using the standard zigzag scan."""
        bits = [b for byte in codewords for b in [(byte >> i) & 1 for i in range(7, -1, -1)]]
        bit_iter = iter(bits)
        col = self.size - 1
        going_up = True
        while col > 0:
            if col == 6:  # skip vertical timing column
                col -= 1
            for row in (range(self.size - 1, -1, -1) if going_up else range(self.size)):
                for c in (col, col - 1):
                    if self._reserved[row][c]:
                        continue
                    try:
                        self.modules[row][c] = next(bit_iter)
                    except StopIteration:
                        self.modules[row][c] = 0
            going_up = not going_up
            col -= 2

    def apply_mask(self, pattern: int) -> "QRMatrix":
        """Return a new masked matrix (data modules only; function modules untouched)."""
        masked = QRMatrix.__new__(QRMatrix)
        masked.version, masked.ecc_level, masked.size = self.version, self.ecc_level, self.size
        masked._reserved = self._reserved
        fn = _MASK_FUNCS[pattern]
        masked.modules = [
            [
                (self.modules[r][c] ^ 1) if (not self._reserved[r][c] and fn(r, c)) else self.modules[r][c]
                for c in range(self.size)
            ]
            for r in range(self.size)
        ]
        return masked

    def write_format_info(self, mask_pattern: int) -> None:
        data = (_ECC_INDICATOR[self.ecc_level] << 3) | mask_pattern
        bits = _bch_encode(data, _G15) ^ _G15_MASK  # 15-bit integer, LSB = bit 0

        for i in range(15):
            bit = (bits >> i) & 1
            if i < 6:
                self.modules[i][8] = bit
            elif i < 8:
                self.modules[i + 1][8] = bit
            else:
                self.modules[self.size - 15 + i][8] = bit

            if i < 8:
                self.modules[8][self.size - i - 1] = bit
            elif i < 9:
                self.modules[8][15 - i - 1 + 1] = bit
            else:
                self.modules[8][15 - i - 1] = bit

        self.modules[self.size - 8][8] = 1  # dark module

        if self.version >= 7:
            vbits = _bch_encode(self.version, _G18)  # 18-bit integer, LSB = bit 0
            for i in range(18):
                bit = (vbits >> i) & 1
                self.modules[i // 3][i % 3 + self.size - 8 - 3] = bit
                self.modules[i % 3 + self.size - 8 - 3][i // 3] = bit

    def penalty_score(self) -> int:
        return (
            self._penalty_runs()
            + self._penalty_blocks()
            + self._penalty_finder_like()
            + self._penalty_balance()
        )

    def _penalty_runs(self) -> int:
        score = 0
        for line in list(self.modules) + [list(col) for col in zip(*self.modules)]:
            run_len, run_val = 1, line[0]
            for v in line[1:]:
                if v == run_val:
                    run_len += 1
                else:
                    if run_len >= 5:
                        score += run_len - 2
                    run_val, run_len = v, 1
            if run_len >= 5:
                score += run_len - 2
        return score

    def _penalty_blocks(self) -> int:
        score = 0
        for r in range(self.size - 1):
            for c in range(self.size - 1):
                v = self.modules[r][c]
                if v == self.modules[r][c + 1] == self.modules[r + 1][c] == self.modules[r + 1][c + 1]:
                    score += 3
        return score

    def _penalty_finder_like(self) -> int:
        pattern_a = [1, 0, 1, 1, 1, 0, 1, 0, 0, 0, 0]
        pattern_b = [0, 0, 0, 0, 1, 0, 1, 1, 1, 0, 1]
        score = 0
        for line in list(self.modules) + [list(col) for col in zip(*self.modules)]:
            for i in range(len(line) - 10):
                window = line[i:i + 11]
                if window == pattern_a or window == pattern_b:
                    score += 40
        return score

    def _penalty_balance(self) -> int:
        total = self.size * self.size
        dark = sum(sum(row) for row in self.modules)
        percent = dark * 100 // total
        prev = (percent // 5) * 5
        nxt = prev + 5
        return min(abs(prev - 50) // 5, abs(nxt - 50) // 5) * 10


def build_matrix(codewords: List[int], version: int, ecc_level: str) -> Tuple[QRMatrix, int]:
    """Place data, try all 8 masks, and return the lowest-penalty matrix + chosen mask id."""
    base = QRMatrix(version, ecc_level)
    base.place_data(codewords)

    best: Optional[QRMatrix] = None
    best_score = None
    best_pattern = None
    for pattern in range(8):
        candidate = base.apply_mask(pattern)
        candidate.write_format_info(pattern)
        score = candidate.penalty_score()
        if best_score is None or score < best_score:
            best, best_score, best_pattern = candidate, score, pattern

    if best is None or best_pattern is None:
        raise MaskSelectionError(
            "Unable to select a data mask pattern",
            code=ErrorCode.MASK_SELECTION_FAILED,
        )
    return best, best_pattern
