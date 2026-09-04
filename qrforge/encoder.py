"""
encoder.py
==========
Implements the ISO/IEC 18004 data-encoding stage: mode selection (Numeric /
Alphanumeric / Byte), bit-stream construction, version auto-selection, and
splitting the codeword stream across Reed-Solomon blocks. Kanji mode is
intentionally out of scope (documented limitation) since Byte mode already
losslessly represents any UTF-8 payload.
"""

from __future__ import annotations
from enum import Enum
from typing import Generator, Iterable, List, Tuple

from .exceptions import DataTooLargeError, EncodingError, ErrorCode
from .reedsolomon import rs_encode
from .tables import RS_BLOCK_TABLE

ALPHANUMERIC_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"
_ALPHA_INDEX = {c: i for i, c in enumerate(ALPHANUMERIC_CHARSET)}

MODE_NUMERIC = "numeric"
MODE_ALPHANUMERIC = "alphanumeric"
MODE_BYTE = "byte"

_MODE_INDICATOR = {MODE_NUMERIC: 0b0001, MODE_ALPHANUMERIC: 0b0010, MODE_BYTE: 0b0100}


class BitBuffer:
    """
    A growable bit stream, following the same "small focused object with
    full dunder support" convention used across the QRForge/portfolio tools.
    """

    __slots__ = ("_bits",)

    def __init__(self) -> None:
        self._bits: List[int] = []

    def __len__(self) -> int:
        return len(self._bits)

    def __iter__(self) -> Generator[int, None, None]:
        yield from self._bits

    def put(self, value: int, length: int) -> "BitBuffer":
        for i in range(length - 1, -1, -1):
            self._bits.append((value >> i) & 1)
        return self

    def to_bytes(self) -> List[int]:
        padded = self._bits + [0] * ((8 - len(self._bits) % 8) % 8)
        return [
            int("".join(map(str, padded[i:i + 8])), 2)
            for i in range(0, len(padded), 8)
        ]


def select_mode(data: bytes) -> str:
    """Pick the most space-efficient mode that losslessly fits `data`."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return MODE_BYTE
    if text and all(c in "0123456789" for c in text):
        return MODE_NUMERIC
    if text and all(c in _ALPHA_INDEX for c in text):
        return MODE_ALPHANUMERIC
    return MODE_BYTE


def _char_count_bits(mode: str, version: int) -> int:
    if version <= 9:
        table = {MODE_NUMERIC: 10, MODE_ALPHANUMERIC: 9, MODE_BYTE: 8}
    elif version <= 26:
        table = {MODE_NUMERIC: 12, MODE_ALPHANUMERIC: 11, MODE_BYTE: 16}
    else:
        table = {MODE_NUMERIC: 14, MODE_ALPHANUMERIC: 13, MODE_BYTE: 16}
    return table[mode]


def _encode_body(buf: BitBuffer, mode: str, data: bytes) -> None:
    if mode == MODE_NUMERIC:
        text = data.decode("ascii")
        for i in range(0, len(text), 3):
            chunk = text[i:i + 3]
            bits = {1: 4, 2: 7, 3: 10}[len(chunk)]
            buf.put(int(chunk), bits)
    elif mode == MODE_ALPHANUMERIC:
        text = data.decode("ascii")
        for i in range(0, len(text), 2):
            chunk = text[i:i + 2]
            if len(chunk) == 2:
                buf.put(_ALPHA_INDEX[chunk[0]] * 45 + _ALPHA_INDEX[chunk[1]], 11)
            else:
                buf.put(_ALPHA_INDEX[chunk[0]], 6)
    else:
        for byte in data:
            buf.put(byte, 8)


def data_capacity_bits(version: int, ecc_level: str) -> int:
    """Total usable data-codeword bits (excludes RS/EC codewords) for version+level."""
    _, groups = RS_BLOCK_TABLE[version][ecc_level]
    return sum(n * cw for n, cw in groups) * 8


def select_version(data: bytes, ecc_level: str, mode: str, min_version: int = 1) -> int:
    """
    Find the smallest QR version (>= min_version) whose data capacity fits
    the encoded payload at the requested ECC level. Raises DataTooLargeError
    if even version 40 cannot hold it.
    """
    for version in range(min_version, 41):
        header_bits = 4 + _char_count_bits(mode, version)
        body_bits = (
            len(data) * 8 if mode == MODE_BYTE
            else _estimate_body_bits(mode, data)
        )
        if header_bits + body_bits <= data_capacity_bits(version, ecc_level):
            return version
    raise DataTooLargeError(
        f"Payload of {len(data)} bytes exceeds QR version 40 capacity at ECC level {ecc_level}",
        code=ErrorCode.DATA_TOO_LARGE,
        payload_size=len(data),
        ecc_level=ecc_level,
    )


def _estimate_body_bits(mode: str, data: bytes) -> int:
    n = len(data)
    if mode == MODE_NUMERIC:
        full, rem = divmod(n, 3)
        return full * 10 + {0: 0, 1: 4, 2: 7}[rem]
    if mode == MODE_ALPHANUMERIC:
        full, rem = divmod(n, 2)
        return full * 11 + (6 if rem else 0)
    return n * 8


def build_bitstream(data: bytes, version: int, ecc_level: str, mode: str) -> List[int]:
    """Construct the final, padded codeword sequence (pre error-correction)."""
    buf = BitBuffer()
    buf.put(_MODE_INDICATOR[mode], 4)
    buf.put(len(data), _char_count_bits(mode, version))
    _encode_body(buf, mode, data)

    capacity_bits = data_capacity_bits(version, ecc_level)
    terminator_len = min(4, capacity_bits - len(buf))
    if terminator_len > 0:
        buf.put(0, terminator_len)
    while len(buf) % 8 != 0:
        buf.put(0, 1)

    codewords = buf.to_bytes()
    capacity_bytes = capacity_bits // 8
    pad_bytes = (0xEC, 0x11)
    i = 0
    while len(codewords) < capacity_bytes:
        codewords.append(pad_bytes[i % 2])
        i += 1
    if len(codewords) > capacity_bytes:
        raise EncodingError(
            f"Encoded stream ({len(codewords)} bytes) exceeds version {version} capacity "
            f"({capacity_bytes} bytes)",
            code=ErrorCode.VERSION_CAPACITY_EXCEEDED,
        )
    return codewords


def interleave_with_ecc(codewords: List[int], version: int, ecc_level: str) -> List[int]:
    """
    Split data codewords into RS blocks, generate EC codewords per block,
    then interleave data and EC codewords per ISO/IEC 18004 section 8.6.
    """
    ec_len, groups = RS_BLOCK_TABLE[version][ecc_level]
    blocks: List[List[int]] = []
    ec_blocks: List[List[int]] = []
    offset = 0
    for num_blocks, data_len in groups:
        for _ in range(num_blocks):
            block = codewords[offset:offset + data_len]
            offset += data_len
            blocks.append(block)
            ec_blocks.append(rs_encode(block, ec_len))

    max_data_len = max(len(b) for b in blocks)
    interleaved: List[int] = []
    for i in range(max_data_len):
        for block in blocks:
            if i < len(block):
                interleaved.append(block[i])
    for i in range(ec_len):
        for ec_block in ec_blocks:
            interleaved.append(ec_block[i])
    return interleaved
