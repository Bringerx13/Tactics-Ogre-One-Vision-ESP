#!/usr/bin/env python3
"""Export Warren Report XLC text using only validated string-pointer columns.

This is a read-only exporter. It does not modify XLC, BIN, ISO, or translation files.

Usage:
    python export_warren_report_xlc_clean.py INPUT_WARRENREPORT_DIR OUTPUT_CSV

Example:
    python export_warren_report_xlc_clean.py \
        "E:\\Tactics ogre\\Gibbed_Extracted\\WarrenReport" \
        "E:\\Tactics ogre\\USA_Export_Fixed\\Warren_Report_XLC_Text_Export_Clean.csv"

The script expects xlc_fixed.py, codec.py, and export.py in the same directory.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from xlc_fixed import parse_xlc  # type: ignore  # noqa: E402
from codec import decode  # type: ignore  # noqa: E402
from export import norm  # type: ignore  # noqa: E402


def decode_cell(blob: bytes, offset: int) -> tuple[str, str]:
    """Return normalized text and status without aborting the whole export."""
    try:
        decoded, _ = decode(blob, offset)
        return norm(decoded)[2], "OK"
    except Exception as exc:  # keep a bad pointer visible in the CSV
        return "", f"ERROR:{type(exc).__name__}:{exc}"


def export_tree(root: Path, output_csv: Path) -> tuple[list[dict[str, Any]], list[str], Counter[str]]:
    records: list[dict[str, Any]] = []
    skipped: list[str] = []
    resource_stats: Counter[str] = Counter()

    xlc_files = sorted(root.rglob("*.xlc"))
    for path in xlc_files:
        relative = path.relative_to(root).as_posix()
        try:
            blob = path.read_bytes()
        except OSError as exc:
            skipped.append(f"{relative}: READ_ERROR: {exc}")
            continue

        if blob[:4] != b"xlce":
            skipped.append(f"{relative}: NOT_XLCE_HEADER")
            continue

        try:
            info = parse_xlc(blob)
        except Exception as exc:
            skipped.append(f"{relative}: PARSE_ERROR: {type(exc).__name__}: {exc}")
            continue

        if not info:
            skipped.append(f"{relative}: PARSER_RETURNED_NONE")
            continue

        # Critical fix: export only columns that xlc_fixed validated as
        # string-pointer columns. Other columns may contain counters, offsets,
        # or pointers into the middle of unrelated strings (e.g. lce/ce/e).
        string_columns = sorted(set(info.get("strcols", [])))
        if not string_columns:
            skipped.append(f"{relative}: NO_VALIDATED_STRING_COLUMNS")
            continue

        resource_stats[relative] += 0
        for column in string_columns:
            values = info["cols"].get(column, [])
            for row_index, offset in enumerate(values):
                if not offset:
                    continue
                text, status = decode_cell(blob, offset)
                records.append(
                    {
                        "file": relative,
                        "row": row_index,
                        "column": column,
                        "offset": offset,
                        "text": text,
                        "status": status,
                    }
                )
                resource_stats[relative] += 1

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = ["file", "row", "column", "offset", "text", "status"]
    with output_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        writer.writerows(records)

    return records, skipped, resource_stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="Extracted WarrenReport directory")
    parser.add_argument("output_csv", type=Path, help="Destination CSV path")
    args = parser.parse_args()

    root = args.input_dir.expanduser().resolve()
    output_csv = args.output_csv.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"Input directory does not exist: {root}")

    records, skipped, resource_stats = export_tree(root, output_csv)
    errors = sum(1 for item in records if item["status"] != "OK")
    nonempty = sum(1 for item in records if str(item["text"]).strip())

    summary_path = output_csv.with_name(output_csv.stem + "_Summary.txt")
    with summary_path.open("w", encoding="utf-8") as handle:
        handle.write("WARREN REPORT XLC EXPORT — VALIDATED STRING COLUMNS\n")
        handle.write(f"Input directory: {root}\n")
        handle.write(f"CSV output: {output_csv}\n\n")
        handle.write(f"CSV records: {len(records)}\n")
        handle.write(f"Non-empty texts: {nonempty}\n")
        handle.write(f"Decode errors: {errors}\n\n")
        handle.write("RECORDS BY RESOURCE\n")
        for resource, count in sorted(resource_stats.items()):
            handle.write(f"{resource}: {count}\n")
        handle.write("\nSKIPPED / UNPARSED XLC FILES\n")
        if skipped:
            for item in skipped:
                handle.write(item + "\n")
        else:
            handle.write("None\n")
        handle.write("\nNo source XLC, BIN, ISO, or translation files were modified.\n")

    print("ARCHIVOS XLC ENCONTRADOS:", len(list(root.rglob("*.xlc"))))
    print("REGISTROS EXPORTADOS:", len(records))
    print("TEXTOS NO VACIOS:", nonempty)
    print("ERRORES DE DECODIFICACION:", errors)
    print("RECURSOS SIN EXPORTAR:", len(skipped))
    print("CSV CREADO:", output_csv)
    print("RESUMEN CREADO:", summary_path)
    print("No se modifico ningun archivo original.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
