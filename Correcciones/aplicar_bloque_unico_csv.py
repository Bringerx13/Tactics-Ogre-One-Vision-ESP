#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aplica un lote traducido por hashes al CSV maestro, dentro del filtro indicado.

Las traducciones globales solo rellenan celdas vacías. No sobrescribe traducciones
existentes ni fusiona grupos con variantes contextuales. Las excepciones se aplican
por ubicación exacta usando la columna excepciones_por_ubicacion.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from pathlib import Path

SPAN_RE = re.compile(r'^\{span ([0-9a-f]{2}) ([0-9a-f]{4}) ([0-9a-f]{2}) ([0-9a-f]{2})((?: [0-9a-f]{12})*)\}')
LOCATION_FIELDS = ("archivo", "tipo", "fila", "columna", "id_entrada", "nid")

def normalizar_ingles(texto: str) -> str:
    texto = texto or ""
    match = SPAN_RE.match(texto)
    if match:
        texto = texto[match.end():]
    return texto.replace("{w}", "")

def hash_texto(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]

def location_key(row: dict) -> tuple:
    return tuple(row.get(k, "") or "" for k in LOCATION_FIELDS)

def main() -> int:
    p = argparse.ArgumentParser(description="Integra traducciones agrupadas al CSV maestro.")
    p.add_argument("csv_maestro")
    p.add_argument("lote_traducido")
    p.add_argument("--archivo", default="WarrenReport")
    p.add_argument("--salida", default=None)
    p.add_argument("--sobrescribir-existentes", action="store_true")
    a = p.parse_args()

    master_path, batch_path = Path(a.csv_maestro), Path(a.lote_traducido)
    for path in (master_path, batch_path):
        if not path.is_file():
            p.error(f"No existe el archivo: {path}")

    with master_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        if not fields or not set(LOCATION_FIELDS + ("texto_ingles", "texto_espanol")).issubset(fields):
            p.error("El CSV maestro no tiene las columnas esperadas.")
        master_rows = list(reader)

    with batch_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        batch_fields = set(reader.fieldnames or [])
        required = {"hash", "texto_ingles", "texto_espanol_nuevo", "excepciones_por_ubicacion"}
        if not required.issubset(batch_fields):
            p.error("El lote no procede de exportar_bloque_unico_csv.py.")
        batch_rows = list(reader)

    scope = (a.archivo or "").casefold()
    index = {}
    for row in master_rows:
        if scope and scope not in (row.get("archivo", "") or "").casefold():
            continue
        english = normalizar_ingles(row.get("texto_ingles", ""))
        if english:
            index.setdefault(hash_texto(english), []).append(row)

    global_updates = exception_updates = skipped_conflict = 0
    skipped_empty = skipped_existing = unknown = 0
    errors = []

    for batch in batch_rows:
        h = (batch.get("hash") or "").strip()
        english = normalizar_ingles(batch.get("texto_ingles") or "")
        if not h or not english or hash_texto(english) != h:
            errors.append(f"El hash no coincide con el inglés: {h}")
            continue
        targets = index.get(h)
        if not targets:
            unknown += 1
            continue

        try:
            exceptions = json.loads(batch.get("excepciones_por_ubicacion") or "[]")
        except json.JSONDecodeError as exc:
            errors.append(f"Excepciones JSON inválidas para {h}: {exc}")
            continue
        if not isinstance(exceptions, list):
            errors.append(f"excepciones_por_ubicacion debe ser una lista para {h}")
            continue

        if exceptions:
            by_location = {location_key(row): row for row in targets}
            for item in exceptions:
                if not isinstance(item, dict):
                    errors.append(f"Excepción no válida para {h}")
                    continue
                translated = item.get("texto_espanol", "")
                if not isinstance(translated, str) or not translated.strip():
                    errors.append(f"Excepción sin texto español para {h}")
                    continue
                key = tuple(item.get(k, "") or "" for k in LOCATION_FIELDS)
                target = by_location.get(key)
                if target is None:
                    errors.append(f"Ubicación no encontrada para {h}: {key}")
                    continue
                if (target.get("texto_espanol") or "").strip() and not a.sobrescribir_existentes:
                    skipped_existing += 1
                    continue
                target["texto_espanol"] = translated
                exception_updates += 1
            continue

        translated = batch.get("texto_espanol_nuevo") or ""
        if not translated.strip():
            skipped_empty += 1
            continue

        variants = {row.get("texto_espanol", "") for row in targets
                    if (row.get("texto_espanol") or "").strip()}
        if len(variants) > 1:
            skipped_conflict += 1
            continue

        for target in targets:
            current = target.get("texto_espanol", "") or ""
            if current.strip() and not a.sobrescribir_existentes:
                skipped_existing += 1
                continue
            if current != translated:
                target["texto_espanol"] = translated
                global_updates += 1

    if errors:
        print("Errores detectados; no se escribió ningún CSV.")
        for error in errors[:30]:
            print("ERROR:", error)
        return 2

    output = Path(a.salida) if a.salida else master_path.with_name(
        master_path.stem + "_warren_actualizado" + master_path.suffix
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        writer.writerows(master_rows)

    print(f"CSV de salida: {output}")
    print(f"Traducciones globales aplicadas: {global_updates}")
    print(f"Excepciones aplicadas por ubicación: {exception_updates}")
    print(f"Grupos omitidos por variantes contextuales: {skipped_conflict}")
    print(f"Traducciones existentes no sobrescritas: {skipped_existing}")
    print(f"Filas de lote sin traducción nueva: {skipped_empty}")
    print(f"Hashes no encontrados en el filtro: {unknown}")
    print("El CSV maestro original no fue modificado.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
