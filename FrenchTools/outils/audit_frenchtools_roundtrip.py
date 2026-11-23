#!/usr/bin/env python3
"""Read-only optimized byte roundtrip audit for FrenchTools XLC/EMES resources."""
import os
import sys
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from codec import encode
from tree import parse_emes
from xlc import parse_xlc


def log(message):
    print(message, flush=True)


def candidate_files(root):
    candidates = []
    all_files = 0
    last_report = time.time()
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            all_files += 1
            path = os.path.join(base, name)
            ext = os.path.splitext(name)[1].lower()
            if ext in (".xlc", ".emes"):
                candidates.append(path)
        now = time.time()
        if now - last_report >= 3:
            log(f"Buscando recursos... archivos localizados: {all_files:,}; candidatos XLC/EMES: {len(candidates):,}")
            last_report = now
    log(f"Búsqueda terminada: {all_files:,} archivos; {len(candidates):,} candidatos por extensión.")
    return candidates, all_files


def scan_by_magic(root):
    """Fallback for extracts where Gibbed did not preserve file extensions."""
    candidates = []
    visited = 0
    last_report = time.time()
    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            visited += 1
            path = os.path.join(base, name)
            try:
                with open(path, "rb") as f:
                    magic = f.read(4)
            except OSError:
                continue
            if magic in (b"xlce", b"EMES"):
                candidates.append(path)
            now = time.time()
            if now - last_report >= 3:
                log(f"Buscando por firma... {visited:,} archivos revisados; {len(candidates):,} recursos encontrados.")
                last_report = now
    log(f"Búsqueda por firma terminada: {visited:,} archivos; {len(candidates):,} recursos encontrados.")
    return candidates


def inspect_file(path, counters, details, errors):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as exc:
        errors.append(f"{path}\tREAD_ERROR\t{exc}")
        return

    if data[:4] == b"xlce":
        counters["xlce_signature"] += 1
        try:
            info = parse_xlc(data)
        except Exception as exc:
            counters["xlc_parse_error"] += 1
            errors.append(f"{path}\tXLC_PARSE_ERROR\t{type(exc).__name__}: {exc}")
            return
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
                        f"{path}\tXLC_ENCODE_ERROR\toff=0x{slot['off']:X}\t"
                        f"{type(exc).__name__}: {exc}\ttext={slot['text'][:160]!r}"
                    )
                continue
            if raw != rebuilt:
                counters["byte_mismatches"] += 1
                if len(details) < 200:
                    details.append(
                        f"{path}\tXLC_BYTE_MISMATCH\toff=0x{slot['off']:X}\t"
                        f"raw={raw.hex()}\tencoded={rebuilt.hex()}\ttext={slot['text'][:160]!r}"
                    )

    elif data[:4] == b"EMES":
        counters["emes_signature"] += 1
        try:
            idmap, slots, tail, idpad = parse_emes(data)
        except Exception as exc:
            counters["emes_parse_error"] += 1
            errors.append(f"{path}\tEMES_PARSE_ERROR\t{type(exc).__name__}: {exc}")
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
                        f"{path}\tEMES_ENCODE_ERROR\toff=0x{slot['start']:X}\t"
                        f"{type(exc).__name__}: {exc}\ttext={slot['text'][:160]!r}"
                    )
                continue
            if raw != rebuilt:
                counters["byte_mismatches"] += 1
                if len(details) < 200:
                    details.append(
                        f"{path}\tEMES_BYTE_MISMATCH\toff=0x{slot['start']:X}\t"
                        f"raw={raw.hex()}\tencoded={rebuilt.hex()}\ttext={slot['text'][:160]!r}"
                    )


def main():
    if len(sys.argv) != 2:
        print('Uso: python -u audit_frenchtools_roundtrip.py "E:\\\\Tactics ogre\\\\Gibbed_Extracted"')
        return 2

    root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(root):
        log("ERROR: no existe el directorio: " + root)
        return 2

    started = time.time()
    log("Auditoría iniciada. No se modificará ningún archivo.")
    log("Carpeta: " + root)
    log("Fase 1/3: buscando archivos XLC y EMES por extensión...")

    candidates, all_files = candidate_files(root)
    if not candidates:
        log("No se encontraron extensiones .xlc/.emes; se usará búsqueda por firma binaria.")
        candidates = scan_by_magic(root)

    counters = Counter()
    details = []
    errors = []
    total = len(candidates)

    log(f"Fase 2/3: analizando {total:,} recursos candidatos...")
    last_report = time.time()
    for index, path in enumerate(candidates, 1):
        inspect_file(path, counters, details, errors)
        now = time.time()
        if index == 1 or index % 25 == 0 or index == total or now - last_report >= 3:
            log(
                f"Progreso: {index:,}/{total:,} recursos | "
                f"XLC texto: {counters['xlc_text_files']:,} | "
                f"EMES: {counters['emes_text_files']:,} | "
                f"diferencias: {counters['byte_mismatches']:,} | "
                f"errores: {counters['encode_errors'] + counters['xlc_parse_error'] + counters['emes_parse_error']:,}"
            )
            last_report = now

    report = [
        "FRENCHTOOLS - BYTE ROUNDTRIP AUDIT",
        "ROOT: " + root,
        f"FILES_IN_TREE: {all_files}",
        f"CANDIDATE_FILES: {total}",
        f"ELAPSED_SECONDS: {time.time() - started:.1f}",
        "",
        "[COUNTS]",
    ]
    for key in sorted(counters):
        report.append(f"{key}={counters[key]}")
    report += ["", "[FIRST 200 BYTE MISMATCHES OR ENCODE ERRORS]"]
    report += details or ["(none)"]
    report += ["", "[PARSE / READ ERRORS]"]
    report += errors or ["(none)"]

    out_path = os.path.join(os.path.dirname(root), "FrenchTools_OneVision_roundtrip_audit.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    log("Fase 3/3: informe guardado.")
    log("Tiempo total: %.1f segundos" % (time.time() - started))
    log("Informe completo: " + out_path)
    log("Resumen: " + " | ".join(f"{k}={v}" for k, v in sorted(counters.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
