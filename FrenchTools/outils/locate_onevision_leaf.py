#!/usr/bin/env python3
"""Locate a One Vision PAKD leaf by exact plain-text bytes; read-only."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tree import Game

def main():
    if len(sys.argv) < 3:
        print('Uso: python locate_onevision_leaf.py "<USRDIR>" "<texto exacto>" ["<otro texto>" ...]', flush=True)
        return 2
    root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(root):
        raise FileNotFoundError(root)
    needles = [s.encode("ascii") for s in sys.argv[2:]]
    game = Game(root)
    all_leaves = list(game.leaves())
    print("Hojas recorridas:", len(all_leaves), flush=True)
    for arg, needle in zip(sys.argv[2:], needles):
        print("\nBUSQUEDA:", arg, flush=True)
        hits = 0
        for path, data in all_leaves:
            off = data.find(needle)
            if off >= 0:
                hits += 1
                print("COORDENADA:", "/".join(map(str, path)),
                      "| HEX:", "/".join(f"{x:04X}" for x in path),
                      "| BYTES:", len(data), "| OFFSET:", off,
                      "| FIRMA:", repr(data[:4]), flush=True)
        print("COINCIDENCIAS:", hits, flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
