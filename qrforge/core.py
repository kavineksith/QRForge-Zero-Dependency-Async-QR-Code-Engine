"""
core.py
=======
The synchronous QR generation engine. This is the CPU-bound unit of work
that the async pipeline fans out across a process/thread pool -- QR
encoding (Reed-Solomon, matrix masking) is pure computation with no I/O
to await, so true parallelism (not just concurrency) is what actually
helps throughput here.
"""

from __future__ import annotations
import os
import time
from typing import Optional

from .encoder import build_bitstream, interleave_with_ecc, select_mode, select_version
from .exceptions import (
    ErrorCode,
    FileSystemError,
    InputValidationError,
    PermissionDeniedError,
    QRForgeError,
)
from .matrix import build_matrix
from .models import QRJob, QRResult
from .renderer import render

VALID_ECC_LEVELS = ("L", "M", "Q", "H")


def validate_output_dir(directory: str) -> None:
    """Ensure the output directory exists and is writable, raising typed errors otherwise."""
    try:
        os.makedirs(directory, exist_ok=True)
        probe = os.path.join(directory, ".qrforge_write_test")
        with open(probe, "w") as f:
            f.write("ok")
        os.remove(probe)
    except PermissionError as exc:
        raise PermissionDeniedError(
            f"No write permission for output directory: {directory}",
            code=ErrorCode.PERMISSION_DENIED,
            directory=directory,
        ) from exc
    except OSError as exc:
        raise FileSystemError(
            f"Cannot prepare output directory {directory}: {exc}",
            code=ErrorCode.OUTPUT_DIR_UNAVAILABLE,
            directory=directory,
        ) from exc


def generate_qr(job: QRJob) -> QRResult:
    """
    Run the full encode -> matrix -> render -> save pipeline for one job.
    Never raises: failures are captured into a QRResult(success=False, ...)
    so batch pipelines can continue past individual bad inputs.
    """
    start = time.perf_counter()
    try:
        if not job.data or not job.data.strip():
            raise InputValidationError("QR payload cannot be empty", code=ErrorCode.EMPTY_DATA)
        if job.ecc_level not in VALID_ECC_LEVELS:
            raise InputValidationError(
                f"Invalid ECC level {job.ecc_level!r}; must be one of {VALID_ECC_LEVELS}",
                code=ErrorCode.INVALID_ECC_LEVEL,
            )

        payload = job.data.encode("utf-8")
        mode = select_mode(payload)
        version = job.version or select_version(payload, job.ecc_level, mode)
        if job.version and job.version < select_version(payload, job.ecc_level, mode):
            raise InputValidationError(
                f"Requested version {job.version} is too small for this payload at "
                f"ECC level {job.ecc_level}",
                code=ErrorCode.INVALID_VERSION,
            )

        codewords = build_bitstream(payload, version, job.ecc_level, mode)
        interleaved = interleave_with_ecc(codewords, version, job.ecc_level)
        matrix, mask_pattern = build_matrix(interleaved, version, job.ecc_level)

        canvas = render(
            matrix,
            box_size=job.box_size,
            border=job.border,
            styled=job.styled,
            drawer_style=job.drawer_style,
            color_mask=job.color_mask,
            foreground=job.foreground,
            background=job.background,
        )

        output_dir = os.path.dirname(job.output_path) or "."
        validate_output_dir(output_dir)
        canvas.save(job.output_path)

        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        return QRResult(
            job=job, success=True, output_path=job.output_path, version=version,
            mask_pattern=mask_pattern, mode=mode, byte_size=len(payload), duration_ms=duration_ms,
        )
    except QRForgeError as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        return QRResult(
            job=job, success=False, error=str(exc.message if hasattr(exc, "message") else exc),
            error_code=int(exc.code) if hasattr(exc, "code") else None, duration_ms=duration_ms,
        )
    except Exception as exc:  # noqa: BLE001 - defend batch runs from unexpected failures
        duration_ms = round((time.perf_counter() - start) * 1000, 3)
        return QRResult(job=job, success=False, error=str(exc), duration_ms=duration_ms)
