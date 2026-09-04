#!/usr/bin/env bash
#
# qrforge.sh - Bash wrapper around the QRForge Python CLI.
#
# Provides shorthand subcommands and its own shell-level audit trail
# (separate from the Python JSONL audit log) so every invocation of this
# script -- including argument-parsing failures before Python even starts --
# is recorded for accountability.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SHELL_LOG="${QRFORGE_SHELL_LOG:-$SCRIPT_DIR/qrforge_shell_audit.log}"

log() {
    local level="$1"; shift
    printf '%s [%s] pid=%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%S.%3NZ')" "$level" "$$" "$*" >> "$SHELL_LOG"
}

usage() {
    cat <<'EOF'
QRForge - Bash wrapper

Usage:
  ./qrforge.sh gen "<data>" [options...]      Generate a single QR code
  ./qrforge.sh styled "<data>" [options...]   Generate a styled QR code (circle+radial defaults)
  ./qrforge.sh batch <file> [options...]      Batch-generate from a .txt/.csv input file
  ./qrforge.sh interactive                    Run interactive mode
  ./qrforge.sh test                           Run the full unit test suite
  ./qrforge.sh help                           Show this message

Any additional flags are passed through verbatim to the Python CLI, e.g.:
  ./qrforge.sh gen "https://example.com" -e H --box-size 12 -d out/
  ./qrforge.sh batch payloads.csv --report-format xlsx --concurrency 8

Environment:
  PYTHON_BIN          Python interpreter to use (default: python3)
  QRFORGE_SHELL_LOG   Path to this wrapper's own audit log
                       (default: ./qrforge_shell_audit.log)
EOF
}

require_python() {
    if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
        log ERROR "python interpreter not found: $PYTHON_BIN"
        echo "Error: '$PYTHON_BIN' not found on PATH. Set PYTHON_BIN or install Python 3.10+." >&2
        exit 127
    fi
}

run_python_cli() {
    require_python
    log INFO "invoking cli args=[$*]"
    if "$PYTHON_BIN" -m qrforge.cli "$@"; then
        log AUDIT "cli_exit_success args=[$*]"
    else
        local code=$?
        log AUDIT "cli_exit_failure code=$code args=[$*]"
        exit "$code"
    fi
}

main() {
    cd "$SCRIPT_DIR"
    local cmd="${1:-help}"
    shift || true

    case "$cmd" in
        gen)
            [[ $# -ge 1 ]] || { echo "Usage: $0 gen \"<data>\" [options...]" >&2; exit 2; }
            log INFO "gen command data_len=${#1}"
            run_python_cli "$@"
            ;;
        styled)
            [[ $# -ge 1 ]] || { echo "Usage: $0 styled \"<data>\" [options...]" >&2; exit 2; }
            local data="$1"; shift
            log INFO "styled command data_len=${#data}"
            run_python_cli "$data" --styled --drawer circle --color radial "$@"
            ;;
        batch)
            [[ $# -ge 1 ]] || { echo "Usage: $0 batch <file> [options...]" >&2; exit 2; }
            log INFO "batch command file=$1"
            run_python_cli --batch "$@"
            ;;
        interactive|-i)
            log INFO "interactive command"
            run_python_cli --interactive
            ;;
        test)
            require_python
            log INFO "running unit test suite"
            if "$PYTHON_BIN" -m unittest discover -s tests -v; then
                log AUDIT "test_suite_passed"
            else
                log AUDIT "test_suite_failed"
                exit 1
            fi
            ;;
        help|-h|--help)
            usage
            ;;
        *)
            echo "Unknown command: $cmd" >&2
            usage
            exit 2
            ;;
    esac
}

main "$@"
