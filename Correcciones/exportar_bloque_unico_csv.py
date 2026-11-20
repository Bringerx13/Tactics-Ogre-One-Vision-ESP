#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exporta textos ingleses únicos de un CSV maestro a un CSV de revisión por bloques.

Agrupa usando exactamente la normalización de FrenchTools:
- elimina un encabezado {span ...} inicial;
- elimina {w};
- conserva los demás marcadores.

El CSV maestro nunca se modifica.
"""
from __future__ import annotations
import argparse, csv, hashlib, json, re
from collections import defaultdict
from pathlib import Path

SPAN_RE = re.compile(r'^\{span ([0-9a-f]{2}) ([0-9a-f]{4}) ([0-9a-f]{2}) ([0-9a-f]{2})((?: [0-9a-f]{12})*)\}')
LOCATION_FIELDS = ("archivo", "tipo", "fila", "columna", "id_entrada", "nid")
OUT_FIELDS = ("hash", "texto_ingles", "apariciones", "pendientes",
              "variantes_espanol", "ubicaciones", "estado",
              "texto_espanol_nuevo", "excepciones_por_ubicacion")

def normalizar_ingles(texto: str) -> str:
    texto = texto or ""
    match = SPAN_RE.match(texto)
    if match:
        texto = texto[match.end():]
    return texto.replace("{w}", "")

def hash_texto(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]

def main() -> int:
    p = argparse.ArgumentParser(description="Exporta un bloque de textos ingleses únicos.")
    p.add_argument("csv_maestro")
    p.add_argument("--archivo", default="WarrenReport",
                   help="Filtro de ruta; por defecto WarrenReport.")
    p.add_argument("--limite", type=int, default=200)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--incluir-variantes", action="store_true",
                   help="Incluye grupos que ya tienen traducción, pero con variantes.")
    p.add_argument("--salida", default="WarrenReport_Lote_001.csv")
    a = p.parse_args()

    source = Path(a.csv_maestro)
    if not source.is_file():
        p.error(f"No existe el CSV maestro: {source}")
    if a.limite < 1 or a.offset < 0:
        p.error("--limite debe ser > 0 y --offset >= 0.")

    with source.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = set(reader.fieldnames or [])
        required = set(LOCATION_FIELDS) | {"texto_ingles", "texto_espanol"}
        missing = sorted(required - fields)
        if missing:
            p.error("Faltan columnas: " + ", ".join(missing))
        rows = list(reader)

    neighbours = defaultdict(dict)
    for row in rows:
        try:
            n = int(row.get("fila") or -1)
        except ValueError:
            n = -1
        if n >= 0:
            neighbours[(row.get("archivo", ""), row.get("columna", ""))][n] = row

    groups = {}
    wanted = (a.archivo or "").casefold()
    for row in rows:
        if wanted and wanted not in (row.get("archivo", "") or "").casefold():
            continue
        english = normalizar_ingles(row.get("texto_ingles", ""))
        if not english:
            continue
        h = hash_texto(english)
        group = groups.get(h)
        if group is None:
            group = {"hash": h, "texto_ingles": english,
                     "locations": [], "variants": defaultdict(list),
                     "pending": []}
            groups[h] = group
        elif group["texto_ingles"] != english:
            raise RuntimeError(f"Colisión SHA-1/12 detectada: {h}")

        location = {k: row.get(k, "") or "" for k in LOCATION_FIELDS}
        try:
            n = int(row.get("fila") or -1)
        except ValueError:
            n = -1
        sibling_rows = neighbours[(row.get("archivo", ""), row.get("columna", ""))]
        previous_row = sibling_rows.get(n - 1, {}) if n >= 0 else {}
        next_row = sibling_rows.get(n + 1, {}) if n >= 0 else {}
        location["texto_ingles_original"] = row.get("texto_ingles", "")
        location["texto_espanol_actual"] = row.get("texto_espanol", "")
        location["contexto_anterior"] = previous_row.get("texto_ingles", "")
        location["contexto_siguiente"] = next_row.get("texto_ingles", "")
        group["locations"].append(location)

        spanish = row.get("texto_espanol", "") or ""
        if spanish.strip():
            group["variants"][spanish].append(location)
        else:
            group["pending"].append(location)

    candidates = []
    for h, group in groups.items():
        if group["pending"] or (a.incluir_variantes and len(group["variants"]) > 1):
            first = group["locations"][0]
            try:
                first_row = int(first.get("fila") or 0)
            except ValueError:
                first_row = 0
            candidates.append((first.get("archivo", "").casefold(), first_row,
                               first.get("columna", ""), h, group))
    candidates.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    chosen = candidates[a.offset:a.offset + a.limite]

    output = Path(a.salida)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_FIELDS, lineterminator="\n")
        writer.writeheader()
        for _, _, _, h, group in chosen:
            variants = [
                {"texto_espanol": text, "apariciones": len(locations),
                 "ubicaciones": locations}
                for text, locations in sorted(group["variants"].items())
            ]
            status = ("REVISAR_VARIANTES" if len(group["variants"]) > 1
                      else "PENDIENTE" if not group["variants"]
                      else "RELLENAR_APARICIONES_VACIAS")
            writer.writerow({
                "hash": h,
                "texto_ingles": group["texto_ingles"],
                "apariciones": len(group["locations"]),
                "pendientes": len(group["pending"]),
                "variantes_espanol": json.dumps(variants, ensure_ascii=False, separators=(",", ":")),
                "ubicaciones": json.dumps(group["locations"], ensure_ascii=False, separators=(",", ":")),
                "estado": status,
                "texto_espanol_nuevo": "",
                "excepciones_por_ubicacion": "[]"
            })

    print(f"CSV maestro: {source}")
    print(f"Textos únicos del filtro '{a.archivo}': {len(groups)}")
    print(f"Textos elegibles: {len(candidates)}")
    print(f"Textos exportados: {len(chosen)}")
    print(f"Rango: {a.offset + 1}–{a.offset + len(chosen)}")
    print(f"Archivo de revisión: {output}")
    print("El CSV maestro no fue modificado.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
