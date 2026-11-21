#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reutiliza traducciones de textos ingleses idénticos sin sobrescribir el CSV maestro.

Normalización de hash, igual que el catálogo global:
- elimina solo el marcador {span ...} inicial;
- elimina todos los marcadores {w};
- conserva el resto del texto, marcadores, espacios y saltos de línea.

Una traducción se reutiliza únicamente cuando el grupo tiene exactamente una
variante española no vacía. Los grupos con variantes distintas se dejan intactos.
El inglés de cada ubicación se valida y, si fue alterado, se restaura desde el
CSV inglés original. El archivo de entrada nunca se modifica.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path

SPAN_RE = re.compile(
    r'^\{span ([0-9a-f]{2}) ([0-9a-f]{4}) ([0-9a-f]{2}) ([0-9a-f]{2})'
    r'((?: [0-9a-f]{12})*)\}'
)
LOCATION_FIELDS = ("archivo", "tipo", "fila", "columna", "id_entrada", "nid")
REQUIRED_FIELDS = set(LOCATION_FIELDS) | {
    "texto_ingles", "texto_espanol", "caracteres", "marcadores"
}


def normalize_english(text: str) -> str:
    text = text or ""
    match = SPAN_RE.match(text)
    if match:
        text = text[match.end():]
    return text.replace("{w}", "")


def hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def location_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row.get(field, "") or "" for field in LOCATION_FIELDS)


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"El CSV no tiene encabezados: {path}")
        missing = sorted(REQUIRED_FIELDS - set(reader.fieldnames))
        if missing:
            raise ValueError(
                f"Faltan columnas en {path}: {', '.join(missing)}"
            )
        return list(reader.fieldnames), list(reader)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rellena apariciones vacías con traducciones idénticas por hash."
    )
    parser.add_argument("csv_maestro", help="CSV español que se conservará intacto.")
    parser.add_argument(
        "--ingles-original", required=True,
        help="Tactics_Ogre_Textos_English_Original.csv"
    )
    parser.add_argument(
        "--salida", required=True,
        help="Ruta del nuevo CSV; no debe ser la misma que el maestro."
    )
    args = parser.parse_args()

    master_path = Path(args.csv_maestro)
    original_path = Path(args.ingles_original)
    output_path = Path(args.salida)

    if not master_path.is_file():
        parser.error(f"No existe el CSV maestro: {master_path}")
    if not original_path.is_file():
        parser.error(f"No existe el inglés original: {original_path}")
    if master_path.resolve() == output_path.resolve():
        parser.error("La salida debe ser distinta del CSV maestro.")
    if output_path.exists():
        parser.error(f"La salida ya existe; no se sobrescribirá: {output_path}")

    # Permite campos grandes si el CSV contiene textos extensos.
    csv.field_size_limit(min(sys.maxsize, 2_147_483_647))

    master_fields, master_rows = read_csv(master_path)
    original_fields, original_rows = read_csv(original_path)

    original_index: dict[tuple[str, ...], dict[str, str]] = {}
    for number, row in enumerate(original_rows, start=2):
        key = location_key(row)
        if key in original_index:
            raise ValueError(
                f"Ubicación duplicada en inglés original, fila {number}: {key}"
            )
        original_index[key] = row

    master_index: dict[tuple[str, ...], dict[str, str]] = {}
    restored_english = 0
    for number, row in enumerate(master_rows, start=2):
        key = location_key(row)
        if key in master_index:
            raise ValueError(
                f"Ubicación duplicada en CSV maestro, fila {number}: {key}"
            )
        master_index[key] = row

        original = original_index.get(key)
        if original is None:
            raise ValueError(
                f"Ubicación no encontrada en inglés original, fila {number}: {key}"
            )

        # Los metadatos de marcadores y caracteres deben coincidir con el original.
        for field in ("caracteres", "marcadores"):
            if (row.get(field, "") or "") != (original.get(field, "") or ""):
                raise ValueError(
                    f"Diferencia en {field}, fila {number}, ubicación {key}. "
                    "No se escribió ningún archivo."
                )

        original_english = original.get("texto_ingles", "") or ""
        if (row.get("texto_ingles", "") or "") != original_english:
            row["texto_ingles"] = original_english
            restored_english += 1

    if len(master_rows) != len(original_rows):
        raise ValueError(
            f"Cantidad de registros distinta: maestro={len(master_rows)}, "
            f"original={len(original_rows)}"
        )

    # Agrupa por el mismo hash global utilizado por FrenchTools/catálogo.
    groups: dict[str, dict] = {}
    for row in master_rows:
        normalized = normalize_english(row.get("texto_ingles", ""))
        if not normalized:
            continue

        digest = hash_text(normalized)
        group = groups.get(digest)
        if group is None:
            group = {
                "normalized": normalized,
                "rows": [],
                "translations": defaultdict(int),
                "pending": [],
            }
            groups[digest] = group
        elif group["normalized"] != normalized:
            raise ValueError(
                f"Colisión SHA-1/12 detectada para el hash {digest}. "
                "No se escribió ningún archivo."
            )

        group["rows"].append(row)
        spanish = row.get("texto_espanol", "") or ""
        if spanish.strip():
            group["translations"][spanish] += 1
        else:
            group["pending"].append(row)

    states = {
        "TRADUCIDO": 0,
        "REUTILIZAR_Y_COMPLETAR": 0,
        "REVISAR_VARIANTES": 0,
        "PENDIENTE": 0,
    }
    groups_reused = 0
    cells_filled = 0
    battle_cells_filled = 0

    for group in groups.values():
        variants = group["translations"]
        pending = group["pending"]

        if not variants:
            states["PENDIENTE"] += 1
            continue
        if len(variants) > 1:
            states["REVISAR_VARIANTES"] += 1
            continue
        if not pending:
            states["TRADUCIDO"] += 1
            continue

        states["REUTILIZAR_Y_COMPLETAR"] += 1
        groups_reused += 1
        translation = next(iter(variants))
        if not translation.strip():
            raise ValueError("Se detectó una variante española vacía.")

        for row in pending:
            if (row.get("texto_espanol", "") or "").strip():
                raise ValueError("Se intentó sobrescribir una traducción existente.")
            row["texto_espanol"] = translation
            cells_filled += 1
            if "battle_text.xlc" in (row.get("archivo", "") or "").casefold():
                battle_cells_filled += 1

    # Validación final: inglés y metadatos quedan alineados al original.
    for row in master_rows:
        original = original_index[location_key(row)]
        if (row.get("texto_ingles", "") or "") != (
            original.get("texto_ingles", "") or ""
        ):
            raise ValueError("La validación final del inglés original falló.")
        for field in ("caracteres", "marcadores"):
            if (row.get(field, "") or "") != (original.get(field, "") or ""):
                raise ValueError(f"La validación final de {field} falló.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=master_fields,
            extrasaction="raise",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(master_rows)

    translated_after = sum(
        1 for row in master_rows if (row.get("texto_espanol", "") or "").strip()
    )
    battle_total = sum(
        1 for row in master_rows
        if "battle_text.xlc" in (row.get("archivo", "") or "").casefold()
    )
    battle_translated = sum(
        1 for row in master_rows
        if "battle_text.xlc" in (row.get("archivo", "") or "").casefold()
        and (row.get("texto_espanol", "") or "").strip()
    )

    print("Integración por hash completada.")
    print(f"CSV de entrada sin modificar: {master_path}")
    print(f"CSV de salida: {output_path}")
    print(f"Registros: {len(master_rows)}")
    print(f"Grupos hash únicos: {len(groups)}")
    print(f"Grupos completamente traducidos: {states['TRADUCIDO']}")
    print(f"Grupos con una traducción reutilizable: {groups_reused}")
    print(f"Grupos con variantes omitidos para revisión: {states['REVISAR_VARIANTES']}")
    print(f"Grupos sin traducción: {states['PENDIENTE']}")
    print(f"Celdas españolas rellenadas: {cells_filled}")
    print(f"Celdas rellenadas en battle_text.xlc: {battle_cells_filled}")
    print(f"Textos ingleses restaurados desde el original: {restored_english}")
    print(f"Total de celdas españolas no vacías tras el proceso: {translated_after}")
    print(f"Registros battle_text.xlc: {battle_total}")
    print(f"Registros battle_text.xlc con español: {battle_translated}")
    print("No se sobrescribieron traducciones existentes ni se modificó el maestro.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
