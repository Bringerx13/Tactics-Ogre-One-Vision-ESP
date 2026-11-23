#!/usr/bin/env python3
"""Read-only structural diagnostic for one unsupported xlce leaf."""
import os, sys, struct
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tree import Game
from codec import decode, DecodeError

def hx(vals):
    return " ".join(f"{v:08X}" for v in vals)

def main():
    if len(sys.argv) != 5:
        print('Uso: python inspect_unknown_xlc.py "<USRDIR>" <dir> <file> <leaf>')
        return 2
    root = os.path.abspath(sys.argv[1])
    did, fid, leaf = (int(x, 0) for x in sys.argv[2:])
    game = Game(root)
    target = (did, fid, leaf)
    selected = None
    for path, data in game.leaves():
        if path == target:
            selected = data
            break
    if selected is None:
        raise RuntimeError("No se encontró la hoja " + repr(target))
    b = selected
    print("RECURSO:", "/".join(map(str, target)), flush=True)
    print("BYTES:", len(b), "FIRMA:", repr(b[:4]), flush=True)
    if len(b) < 16 or b[:4] != b"xlce":
        raise RuntimeError("La hoja no tiene cabecera xlce")
    n, do, es = struct.unpack_from("<III", b, 4)
    hend = 16 + n * es
    print(f"HEADER: n={n} do={do} (0x{do:X}) es={es} hend={hend} (0x{hend:X})", flush=True)
    print("PRIMEROS 64 BYTES:", b[:64].hex(" "), flush=True)
    print("ULTIMOS 32 BYTES:", b[-32:].hex(" "), flush=True)
    if es < 4 or hend > len(b):
        print("CABECERA/TABLA FUERA DE RANGO", flush=True)
        return 1

    rows = [struct.unpack_from("<" + "I" * (es // 4), b, 16 + r * es)
            for r in range(n)]
    for c in range(es // 4):
        vals = [row[c] for row in rows]
        nz = [v for v in vals if v]
        inside = [v for v in nz if hend <= v < len(b)]
        prev0 = [v for v in inside if v == hend or b[v-1] == 0]
        at0 = [v for v in inside if b[v] == 0]
        decok = []
        for v in prev0:
            try:
                decode(b, v)
                decok.append(v)
            except Exception:
                pass
        print(f"COL {c*4:02X}: nonzero={len(nz)} in_file={len(inside)} prev_zero={len(prev0)} at_zero={len(at0)} decode_ok={len(decok)}",
              flush=True)
        print("  FIRST:", hx(nz[:12]), flush=True)
        bad = [v for v in nz if v not in prev0]
        if bad:
            print("  FIRST_NOT_STANDARD_PTR:", hx(bad[:8]), flush=True)
        if decok:
            for v in decok[:4]:
                try:
                    s, end = decode(b, v)
                    print(f"  DECODE @{v} end={end}: {s[:100]!r}", flush=True)
                except Exception:
                    pass

    print("\nPRIMEROS 12 REGISTROS (DWORDS):", flush=True)
    for r in range(min(n, 12)):
        print(f"  ROW {r:04X}:", hx(rows[r]), flush=True)

    needles = [
        b"An INDIRECT spell that SHACKLES a SINGLE TARGET by binding it with molten rock.",
        b"A spell that deals ICE damage in an AREA and can inflict STOP. Usable only on SNOW and ICE tiles."
    ]
    for needle in needles:
        pos = b.find(needle)
        print(f"\nTEXT offset={pos} len={len(needle)} text={needle.decode('ascii')}", flush=True)
        if pos >= 0:
            lo, hi = max(0, pos-32), min(len(b), pos+len(needle)+32)
            print("  CONTEXT:", b[lo:hi].hex(" "), flush=True)
            for c in range(es // 4):
                hits = [(r, rows[r][c]) for r in range(n)
                        if rows[r][c] in (pos, pos-1, pos-2, pos-4, pos-hend, pos-hend-1)]
                if hits:
                    print(f"  POINTER_MATCH COL {c*4:02X}:", hits[:12], flush=True)
            for base_name, base in (("absolute", 0), ("header_end", hend), ("do", do), ("do_plus_hend", do+hend)):
                val = pos - base
                hits = [(r, c*4) for r in range(n) for c in range(es//4) if rows[r][c] == val]
                if hits:
                    print(f"  RELATIVE_MATCH {base_name} value=0x{val:X}:", hits[:12], flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
