"""
models.py
=========
Domain objects for a single QR generation request/result, with the
comprehensive dunder-method suite used consistently across the portfolio
(__slots__, __repr__, __str__, __eq__, __hash__, __lt__, __len__).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass(slots=True)
class QRJob:
    """A single unit of work: one payload to encode into one QR image."""

    data: str
    output_path: str
    version: Optional[int] = None
    ecc_level: str = "L"
    box_size: int = 10
    border: int = 4
    styled: bool = False
    drawer_style: str = "square"
    color_mask: str = "solid"
    foreground: str = "black"
    background: str = "white"
    label: str = ""

    def __post_init__(self) -> None:
        if not self.label:
            self.label = self.data[:32]

    def __len__(self) -> int:
        return len(self.data)

    def __contains__(self, substring: str) -> bool:
        return substring in self.data

    def __str__(self) -> str:
        return f"QRJob({self.label!r} -> {self.output_path})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QRJob):
            return NotImplemented
        return (self.data, self.output_path) == (other.data, other.output_path)

    def __hash__(self) -> int:
        return hash((self.data, self.output_path))

    def __lt__(self, other: "QRJob") -> bool:
        if not isinstance(other, QRJob):
            return NotImplemented
        return len(self.data) < len(other.data)


@dataclass(slots=True)
class QRResult:
    """The outcome of processing one QRJob."""

    job: QRJob
    success: bool
    output_path: str = ""
    version: int = 0
    mask_pattern: int = -1
    mode: str = ""
    byte_size: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None
    error_code: Optional[int] = None

    def __bool__(self) -> bool:
        return self.success

    def __str__(self) -> str:
        if self.success:
            return f"OK   {self.job.label!r:36s} v{self.version} {self.mode:12s} -> {self.output_path}"
        return f"FAIL {self.job.label!r:36s} :: {self.error}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QRResult):
            return NotImplemented
        return self.job == other.job and self.success == other.success

    def __hash__(self) -> int:
        return hash((self.job, self.success))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.job.label,
            "data_preview": self.job.data[:60],
            "success": self.success,
            "output_path": self.output_path,
            "version": self.version,
            "mask_pattern": self.mask_pattern,
            "mode": self.mode,
            "byte_size": self.byte_size,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "error_code": self.error_code,
        }
