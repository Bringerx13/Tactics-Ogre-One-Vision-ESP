#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera un sistema de traducción por textos únicos a partir del CSV maestro.

No modifica el CSV de entrada. Crea:
  traducciones.json              Hash -> español (solo grupos sin conflicto).
  excepciones_contexto.json      Traducciones existentes ambiguas, por ubicación.
  catalogo_textos.json           Todos los textos únicos y todas sus ubicaciones.
  conflictos_contexto.json       Variantes españolas y ubicaciones para revisar.
  resumen_migracion.txt           Estadísticas y validaciones.

La normalización reproduce FrenchTools/outils/export.py:
  - elimina el encabezado {span ...} inicial;
  - elimina {w} del cuerpo;
  - conserva los demás marcadores.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

SPAN_RE = re.compile(
    r'^\{span ([0-9a-f]{2}) ([0-9a-f]{4}) '
    r'([0-9a-f]{2}) ([0-9a-f]{2})((?: [0-9a-f]{12})*)\}'
)
LOCATION_FIELDS = (
    "archivo", "tipo", "fila", "columna", "id_entrada", "nid"
)


def normalizar_ingles(texto: str) -> str:
    """Misma normalización que FrenchTools: sin span inicial ni {w}."""
    texto = texto or ""
    match = SPAN_RE.match(texto)
    if match:
        texto = texto[match.end():]
    return texto.replace("{w}", "")


def hash_texto(texto_normalizado: str) -> str:
    return hashlib.sha1(texto_normalizado.encode("utf-8")).hexdigest()[:12]


def obtener_ubicacion(fila: dict) -> dict:
    return {campo: (fila.get(campo) or "") for campo in LOCATION_FIELDS}


def clave_ubicacion(hash_id: str, ubicacion: dict) -> str:
    datos = [hash_id] + [ubicacion[c] for c in LOCATION_FIELDS]
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"))


def escribir_json(ruta: Path, datos) -> None:
    ruta.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Crea el catálogo JSON de textos únicos desde el CSV maestro."
    )
    parser.add_argument(
        "csv_entrada", nargs="?",
        default="Tactics_Ogre_espanol_neutral_espacios.csv",
        help="CSV maestro de entrada."
    )
    parser.add_argument(
        "--salida-dir", default="JSON_Translation",
        help="Carpeta donde se crearán los JSON."
    )
    args = parser.parse_args()

    entrada = Path(args.csv_entrada)
    salida = Path(args.salida_dir)
    if not entrada.is_file():
        parser.error(f"No existe el CSV: {entrada}")

    grupos: dict[str, dict] = {}
    filas_totales = 0
    filas_sin_texto = 0
    ubicaciones_vistas: dict[str, str] = {}
    duplicados_ubicacion = []

    with entrada.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        campos = set(lector.fieldnames or [])
        requeridos = {
            "archivo", "tipo", "fila", "columna",
            "id_entrada", "nid", "texto_ingles", "texto_espanol"
        }
        faltantes = sorted(requeridos - campos)
        if faltantes:
            parser.error("Faltan columnas requeridas: " + ", ".join(faltantes))

        for fila in lector:
            filas_totales += 1
            ingles_original = fila.get("texto_ingles") or ""
            ingles = normalizar_ingles(ingles_original)
            espanol = fila.get("texto_espanol") or ""
            if not ingles:
                filas_sin_texto += 1
                continue

            hash_id = hash_texto(ingles)
            ubicacion = obtener_ubicacion(fila)
            llave_ubicacion = clave_ubicacion(hash_id, ubicacion)

            grupo = grupos.get(hash_id)
            if grupo is None:
                grupo = {
                    "hash": hash_id,
                    "texto_ingles": ingles,
                    "apariciones": 0,
                    "archivos": set(),
                    "ubicaciones": [],
                    "variantes": defaultdict(list),
                    "sin_traduccion": []
                }
                grupos[hash_id] = grupo
            elif grupo["texto_ingles"] != ingles:
                raise RuntimeError(
                    f"Colisión SHA-1 truncada detectada para {hash_id}"
                )

            grupo["apariciones"] += 1
            grupo["archivos"].add(ubicacion["archivo"])
            grupo["ubicaciones"].append(ubicacion)

            if espanol.strip():
                grupo["variantes"][espanol].append(ubicacion)
                anterior = ubicaciones_vistas.get(llave_ubicacion)
                if anterior is not None and anterior != espanol:
                    duplicados_ubicacion.append({
                        "hash": hash_id,
                        "ubicacion": ubicacion,
                        "espanol_1": anterior,
                        "espanol_2": espanol
                    })
                else:
                    ubicaciones_vistas[llave_ubicacion] = espanol
            else:
                grupo["sin_traduccion"].append(ubicacion)

    traducciones = {}
    excepciones = {}
    catalogo = {}
    conflictos = {}
    grupos_unificados = 0
    grupos_conflictivos = 0
    grupos_pendientes = 0
    celdas_traducidas = 0
    celdas_vacias = 0
    filas_repetidas = 0

    for hash_id, grupo in sorted(grupos.items()):
        variantes = grupo["variantes"]
        numero_variantes = len(variantes)
        celdas_traducidas += sum(len(v) for v in variantes.values())
        celdas_vacias += len(grupo["sin_traduccion"])
        filas_repetidas += max(0, grupo["apariciones"] - 1)

        if numero_variantes == 0:
            estado = "pendiente"
            grupos_pendientes += 1
        elif numero_variantes == 1:
            estado = "unificado"
            grupos_unificados += 1
            traducciones[hash_id] = next(iter(variantes))
        else:
            estado = "conflicto_contexto"
            grupos_conflictivos += 1

            variantes_json = []
            for texto_es, ubicaciones in sorted(variantes.items()):
                variantes_json.append({
                    "texto_espanol": texto_es,
                    "apariciones": len(ubicaciones),
                    "ubicaciones": ubicaciones
                })
                for ubicacion in ubicaciones:
                    llave = clave_ubicacion(hash_id, ubicacion)
                    valor = {
                        "hash": hash_id,
                        "texto_ingles": grupo["texto_ingles"],
                        "ubicacion": ubicacion,
                        "texto_espanol": texto_es
                    }
                    anterior = excepciones.get(llave)
                    if anterior and anterior["texto_espanol"] != texto_es:
                        duplicados_ubicacion.append({
                            "hash": hash_id,
                            "ubicacion": ubicacion,
                            "espanol_1": anterior["texto_espanol"],
                            "espanol_2": texto_es
                        })
                    else:
                        excepciones[llave] = valor

            conflictos[hash_id] = {
                "hash": hash_id,
                "texto_ingles": grupo["texto_ingles"],
                "apariciones": grupo["apariciones"],
                "variantes": variantes_json,
                "ubicaciones_sin_traduccion": grupo["sin_traduccion"]
            }

        catalogo[hash_id] = {
            "hash": hash_id,
            "texto_ingles": grupo["texto_ingles"],
            "apariciones": grupo["apariciones"],
            "estado": estado,
            "cantidad_variantes_es": numero_variantes,
            "archivos": sorted(grupo["archivos"]),
            "ubicaciones": grupo["ubicaciones"]
        }

    salida.mkdir(parents=True, exist_ok=True)
    escribir_json(salida / "traducciones.json", traducciones)
    escribir_json(salida / "excepciones_contexto.json", excepciones)
    escribir_json(salida / "catalogo_textos.json", catalogo)
    escribir_json(salida / "conflictos_contexto.json", conflictos)
    escribir_json(salida / "duplicados_ubicacion.json", duplicados_ubicacion)

    resumen = [
        "MIGRACIÓN CSV -> JSON",
        f"CSV de entrada: {entrada.resolve()}",
        f"Filas leídas: {filas_totales}",
        f"Filas sin texto inglés útil: {filas_sin_texto}",
        f"Grupos/textos únicos: {len(grupos)}",
        f"Grupos con traducción uniforme: {grupos_unificados}",
        f"Grupos con variantes por contexto: {grupos_conflictivos}",
        f"Grupos sin traducción: {grupos_pendientes}",
        f"Celdas con traducción española: {celdas_traducidas}",
        f"Celdas sin traducción: {celdas_vacias}",
        f"Excepciones de contexto creadas: {len(excepciones)}",
        f"Repeticiones agrupadas (apariciones excedentes): {filas_repetidas}",
        f"Conflictos de ubicación exacta: {len(duplicados_ubicacion)}",
        "",
        "Archivos generados:",
        "  traducciones.json",
        "  excepciones_contexto.json",
        "  catalogo_textos.json",
        "  conflictos_contexto.json",
        "  duplicados_ubicacion.json",
        "",
        "El CSV de entrada no fue modificado.",
        "Las claves usan SHA-1/12 sobre el inglés sin span inicial ni {w},",
        "igual que FrenchTools/outils/export.py."
    ]
    (salida / "resumen_migracion.txt").write_text(
        "\n".join(resumen) + "\n", encoding="utf-8"
    )

    print("\n".join(resumen))
    if duplicados_ubicacion:
        print(
            "\nADVERTENCIA: hay ubicaciones duplicadas con traducciones distintas. "
            "Revisa duplicados_ubicacion.json antes de fusionar."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
