"""
reedsolomon.py
==============
Pure stdlib GF(256) Reed-Solomon error correction codeword generator, as
specified by ISO/IEC 18004 (QR Code) Annex A. Implemented from first
principles: no third-party dependency is used anywhere in QRForge.

The QR code standard uses the field GF(2^8) with primitive polynomial
x^8 + x^4 + x^3 + x^2 + 1 (0x11D) and generator element 2.
"""

from __future__ import annotations
from functools import lru_cache
from typing import List, Tuple


class GaloisField256:
    """
    GF(256) arithmetic engine built once and reused (log/antilog tables).

    Dunder methods are intentionally included on this "field object" even
    though it is normally used as a singleton, because it models a genuine
    mathematical structure and benefits from `len`, `__contains__`, and
    `__repr__` for debugging/introspection during development.
    """

    __slots__ = ("_exp", "_log")
    PRIME_POLY = 0x11D

    def __init__(self) -> None:
        exp = [0] * 512
        log = [0] * 256
        x = 1
        for i in range(255):
            exp[i] = x
            log[x] = i
            x <<= 1
            if x & 0x100:
                x ^= self.PRIME_POLY
        for i in range(255, 512):
            exp[i] = exp[i - 255]
        self._exp = exp
        self._log = log

    def __len__(self) -> int:
        return 256

    def __contains__(self, value: int) -> bool:
        return 0 <= value <= 255

    def __repr__(self) -> str:
        return f"GaloisField256(primitive_poly={hex(self.PRIME_POLY)})"

    def multiply(self, a: int, b: int) -> int:
        if a == 0 or b == 0:
            return 0
        return self._exp[self._log[a] + self._log[b]]

    def exp(self, power: int) -> int:
        return self._exp[power % 255]

    def log(self, value: int) -> int:
        return self._log[value]


_GF = GaloisField256()


@lru_cache(maxsize=None)
def _generator_polynomial(degree: int) -> Tuple[int, ...]:
    """Build the RS generator polynomial of the given degree over GF(256)."""
    poly: List[int] = [1]
    for i in range(degree):
        factor = [1, _GF.exp(i)]
        new_poly = [0] * (len(poly) + 1)
        for j, coeff_a in enumerate(poly):
            for k, coeff_b in enumerate(factor):
                new_poly[j + k] ^= _GF.multiply(coeff_a, coeff_b)
        poly = new_poly
    return tuple(poly)


def rs_encode(data: List[int], ec_len: int) -> List[int]:
    """
    Compute `ec_len` Reed-Solomon error correction codewords for `data`.

    Args:
        data: data codewords (0-255 each) for one RS block.
        ec_len: number of error correction codewords to generate.

    Returns:
        List of ec_len error correction codewords.
    """
    generator = _generator_polynomial(ec_len)
    remainder = list(data) + [0] * ec_len
    for i in range(len(data)):
        coeff = remainder[i]
        if coeff == 0:
            continue
        for j, gcoeff in enumerate(generator):
            remainder[i + j] ^= _GF.multiply(gcoeff, coeff)
    return remainder[len(data):]
