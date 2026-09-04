"""
report.py
=========
Generates batch-run reports in JSON, CSV, terminal, and Excel (.xlsx)
formats. The XLSX writer builds the OOXML package by hand with `zipfile`
+ `xml.sax.saxutils.escape` -- no openpyxl/xlsxwriter dependency.
"""

from __future__ import annotations
import csv
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import List
from xml.sax.saxutils import escape

from .exceptions import ErrorCode, ReportGenerationError
from .models import QRResult

_COLUMNS = [
    "label", "success", "output_path", "version", "mode",
    "mask_pattern", "byte_size", "duration_ms", "error", "error_code",
]


def to_json(results: List[QRResult], path: str) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": len(results),
        "succeeded": sum(1 for r in results if r.success),
        "failed": sum(1 for r in results if not r.success),
        "results": [r.to_dict() for r in results],
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except OSError as exc:
        raise ReportGenerationError(f"Failed to write JSON report: {exc}",
                                     code=ErrorCode.REPORT_GENERATION_FAILED, path=path) from exc


def to_csv(results: List[QRResult], path: str) -> None:
    try:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_COLUMNS)
            writer.writeheader()
            for r in results:
                row = r.to_dict()
                writer.writerow({k: row.get(k, "") for k in _COLUMNS})
    except OSError as exc:
        raise ReportGenerationError(f"Failed to write CSV report: {exc}",
                                     code=ErrorCode.REPORT_GENERATION_FAILED, path=path) from exc


def to_terminal(results: List[QRResult]) -> str:
    lines = []
    ok = sum(1 for r in results if r.success)
    fail = len(results) - ok
    lines.append(f"\n{'=' * 60}\nQRForge Batch Report -- {len(results)} job(s), {ok} ok, {fail} failed\n{'=' * 60}")
    for r in sorted(results, key=lambda x: (not x.success, x.job.label)):
        lines.append(str(r))
    return "\n".join(lines)


# --- minimal pure-stdlib XLSX writer ---------------------------------------

def _col_letter(n: int) -> str:
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _sheet_xml(rows: List[List[str]]) -> str:
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
    out.append('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">')
    out.append("<sheetData>")
    for r_idx, row in enumerate(rows, start=1):
        out.append(f'<row r="{r_idx}">')
        for c_idx, value in enumerate(row, start=1):
            ref = f"{_col_letter(c_idx)}{r_idx}"
            out.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out)


def to_xlsx(results: List[QRResult], path: str) -> None:
    rows = [_COLUMNS] + [[r.to_dict().get(col, "") for col in _COLUMNS] for r in results]
    try:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '</Types>'
            ))
            z.writestr("_rels/.rels", (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                '</Relationships>'
            ))
            z.writestr("xl/_rels/workbook.xml.rels", (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                '</Relationships>'
            ))
            z.writestr("xl/workbook.xml", (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="QRForge Report" sheetId="1" r:id="rId1"/></sheets>'
                '</workbook>'
            ))
            z.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows))
    except OSError as exc:
        raise ReportGenerationError(f"Failed to write XLSX report: {exc}",
                                     code=ErrorCode.REPORT_GENERATION_FAILED, path=path) from exc
