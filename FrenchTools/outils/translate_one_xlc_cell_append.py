#!/usr/bin/env python3
"""Apply one translated cell to an overlapping One Vision XLC using append-only storage.

Only the selected pointer cell is changed. All original resource bytes remain
in place; the translated string is appended at EOF and the selected 32-bit
pointer is redirected to it. Enclosing PAKD/BIN/FILETABLE and preload copies
are rebuilt with the FrenchTools pipeline.
"""
import os
import sys
import json
import struct
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tree import Game
from codec import decode, encode
from export import norm
from build import Builder
import span as spanmod
from isopatch import rebuild_iso


def log(lines, message):
    print(message, flush=True)
    lines.append(message)


def parse_overlap_xlc(data):
    if data[:4] != b"xlce" or len(data) < 16:
        raise ValueError("Firma/cabecera XLC no válida")
    n, do, es = struct.unpack_from("<III", data, 4)
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


def rebuild_append_one(original, info, row, col, translated_text, mode):
    cell = next(
        (c for c in info["cells"] if c["row"] == row and c["col"] == col),
        None,
    )
    if cell is None:
        raise ValueError(f"No existe celda de texto fila={row}, columna={col}")

    hdr, autowrap, body = norm(cell["text"])
    encoded_body, _ = encode(translated_text, autowrap=autowrap)
    prefix = spanmod.make_header(hdr, translated_text, mode) if hdr else b""
    new_string = prefix + encoded_body

    out = bytearray(original)
    new_offset = len(out)
    out += new_string + b"\0"
    struct.pack_into("<I", out, 16 + row * info["es"] + col, new_offset)

    return bytes(out), cell, new_offset, len(prefix), len(new_string)


def verify_rebuild(original, rebuilt, old_info, row, col, expected_text):
    new_info = parse_overlap_xlc(rebuilt)
    before = {(c["row"], c["col"]): c for c in old_info["cells"]}
    after = {(c["row"], c["col"]): c for c in new_info["cells"]}
    target = (row, col)
    if set(before) != set(after):
        raise RuntimeError("Cambió el conjunto de celdas de texto")

    text_mismatches = []
    pointer_mismatches = []
    for key, old_cell in before.items():
        new_cell = after[key]
        if key == target:
            _, _, actual_body = norm(new_cell["text"])
            if actual_body != expected_text:
                text_mismatches.append((key, "target text differs", actual_body))
            continue
        if new_cell["text"] != old_cell["text"]:
            text_mismatches.append((key, old_cell["text"], new_cell["text"]))
        if new_cell["offset"] != old_cell["offset"]:
            pointer_mismatches.append((key, old_cell["offset"], new_cell["offset"]))

    expected_prefix = bytearray(original)
    target_old = before[target]["offset"]
    new_target = after[target]["offset"]
    struct.pack_into("<I", expected_prefix, 16 + row * old_info["es"] + col, new_target)
    original_bytes_preserved = rebuilt[:len(original)] == bytes(expected_prefix)

    if text_mismatches or pointer_mismatches or not original_bytes_preserved:
        raise RuntimeError(
            "Verificación previa a ISO fallida: "
            f"text_mismatches={len(text_mismatches)}, "
            f"pointer_mismatches={len(pointer_mismatches)}, "
            f"original_bytes_preserved={original_bytes_preserved}"
        )

    return len(after), original_bytes_preserved, target_old, new_target


def update_preload_copy(game, builder, target_pair, lines):
    blob_dir = game.ft.dir(0)
    if not blob_dir["files"]:
        raise RuntimeError("FILETABLE dir 0000 no contiene archivos")
    first_file = blob_dir["files"][0]
    raw = game.bin(0)
    off = game.ft.offset(blob_dir, first_file)
    raw = raw[off:off + first_file["size"]]
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
            matches.append((did, fid, len(rebuilt_file)))

    if matches:
        new_blob = (
            struct.pack("<I", count)
            + b"".join(struct.pack("<II", *entry) for entry in entries)
            + b"".join(blocks)
        )
        builder.leaf_mods[(0, 0)] = {(): new_blob}
        for did, fid, size in matches:
            log(lines, f"PRELOAD: copia actualizada para {did}/{fid}, bytes={size}")
    else:
        log(lines, "PRELOAD: no hay copia de este archivo en el blob 0000.BIN")


def main():
    if len(sys.argv) not in (10, 11):
        print(
            'Uso: python -u translate_one_xlc_cell_append.py '
            '"<USRDIR>" "<ISO original>" "<ISO salida>" '
            '<dir_id> <file_id> <hoja> <fila> <columna> '
            '"<texto español>" [recompute|keep]',
            flush=True,
        )
        return 2

    usrdir, iso_in, iso_out = map(os.path.abspath, sys.argv[1:4])
    did, fid, leaf, row, col = (int(x, 0) for x in sys.argv[4:9])
    translated_text = sys.argv[9]
    mode = sys.argv[10] if len(sys.argv) == 11 else "recompute"
    target = (did, fid, leaf)

    if mode not in ("recompute", "keep"):
        raise ValueError("Modo debe ser recompute o keep")
    if not os.path.isdir(usrdir):
        raise FileNotFoundError("No existe USRDIR: " + usrdir)
    if not os.path.isfile(iso_in):
        raise FileNotFoundError("No existe ISO original: " + iso_in)
    if os.path.normcase(iso_in) == os.path.normcase(iso_out):
        raise ValueError("La ISO de salida debe tener un nombre diferente")
    if not translated_text:
        raise ValueError("El texto traducido está vacío")

    lines = []
    log(lines, "FRENCHTOOLS - ONE CELL APPEND-ONLY TRANSLATION")
    log(lines, "USRDIR: " + usrdir)
    log(lines, "ISO original: " + iso_in)
    log(lines, "ISO salida: " + iso_out)
    log(lines, "Recurso: " + "/".join(map(str, target)))
    log(lines, f"Celda: fila={row}, columna={col}")
    log(lines, "Modo span: " + mode)

    game = Game(usrdir)
    original = next((data for path, data in game.leaves() if path == target), None)
    if original is None:
        raise RuntimeError("No se encontró la hoja: " + repr(target))

    info = parse_overlap_xlc(original)
    old_text_count = len(info["cells"])
    rebuilt, cell, new_offset, prefix_size, new_string_size = rebuild_append_one(
        original, info, row, col, translated_text, mode
    )
    verified_count, preserved, old_offset, verified_new_offset = verify_rebuild(
        original, rebuilt, info, row, col, translated_text
    )

    log(lines, f"Columnas de punteros: {info['pointer_columns']}")
    log(lines, f"Celdas de texto: {old_text_count}")
    log(lines, "Texto original: " + cell["text"])
    log(lines, "Texto español: " + translated_text)
    log(lines, f"Puntero anterior: 0x{old_offset:X}")
    log(lines, f"Puntero nuevo: 0x{verified_new_offset:X}")
    log(lines, f"Cabecera span añadida: {prefix_size} bytes")
    log(lines, f"Cadena añadida: {new_string_size} bytes")
    log(lines, f"Tamaño hoja original/nuevo: {len(original)}/{len(rebuilt)}")
    log(lines, f"Bytes añadidos a la hoja: {len(rebuilt) - len(original)}")
    log(lines, f"Celdas verificadas tras relectura: {verified_count}")
    log(lines, "Todos los demás textos y punteros permanecen iguales: SI")
    log(lines, "Bytes originales preservados salvo el puntero elegido: " + ("SI" if preserved else "NO"))

    builder = Builder(game)
    builder.set_leaf(target, rebuilt)
    update_preload_copy(game, builder, (did, fid), lines)

    replacements = builder.build()
    log(lines, "Archivos USRDIR reconstruidos: " + ", ".join(sorted(replacements)))

    bin_name = f"{did:04X}.BIN"
    if bin_name in replacements:
        old_bin, new_bin = game.bin(did), replacements[bin_name]
        log(lines, f"{bin_name}: tamaño {len(old_bin)} -> {len(new_bin)}")
        common = min(len(old_bin), len(new_bin))
        differences = sum(a != b for a, b in zip(old_bin[:common], new_bin[:common])) + abs(len(old_bin) - len(new_bin))
        log(lines, f"{bin_name}: bytes distintos por posición = {differences}")

    if "FILETABLE.BIN" in replacements:
        old_ft, new_ft = game._orig_ft, replacements["FILETABLE.BIN"]
        common = min(len(old_ft), len(new_ft))
        differences = sum(a != b for a, b in zip(old_ft[:common], new_ft[:common])) + abs(len(old_ft) - len(new_ft))
        log(lines, f"FILETABLE.BIN: tamaño {len(old_ft)} -> {len(new_ft)}")
        log(lines, f"FILETABLE.BIN: bytes distintos por posición = {differences}")

    iso_replacements = {
        "/PSP_GAME/USRDIR/" + name: data
        for name, data in replacements.items()
    }
    log(lines, "Reconstruyendo la ISO...")
    rebuild_iso(iso_in, iso_out, iso_replacements)
    log(lines, "ISO creada: " + iso_out)
    log(lines, f"Tamaño ISO original/nueva: {os.path.getsize(iso_in)}/{os.path.getsize(iso_out)}")

    report_path = os.path.join(
        os.path.dirname(iso_out),
        "OneVision_one_cell_append_translation_report.txt",
    )
    with open(report_path, "w", encoding="utf-8") as report:
        report.write("\n".join(lines) + "\n")
    log(lines, "Informe: " + report_path)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("ERROR: " + type(exc).__name__ + ": " + str(exc), flush=True)
        traceback.print_exc()
        raise SystemExit(1)
