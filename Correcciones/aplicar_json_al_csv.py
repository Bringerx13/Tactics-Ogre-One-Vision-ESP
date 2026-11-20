#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aplica el diccionario JSON y las excepciones al CSV maestro sin alterar el inglés.

Prioridad:
  1. Excepción por ubicación exacta.
  2. Traducción global por hash.
  3. Si no hay ninguna, conserva el texto español actual de esa fila.

Por defecto genera un archivo nuevo terminado en _desde_json.csv.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

SPAN_RE = re.compile(
    r'^\{span ([0-9a-f]{2}) ([0-9a-f]{4}) '
    r'([0-9a-f]{2}) ([0-9a-f]{2})((?: [0-9a-f]{12})*)\}'
)
LOCATION_FIELDS = (
    "archivo", "tipo", "fila", "columna", "id_entrada", "nid"
)


def normalizar_ingles(texto: str) -> str:
    texto = texto or ""
    match = SPAN_RE.match(texto)
    if match:
        texto = texto[match.end():]
    return texto.replace("{w}", "")


def hash_texto(texto: str) -> str:
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]


def clave_ubicacion(hash_id: str, fila: dict) -> str:
    datos = [hash_id] + [(fila.get(campo) or "") for campo in LOCATION_FIELDS]
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Rellena el CSV desde traducciones.json y excepciones_contexto.json."
    )
    parser.add_argument("csv_entrada")
    parser.add_argument("traducciones_json")
    parser.add_argument("excepciones_json")
    parser.add_argument("--salida", default=None)
    args = parser.parse_args()

    entrada = Path(args.csv_entrada)
    traducciones_path = Path(args.traducciones_json)
    excepciones_path = Path(args.excepciones_json)
    for ruta in (entrada, traducciones_path, excepciones_path):
        if not ruta.is_file():
            parser.error(f"No existe el archivo: {ruta}")

    traducciones = json.loads(traducciones_path.read_text(encoding="utf-8"))
    excepciones = json.loads(excepciones_path.read_text(encoding="utf-8"))
    salida = Path(args.salida) if args.salida else entrada.with_name(
        entrada.stem + "_desde_json" + entrada.suffix
    )

    with entrada.open("r", encoding="utf-8-sig", newline="") as origen:
        lector = csv.DictReader(origen)
        campos = lector.fieldnames
        if not campos or "texto_ingles" not in campos or "texto_espanol" not in campos:
            parser.error("El CSV debe contener texto_ingles y texto_espanol.")
        filas = list(lector)

    por_excepcion = 0
    por_hash = 0
    conservadas = 0
    sin_texto = 0
    hashes_sin_traduccion = set()

    for fila in filas:
        ingles = normalizar_ingles(fila.get("texto_ingles") or "")
        if not ingles:
            sin_texto += 1
            continue
        hash_id = hash_texto(ingles)
        llave = clave_ubicacion(hash_id, fila)

        excepcion = excepciones.get(llave)
        if excepcion is not None:
            fila["texto_espanol"] = excepcion["texto_espanol"]
            por_excepcion += 1
        elif hash_id in traducciones:
            fila["texto_espanol"] = traducciones[hash_id]
            por_hash += 1
        elif (fila.get("texto_espanol") or "").strip():
            conservadas += 1
        else:
            hashes_sin_traduccion.add(hash_id)

    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", encoding="utf-8-sig", newline="") as destino:
        escritor = csv.DictWriter(
            destino, fieldnames=campos, extrasaction="raise",
            lineterminator="\n"
        )
        escritor.writeheader()
        escritor.writerows(filas)

    print(f"CSV generado: {salida}")
    print(f"Traducciones aplicadas por excepción: {por_excepcion}")
    print(f"Traducciones aplicadas por hash: {por_hash}")
    print(f"Traducciones existentes conservadas: {conservadas}")
    print(f"Filas sin texto inglés útil: {sin_texto}")
    print(f"Textos aún pendientes (hashes únicos): {len(hashes_sin_traduccion)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
