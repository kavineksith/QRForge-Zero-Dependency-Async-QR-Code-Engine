"""
pipeline.py
===========
Async orchestration layer for batch QR generation. QR encoding is
CPU-bound, so the async layer's job is concurrency *control* (bounding
how many jobs run in parallel) while the actual work is dispatched to a
ProcessPoolExecutor for real parallelism across cores. Batch input files
are read via a generator so multi-gigabyte input lists never have to be
held in memory all at once.
"""

from __future__ import annotations
import asyncio
import csv
import json
import os
from concurrent.futures import ProcessPoolExecutor
from typing import Generator, Iterable, List, Optional

from .audit_logger import AuditLogger, Timer
from .core import generate_qr
from .exceptions import BatchProcessingError, ErrorCode
from .models import QRJob, QRResult


def stream_jobs_from_file(
    path: str,
    output_dir: str,
    ecc_level: str = "L",
    box_size: int = 10,
    border: int = 4,
    styled: bool = False,
    drawer_style: str = "square",
    color_mask: str = "solid",
    foreground: str = "black",
    background: str = "white",
) -> Generator[QRJob, None, None]:
    """
    Lazily yield QRJob instances from a bulk input file (one payload per
    line for .txt, or a `data` column for .csv). Memory usage stays O(1)
    in the number of lines regardless of file size.
    """
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".csv":
            with open(path, "r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None or "data" not in reader.fieldnames:
                    raise BatchProcessingError(
                        "CSV batch file must have a 'data' column",
                        code=ErrorCode.BATCH_INPUT_INVALID,
                        path=path,
                    )
                for i, row in enumerate(reader):
                    payload = (row.get("data") or "").strip()
                    if not payload:
                        continue
                    filename = row.get("filename") or f"qr_{i:05d}.png"
                    yield QRJob(
                        data=payload,
                        output_path=os.path.join(output_dir, filename),
                        ecc_level=row.get("ecc_level") or ecc_level,
                        box_size=box_size, border=border, styled=styled,
                        drawer_style=drawer_style, color_mask=color_mask,
                        foreground=foreground, background=background,
                    )
        else:
            with open(path, "r", encoding="utf-8") as f:
                for i, line in enumerate(f):
                    payload = line.strip()
                    if not payload:
                        continue
                    yield QRJob(
                        data=payload,
                        output_path=os.path.join(output_dir, f"qr_{i:05d}.png"),
                        ecc_level=ecc_level, box_size=box_size, border=border,
                        styled=styled, drawer_style=drawer_style, color_mask=color_mask,
                        foreground=foreground, background=background,
                    )
    except OSError as exc:
        raise BatchProcessingError(
            f"Unable to read batch input file: {path} ({exc})",
            code=ErrorCode.BATCH_INPUT_INVALID,
            path=path,
        ) from exc


async def run_batch(
    jobs: Iterable[QRJob],
    logger: AuditLogger,
    concurrency: int = os.cpu_count() or 4,
) -> List[QRResult]:
    """
    Process jobs with bounded parallelism: a Semaphore caps how many
    in-flight process-pool tasks exist at once, and results stream back
    via asyncio.as_completed so progress can be reported incrementally.
    """
    semaphore = asyncio.Semaphore(concurrency)
    loop = asyncio.get_running_loop()
    results: List[QRResult] = []

    with ProcessPoolExecutor(max_workers=concurrency) as pool:

        async def _run_one(job: QRJob) -> QRResult:
            async with semaphore:
                with Timer(logger, "qr_job", label=job.label):
                    result = await loop.run_in_executor(pool, generate_qr, job)
                if result.success:
                    logger.audit(
                        "qr_generated", label=job.label, output=result.output_path,
                        version=result.version, mode=result.mode, mask=result.mask_pattern,
                    )
                else:
                    logger.error(
                        "qr_generation_failed", label=job.label,
                        error=result.error, error_code=result.error_code,
                    )
                return result

        tasks = [asyncio.create_task(_run_one(job)) for job in jobs]
        if not tasks:
            logger.warning("empty_batch_submitted")
            return results

        for coro in asyncio.as_completed(tasks):
            results.append(await coro)

    return results


def run_batch_sync(
    jobs: Iterable[QRJob],
    logger: AuditLogger,
    concurrency: int = os.cpu_count() or 4,
) -> List[QRResult]:
    """Synchronous convenience wrapper around `run_batch` for the CLI entry point."""
    return asyncio.run(run_batch(jobs, logger, concurrency))
