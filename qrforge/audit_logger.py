"""
audit_logger.py
================
Rotating, thread-safe JSONL audit logger. Every generation event (success
or failure) is written as one JSON object per line for easy downstream
ingestion (SIEM, jq, pandas). A custom AUDIT severity sits above CRITICAL
and always bypasses the configured level filter, so accountability records
are never silently dropped by a verbose/quiet log-level setting.
"""

from __future__ import annotations
import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Dict, Optional


class Severity(IntEnum):
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50
    AUDIT = 60  # always emitted, regardless of configured threshold


class AuditLogger:
    """
    Thread-safe rotating JSONL logger.

    Rotation is size-based: when the active log file exceeds `max_bytes`,
    it is renamed with a timestamp suffix and a fresh file is started, up
    to `backup_count` retained backups (oldest deleted first).
    """

    __slots__ = ("path", "level", "max_bytes", "backup_count", "_lock", "_console")

    def __init__(
        self,
        path: str = "qrforge_audit.jsonl",
        level: Severity = Severity.INFO,
        max_bytes: int = 5 * 1024 * 1024,
        backup_count: int = 5,
        console: bool = False,
    ) -> None:
        self.path = path
        self.level = level
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._console = console
        self._lock = threading.Lock()

    def __repr__(self) -> str:
        return f"AuditLogger(path={self.path!r}, level={self.level.name}, max_bytes={self.max_bytes})"

    def __enter__(self) -> "AuditLogger":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self.audit("logger_context_exit_with_exception", error=str(exc))

    def _rotate_if_needed(self) -> None:
        try:
            if not os.path.exists(self.path) or os.path.getsize(self.path) < self.max_bytes:
                return
        except OSError:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        rotated = f"{self.path}.{stamp}"
        os.replace(self.path, rotated)

        backups = sorted(
            (f for f in os.listdir(os.path.dirname(self.path) or ".") if f.startswith(os.path.basename(self.path) + ".")),
        )
        excess = len(backups) - self.backup_count
        for old in backups[:max(0, excess)]:
            try:
                os.remove(os.path.join(os.path.dirname(self.path) or ".", old))
            except OSError:
                pass

    def _write(self, severity: Severity, event: str, **fields: Any) -> None:
        if severity < self.level and severity != Severity.AUDIT:
            return
        record: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": severity.name,
            "event": event,
            "pid": os.getpid(),
            "thread": threading.current_thread().name,
            **fields,
        }
        line = json.dumps(record, default=str, sort_keys=True)
        with self._lock:
            self._rotate_if_needed()
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        if self._console:
            print(f"[{record['severity']}] {event} :: {fields}")

    def debug(self, event: str, **fields: Any) -> None:
        self._write(Severity.DEBUG, event, **fields)

    def info(self, event: str, **fields: Any) -> None:
        self._write(Severity.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        self._write(Severity.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        self._write(Severity.ERROR, event, **fields)

    def critical(self, event: str, **fields: Any) -> None:
        self._write(Severity.CRITICAL, event, **fields)

    def audit(self, event: str, **fields: Any) -> None:
        """AUDIT-severity events always bypass the level filter."""
        self._write(Severity.AUDIT, event, **fields)

    async def async_audit(self, event: str, **fields: Any) -> None:
        await asyncio.get_running_loop().run_in_executor(None, lambda: self.audit(event, **fields))

    async def async_info(self, event: str, **fields: Any) -> None:
        await asyncio.get_running_loop().run_in_executor(None, lambda: self.info(event, **fields))

    async def async_error(self, event: str, **fields: Any) -> None:
        await asyncio.get_running_loop().run_in_executor(None, lambda: self.error(event, **fields))


class Timer:
    """Small context-manager helper to time and audit-log an operation's duration."""

    __slots__ = ("logger", "event", "fields", "_start")

    def __init__(self, logger: AuditLogger, event: str, **fields: Any) -> None:
        self.logger = logger
        self.event = event
        self.fields = fields
        self._start: Optional[float] = None

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed_ms = round((time.perf_counter() - (self._start or 0)) * 1000, 3)
        status = "failed" if exc else "completed"
        self.logger.audit(f"{self.event}_{status}", duration_ms=elapsed_ms, **self.fields)
