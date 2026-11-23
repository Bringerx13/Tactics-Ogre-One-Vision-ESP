#!/usr/bin/env python3
"""Apply all translated cells for one XLC from the project CSV using append-only storage.

The original XLC text pool is never compacted or rewritten. Each changed cell gets
a new encoded string appended at EOF and only that cell's 32-bit pointer is changed.
The script validates CSV coordinates and exact English source text before building.
"""
import os
import sys
import csv
import struct
import traceback
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tree import Game
from codec import decode, encode
from export import norm
from build import Builder
import span as spanmod
from isopatch import rebuild_iso

TARGET_PATH = (700, 0, 3)
TARGET_CSV = "WarrenReport/WarrenReport/people.xlc"


def log(message):
    print(message, flush=True)


def parse_overlap_xlc(data):
    if data[:4] != b"xlce" or len(data) < 16:
        raise ValueError("Firma/cabecera XLC no válida")
    n, _do, es = struct.unpack_from("<III", data, 4)
    if es < 4 or es % 4:
        raise ValueError(f"Tamaño de registro no compatible: {es}")
    hend = 16 + n * es
    if hend > len(data):
        raise ValueError("La tabla de registros supera el tamaño del recurso")

    columns = []
    cells = []
    for col in range(0, es, 4):
        values = [
            struct.unpack_from("<I", data, 16 + row * es + col)[0]
            for row in range(n)
        ]
        nonzero = [(row, value) for row, value in enumerate(values) if value]
        if not nonzero or not all(hend <= value < len(data) for _, value in nonzero):
            continue
        found = []
        try:
            for row, value in nonzero:
                text, end = decode(data, value)
                found.append({
                    "row": row, "col": col, "offset": value,
                    "text": text, "end": end,
                })
        except Exception:
            continue
        columns.append(col)
        cells.extend(found)

    if not columns:
        raise ValueError("No se detectaron columnas de punteros XLC")
    return {
        "n": n, "es": es, "hend": hend,
        "pointer_columns": columns,
        "cells": sorted(cells, key=lambda c: (c["row"], c["col"])),
    }


def read_csv_translations(csv_path):
    translations = {}
    total_file_rows = 0
    translated_rows = 0
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"archivo", "fila", "columna", "texto_ingles", "texto_espanol"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError("Faltan columnas en el CSV: " + ", ".join(sorted(missing)))

        for line_no, item in enumerate(reader, start=2):
            if item.get("archivo", "").strip() != TARGET_CSV:
                continue
            total_file_rows += 1
            translated = (item.get("texto_espanol") or "").strip()
            if not translated:
                continue
            translated_rows += 1
            try:
                row = int(item["fila"])
                col = int(item["columna"])
            except Exception:
                raise ValueError(f"Fila CSV {line_no}: fila/columna no numéricas")
            key = (row, col)
            record = {
                "row": row,
                "col": col,
                "english": item.get("texto_ingles") or "",
                "spanish": item.get("texto_espanol") or "",
                "line": line_no,
            }
            if key in translations:
                previous = translations[key]
                raise ValueError(
                    f"Coordenada duplicada {key} en líneas CSV "
                    f"{previous['line']} y {line_no}"
                )
            translations[key] = record

    return translations, total_file_rows, translated_rows


def prepare(original, info, translations, mode):
    cells = {(c["row"], c["col"]): c for c in info["cells"]}
    missing = []
    source_mismatch = []
    trailing_padding = []
    changes = []
    unchanged = []
    for key, tr in sorted(translations.items()):
        cell = cells.get(key)
        if cell is None:
            missing.append((key, tr["line"]))
            continue
        if cell["text"] != tr["english"]:
            # En people.xlc hay una celda cuyo texto original termina en "\\n  ".
            # El CSV conserva el salto de línea, pero omite esos dos espacios de relleno.
            # Aceptamos exclusivamente esta diferencia; nunca se recorta ni reescribe
            # el texto original que permanece en el bloque append-only.
            if tr["english"].endswith("\\n") and cell["text"] == tr["english"] + "  ":
                trailing_padding.append((key, tr["line"], 2))
            else:
                source_mismatch.append((key, tr["line"], tr["english"], cell["text"]))
                continue

        hdr, autowrap, old_body = norm(cell["text"])
        new_body = tr["spanish"]
        if new_body == old_body:
            unchanged.append((key, tr))
            continue

        if new_body.startswith("{span "):
            raise ValueError(
                f"La traducción de {key} contiene un encabezado {{span ...}}. "
                "El CSV debe guardar solo el cuerpo; el encabezado se genera automáticamente."
            )
        encoded_body, _ = encode(new_body, autowrap=autowrap)
        prefix = spanmod.make_header(hdr, new_body, mode) if hdr else b""
        new_string = prefix + encoded_body
        changes.append({
            "key": key,
            "old_offset": cell["offset"],
            "new_string": new_string,
            "expected_body": new_body,
            "span_bytes": len(prefix),
            "string_bytes": len(new_string),
            "line": tr["line"],
        })

    if missing or source_mismatch:
        log(f"COORDENADAS SIN CELDA XLC: {len(missing)}")
        for x in missing[:10]:
            log(f"  fila/columna={x[0]}, línea CSV={x[1]}")
        log(f"TEXTOS INGLESES QUE NO COINCIDEN EXACTAMENTE: {len(source_mismatch)}")
        for x in source_mismatch[:10]:
            log(f"  fila/columna={x[0]}, línea CSV={x[1]}")
            log(f"    CSV: {x[2]!r}")
            log(f"    XLC: {x[3]!r}")
        raise ValueError(
            "Validación detenida: no se modificó ningún archivo. "
            "Hay que resolver las coordenadas o textos originales que no coinciden."
        )

    return cells, changes, unchanged, trailing_padding


def rebuild_append_batch(original, info, changes):
    out = bytearray(original)
    new_offsets = {}
    for change in changes:
        new_offset = len(out)
        out += change["new_string"] + b"\0"
        row, col = change["key"]
        struct.pack_into("<I", out, 16 + row * info["es"] + col, new_offset)
        new_offsets[change["key"]] = new_offset
    return bytes(out), new_offsets


def verify_batch(original, rebuilt, old_info, changes, unchanged):
    new_info = parse_overlap_xlc(rebuilt)
    before = {(c["row"], c["col"]): c for c in old_info["cells"]}
    after = {(c["row"], c["col"]): c for c in new_info["cells"]}
    if set(before) != set(after):
        raise RuntimeError("Cambió el conjunto de celdas de texto")

    change_map = {x["key"]: x for x in changes}
    text_errors = []
    pointer_errors = []
    for key, old_cell in before.items():
        new_cell = after[key]
        if key in change_map:
            _, _, actual_body = norm(new_cell["text"])
            if actual_body != change_map[key]["expected_body"]:
                text_errors.append((key, "traducción distinta", actual_body))
        else:
            if new_cell["text"] != old_cell["text"]:
                text_errors.append((key, "texto no modificado cambió", new_cell["text"]))
            if new_cell["offset"] != old_cell["offset"]:
                pointer_errors.append((key, old_cell["offset"], new_cell["offset"]))

    expected_prefix = bytearray(original)
    for key, new_offset in ((k, after[k]["offset"]) for k in change_map):
        row, col = key
        struct.pack_into("<I", expected_prefix, 16 + row * old_info["es"] + col, new_offset)
    prefix_ok = rebuilt[:len(original)] == bytes(expected_prefix)

    if text_errors or pointer_errors or not prefix_ok:
        raise RuntimeError(
            "Verificación append-only fallida: "
            f"textos={len(text_errors)}, punteros={len(pointer_errors)}, "
            f"bytes_originales_conservados={prefix_ok}"
        )
    return len(after), prefix_ok


def update_preload_copy(game, builder, target_pair):
    blob_dir = game.ft.dir(0)
    if not blob_dir["files"]:
        raise RuntimeError("FILETABLE dir 0000 no contiene archivos")
    first_file = blob_dir["files"][0]
    raw_bin = game.bin(0)
    off = game.ft.offset(blob_dir, first_file)
    raw = raw_bin[off:off + first_file["size"]]
    if len(raw) < 4:
        raise RuntimeError("El blob preload de 0000.BIN está truncado")

    count = struct.unpack_from("<I", raw, 0)[0]
    table_end = 4 + 8 * count
    if table_end > len(raw):
        raise RuntimeError("Tabla interna del preload fuera de límites")
    entries = [
        list(struct.unpack_from("<II", raw, 4 + 8 * i))
        for i in range(count)
    ]
    pos = table_end
    blocks = []
    for _file_id, size in entries:
        if pos + size > len(raw):
            raise RuntimeError("Bloque del preload fuera de límites")
        blocks.append(raw[pos:pos + size])
        pos += size

    did_target, fid_target = target_pair
    matches = []
    for i, (file_id, _size) in enumerate(entries):
        did = file_id & 0xFFFF
        fid = file_id >> 16
        if (did, fid) == (did_target, fid_target):
            rebuilt_file = builder.file_bytes(did, fid)
            blocks[i] = rebuilt_file
            entries[i][1] = len(rebuilt_file)
            matches.append(len(rebuilt_file))

    if matches:
        new_blob = (
            struct.pack("<I", count)
            + b"".join(struct.pack("<II", *entry) for entry in entries)
            + b"".join(blocks)
        )
        builder.leaf_mods[(0, 0)] = {(): new_blob}
        log(f"PRELOAD: {len(matches)} copia(s) actualizada(s), bytes={matches}")
    else:
        log("PRELOAD: no existe copia de este archivo en el blob 0000.BIN")


def main():
    if len(sys.argv) not in (5, 6):
        log(
            'Uso:\n'
            '  AUDITORÍA: python -u translate_xlc_csv_append.py '
            '"<USRDIR>" "<CSV>" "<ISO original>" --check [recompute|keep]\n'
            '  ISO:       python -u translate_xlc_csv_append.py '
            '"<USRDIR>" "<CSV>" "<ISO original>" "<ISO salida>" [recompute|keep]'
        )
        return 2

    usrdir, csv_path, iso_in = map(os.path.abspath, sys.argv[1:4])
    output_arg = sys.argv[4]
    mode = sys.argv[5] if len(sys.argv) == 6 else "recompute"
    if mode not in ("recompute", "keep"):
        raise ValueError("Modo span debe ser recompute o keep")
    if not os.path.isdir(usrdir):
        raise FileNotFoundError("No existe USRDIR: " + usrdir)
    if not os.path.isfile(csv_path):
        raise FileNotFoundError("No existe CSV: " + csv_path)
    if not os.path.isfile(iso_in):
        raise FileNotFoundError("No existe ISO original: " + iso_in)

    check_only = output_arg == "--check"
    iso_out = None if check_only else os.path.abspath(output_arg)
    if iso_out and os.path.normcase(iso_in) == os.path.normcase(iso_out):
        raise ValueError("La ISO de salida debe tener un nombre diferente")

    log("FRENCHTOOLS - PEOPLE.XLC APPEND-ONLY CSV BATCH")
    log("Recurso CSV: " + TARGET_CSV)
    log("Recurso XLC: 700/0/3")
    log("Modo span: " + mode)

    translations, total_rows, translated_rows = read_csv_translations(csv_path)
    game = Game(usrdir)
    original = next((data for path, data in game.leaves() if path == TARGET_PATH), None)
    if original is None:
        raise RuntimeError("No se encontró la hoja XLC 700/0/3 en USRDIR")
    info = parse_overlap_xlc(original)
    cells, changes, unchanged, trailing_padding = prepare(original, info, translations, mode)
    if trailing_padding:
        log(f"DIFERENCIAS ACEPTADAS POR RELLENO FINAL: {len(trailing_padding)}")
        for key, line, count in trailing_padding:
            log(
                f"  fila/columna={key}, línea CSV={line}: "
                f"CSV termina en \\n; XLC conserva {count} espacios adicionales"
            )
        log("Los espacios originales se conservan; no se recortan ni reescriben.")

    log(f"Filas del CSV para people.xlc: {total_rows}")
    log(f"Filas con traducción no vacía: {translated_rows}")
    log(f"Celdas de texto detectadas en XLC: {len(info['cells'])}")
    log(f"Coordenadas de traducción únicas: {len(translations)}")
    log(f"Traducciones que requieren cambio real: {len(changes)}")
    log(f"Traducciones idénticas al cuerpo original (sin añadir bytes): {len(unchanged)}")
    log(f"Bytes originales del XLC: {len(original)}")
    log(f"Bytes que se añadirán al XLC: {sum(x['string_bytes'] + 1 for x in changes)}")

    rebuilt, new_offsets = rebuild_append_batch(original, info, changes)
    verified_count, prefix_ok = verify_batch(original, rebuilt, info, changes, unchanged)
    log(f"Tamaño XLC resultante: {len(rebuilt)}")
    log(f"Celdas verificadas tras releer: {verified_count}")
    log("Todos los textos y punteros no traducidos permanecen intactos: SI")
    log("Bytes originales conservados salvo punteros traducidos: " + ("SI" if prefix_ok else "NO"))
    if check_only:
        log("MODO AUDITORÍA: no se creó ni modificó ningún archivo.")
        return 0

    builder = Builder(game)
    builder.set_leaf(TARGET_PATH, rebuilt)
    update_preload_copy(game, builder, TARGET_PATH[:2])
    replacements = builder.build()
    log("Archivos USRDIR reconstruidos: " + ", ".join(sorted(replacements)))

    bin_name = f"{TARGET_PATH[0]:04X}.BIN"
    if bin_name in replacements:
        old_bin, new_bin = game.bin(TARGET_PATH[0]), replacements[bin_name]
        log(f"{bin_name}: tamaño {len(old_bin)} -> {len(new_bin)}")
    if "FILETABLE.BIN" in replacements:
        log(f"FILETABLE.BIN: tamaño {len(game._orig_ft)} -> {len(replacements['FILETABLE.BIN'])}")

    iso_replacements = {
        "/PSP_GAME/USRDIR/" + name: data
        for name, data in replacements.items()
    }
    log("Reconstruyendo la ISO...")
    rebuild_iso(iso_in, iso_out, iso_replacements)
    log("ISO creada: " + iso_out)
    log(f"Tamaño ISO: {os.path.getsize(iso_in)} -> {os.path.getsize(iso_out)}")

    report_path = os.path.join(
        os.path.dirname(iso_out),
        "OneVision_people_append_only_report.txt",
    )
    with open(report_path, "w", encoding="utf-8") as report:
        report.write("FRENCHTOOLS - PEOPLE.XLC APPEND-ONLY CSV BATCH\n")
        report.write(f"CSV total rows: {total_rows}\n")
        report.write(f"Translated CSV rows: {translated_rows}\n")
        report.write(f"Changed cells: {len(changes)}\n")
        report.write(f"Unchanged translations: {len(unchanged)}\n")
        report.write(f"Original XLC bytes: {len(original)}\n")
        report.write(f"Result XLC bytes: {len(rebuilt)}\n")
        report.write(f"Appended bytes: {len(rebuilt)-len(original)}\n")
        report.write(f"Cells re-read: {verified_count}\n")
        report.write(f"Original prefix preserved except target pointers: {prefix_ok}\n")
        report.write(f"Updated preload: see console output\n")
    log("Informe: " + report_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log("ERROR: " + type(exc).__name__ + ": " + str(exc))
        traceback.print_exc()
        raise SystemExit(1)
