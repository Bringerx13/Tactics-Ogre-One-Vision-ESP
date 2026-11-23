#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit the net XLC size if people.xlc strings are replaced in the original pool.

This is diagnostic only: it does not alter USRDIR, CSV, or ISO files.
It uses the same codec/span preparation as the append-only batch tool, but
compares each translated encoded string against its original encoded allocation.
"""
import os
import sys
import csv
import argparse
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tree import Game
from translate_xlc_csv_append import (
    TARGET_PATH, TARGET_CSV, parse_overlap_xlc,
    read_csv_translations, prepare
)


def main():
    ap = argparse.ArgumentParser(
        description="Calcula cuánto crecería o disminuiría people.xlc sustituyendo textos en su pool original."
    )
    ap.add_argument("usrdir", help="Carpeta USRDIR extraída")
    ap.add_argument("csv_path", help="CSV maestro de traducciones")
    ap.add_argument("--mode", choices=("recompute", "keep"), default="recompute")
    ap.add_argument(
        "--report",
        default="people_xlc_diferencias_bytes.tsv",
        help="Informe TSV de cada celda traducida"
    )
    args = ap.parse_args()

    game = Game(os.path.abspath(args.usrdir))
    original = next((data for path, data in game.leaves() if path == TARGET_PATH), None)
    if original is None:
        raise RuntimeError("No se encontró people.xlc en la hoja 700/0/3")

    info = parse_overlap_xlc(original)
    translations, total_rows, translated_rows = read_csv_translations(
        os.path.abspath(args.csv_path)
    )
    cells, changes, unchanged, padding = prepare(
        original, info, translations, args.mode
    )

    # A compact/repacked pool is only safe to estimate this way when each
    # string has its own non-overlapping pointer range.
    by_offset = sorted(info["cells"], key=lambda c: c["offset"])
    offsets = [c["offset"] for c in by_offset]
    if len(offsets) != len(set(offsets)):
        raise RuntimeError("Hay offsets compartidos; no se puede usar este cálculo simple.")
    for left, right in zip(by_offset, by_offset[1:]):
        if left["end"] > right["offset"]:
            raise RuntimeError(
                "Hay cadenas solapadas/interiores; se necesita un empaquetador específico."
            )

    change_map = {item["key"]: item for item in changes}
    records = []
    deltas = []
    shorter = longer = same = 0

    for key, tr in sorted(translations.items()):
        cell = cells[key]
        change = change_map.get(key)
        old_bytes = cell["end"] - cell["offset"]  # includes final NUL
        if change is None:
            new_bytes = old_bytes
            delta = 0
            estado = "idéntica"
        else:
            new_bytes = len(change["new_string"]) + 1
            delta = new_bytes - old_bytes
            if delta < 0:
                shorter += 1
                estado = "más corta"
            elif delta > 0:
                longer += 1
                estado = "más larga"
            else:
                same += 1
                estado = "mismo tamaño"
        deltas.append(delta)
        records.append({
            "fila": tr["row"],
            "columna": tr["col"],
            "estado": estado,
            "bytes_ingles_original": old_bytes,
            "bytes_espanol_codificado": new_bytes,
            "diferencia_bytes": delta,
            "texto_ingles": tr["english"],
            "texto_espanol": tr["spanish"],
        })

    net_delta = sum(deltas)
    projected = len(original) + net_delta
    append_bytes = sum(len(x["new_string"]) + 1 for x in changes)

    print("AUDITORÍA DE TAMAÑO - PEOPLE.XLC (SIN MODIFICAR ARCHIVOS)")
    print(f"Filas CSV para people.xlc: {total_rows}")
    print(f"Traducciones no vacías: {translated_rows}")
    print(f"Traducciones idénticas al original: {len(unchanged)}")
    print(f"Traducciones que cambian: {len(changes)}")
    print(f"Bytes originales del XLC: {len(original)}")
    print(f"Bytes que añade append-only: {append_bytes}")
    print(f"Traducciones más cortas que su texto inglés: {shorter}")
    print(f"Traducciones más largas que su texto inglés: {longer}")
    print(f"Traducciones del mismo tamaño: {same}")
    print(f"Diferencia neta al sustituir dentro del pool: {net_delta:+d} bytes")
    print(f"Tamaño estimado sustituyendo el pool original: {projected} bytes")
    print(f"Cabe en el tamaño original: {'SI' if projected <= len(original) else 'NO'}")
    if padding:
        print(f"Diferencias por espacios finales aceptadas: {len(padding)}")

    report_path = os.path.abspath(args.report)
    with open(report_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "fila", "columna", "estado", "bytes_ingles_original",
                "bytes_espanol_codificado", "diferencia_bytes",
                "texto_ingles", "texto_espanol"
            ],
            delimiter="\\t",
            quoting=csv.QUOTE_MINIMAL
        )
        writer.writeheader()
        writer.writerows(sorted(records, key=lambda x: x["diferencia_bytes"], reverse=True))

    print("Informe por celda: " + report_path)
    print("Este cálculo conserva las cadenas originales no traducidas y sus huecos;")
    print("solo estima la sustitución del pool. No ha creado ni modificado XLC, BIN o ISO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
