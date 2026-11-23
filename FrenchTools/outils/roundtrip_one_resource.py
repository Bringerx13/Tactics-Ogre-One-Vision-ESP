#!/usr/bin/env python3
"""Round-trip one selected XLC/EMES leaf and rebuild a One Vision ISO.

This is a diagnostic only: every decoded string is re-encoded unchanged.
No translation is introduced. The selected resource is repacked through
PAKD, BIN, FILETABLE and ISO using the FrenchTools pipeline.
"""
import os
import sys
import struct
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from codec import encode
from tree import Game, parse_emes, build_emes
from xlc import parse_xlc, build_xlc
from xlc_fixed import parse_xlc as parse_xlc_fixed, build_xlc as build_xlc_fixed
from build import Builder
from isopatch import rebuild_iso


def log(lines, message):
    print(message, flush=True)
    lines.append(message)


def changed_bytes(a, b):
    common = min(len(a), len(b))
    different = sum(x != y for x, y in zip(a[:common], b[:common]))
    return different + abs(len(a) - len(b))


def update_preload_copy(game, builder, lines):
    """Mirror apply_fixed.py: update any 0000.BIN preload copy of this file."""
    blob_dir = game.ft.dir(0)
    if not blob_dir["files"]:
        raise RuntimeError("FILETABLE dir 0000 no contiene archivos")
    first_file = blob_dir["files"][0]
    raw0 = game.bin(0)
    off0 = game.ft.offset(blob_dir, first_file)
    raw0 = raw0[off0:off0 + first_file["size"]]
    if len(raw0) < 4:
        raise RuntimeError("El blob preload de 0000.BIN está truncado")

    count = struct.unpack_from("<I", raw0, 0)[0]
    table_end = 4 + 8 * count
    if table_end > len(raw0):
        raise RuntimeError("Tabla interna del preload fuera de límites")

    entries = [
        list(struct.unpack_from("<II", raw0, 4 + 8 * i))
        for i in range(count)
    ]
    pos = table_end
    data_blocks = []
    for _file_id, size in entries:
        if pos + size > len(raw0):
            raise RuntimeError("Bloque del preload fuera de límites")
        data_blocks.append(raw0[pos:pos + size])
        pos += size

    changed = False
    for i, (file_id, _size) in enumerate(entries):
        did = file_id & 0xFFFF
        fid = file_id >> 16
        if (did, fid) in builder.leaf_mods:
            rebuilt = builder.file_bytes(did, fid)
            data_blocks[i] = rebuilt
            entries[i][1] = len(rebuilt)
            changed = True

    if changed:
        new_blob = (
            struct.pack("<I", count)
            + b"".join(struct.pack("<II", *entry) for entry in entries)
            + b"".join(data_blocks)
        )
        builder.leaf_mods[(0, 0)] = {(): new_blob}
        log(lines, "PRELOAD: copia del archivo actualizado en 0000.BIN")
    else:
        log(lines, "PRELOAD: no hay copia de este archivo en el blob 0000.BIN")


def main():
    if len(sys.argv) < 7:
        print(
            'Uso: python -u roundtrip_one_resource.py '
            '"<USRDIR>" "<ISO original>" "<ISO salida>" '
            '<dir_id_decimal> <file_id> <indice_hoja> [<indice_hoja> ...]',
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
    log(lines, "FRENCHTOOLS - ONE RESOURCE ROUNDTRIP")
    log(lines, "USRDIR: " + usrdir)
    log(lines, "ISO original: " + iso_in)
    log(lines, "ISO salida: " + iso_out)
    log(lines, "Recurso: " + "/".join(str(x) for x in target))
    log(lines, "Modo: reconstrucción idéntica; no se aplican traducciones.")

    game = Game(usrdir)
    selected = None
    for path, data in game.leaves():
        if path == target:
            selected = data
            break
    if selected is None:
        raise RuntimeError("No se encontró la hoja solicitada: " + repr(target))

    if selected[:4] == b"EMES":
        idmap, slots, tail, idpad = parse_emes(selected)
        if not slots:
            raise RuntimeError("El EMES seleccionado no contiene cadenas")
        encoded = [encode(slot["text"])[0] for slot in slots]
        rebuilt_leaf = build_emes(idmap, slots, tail, idpad, encoded)
        kind = "EMES"
        slots_count = len(slots)
    elif selected[:4] == b"xlce":
        if target == (700, 0, 3):
            info = parse_xlc_fixed(selected)
            build_fn = build_xlc_fixed
            kind = "XLC_FIXED"
        else:
            info = parse_xlc(selected)
            build_fn = build_xlc
            kind = "XLC"
        if not info:
            raise RuntimeError("La hoja tiene firma xlce, pero no se reconoce como XLC de texto")
        encoded = [encode(slot["text"])[0] for slot in info["slots"]]
        rebuilt_leaf = build_fn(selected, info, encoded)
        slots_count = len(info["slots"])
    else:
        raise RuntimeError(
            "La hoja seleccionada no es XLC ni EMES; firma=" + repr(selected[:8])
        )

    leaf_same = rebuilt_leaf == selected
    log(lines, f"Tipo: {kind}")
    log(lines, f"Cadenas reconstruidas: {slots_count}")
    log(lines, f"Hoja idéntica byte a byte: {'SI' if leaf_same else 'NO'}")
    log(lines, f"Tamaño original/nuevo de la hoja: {len(selected)}/{len(rebuilt_leaf)}")

    builder = Builder(game)
    builder.set_leaf(target, rebuilt_leaf)
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
        "OneVision_roundtrip_single_resource_report.txt",
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
