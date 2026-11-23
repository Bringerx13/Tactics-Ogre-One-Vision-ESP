#!/usr/bin/env python3
"""Identity round-trip of one raw One Vision leaf, bypassing XLC/EMES parsing.

This diagnostic does NOT decode or re-encode strings. It reinserts the exact
original leaf bytes, rebuilds its enclosing PAKD containers and BIN, updates
a matching 0000.BIN preload copy if present, then rebuilds the ISO.
"""
import os
import sys
import struct
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tree import Game
from build import Builder
from isopatch import rebuild_iso


def changed_bytes(a, b):
    common = min(len(a), len(b))
    different = sum(x != y for x, y in zip(a[:common], b[:common]))
    return different + abs(len(a) - len(b))


def log(lines, message):
    print(message, flush=True)
    lines.append(message)


def update_preload_copy(game, builder, lines):
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

    changed = False
    matches = []
    for i, (file_id, _size) in enumerate(entries):
        did = file_id & 0xFFFF
        fid = file_id >> 16
        if (did, fid) == tuple(next(iter(builder.leaf_mods))[:2]):
            rebuilt = builder.file_bytes(did, fid)
            blocks[i] = rebuilt
            entries[i][1] = len(rebuilt)
            matches.append((did, fid, len(rebuilt)))
            changed = True

    if changed:
        new_blob = (
            struct.pack("<I", count)
            + b"".join(struct.pack("<II", *entry) for entry in entries)
            + b"".join(blocks)
        )
        builder.leaf_mods[(0, 0)] = {(): new_blob}
        log(lines, "PRELOAD: copia actualizada en 0000.BIN")
        for did, fid, size in matches:
            log(lines, f"PRELOAD: recurso {did}/{fid}, bytes={size}")
    else:
        log(lines, "PRELOAD: no hay copia de este archivo en el blob 0000.BIN")


def main():
    if len(sys.argv) < 7:
        print(
            'Uso: python -u roundtrip_one_resource_raw.py '
            '"<USRDIR>" "<ISO original>" "<ISO salida>" '
            '<dir_id> <file_id> <indice_hoja> [<indice_hoja> ...]',
            flush=True,
        )
        return 2

    usrdir, iso_in, iso_out = map(os.path.abspath, sys.argv[1:4])
    did = int(sys.argv[4], 0)
    fid = int(sys.argv[5], 0)
    subpath = tuple(int(x, 0) for x in sys.argv[6:])
    target = (did, fid) + subpath

    if not os.path.isdir(usrdir):
        raise FileNotFoundError("No existe USRDIR: " + usrdir)
    if not os.path.isfile(iso_in):
        raise FileNotFoundError("No existe ISO original: " + iso_in)
    if os.path.normcase(iso_in) == os.path.normcase(iso_out):
        raise ValueError("La ISO de salida debe tener un nombre diferente")

    lines = []
    log(lines, "FRENCHTOOLS - ONE RESOURCE RAW IDENTITY ROUNDTRIP")
    log(lines, "USRDIR: " + usrdir)
    log(lines, "ISO original: " + iso_in)
    log(lines, "ISO salida: " + iso_out)
    log(lines, "Recurso: " + "/".join(str(x) for x in target))
    log(lines, "Modo: se conservan los bytes originales; sin parsear ni traducir.")

    game = Game(usrdir)
    selected = None
    for path, data in game.leaves():
        if path == target:
            selected = data
            break
    if selected is None:
        raise RuntimeError("No se encontró la hoja solicitada: " + repr(target))

    log(lines, f"Firma: {selected[:4]!r}")
    log(lines, f"Hoja original: {len(selected)} bytes")
    log(lines, "Hoja reinsertada: los mismos bytes originales")
    log(lines, "Hoja idéntica byte a byte: SI")

    builder = Builder(game)
    builder.set_leaf(target, selected)
    update_preload_copy(game, builder, lines)

    replacements = builder.build()
    log(lines, "Archivos USRDIR reconstruidos: " + ", ".join(sorted(replacements)))

    bin_name = f"{did:04X}.BIN"
    if bin_name in replacements:
        old_bin = game.bin(did)
        new_bin = replacements[bin_name]
        log(lines, f"{bin_name}: tamaño {len(old_bin)} -> {len(new_bin)}")
        log(lines, f"{bin_name}: bytes distintos = {changed_bytes(old_bin, new_bin)}")

    old_ft = game._orig_ft
    new_ft = replacements.get("FILETABLE.BIN")
    if new_ft is not None:
        log(lines, f"FILETABLE.BIN: tamaño {len(old_ft)} -> {len(new_ft)}")
        log(lines, f"FILETABLE.BIN: bytes distintos = {changed_bytes(old_ft, new_ft)}")

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
        "OneVision_roundtrip_single_resource_raw_report.txt",
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
