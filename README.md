# 🎯 QRForge — Zero-Dependency, Async QR Code Engine (CLI)

A **from-scratch, ISO/IEC 18004-compliant QR code generator** written in
pure-stdlib Python. Unlike most "QR generator" projects, QRForge does not
call `pip install qrcode` and wrap it — it implements the actual
specification: Galois-field Reed-Solomon error correction, ISO data
encoding, 8-pattern mask penalty scoring, and even the PNG file format
itself, all with **zero third-party dependencies**.

This project exists as a portfolio piece demonstrating production-grade
Python engineering: async/parallel orchestration, a disciplined exception
architecture, accountable audit logging, and a correctly-implemented binary
file format encoder — not just "call a library and print a message."

---

## 📌 Problem Statement

Most public "QR generator" tutorials are thin wrappers around the `qrcode`
and `Pillow` packages: they add no engineering value beyond argument
parsing, and they inherit whatever dependency, licensing, and supply-chain
risk those packages carry. That's a fine choice for a five-minute script,
but it demonstrates nothing about the author's ability to implement a real
binary encoding specification, and it's a liability in dependency-averse
environments (air-gapped systems, hardened CI, regulated infra) where every
`pip install` is an audit item.

QRForge solves this by implementing the QR code specification directly:

* **Data encoding** — automatic mode selection (Numeric / Alphanumeric /
  Byte) and ISO/IEC 18004 bit-stream construction.
* **Error correction** — a from-scratch GF(256) Reed-Solomon codec, not a
  library call.
* **Symbol construction** — finder/timing/alignment patterns, BCH-encoded
  format & version information, and penalty-driven selection of the best of
  the 8 standard data masks.
* **Rendering** — a hand-written, dependency-free PNG encoder (`zlib` +
  `struct` only) with styled module drawers and gradient color masks.
* **Operational maturity** — async/parallel batch processing, structured
  exceptions, rotating JSONL audit logging, and multi-format reporting —
  the same standard the rest of this portfolio holds to.

Every generated QR code is verified in this repository's test suite (and
was cross-validated during development against an independent reference
decoder) to actually scan correctly — correctness isn't assumed, it's
checked.

---

## 🏗️ Solution Architecture

```
qrforge/
├── __init__.py         Public API surface
├── exceptions.py        OOP exception hierarchy: IntEnum codes, registry, from_code()
├── reedsolomon.py        GF(256) arithmetic + Reed-Solomon codeword generator
├── tables.py             ISO/IEC 18004 structural tables (RS block sizes, alignment coords)
├── encoder.py            Mode selection, bit-stream construction, version auto-selection
├── matrix.py              Module matrix: finder/timing/alignment/format/version + masking
├── png_writer.py          Pure-stdlib PNG (RGB, zlib-compressed) encoder
├── renderer.py            Styled rasterization: module drawers + gradient color masks
├── models.py              QRJob / QRResult domain objects (full dunder-method suites)
├── audit_logger.py        Rotating thread-safe JSONL logger with AUDIT severity
├── core.py                 Synchronous encode -> matrix -> render -> save pipeline
├── pipeline.py            Async batch orchestrator (Semaphore + ProcessPoolExecutor)
├── report.py               JSON / CSV / XLSX (stdlib OOXML) / terminal report generation
└── cli.py                 argparse CLI + interactive mode entry point

tests/                    132 unit tests covering every module above
qrforge.sh                 Bash wrapper: shorthand commands + shell-level audit log
```

**Pipeline flow for one QR code:**

```
payload (str)
   │
   ▼
select_mode()            -- Numeric / Alphanumeric / Byte
   │
   ▼
select_version()         -- smallest version 1-40 that fits, at the requested ECC level
   │
   ▼
build_bitstream()        -- mode header + character count + body + terminator + padding
   │
   ▼
interleave_with_ecc()    -- split into RS blocks, generate EC codewords, interleave
   │
   ▼
build_matrix()           -- place data, try all 8 masks, score penalties, keep best
   │
   ▼
render()                 -- rasterize modules into an RGB canvas (styled or plain)
   │
   ▼
RGBCanvas.save()          -- hand-rolled PNG encoding via zlib/struct
```

**Batch flow:** `stream_jobs_from_file()` (a generator — O(1) memory
regardless of input file size) feeds `QRJob` objects into `run_batch()`,
which bounds concurrency with an `asyncio.Semaphore` while dispatching the
actual (CPU-bound) encoding work to a `ProcessPoolExecutor` for real
multi-core parallelism, then collects results via `asyncio.as_completed`
for incremental progress.

### Why implement QR encoding from scratch?

QR encoding is genuinely CPU-bound, self-contained math (Galois-field
arithmetic + a well-specified placement algorithm) — a good fit for a
dependency-free implementation, unlike, say, reimplementing TLS. Every
structural table used (Reed-Solomon block sizes, alignment pattern
coordinates, BCH generator polynomials) comes directly from the public
ISO/IEC 18004 specification.

### Known scope boundary: Kanji mode

Kanji mode (ISO/IEC 18004's dedicated Shift-JIS 13-bit encoding) is not
implemented. Any Unicode payload — including Japanese text — is still
correctly encoded and scannable via **Byte mode** (UTF-8), just at a
slightly lower bit-efficiency than a Kanji-mode-only encoder would achieve.
This was a deliberate scope decision, not an oversight: Byte mode already
guarantees lossless, spec-compliant encoding of any input.

---

## 📥 Installation

Requires **Python 3.10+**. No `pip install` needed — everything is stdlib.

```bash
git clone <this-repo>
cd QRForge
chmod +x qrforge.sh
```

---

## 🚀 Usage

### Single QR code

```bash
python -m qrforge.cli "https://example.com"
```

### Custom output location

```bash
python -m qrforge.cli "https://example.com" -o example.png -d out/
```

### Styled QR code

```bash
python -m qrforge.cli "https://example.com" --styled --drawer circle --color radial
```

### Full customization

```bash
python -m qrforge.cli "My Data" -o custom.png -v 5 -e H -b 15 --border 2 \
  --styled --drawer rounded --color vertical --foreground "#1e3a8a" --background white
```

### Interactive mode

```bash
python -m qrforge.cli --interactive
```

### Batch generation (async, parallel, with a report)

Input can be a `.txt` file (one payload per line) or a `.csv` file with a
`data` column (optionally `filename` and `ecc_level` columns too):

```bash
python -m qrforge.cli --batch payloads.txt -d qr_codes \
  --concurrency 8 --report-format xlsx
```

### Bash wrapper shorthand

```bash
./qrforge.sh gen "https://example.com" -e H
./qrforge.sh styled "https://example.com"          # circle + radial defaults
./qrforge.sh batch payloads.csv --report-format json
./qrforge.sh interactive
./qrforge.sh test                                    # run the full unit test suite
```

---

## ⚙️ Options

| Option                | Description                                                                    |
| ---------------------- | -------------------------------------------------------------------------------- |
| `-v, --version`        | QR version (1–40). Auto-selects the smallest fitting version if omitted        |
| `-e, --error-correction` | Error correction level: `L`, `M`, `Q`, `H` (default: `L`)                     |
| `-b, --box-size`        | Pixel size of each module (default: 10)                                       |
| `--border`              | Quiet-zone border in modules (default: 4; ISO minimum, don't go below this)    |
| `-s, --styled`          | Enable styled rendering                                                        |
| `--drawer`               | Module shape: `square`, `rounded`, `gapped`, `circle`, `vertical`, `horizontal` |
| `--color`                | Color mask: `solid`, `radial`, `square`, `horizontal`, `vertical`             |
| `--foreground`           | Foreground color, name or `#RRGGBB` (default: black)                          |
| `--background`           | Background color, name or `#RRGGBB` (default: white)                          |
| `--batch FILE`           | Path to a `.txt`/`.csv` batch input file                                      |
| `--concurrency`          | Max parallel workers for batch mode (default: CPU count)                      |
| `--report-format`         | Batch report format: `json`, `csv`, `xlsx`, `terminal` (default: `terminal`)  |
| `--log-file`              | Audit log path (default: `qrforge_audit.jsonl`)                              |

Run `python -m qrforge.cli --help` for the complete list.

---

## 📁 Output

Single-mode QR codes are saved to the specified output directory (default:
`qr_codes`). Batch mode writes one PNG per payload plus a report file.
Every run appends structured JSONL events to the audit log — including an
`AUDIT`-severity record per successful generation that **always** gets
written regardless of the configured log verbosity, so accountability
records can never be silently suppressed by a `--quiet` flag or a coarse
log level.

---

## 🔧 Troubleshooting

**"Payload of N bytes exceeds QR version 40 capacity at ECC level X"**
The data is too large for a QR code at that error-correction level. Try a
lower ECC level (`L` holds the most data, `H` the least) or shorten the
payload.

**"Requested version N is too small for this payload"**
You passed `-v` explicitly but the payload doesn't fit at that version and
ECC level. Either omit `-v` (auto-select) or raise it.

**Styled QR code won't scan**
Function patterns (finder squares, timing lines, format/version info) are
always rendered solid, and gradient fades are capped, specifically to keep
styled codes scannable — but very low-contrast foreground/background pairs
(e.g. two similar pastel shades) can still defeat real-world cameras even
though they decode fine in software. Prefer high-contrast color pairs, and
test a physical print/screen scan before high-stakes use (event badges,
product packaging, etc.).

**"No write permission for output directory" / PermissionDeniedError**
The process can't write to the target directory. Check ownership/permissions
or point `-d` at a writable location.

**Batch report is empty / all jobs failed**
Check the printed terminal summary (always shown) and the audit log
(`--log-file`) for the specific `qr_generation_failed` events with their
`error` and `error_code` fields.

**Batch input CSV rejected**
CSV batch files must have a `data` column (header row). `filename` and
`ecc_level` columns are optional per-row overrides.

**Slow batch runs**
`--concurrency` defaults to your CPU count. QR encoding is CPU-bound (RS
math + matrix masking), so raising concurrency past your physical core
count won't help and may hurt due to process-pool overhead.

**Running the test suite**
```bash
python -m unittest discover -s tests -v
# or
./qrforge.sh test
```

---

## 🧪 Testing & Verification

132 unit tests cover every module, including exact Reed-Solomon regression
vectors, byte-for-byte module-matrix construction checks, PNG chunk
structure validation, XLSX zip/XML structure validation, audit log rotation
behavior, and end-to-end generation across all ECC levels and styling
options. During development, the full encoding pipeline was additionally
cross-validated module-by-module against an independent QR encoder and
decode-verified with an independent scanner across randomized payloads,
sizes, ECC levels, and every drawer/color-mask combination.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE)
file for details.

## 🛑 Disclaimer

QRForge is provided **as-is**, without any warranty, express or implied. It
is intended for educational, portfolio, and general-purpose use. QR codes
generated by any tool — including this one — should be scan-tested in your
actual target environment before use in critical contexts (payments,
ticketing, medical, access control, or other security-sensitive
applications). The author(s) are not responsible for consequences arising
from generated QR codes that encode incorrect, malicious, or unintended
data supplied by the user. This is a personal portfolio project; use at
your own risk.
