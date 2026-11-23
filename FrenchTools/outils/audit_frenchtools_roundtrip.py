#!/usr/bin/env python3
"""Read-only audit: does FrenchTools encode unchanged One Vision text byte-for-byte?"""
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from codec import encode
from tree import parse_emes
from xlc import parse_xlc


def inspect_file(path, counters, details, errors):
    try:
        data = open(path, "rb").read()
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
                if len(details) < 100:
                    details.append(
                        f"{path}\tXLC_ENCODE_ERROR\toff=0x{slot['off']:X}\t"
                        f"{type(exc).__name__}: {exc}\ttext={slot['text'][:160]!r}"
                    )
                continue
            if raw != rebuilt:
                counters["byte_mismatches"] += 1
                if len(details) < 100:
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
                if len(details) < 100:
                    details.append(
                        f"{path}\tEMES_ENCODE_ERROR\toff=0x{slot['start']:X}\t"
                        f"{type(exc).__name__}: {exc}\ttext={slot['text'][:160]!r}"
                    )
                continue
            if raw != rebuilt:
                counters["byte_mismatches"] += 1
                if len(details) < 100:
                    details.append(
                        f"{path}\tEMES_BYTE_MISMATCH\toff=0x{slot['start']:X}\t"
                        f"raw={raw.hex()}\tencoded={rebuilt.hex()}\ttext={slot['text'][:160]!r}"
                    )


def main():
    if len(sys.argv) != 2:
        print('Uso: python audit_frenchtools_roundtrip.py "E:\\\\Tactics ogre\\\\Gibbed_Extracted"')
        return 2

    root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(root):
        print("ERROR: no existe el directorio:", root)
        return 2

    counters = Counter()
    details = []
    errors = []
    scanned = 0

    for base, dirs, files in os.walk(root):
        dirs.sort()
        for name in sorted(files):
            path = os.path.join(base, name)
            try:
                with open(path, "rb") as f:
                    magic = f.read(4)
            except OSError as exc:
                errors.append(f"{path}\tREAD_ERROR\t{exc}")
                continue
            if magic not in (b"xlce", b"EMES"):
                continue
            scanned += 1
            inspect_file(path, counters, details, errors)

    report = [
        "FRENCHTOOLS - BYTE ROUNDTRIP AUDIT",
        "ROOT: " + root,
        f"FILES_WITH_TEXT_SIGNATURE={scanned}",
        "",
        "[COUNTS]",
    ]
    for key in sorted(counters):
        report.append(f"{key}={counters[key]}")
    report += ["", "[FIRST 100 BYTE MISMATCHES OR ENCODE ERRORS]"]
    report += details or ["(none)"]
    report += ["", "[PARSE / READ ERRORS]"]
    report += errors or ["(none)"]

    out_path = os.path.join(os.path.dirname(root), "FrenchTools_OneVision_roundtrip_audit.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print("\n".join(report[:45]))
    print("")
    print("Informe completo:", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
