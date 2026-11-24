#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Export all people.xlc biography cells for a complete EN/ES fidelity review.

This script is read-only. It does not modify either source CSV.
The output is a UTF-8 TSV with the exact CSV coordinates, English from the
working CSV, matching English from the original reference CSV, and Spanish.
"""
import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path

TARGET = "WarrenReport/WarrenReport/people.xlc"
KEY_FIELDS = ("archivo", "tipo", "fila", "columna", "id_entrada", "nid")
REQUIRED = set(KEY_FIELDS) | {"texto_ingles"}


def read_rows(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        missing = REQUIRED - fields
        if missing:
            raise ValueError(
                f"{path}: faltan columnas requeridas: {', '.join(sorted(missing))}"
            )
        return reader.fieldnames, list(reader)


def key_for(row):
    return tuple((row.get(name) or "") for name in KEY_FIELDS)


def main():
    ap = argparse.ArgumentParser(
        description="Exporta las biografías de people.xlc para revisión completa."
    )
    ap.add_argument("csv_traducido", help="Tactics_Ogre_espanol_neutral.csv")
    ap.add_argument("csv_original", help="Tactics_Ogre_Textos_English_Original.csv")
    ap.add_argument(
        "--salida",
        default="people_biografias_revision.tsv",
        help="TSV de salida (predeterminado: people_biografias_revision.tsv)"
    )
    args = ap.parse_args()

    translated_fields, translated_rows = read_rows(args.csv_traducido)
    _, original_rows = read_rows(args.csv_original)

    original_index = defaultdict(list)
    for row in original_rows:
        if (row.get("archivo") or "").strip() == TARGET and (row.get("columna") or "").strip() == "20":
            original_index[key_for(row)].append(row)

    bios = [
        row for row in translated_rows
        if (row.get("archivo") or "").strip() == TARGET
        and (row.get("columna") or "").strip() == "20"
    ]

    output_fields = [
        "archivo", "tipo", "fila", "columna", "id_entrada", "nid",
        "estado_original", "texto_ingles_original",
        "texto_ingles_csv", "texto_espanol", "caracteres", "marcadores"
    ]
    out_path = Path(args.salida)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    exact = missing = ambiguous = mismatch = 0
    translated = pending = 0
    seen_keys = Counter(key_for(row) for row in bios)

    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=output_fields, delimiter="\t",
            quoting=csv.QUOTE_MINIMAL, extrasaction="ignore"
        )
        writer.writeheader()
        for row in bios:
            matches = original_index.get(key_for(row), [])
            if not matches:
                status = "NO_ENCONTRADO"
                english_original = ""
                missing += 1
            elif len(matches) > 1:
                status = "DUPLICADO_EN_ORIGINAL"
                english_original = " || ".join(x.get("texto_ingles", "") for x in matches)
                ambiguous += 1
            else:
                english_original = matches[0].get("texto_ingles", "") or ""
                if english_original == (row.get("texto_ingles") or ""):
                    status = "COINCIDE"
                    exact += 1
                else:
                    status = "NO_COINCIDE"
                    mismatch += 1

            spanish = row.get("texto_espanol") or ""
            if spanish.strip():
                translated += 1
            else:
                pending += 1

            item = {name: (row.get(name) or "") for name in output_fields}
            item["estado_original"] = status
            item["texto_ingles_original"] = english_original
            writer.writerow(item)

    duplicates = sum(1 for n in seen_keys.values() if n > 1)
    print("EXPORTACIÓN DE BIOGRAFÍAS PEOPLE.XLC")
    print(f"Registros de biografía (columna 20): {len(bios)}")
    print(f"Con traducción española: {translated}")
    print(f"Pendientes sin traducción: {pending}")
    print(f"Inglés coincide exactamente con el CSV original: {exact}")
    print(f"Sin correspondencia en el CSV original: {missing}")
    print(f"Inglés diferente del CSV original: {mismatch}")
    print(f"Claves duplicadas en el CSV original: {ambiguous}")
    print(f"Coordenadas repetidas en el CSV traducido: {duplicates}")
    print(f"Archivo creado: {out_path.resolve()}")
    if missing or mismatch or ambiguous or duplicates:
        print("ADVERTENCIA: revisar los estados/duplicados antes de evaluar las traducciones.")
    else:
        print("VALIDACIÓN DE FUENTE: todas las coordenadas son únicas y coinciden exactamente.")
    print("No se modificó ninguno de los dos CSV de entrada.")


if __name__ == "__main__":
    main()
