"""
exceptions.py
=============
OOP-based custom exception hierarchy for QRForge. Every exception carries a
stable, machine-checkable IntEnum error code so downstream automation
(CI pipelines, SOC tooling, audit correlation) can branch on `.code` rather
than parsing free-text messages.
"""

from __future__ import annotations
from enum import IntEnum
from typing import Any, Dict, Optional, Type


class ErrorCode(IntEnum):
    """Stable numeric error codes, grouped by subsystem (x00-x99 per family)."""

    UNKNOWN = 1000

    # Input / validation family (11xx)
    EMPTY_DATA = 1100
    DATA_TOO_LARGE = 1101
    INVALID_ENCODING = 1102
    INVALID_ECC_LEVEL = 1103
    INVALID_VERSION = 1104
    INVALID_STYLE_OPTION = 1105
    INVALID_COLOR = 1106

    # Encoding engine family (12xx)
    VERSION_CAPACITY_EXCEEDED = 1200
    MASK_SELECTION_FAILED = 1201
    RS_ENCODING_FAILED = 1202

    # Rendering family (13xx)
    IMAGE_RENDER_FAILED = 1300
    PNG_WRITE_FAILED = 1301

    # Filesystem family (14xx)
    OUTPUT_DIR_UNAVAILABLE = 1400
    PERMISSION_DENIED = 1401
    FILE_WRITE_FAILED = 1402

    # Batch / pipeline family (15xx)
    BATCH_INPUT_INVALID = 1500
    PARTIAL_BATCH_FAILURE = 1501

    # Report family (16xx)
    REPORT_GENERATION_FAILED = 1600
    UNSUPPORTED_REPORT_FORMAT = 1601


class QRForgeError(Exception):
    """
    Base exception for the entire QRForge project.

    Every subclass registers itself in `_registry` at class-definition time
    keyed by its ErrorCode, enabling reconstruction of the correct exception
    type from a bare code via `QRForgeError.from_code(...)` -- useful when
    deserializing errors out of the JSONL audit log or a report file.
    """

    _registry: Dict[int, Type["QRForgeError"]] = {}
    default_code: ErrorCode = ErrorCode.UNKNOWN

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        QRForgeError._registry[int(cls.default_code)] = cls

    def __init__(self, message: str, code: Optional[ErrorCode] = None, **context: Any) -> None:
        self.code: ErrorCode = code if code is not None else self.default_code
        self.message = message
        self.context: Dict[str, Any] = context
        super().__init__(message)

    def __repr__(self) -> str:
        ctx = f", context={self.context}" if self.context else ""
        return f"{type(self).__name__}(code={self.code.name}, message={self.message!r}{ctx})"

    def __str__(self) -> str:
        return f"[{self.code.name}:{self.code.value}] {self.message}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, QRForgeError):
            return NotImplemented
        return self.code == other.code and self.message == other.message

    def __hash__(self) -> int:
        return hash((self.code, self.message))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for audit logging / report embedding."""
        return {
            "exception": type(self).__name__,
            "code": int(self.code),
            "code_name": self.code.name,
            "message": self.message,
            "context": self.context,
        }

    @classmethod
    def from_code(cls, code: int, message: str, **context: Any) -> "QRForgeError":
        """
        Factory that reconstructs the most specific registered exception
        type for a given numeric error code, falling back to the base
        QRForgeError if the code is unrecognized.
        """
        target_cls = cls._registry.get(int(code), QRForgeError)
        if target_cls is QRForgeError:
            return QRForgeError(message, code=ErrorCode(code) if code in ErrorCode._value2member_map_ else ErrorCode.UNKNOWN, **context)
        return target_cls(message, **context)


class InputValidationError(QRForgeError):
    """Raised when caller-supplied data or parameters fail validation."""
    default_code = ErrorCode.EMPTY_DATA


class DataTooLargeError(InputValidationError):
    """Raised when data exceeds the maximum capacity for any QR version."""
    default_code = ErrorCode.DATA_TOO_LARGE


class InvalidStyleOptionError(InputValidationError):
    """Raised when an unknown drawer style, color mask, or color name is given."""
    default_code = ErrorCode.INVALID_STYLE_OPTION


class EncodingError(QRForgeError):
    """Raised when the QR data/error-correction encoding pipeline fails."""
    default_code = ErrorCode.VERSION_CAPACITY_EXCEEDED


class MaskSelectionError(EncodingError):
    """Raised if no data mask could be scored/selected."""
    default_code = ErrorCode.MASK_SELECTION_FAILED


class RenderError(QRForgeError):
    """Raised when rasterizing the QR matrix into an image fails."""
    default_code = ErrorCode.IMAGE_RENDER_FAILED


class PNGWriteError(RenderError):
    """Raised when the pure-stdlib PNG encoder fails to write a file."""
    default_code = ErrorCode.PNG_WRITE_FAILED


class FileSystemError(QRForgeError):
    """Raised for output-directory / filesystem related failures."""
    default_code = ErrorCode.OUTPUT_DIR_UNAVAILABLE


class PermissionDeniedError(FileSystemError):
    """Raised when the process lacks permission to read/write required paths."""
    default_code = ErrorCode.PERMISSION_DENIED


class BatchProcessingError(QRForgeError):
    """Raised for batch/pipeline-level failures across many QR jobs."""
    default_code = ErrorCode.BATCH_INPUT_INVALID


class ReportGenerationError(QRForgeError):
    """Raised when JSON/CSV/XLSX/terminal report generation fails."""
    default_code = ErrorCode.REPORT_GENERATION_FAILED
