#!/usr/bin/env python3
"""In-memory self-test for append-only parsing/rebuilding of overlapping XLC pointers.

No files are modified. Every pointer cell is redirected to a private copy of
its decoded original bytes appended to the end of the resource. Then the
resource is parsed again and every cell is compared with its original text.
"""
import os
import sys
import struct
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tree import Game
from codec import decode


def parse_overlap_xlc(data):
    if data[:4] != b"xlce" or len(data) < 16:
        raise ValueError("Firma/cabecera XLC no válida")
    n, do, es = struct.unpack_from("<III", data, 4)
    if es < 4 or es % 4:
        raise ValueError(f"Tamaño de registro no compatible: {es}")
    hend = 16 + n * es
    if hend > len(data):
        raise ValueError("La tabla de registros supera el tamaño del recurso")

    pointer_columns = []
    cells = []
    for col in range(0, es, 4):
        values = [struct.unpack_from("<I", data, 16 + row * es + col)[0]
                  for row in range(n)]
        nonzero = [(row, value) for row, value in enumerate(values) if value]
        if not nonzero:
            continue
        if not all(hend <= value < len(data) for _, value in nonzero):
            continue
        decoded_cells = []
        try:
            for row, value in nonzero:
                text, end = decode(data, value)
                decoded_cells.append({
                    "row": row, "col": col, "offset": value,
                    "text": text, "end": end,
                    "raw": data[value:end - 1],
                })
        except Exception:
            continue
        pointer_columns.append(col)
        cells.extend(decoded_cells)

    if not pointer_columns:
        raise ValueError("No se detectaron columnas de punteros de texto")
    return {
        "n": n, "do": do, "es": es, "hend": hend,
        "pointer_columns": pointer_columns,
        "cells": sorted(cells, key=lambda x: (x["row"], x["col"])),
    }


def rebuild_append_only(original, info, replacements):
    """replacements[(row,col)] = encoded bytes without trailing NUL."""
    out = bytearray(original)
    changed = 0
    for cell in info["cells"]:
        key = (cell["row"], cell["col"])
        if key not in replacements:
            continue
        encoded = replacements[key]
        new_offset = len(out)
        if new_offset > 0xFFFFFFFF:
            raise OverflowError("El XLC superaría el límite de offsets de 32 bits")
        out += encoded + b"\0"
        struct.pack_into(
            "<I", out,
            16 + cell["row"] * info["es"] + cell["col"],
            new_offset,
        )
        changed += 1
    return bytes(out), changed


def main():
    if len(sys.argv) != 5:
        print('Uso: python audit_xlc_append_only.py "<USRDIR>" <dir> <file> <leaf>')
        return 2

    root = os.path.abspath(sys.argv[1])
    did, fid, leaf = (int(x, 0) for x in sys.argv[2:])
    target = (did, fid, leaf)
    game = Game(root)
    original = next(
        (data for path, data in game.leaves() if path == target),
        None,
    )
    if original is None:
        raise RuntimeError("No se encontró el recurso: " + repr(target))

    info = parse_overlap_xlc(original)
    counts = Counter()
    offsets = [cell["offset"] for cell in info["cells"]]
    for cell in info["cells"]:
        if cell["offset"] == info["hend"] or original[cell["offset"] - 1] == 0:
            counts["starts_after_null"] += 1
        else:
            counts["interior_or_nonstandard_start"] += 1

    # A private appended copy of each cell is the safest possible rewrite:
    # no original string bytes are moved, truncated, merged, or overwritten.
    replacements = {
        (cell["row"], cell["col"]): cell["raw"]
        for cell in info["cells"]
    }
    rebuilt, changed = rebuild_append_only(original, info, replacements)
    reparsed = parse_overlap_xlc(rebuilt)

    before = {
        (cell["row"], cell["col"]): cell["text"]
        for cell in info["cells"]
    }
    after = {
        (cell["row"], cell["col"]): cell["text"]
        for cell in reparsed["cells"]
    }
    mismatch = [
        key for key in before
        if key not in after or before[key] != after[key]
    ]
    missing = [key for key in before if key not in after]
    extra = [key for key in after if key not in before]
    changed_old_area = rebuilt[:len(original)] != original

    print("FRENCHTOOLS - APPEND-ONLY XLC SELF TEST")
    print("RECURSO:", "/".join(map(str, target)))
    print("BYTES ORIGINAL:", len(original))
    print("HEADER: n=%d es=%d hend=0x%X" % (info["n"], info["es"], info["hend"]))
    print("COLUMNAS DE PUNTEROS:", info["pointer_columns"])
    print("CELDAS DE TEXTO:", len(info["cells"]))
    print("OFFSETS UNICOS:", len(set(offsets)))
    print("INICIOS TRAS NUL:", counts["starts_after_null"])
    print("INICIOS INTERIORES/NO ESTANDAR:", counts["interior_or_nonstandard_start"])
    print("CELDAS REDIRIGIDAS A COPIAS:", changed)
    print("BYTES RESULTANTES EN MEMORIA:", len(rebuilt))
    print("BYTES AÑADIDOS:", len(rebuilt) - len(original))
    print("ZONA ORIGINAL CONSERVADA BYTE A BYTE:", "SI" if not changed_old_area else "NO")
    print("CELDAS FALTANTES TRAS RELECTURA:", len(missing))
    print("CELDAS ADICIONALES:", len(extra))
    print("TEXTOS DISTINTOS TRAS RELECTURA:", len(mismatch))
    print("RESULTADO:", "OK" if not mismatch and not missing and not extra and not changed_old_area else "FALLO")
    if mismatch[:20]:
        print("PRIMERAS DIFERENCIAS:", mismatch[:20])
    return 0 if not mismatch and not missing and not extra and not changed_old_area else 1


if __name__ == "__main__":
    raise SystemExit(main())
