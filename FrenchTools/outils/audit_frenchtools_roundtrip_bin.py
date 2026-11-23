#!/usr/bin/env python3
"""Read-only byte roundtrip audit over One Vision FILETABLE/BIN/PAKD resources."""
import os
import sys
import time
import struct
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from codec import encode
from tree import Game, parse_emes
from xlc import parse_xlc as parse_xlc_normal
from xlc_fixed import parse_xlc as parse_xlc_fixed


def log(message):
    print(message, flush=True)


def audit_xlc(data, label, counters, details, errors):
    counters["xlce_signature"] += 1
    info = None
    try:
        info = parse_xlc_normal(data)
    except Exception as exc:
        counters["xlc_normal_parse_error"] += 1
        errors.append(f"{label}\tXLC_NORMAL_PARSE_ERROR\t{type(exc).__name__}: {exc}")

    if info is None:
        try:
            info = parse_xlc_fixed(data)
            if info is not None:
                counters["xlc_fixed_fallback"] += 1
        except Exception as exc:
            counters["xlc_fixed_parse_error"] += 1
            errors.append(f"{label}\tXLC_FIXED_PARSE_ERROR\t{type(exc).__name__}: {exc}")

    if info is None:
        counters["xlc_not_text"] += 1
        return

    counters["xlc_text_files"] += 1
    counters["xlc_slots"] += len(info["slots"])
    for slot in info["slots"]:
        raw = data[slot["off"]:slot["end"] - 1]
        try:
            rebuilt, _ = encode(slot["text"])
        except Exception as exc:
            counters["encode_errors"] += 1
            if len(details) < 200:
                details.append(
                    f"{label}\tXLC_ENCODE_ERROR\toff=0x{slot['off']:X}\t"
                    f"{type(exc).__name__}: {exc}\ttext={slot['text'][:140]!r}"
                )
            continue
        if raw != rebuilt:
            counters["byte_mismatches"] += 1
            if len(details) < 200:
                details.append(
                    f"{label}\tXLC_BYTE_MISMATCH\toff=0x{slot['off']:X}\t"
                    f"raw={raw.hex()}\tencoded={rebuilt.hex()}\ttext={slot['text'][:140]!r}"
                )


def audit_emes(data, label, counters, details, errors):
    counters["emes_signature"] += 1
    try:
        idmap, slots, tail, idpad = parse_emes(data)
    except Exception as exc:
        counters["emes_parse_error"] += 1
        errors.append(f"{label}\tEMES_PARSE_ERROR\t{type(exc).__name__}: {exc}")
        return

    counters["emes_text_files"] += 1
    counters["emes_slots"] += len(slots)
    for slot in slots:
        raw = data[slot["start"]:slot["end"] - 1]
        try:
            rebuilt, _ = encode(slot["text"])
        except Exception as exc:
            counters["encode_errors"] += 1
            if len(details) < 200:
                details.append(
                    f"{label}\tEMES_ENCODE_ERROR\toff=0x{slot['start']:X}\t"
                    f"{type(exc).__name__}: {exc}\ttext={slot['text'][:140]!r}"
                )
            continue
        if raw != rebuilt:
            counters["byte_mismatches"] += 1
            if len(details) < 200:
                details.append(
                    f"{label}\tEMES_BYTE_MISMATCH\toff=0x{slot['start']:X}\t"
                    f"raw={raw.hex()}\tencoded={rebuilt.hex()}\ttext={slot['text'][:140]!r}"
                )


def main():
    if len(sys.argv) != 2:
        log('Uso: python -u audit_frenchtools_roundtrip_bin.py "E:\\\\Tactics ogre\\\\USRDIR_OneVision"')
        return 2

    root = os.path.abspath(sys.argv[1])
    ft_path = os.path.join(root, "FILETABLE.BIN")
    if not os.path.isfile(ft_path):
        log("ERROR: falta FILETABLE.BIN en " + root)
        log("Este programa necesita la carpeta USRDIR completa extraída de la ISO.")
        return 2

    started = time.time()
    log("FRENCHTOOLS - BYTE ROUNDTRIP AUDIT (BIN)")
    log("ROOT: " + root)
    log("Modo: solo lectura; no modifica archivos.")
    log("Leyendo FILETABLE.BIN...")

    try:
        game = Game(root)
    except Exception as exc:
        log(f"ERROR al leer FILETABLE/BIN: {type(exc).__name__}: {exc}")
        return 1

    top_files = sum(len(d["files"]) for d in game.ft.dirs)
    log(f"FILETABLE cargado: {len(game.ft.dirs)} directorios; {top_files:,} archivos raíz.")
    log("Recorriendo los contenedores BIN y PAKD. El avance se mostrará cada 500 hojas.")

    counters = Counter()
    details = []
    errors = []
    leaves = 0
    resources = 0
    last_report = time.time()

    try:
        for path, data in game.leaves():
            leaves += 1
            did, fid = path[0], path[1]
            label = f"{did:04X}.BIN/fid={fid:04X}/" + "/".join(map(str, path[2:]))

            if data[:4] == b"xlce":
                resources += 1
                audit_xlc(data, label, counters, details, errors)
            elif data[:4] == b"EMES":
                resources += 1
                audit_emes(data, label, counters, details, errors)

            now = time.time()
            if leaves == 1 or leaves % 500 == 0 or now - last_report >= 3:
                log(
                    f"Hojas recorridas: {leaves:,} | recursos de texto: {resources:,} | "
                    f"XLC texto: {counters['xlc_text_files']:,} | EMES: {counters['emes_text_files']:,} | "
                    f"diferencias: {counters['byte_mismatches']:,}"
                )
                last_report = now

    except Exception as exc:
        errors.append(f"TREE_SCAN_ERROR\t{type(exc).__name__}: {exc}")
        log(f"ERROR durante el recorrido: {type(exc).__name__}: {exc}")

    elapsed = time.time() - started
    report = [
        "FRENCHTOOLS - BYTE ROUNDTRIP AUDIT (BIN)",
        "ROOT: " + root,
        f"DIRECTORIES: {len(game.ft.dirs)}",
        f"TOP_LEVEL_FILES: {top_files}",
        f"LEAVES_SCANNED: {leaves}",
        f"TEXT_RESOURCES: {resources}",
        f"ELAPSED_SECONDS: {elapsed:.1f}",
        "",
        "[COUNTS]",
    ]
    for key in sorted(counters):
        report.append(f"{key}={counters[key]}")
    report += ["", "[FIRST 200 BYTE MISMATCHES OR ENCODE ERRORS]"]
    report += details or ["(none)"]
    report += ["", "[PARSE / TREE ERRORS]"]
    report += errors or ["(none)"]

    out_path = os.path.join(os.path.dirname(root), "FrenchTools_OneVision_roundtrip_audit_BIN.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    log("Auditoría terminada.")
    log(f"Hojas recorridas: {leaves:,}; recursos de texto: {resources:,}.")
    log(f"Tiempo total: {elapsed:.1f} segundos.")
    log("Informe: " + out_path)
    log("Resumen: " + " | ".join(f"{k}={v}" for k, v in sorted(counters.items())))
    return 0 if not any(k.endswith("parse_error") for k in counters) else 1


if __name__ == "__main__":
    raise SystemExit(main())
