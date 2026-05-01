"""Run MBP-10 quality checks over multiple Databento DBN files.

This wrapper keeps the single-file parser as the source of truth, then
collects the key printed metrics into one cross-session report.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from pathlib import Path


JOB_RE = re.compile(r"(GLBX-\d{8}-[A-Z0-9]+)")
DATE_RE = re.compile(r"(\d{8})")
KEY_VALUE_RE = re.compile(r"^([a-zA-Z0-9_]+)=(.*)$")
CORR_RE = re.compile(r"([^:, ]+):(-?\d+(?:\.\d+)?)")


def discover_dbn_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    patterns = ("*.dbn", "*.dbn.zst")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(path.rglob(pattern))
    return sorted(files)


def session_label(path: Path) -> str:
    job_match = JOB_RE.search(str(path))
    date_match = DATE_RE.search(path.name)
    parts = []
    if date_match:
        parts.append(date_match.group(1))
    if job_match:
        parts.append(job_match.group(1))
    return "_".join(parts) if parts else path.stem.replace(".", "_")


def parse_quality_output(output: str) -> dict[str, str]:
    row: dict[str, str] = {}
    for line in output.splitlines():
        match = KEY_VALUE_RE.match(line.strip())
        if not match:
            continue
        key, value = match.groups()
        row[key] = value
        if key.startswith("corr_") or key.startswith("pressure_corr_"):
            for corr_key, corr_value in CORR_RE.findall(value):
                row[f"{key}_{corr_key}"] = corr_value
    return row


def write_csv(rows: list[dict[str, str]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    preferred = [
        "session",
        "dbn_path",
        "target_symbol",
        "target_records",
        "seconds",
        "seconds_with_events",
        "median_events_per_active_second",
        "median_spread",
        "max_spread",
        "trade_records",
        "trade_volume",
        "invalid_or_crossed_spread_records",
        "output_csv",
    ]
    ordered = [field for field in preferred if field in fieldnames]
    ordered.extend(field for field in fieldnames if field not in ordered)
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ordered)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(rows: list[dict[str, str]], output_md: Path) -> None:
    output_md.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "session",
        "target_records",
        "seconds_with_events",
        "median_events_per_active_second",
        "median_spread",
        "trade_records",
        "trade_volume",
    ]
    lines = [
        "# Databento MBP-10 Batch Report",
        "",
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row.get(col, "") for col in columns) + " |")
    lines.extend(
        [
            "",
            "## Files",
            "",
        ]
    )
    for row in rows:
        lines.append(f"- `{row.get('session', '')}`: `{row.get('dbn_path', '')}`")
    output_md.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MBP-10 quality checks over DBN files.")
    parser.add_argument("input", help="DBN file or directory containing .dbn/.dbn.zst files.")
    parser.add_argument("--symbol", required=True, help="Mapped symbol to analyze, e.g. MNQM6.")
    parser.add_argument("--output-dir", default="Analysis/output/mbp10_batch", help="Report output directory.")
    parser.add_argument("--chunk-size", type=int, default=250_000)
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing derived CSVs.")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    derived_dir = output_dir / "derived"
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    dbn_files = discover_dbn_files(input_path)
    if not dbn_files:
        raise SystemExit(f"No .dbn or .dbn.zst files found under {input_path}.")

    script_path = Path(__file__).with_name("databento_mbp10_quality_check.py")
    rows: list[dict[str, str]] = []
    for dbn_path in dbn_files:
        label = session_label(dbn_path)
        derived_csv = derived_dir / f"{label}_{args.symbol}_1s.csv"
        log_path = logs_dir / f"{label}_{args.symbol}.log"

        command = [
            sys.executable,
            str(script_path),
            str(dbn_path),
            "--symbol",
            args.symbol,
            "--chunk-size",
            str(args.chunk_size),
        ]
        if args.overwrite or not derived_csv.exists():
            command.extend(["--output-csv", str(derived_csv)])

        print(f"checking {dbn_path}")
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        log_path.write_text(result.stdout + result.stderr)
        row = parse_quality_output(result.stdout)
        row["session"] = label
        row["dbn_path"] = str(dbn_path)
        row["log_path"] = str(log_path)
        row.setdefault("output_csv", str(derived_csv))
        rows.append(row)

    summary_csv = output_dir / "summary.csv"
    summary_md = output_dir / "summary.md"
    write_csv(rows, summary_csv)
    write_markdown(rows, summary_md)
    print(f"summary_csv={summary_csv}")
    print(f"summary_md={summary_md}")


if __name__ == "__main__":
    main()
