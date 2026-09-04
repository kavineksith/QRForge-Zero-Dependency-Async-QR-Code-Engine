"""
cli.py
======
Command-line entry point for QRForge: single QR generation, interactive
mode, and async batch processing with multi-format reporting.
"""

from __future__ import annotations
import argparse
import os
import sys
from typing import Optional

from .audit_logger import AuditLogger, Severity
from .core import generate_qr
from .exceptions import ErrorCode, QRForgeError
from .models import QRJob
from .pipeline import run_batch_sync, stream_jobs_from_file
from .renderer import DRAWER_STYLES
from .report import to_csv, to_json, to_terminal, to_xlsx

ECC_LEVELS = ("L", "M", "Q", "H")
COLOR_MASKS = ("solid", "radial", "square", "horizontal", "vertical")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qrforge",
        description="QRForge - zero-dependency, async, ISO/IEC 18004-compliant QR code generator",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Examples:
  Basic:
    python -m qrforge.cli "https://example.com"

  Save to a specific file:
    python -m qrforge.cli "https://example.com" -o out/example.png

  Styled:
    python -m qrforge.cli "https://example.com" --styled --drawer circle --color radial

  Interactive mode:
    python -m qrforge.cli --interactive

  Batch (async, parallel) from a file of one payload per line or a CSV with a 'data' column:
    python -m qrforge.cli --batch payloads.txt -d qr_codes --report-format xlsx
""",
    )

    data_group = parser.add_mutually_exclusive_group(required=False)
    data_group.add_argument("data", nargs="?", help="Data to encode in the QR code")
    data_group.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")
    data_group.add_argument("--batch", metavar="FILE", help="Path to a .txt (one payload/line) or .csv ('data' column) batch input file")

    out = parser.add_argument_group("Output")
    out.add_argument("-o", "--output", dest="filename", help="Output filename (single mode only; default: auto-generated)")
    out.add_argument("-d", "--output-dir", default="qr_codes", help="Directory to save QR code(s). Default: qr_codes")

    qr = parser.add_argument_group("QR Parameters")
    qr.add_argument("-v", "--version", type=int, choices=range(1, 41), metavar="1-40", help="QR version. Default: auto")
    qr.add_argument("-e", "--error-correction", choices=ECC_LEVELS, default="L", help="Error correction level. Default: L")
    qr.add_argument("-b", "--box-size", type=int, default=10, help="Pixel size of each module. Default: 10")
    qr.add_argument("--border", type=int, default=4, help="Quiet-zone border in modules. Default: 4")

    style = parser.add_argument_group("Styling")
    style.add_argument("-s", "--styled", action="store_true", help="Enable styled rendering")
    style.add_argument("--drawer", choices=DRAWER_STYLES, default="square", help="Module drawer shape")
    style.add_argument("--color", dest="color_mask", choices=COLOR_MASKS, default="solid", help="Color mask")
    style.add_argument("--foreground", default="black", help="Foreground color (name or #RRGGBB)")
    style.add_argument("--background", default="white", help="Background color (name or #RRGGBB)")

    batch = parser.add_argument_group("Batch Options")
    batch.add_argument("--concurrency", type=int, default=os.cpu_count() or 4, help="Max parallel workers for batch mode")
    batch.add_argument("--report-format", choices=("json", "csv", "xlsx", "terminal"), default="terminal", help="Batch report output format")
    batch.add_argument("--report-path", default=None, help="Report file path (default: <output-dir>/report.<ext>)")

    log = parser.add_argument_group("Logging")
    log.add_argument("--log-file", default="qrforge_audit.jsonl", help="Audit log path (JSONL). Default: qrforge_audit.jsonl")
    log.add_argument("--quiet", action="store_true", help="Suppress console log echo")

    return parser


def get_interactive_input() -> dict:
    print("\nQRForge - Interactive Mode")
    print("-" * 30)
    inputs: dict = {}

    while True:
        inputs["data"] = input("Data to encode (text/URL): ").strip()
        if inputs["data"]:
            break
        print("Error: data cannot be empty.")

    inputs["filename"] = input("Output filename (Enter to auto-generate): ").strip() or None
    inputs["output_dir"] = input("Output directory (default: qr_codes): ").strip() or "qr_codes"

    version = input("QR version 1-40 (Enter for auto): ").strip()
    inputs["version"] = int(version) if version else None

    ec = input("Error correction L/M/Q/H (default: L): ").strip().upper()
    inputs["error_correction"] = ec if ec in ECC_LEVELS else "L"

    box = input("Box size in pixels (default: 10): ").strip()
    inputs["box_size"] = int(box) if box else 10

    border = input("Border in modules (default: 4): ").strip()
    inputs["border"] = int(border) if border else 4

    styled = input("Styled QR code? (y/N): ").strip().lower()
    inputs["styled"] = styled in ("y", "yes")
    inputs["drawer"] = "square"
    inputs["color_mask"] = "solid"
    inputs["foreground"] = "black"
    inputs["background"] = "white"

    if inputs["styled"]:
        drawer = input(f"Drawer style {DRAWER_STYLES} (default: rounded): ").strip().lower()
        inputs["drawer"] = drawer if drawer in DRAWER_STYLES else "rounded"
        color = input(f"Color mask {COLOR_MASKS} (default: radial): ").strip().lower()
        inputs["color_mask"] = color if color in COLOR_MASKS else "radial"
        if inputs["color_mask"] in ("solid",):
            inputs["foreground"] = input("Foreground color (default: black): ").strip() or "black"
        inputs["background"] = input("Background color (default: white): ").strip() or "white"

    return inputs


def _auto_filename(data: str) -> str:
    sanitized = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in data)[:50]
    return f"qr_{sanitized or 'output'}.png"


def run_single(args: argparse.Namespace, logger: AuditLogger) -> int:
    filename = args.filename or _auto_filename(args.data)
    output_path = os.path.join(args.output_dir, filename) if not os.path.isabs(filename) else filename

    job = QRJob(
        data=args.data, output_path=output_path, version=args.version,
        ecc_level=args.error_correction, box_size=args.box_size, border=args.border,
        styled=args.styled, drawer_style=args.drawer, color_mask=args.color_mask,
        foreground=args.foreground, background=args.background,
    )
    logger.info("single_job_started", label=job.label)
    result = generate_qr(job)
    if result.success:
        logger.audit("qr_generated", label=job.label, output=result.output_path, version=result.version)
        print(f"\nSuccessfully generated QR code: {result.output_path}")
        print(f"Version: {result.version}  Mode: {result.mode}  Mask: {result.mask_pattern}  ECC: {job.ecc_level}")
        print(f"Saved in directory: {os.path.abspath(args.output_dir)}")
        return 0
    logger.error("qr_generation_failed", label=job.label, error=result.error, error_code=result.error_code)
    print(f"\nError: {result.error}", file=sys.stderr)
    return 1


def run_batch_mode(args: argparse.Namespace, logger: AuditLogger) -> int:
    logger.info("batch_started", input_file=args.batch, concurrency=args.concurrency)
    jobs = stream_jobs_from_file(
        args.batch, args.output_dir, ecc_level=args.error_correction, box_size=args.box_size,
        border=args.border, styled=args.styled, drawer_style=args.drawer,
        color_mask=args.color_mask, foreground=args.foreground, background=args.background,
    )
    results = run_batch_sync(jobs, logger, concurrency=args.concurrency)
    logger.audit("batch_completed", total=len(results), succeeded=sum(r.success for r in results))

    ext_map = {"json": "json", "csv": "csv", "xlsx": "xlsx", "terminal": None}
    ext = ext_map[args.report_format]
    if ext:
        report_path = args.report_path or os.path.join(args.output_dir, f"report.{ext}")
        os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
        {"json": to_json, "csv": to_csv, "xlsx": to_xlsx}[args.report_format](results, report_path)
        print(f"\nReport written to: {report_path}")
    print(to_terminal(results))
    return 0 if all(r.success for r in results) else 1


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    logger = AuditLogger(path=args.log_file, level=Severity.INFO, console=not args.quiet)

    try:
        if args.batch:
            sys.exit(run_batch_mode(args, logger))

        if args.interactive or not args.data:
            user_inputs = get_interactive_input()
            for key, value in user_inputs.items():
                setattr(args, key, value)

        sys.exit(run_single(args, logger))

    except QRForgeError as exc:
        logger.critical("unhandled_qrforge_error", error=str(exc), code=int(exc.code))
        print(f"\nError [{exc.code.name}]: {exc.message}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("interrupted_by_user")
        print("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        logger.critical("unhandled_exception", error=str(exc))
        print(f"\nUnexpected error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
