#!/usr/bin/env python3
"""Read-only compatibility report for FrenchTools against a One Vision USRDIR."""
import os
import sys
import zlib
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from tree import Game, parse_emes
from xlc import parse_xlc as parse_xlc_normal
from xlc_fixed import parse_xlc as parse_xlc_fixed

# CRC32 values of the 16 BIN files extracted from One Vision/One_Vision.7z.
# The archive itself does not include FILETABLE.BIN.
OVERLAY_CRC32 = {
    "0000.BIN": "B7E73F83",
    "02BC.BIN": "F5EB08D6",
    "0384.BIN": "2C40082C",
    "0385.BIN": "EC270AC7",
    "0386.BIN": "1E72AAAF",
    "0387.BIN": "96B14349",
    "0388.BIN": "FB789608",
    "0389.BIN": "BB1B5E80",
    "038A.BIN": "66A6305C",
    "038B.BIN": "5BFE8C11",
    "038C.BIN": "C50BC40E",
    "038D.BIN": "6DD792C9",
    "03E8.BIN": "F0B165D5",
    "03E9.BIN": "6E7CF8E6",
    "09C4.BIN": "27993E95",
    "0A28.BIN": "811294FC",
}


def main():
    if len(sys.argv) != 2:
        print('Uso: python inspect_onevision_usrdir.py "E:\\\\ruta\\\\USRDIR"')
        return 2

    usrdir = os.path.abspath(sys.argv[1])
    ft_path = os.path.join(usrdir, "FILETABLE.BIN")
    if not os.path.isfile(ft_path):
        print("ERROR: no se encontró FILETABLE.BIN en:", usrdir)
        print("Extrae PSP_GAME/USRDIR completo desde One Vision.iso.")
        return 2

    report = []
    report.append("FRENCHTOOLS / ONE VISION - INFORME DE COMPATIBILIDAD")
    report.append("USRDIR: " + usrdir)
    report.append("")

    game = Game(usrdir)
    dirs_by_id = {d["id"]: d for d in game.ft.dirs}
    report.append(f"FILETABLE: {len(game.ft.dirs)} directorios; {sum(len(d['files']) for d in game.ft.dirs)} registros de archivo")
    report.append("")
    report.append("[COMPROBACION DE LOS BIN DEL PAQUETE ONE VISION]")
    missing_dirs = []
    for filename, expected_crc in OVERLAY_CRC32.items():
        path = os.path.join(usrdir, filename)
        dir_id = int(filename[:4], 16)
        present_in_table = dir_id in dirs_by_id
        if not os.path.isfile(path):
            status = "FALTA_BIN"
            actual_size = 0
            actual_crc = "--------"
        else:
            data = open(path, "rb").read()
            actual_size = len(data)
            actual_crc = f"{zlib.crc32(data) & 0xFFFFFFFF:08X}"
            status = "OK" if actual_crc == expected_crc else "CRC_DISTINTO"
        if not present_in_table:
            missing_dirs.append(dir_id)
        report.append(
            f"{filename}\t{status}\ttabla={present_in_table}\tbytes={actual_size}\tCRC_real={actual_crc}\tCRC_paquete={expected_crc}"
        )
    if missing_dirs:
        report.append("DIRECTORIOS_NO_PRESENTES_EN_FILETABLE: " + ", ".join(f"{x:04X}" for x in missing_dirs))
    report.append("")

    report.append("[DIRECTORIOS DEL FILETABLE]")
    for d in sorted(game.ft.dirs, key=lambda x: x["id"]):
        report.append(
            f"DIR {d['id']:04X}\tarchivos={len(d['files'])}\tenc={d['enc']}\tbs={d['bs']}\tbase=0x{d['base']:X}\tinst={d['inst']}"
        )
    report.append("")

    counts = Counter()
    by_dir = defaultdict(Counter)
    candidates = []
    parse_errors = []
    emes_rows = []

    try:
        leaves = game.leaves()
        for path, data in leaves:
            if len(path) < 2:
                continue
            did, fid = path[0], path[1]
            bucket = by_dir[did]
            counts["leaves"] += 1
            bucket["leaves"] += 1

            if data[:4] == b"xlce":
                counts["xlce_signature"] += 1
                bucket["xlce_signature"] += 1
                n = do = es = None
                if len(data) >= 16:
                    import struct
                    n, do, es = struct.unpack_from("<III", data, 4)
                normal_info = fixed_info = None
                normal_error = fixed_error = None
                try:
                    normal_info = parse_xlc_normal(data)
                except Exception as e:
                    normal_error = f"{type(e).__name__}: {e}"
                try:
                    fixed_info = parse_xlc_fixed(data)
                except Exception as e:
                    fixed_error = f"{type(e).__name__}: {e}"

                if normal_info is not None:
                    counts["xlc_normal_ok"] += 1
                    bucket["xlc_normal_ok"] += 1
                if fixed_info is not None:
                    counts["xlc_fixed_ok"] += 1
                    bucket["xlc_fixed_ok"] += 1
                    if fixed_info.get("aliases"):
                        counts["xlc_with_aliases"] += 1
                        bucket["xlc_with_aliases"] += 1

                state = "NORMAL_Y_FIXED_OK" if normal_info is None and fixed_info is not None else (
                    "AMBOS_OK" if normal_info is not None and fixed_info is not None else
                    "NINGUNO" if normal_info is None and fixed_info is None else "NORMAL_OK_FIXED_FALLA"
                )
                candidates.append(
                    f"{did:04X}.BIN\tfid={fid:04X}\tleaf={'/'.join(map(str, path[2:]))}\t"
                    f"{state}\tbytes={len(data)}\tn={n}\tes={es}\t"
                    f"normal_slots={len(normal_info['slots']) if normal_info else 0}\t"
                    f"fixed_slots={len(fixed_info['slots']) if fixed_info else 0}\t"
                    f"aliases={len(fixed_info.get('aliases', {})) if fixed_info else 0}\t"
                    f"normal_error={normal_error or '-'}\tfixed_error={fixed_error or '-'}"
                )
                if normal_error or fixed_error:
                    parse_errors.append(candidates[-1])

            elif data[:4] == b"EMES":
                counts["emes_signature"] += 1
                bucket["emes_signature"] += 1
                try:
                    idmap, slots, tail, idpad = parse_emes(data)
                    counts["emes_parse_ok"] += 1
                    bucket["emes_parse_ok"] += 1
                    emes_rows.append(
                        f"{did:04X}.BIN\tfid={fid:04X}\tleaf={'/'.join(map(str, path[2:]))}\t"
                        f"bytes={len(data)}\tids={len(idmap)}\tunique_texts={len(slots)}\ttail={len(tail)}"
                    )
                except Exception as e:
                    emes_rows.append(
                        f"{did:04X}.BIN\tfid={fid:04X}\tERROR={type(e).__name__}: {e}"
                    )

    except Exception as e:
        report.append("[ERROR RECORRIENDO RECURSOS]")
        report.append(f"{type(e).__name__}: {e}")
        report.append("")

    report.append("[RESUMEN DE RECURSOS]")
    for key in sorted(counts):
        report.append(f"{key}={counts[key]}")
    report.append("")
    report.append("[RECURSOS XLC]")
    report.extend(candidates or ["(ninguno)"])
    report.append("")
    report.append("[RECURSOS EMES]")
    report.extend(emes_rows or ["(ninguno)"])
    report.append("")
    report.append("[RESUMEN POR DIRECTORIO BIN]")
    for did in sorted(by_dir):
        report.append(f"{did:04X}.BIN\t" + "\t".join(f"{k}={v}" for k, v in sorted(by_dir[did].items())))
    report.append("")
    report.append("[ERRORES DE PARSEO XLC]")
    report.extend(parse_errors or ["(ninguno)"])

    out_path = os.path.join(os.path.dirname(usrdir), "OneVision_FrenchTools_informe.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")

    print("\n".join(report[:90]))
    print("")
    print("Informe completo guardado en:", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
