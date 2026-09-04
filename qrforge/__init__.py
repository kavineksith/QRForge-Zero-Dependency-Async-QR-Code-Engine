"""QRForge -- a zero-dependency, async, ISO/IEC 18004-compliant QR code engine."""

from .core import generate_qr, validate_output_dir
from .exceptions import (
    BatchProcessingError,
    DataTooLargeError,
    EncodingError,
    ErrorCode,
    FileSystemError,
    InputValidationError,
    InvalidStyleOptionError,
    MaskSelectionError,
    PermissionDeniedError,
    PNGWriteError,
    QRForgeError,
    RenderError,
    ReportGenerationError,
)
from .models import QRJob, QRResult
from .pipeline import run_batch, run_batch_sync, stream_jobs_from_file

__all__ = [
    "generate_qr", "validate_output_dir", "QRJob", "QRResult",
    "run_batch", "run_batch_sync", "stream_jobs_from_file",
    "QRForgeError", "ErrorCode", "InputValidationError", "DataTooLargeError",
    "InvalidStyleOptionError", "EncodingError", "MaskSelectionError",
    "RenderError", "PNGWriteError", "FileSystemError", "PermissionDeniedError",
    "BatchProcessingError", "ReportGenerationError",
]

__version__ = "1.0.0"
