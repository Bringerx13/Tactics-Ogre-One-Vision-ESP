#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inventario de cadenas en todos los BIN de Tactics Ogre PSP (versión con progreso).

- Lee todos los BIN de PSP_GAME/USRDIR a partir de FILETABLE.BIN.
- Escanea las áreas completas de cada BIN y las hojas PAKD.
- Interpreta XLC/EMES cuando su estructura es reconocida.
- Examina las copias precargadas dentro de 0000.BIN.
- Busca candidatos ASCII, UTF-16LE y mediante el codec del juego.
- Compara cada candidato con texto_ingles del CSV.

Los informes se escriben de forma incremental. Ctrl+C conserva lo ya inventariado.
No modifica la ISO, BIN, Gibbed ni CSV.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import re
import sys
import tempfile
import time
from pathlib import Path
from collections import Counter
from typing import Any

ASCII_RUN = re.compile(rb"[\x20-\x7E]{6,}")
UTF16_RUN = re.compile(rb"(?:[\x20-\x7E]\x00){6,}")
TAG_RE = re.compile(r"\{[^{}]*\}")
SPAN_RE = re.compile(r"^\{span [^{}]*\}", re.I)
HEADERS = [
    "origen", "bin_dir_id", "bin_file_id", "subruta_pakd", "ubicacion_numerica",
    "ruta_gibbed", "offset_hex", "longitud_bytes", "codificacion", "tipo_detectado",
    "esta_en_csv", "texto", "hex_muestra"
]


def log(message: str) -> None:
    print(message, flush=True)


def norm_text(s: str) -> str:
    s = s.replace("{{", "{").replace("}}", "}")
    s = SPAN_RE.sub("", s)
    s = s.replace("{w}", "").replace("\\n", " ").replace("\n", " ")
    s = TAG_RE.sub(" ", s).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", s, flags=re.UNICODE).split())


def read_csv_english(path: Path | None) -> set[str]:
    if path is None:
        return set()
    if not path.is_file():
        raise FileNotFoundError(f"No existe el CSV: {path}")
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:8192]
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = ","
    values: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames or "texto_ingles" not in reader.fieldnames:
            raise ValueError(f"No se encontró texto_ingles. Encabezados: {reader.fieldnames}")
        for row in reader:
            value = (row.get("texto_ingles") or "").strip()
            if value:
                normalized = norm_text(value)
                if normalized:
                    values.add(normalized)
    return values


def is_text_candidate(s: str, min_letters: int = 4) -> bool:
    plain = s.replace("{{", "{").replace("}}", "}")
    plain = TAG_RE.sub(" ", plain).replace("\\n", " ").replace("\n", " ")
    letters = sum(ch.isalpha() for ch in plain)
    visible = sum(ch.isalnum() for ch in plain)
    words = re.findall(r"[A-Za-zÀ-ÿ]{2,}", plain)
    if letters < min_letters or visible < min_letters:
        return False
    if letters / max(visible, 1) < 0.45:
        return False
    unknown = len(re.findall(r"\{b[0-9A-Fa-f]{2}\}", s))
    if unknown > max(2, letters // 2):
        return False
    return bool(words)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_reverse_map(gibbed_root: Path | None, base_dir: Path) -> dict[tuple[int, ...], str]:
    if gibbed_root is None:
        return {}
    candidates = [
        base_dir / "Correcciones" / "insertar_traduccion_tactics_ogre_espacios_v3.py",
        base_dir / "insertar_traduccion_tactics_ogre_espacios_v3.py",
    ]
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("inventory_v2_inserter", path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            return {tuple(loc): name for name, loc in module.build_gibbed_path_map(gibbed_root).items()}
    log("AVISO: no pude cargar el insertador para asociar rutas Gibbed; usaré ubicaciones numéricas.")
    return {}


def extract_usrdir(iso_path: Path, out_dir: Path, tools_dir: Path) -> int:
    sys.path.insert(0, str(tools_dir))
    from isopatch import walk_iso, SECTOR
    out_dir.mkdir(parents=True, exist_ok=True)
    with iso_path.open("rb") as source:
        files = walk_iso(source)
        targets = [(name, meta) for name, meta in files.items() if name.startswith("/PSP_GAME/USRDIR/")]
        log(f"Archivos USRDIR encontrados en ISO: {len(targets)}")
        for index, (iso_name, (_record, extent, size)) in enumerate(targets, 1):
            source.seek(extent * SECTOR)
            target = out_dir / Path(iso_name).name
            data = source.read(size)
            if len(data) != size:
                raise RuntimeError(f"Lectura incompleta de {iso_name}: {len(data)}/{size}")
            target.write_bytes(data)
            if index == 1 or index % 5 == 0 or index == len(targets):
                log(f"  Extracción USRDIR: {index}/{len(targets)} | {target.name} | {size:,} bytes")
    if not (out_dir / "FILETABLE.BIN").is_file():
        raise RuntimeError("La ISO no contiene PSP_GAME/USRDIR/FILETABLE.BIN.")
    return len(targets)


def decode_game_candidates(data: bytes, game_decode, b2u: dict[int, str],
                           max_text_len: int = 4096, max_attempts: int = 1200):
    """Prueba el codec en inicios plausibles, no en cada byte del recurso.

    Los inicios se limitan a comienzos de bloque/cadena o bytes posteriores a
    controles/datos no textuales. Cada intento queda limitado en longitud.
    """
    n = len(data)
    candidates: list[int] = []
    allowed_controls = (0xFC, 0xFD, 0xFF)
    ordinary = set(" '.,!?-:;()[]\"/\u2019")
    for i, value in enumerate(data):
        if value not in b2u and value not in allowed_controls:
            continue
        if i == 0:
            candidates.append(i)
            continue
        prev = data[i - 1]
        prev_char = b2u.get(prev, "")
        prev_is_wordish = bool(prev_char) and (prev_char.isalnum() or prev_char in ordinary)
        if prev == 0 or prev in allowed_controls or prev < 0x20 or prev not in b2u or not prev_is_wordish:
            candidates.append(i)
        if len(candidates) >= max_attempts:
            break
    accepted_until = -1
    for offset in candidates:
        if offset < accepted_until or offset >= n:
            continue
        window = data[offset:min(n, offset + max_text_len)]
        try:
            text, end = game_decode(window, 0)
        except Exception:
            continue
        if end <= 0 or end > len(window):
            continue
        if is_text_candidate(text, min_letters=5):
            yield offset, end, text
            accepted_until = offset + end


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--iso", required=True, type=Path)
    ap.add_argument("--french-tools", required=True, type=Path)
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--gibbed-root", type=Path, default=None)
    ap.add_argument("--output-dir", type=Path, default=Path("."))
    ap.add_argument("--prefix", default="inventario_textos_v2")
    ap.add_argument("--min-ascii", type=int, default=6)
    ap.add_argument("--progress-every", type=int, default=25,
                    help="Mostrar avance cada N recursos analizados (por defecto 25).")
    ap.add_argument("--max-decode-attempts", type=int, default=1200,
                    help="Máximo de inicios de codec probados por hoja (por defecto 1200).")
    ap.add_argument("--skip-full-bin-scan", action="store_true",
                    help="Omite el escaneo de bytes de BIN completos; acelera, pero puede ocultar cadenas fuera de entradas FILETABLE.")
    args = ap.parse_args()

    start_time = time.time()
    iso = args.iso.expanduser().resolve()
    tools_dir = args.french_tools.expanduser().resolve() / "outils"
    out_dir = args.output_dir.expanduser().resolve()
    if not iso.is_file():
        raise SystemExit(f"No existe la ISO: {iso}")
    if not tools_dir.is_dir():
        raise SystemExit(f"No existe FrenchTools\\outils: {tools_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    all_path = out_dir / f"{args.prefix}_todas_las_cadenas.tsv"
    missing_path = out_dir / f"{args.prefix}_no_en_csv.tsv"
    known_path = out_dir / f"{args.prefix}_xlc_emes.tsv"
    summary_path = out_dir / f"{args.prefix}_resumen.txt"
    progress_path = out_dir / f"{args.prefix}_progreso.log"

    csv_norm = read_csv_english(args.csv.expanduser().resolve()) if args.csv else set()
    reverse_map = load_reverse_map(args.gibbed_root.expanduser().resolve() if args.gibbed_root else None, iso.parent)

    sys.path.insert(0, str(tools_dir))
    from tree import Game, parse_emes
    from pakd import is_pakd, parse_pakd
    from xlc import parse_xlc
    from codec import decode as game_decode, B2U

    all_count = missing_count = known_count = leaf_count = resource_count = 0
    duplicates = 0
    errors = Counter()
    source_counts = Counter()
    seen: set[tuple[Any, ...]] = set()

    with all_path.open("w", encoding="utf-8-sig", newline="") as all_f, \
         missing_path.open("w", encoding="utf-8-sig", newline="") as missing_f, \
         known_path.open("w", encoding="utf-8-sig", newline="") as known_f, \
         progress_path.open("w", encoding="utf-8", newline="") as progress_f:
        all_w = csv.DictWriter(all_f, fieldnames=HEADERS, delimiter="\t", lineterminator="\n")
        missing_w = csv.DictWriter(missing_f, fieldnames=HEADERS, delimiter="\t", lineterminator="\n")
        known_w = csv.DictWriter(known_f, fieldnames=HEADERS, delimiter="\t", lineterminator="\n")
        for writer in (all_w, missing_w, known_w):
            writer.writeheader()

        def progress(message: str) -> None:
            log(message)
            progress_f.write(message + "\n")
            progress_f.flush()

        def add_row(source: str, did: int, fid: int, subpath: tuple[int, ...], rel: str,
                    offset: int, length: int, encoding: str, kind: str, text: str, raw: bytes):
            nonlocal all_count, missing_count, known_count, duplicates
            text = text.strip("\x00\r\n\t ")
            normalized = norm_text(text)
            if not normalized:
                return
            location = "/".join(map(str, (did, fid) + subpath))
            key = (source, location, offset, normalized, encoding)
            if key in seen:
                duplicates += 1
                return
            seen.add(key)
            in_csv = normalized in csv_norm if csv_norm else None
            row = {
                "origen": source,
                "bin_dir_id": did,
                "bin_file_id": fid,
                "subruta_pakd": "/".join(map(str, subpath)),
                "ubicacion_numerica": location,
                "ruta_gibbed": rel,
                "offset_hex": f"0x{offset:X}",
                "longitud_bytes": length,
                "codificacion": encoding,
                "tipo_detectado": kind,
                "esta_en_csv": "SI" if in_csv is True else ("NO" if in_csv is False else "NO_COMPARADO"),
                "texto": text,
                "hex_muestra": raw[:96].hex(" "),
            }
            all_w.writerow(row)
            all_count += 1
            source_counts[source] += 1
            if in_csv is False:
                missing_w.writerow(row)
                missing_count += 1
            if kind in ("XLC", "EMES"):
                known_w.writerow(row)
                known_count += 1
            if all_count % 250 == 0:
                all_f.flush(); missing_f.flush(); known_f.flush()

        def scan_raw(source: str, did: int, fid: int, subpath: tuple[int, ...],
                     rel: str, data: bytes, scan_codec: bool = True):
            nonlocal resource_count
            # Cadenas ASCII.
            for match in ASCII_RUN.finditer(data):
                if len(match.group()) < args.min_ascii:
                    continue
                value = match.group().decode("ascii", errors="replace").strip()
                if is_text_candidate(value, min_letters=4):
                    add_row(source, did, fid, subpath, rel, match.start(), len(match.group()),
                            "ASCII", "CADENA_BRUTA", value, match.group())
            # Cadenas UTF-16LE con caracteres ASCII.
            for match in UTF16_RUN.finditer(data):
                try:
                    value = match.group().decode("utf-16le", errors="strict").strip()
                except UnicodeDecodeError:
                    continue
                if is_text_candidate(value, min_letters=4):
                    add_row(source, did, fid, subpath, rel, match.start(), len(match.group()),
                            "UTF-16LE", "CADENA_BRUTA", value, match.group())
            # Codec del juego solo en hojas/fragmentos, con inicios plausibles acotados.
            if scan_codec:
                for offset, length, value in decode_game_candidates(
                    data, game_decode, B2U, max_attempts=args.max_decode_attempts
                ):
                    raw = data[offset:min(len(data), offset + min(length, 96))]
                    add_row(source, did, fid, subpath, rel, offset, length,
                            "CODEC_TACTICS_OGRE", "CANDIDATO_CODEC", value, raw)
            resource_count += 1
            if resource_count % max(1, args.progress_every) == 0:
                progress(f"  Recursos/fragmentos examinados: {resource_count:,} | candidatos: {all_count:,} | faltan en CSV: {missing_count:,}")

        def walk_blob(source: str, did: int, fid: int, data: bytes,
                      path: tuple[int, ...] = ()):
            nonlocal leaf_count
            if is_pakd(data):
                try:
                    entries, _has_ids, total = parse_pakd(data)
                except Exception as exc:
                    errors["PAKD"] += 1
                    scan_raw(source + "_PAKD_NO_PARSE", did, fid, path,
                             reverse_map.get((did, fid) + path, ""), data)
                    return
                for index, (_rawid, child) in enumerate(entries):
                    walk_blob(source, did, fid, child, path + (index,))
                if 0 <= total < len(data):
                    tail = data[total:]
                    if tail:
                        scan_raw(source + "_PAKD_TAIL", did, fid, path,
                                 reverse_map.get((did, fid) + path, ""), tail, scan_codec=False)
                return

            leaf_count += 1
            rel = reverse_map.get((did, fid) + path, "")
            # Texto estructurado: registrar cada slot por separado con offsets exactos.
            if data[:4] == b"xlce":
                try:
                    info = parse_xlc(data)
                    if info:
                        for slot in info["slots"]:
                            add_row(source, did, fid, path, rel, int(slot["off"]),
                                    int(slot["end"] - slot["off"]), "CODEC_TACTICS_OGRE",
                                    "XLC", slot["text"], data[slot["off"]:slot["end"]])
                    else:
                        errors["XLC_SIN_CADENAS"] += 1
                except Exception:
                    errors["XLC_PARSE"] += 1
            elif data[:4] == b"EMES":
                try:
                    _idmap, slots, _tail, _idpad = parse_emes(data)
                    for slot in slots:
                        add_row(source, did, fid, path, rel, int(slot["off"]),
                                int(slot["end"] - slot["off"]), "CODEC_TACTICS_OGRE",
                                "EMES", slot["text"], data[slot["off"]:slot["end"]])
                except Exception:
                    errors["EMES_PARSE"] += 1
            # Escaneo genérico adicional para texto fuera de la tabla estructurada.
            scan_raw(source, did, fid, path, rel, data, scan_codec=True)

        with tempfile.TemporaryDirectory(prefix="TO_full_text_inventory_v2_") as tmp:
            usrdir = Path(tmp) / "USRDIR"
            progress("=== EXTRACCIÓN TEMPORAL DE USRDIR ===")
            extracted_count = extract_usrdir(iso, usrdir, tools_dir)
            game = Game(str(usrdir))
            total_bins = len(game.ft.dirs)
            total_files = sum(len(d["files"]) for d in game.ft.dirs)
            progress(f"USRDIR extraído: {extracted_count} archivos | {total_bins} directorios BIN | {total_files} entradas FILETABLE")

            # Un directorio BIN a la vez: reduce memoria y deja claro el avance.
            for bin_index, directory in enumerate(game.ft.dirs, 1):
                did = int(directory["id"])
                raw_bin = game.bin(did)
                progress(f"\n=== BIN {bin_index}/{total_bins}: {did:04X}.BIN | {len(raw_bin):,} bytes | {len(directory['files'])} entradas ===")
                if not args.skip_full_bin_scan:
                    scan_raw("BIN_COMPLETO", did, -1, (), f"USRDIR/{did:04X}.BIN (datos completos)", raw_bin, scan_codec=False)
                for file_index, entry in enumerate(directory["files"], 1):
                    fid = int(entry["id"])
                    if (did, fid) == (0, 0):
                        continue  # preload se procesa separadamente
                    offset = game.ft.offset(directory, entry)
                    blob = raw_bin[offset:offset + int(entry["size"])]
                    progress(f"  Recurso {file_index}/{len(directory['files'])}: BIN {did:04X} / archivo {fid} | {len(blob):,} bytes")
                    walk_blob("BIN_PRINCIPAL", did, fid, blob)
                # Libera BIN procesados. Conserva 0000.BIN para leer preload al final.
                if did != 0:
                    game._bins.pop(did, None)
                all_f.flush(); missing_f.flush(); known_f.flush()

            # Copias preload de 0000.BIN: se revisan todas, no solo la entrada 500/10241.
            progress("\n=== COPIAS PRELOAD DENTRO DE 0000.BIN ===")
            directory0 = game.ft.dir(0)
            preload_entry = next((x for x in directory0["files"] if int(x["id"]) == 0), None)
            if preload_entry is None and directory0.get("files"):
                preload_entry = directory0["files"][0]
            if preload_entry is None:
                raise RuntimeError("No se encontró el archivo preload 0/0 en FILETABLE.BIN.")
            raw0 = game.bin(0)
            preload_offset = game.ft.offset(directory0, preload_entry)
            preload = raw0[preload_offset:preload_offset + int(preload_entry["size"])]
            scan_raw("PRELOAD_CONTENEDOR_0000", 0, 0, (), "0000.BIN/preload 0/0 (contenedor)", preload, scan_codec=False)
            if len(preload) < 4:
                raise RuntimeError("El preload 0/0 está truncado.")
            count = int.from_bytes(preload[:4], "little")
            header_end = 4 + 8 * count
            if count > 10000 or header_end > len(preload):
                raise RuntimeError(f"Cabecera preload inválida: count={count}, header_end={header_end}, bytes={len(preload)}")
            pos = header_end
            for preload_index in range(count):
                raw_id = int.from_bytes(preload[4 + preload_index * 8:8 + preload_index * 8], "little")
                size = int.from_bytes(preload[8 + preload_index * 8:12 + preload_index * 8], "little")
                did, fid = raw_id & 0xFFFF, raw_id >> 16
                data = preload[pos:pos + size]
                if len(data) != size:
                    raise RuntimeError(f"Preload #{preload_index} truncado: {len(data)}/{size} bytes")
                progress(f"  PRELOAD {preload_index + 1}/{count}: dir={did} file={fid} | {size:,} bytes")
                walk_blob("COPIA_PRELOAD", did, fid, data)
                pos += size
                all_f.flush(); missing_f.flush(); known_f.flush()
            if pos < len(preload):
                progress(f"  Bytes finales del preload: {len(preload) - pos:,}; se escanearán como tail")
                scan_raw("PRELOAD_TAIL", 0, 0, (), "0000.BIN/preload tail", preload[pos:], scan_codec=False)

        # Cierre y resumen.
        all_f.flush(); missing_f.flush(); known_f.flush()
        elapsed = time.time() - start_time
        with summary_path.open("w", encoding="utf-8") as summary:
            summary.write("INVENTARIO GLOBAL DE CADENAS - VERSIÓN CON PROGRESO\n")
            summary.write(f"ISO: {iso}\nCSV: {args.csv or 'No proporcionado'}\n")
            summary.write(f"Total de candidatos: {all_count}\nCandidatos no encontrados en texto_ingles: {missing_count}\n")
            summary.write(f"Textos XLC/EMES interpretados: {known_count}\nHojas examinadas: {leaf_count}\n")
            summary.write(f"Recursos/fragmentos examinados: {resource_count}\nDuplicados omitidos: {duplicates}\n")
            summary.write(f"Tiempo transcurrido: {elapsed:.1f} segundos\n")
            summary.write("\nCandidatos por origen:\n")
            for name, count_value in sorted(source_counts.items()):
                summary.write(f"  {name}: {count_value}\n")
            summary.write("\nErrores de interpretación:\n")
            for name, count_value in sorted(errors.items()):
                summary.write(f"  {name}: {count_value}\n")
            summary.write("\nNotas: las cadenas ASCII/UTF-16LE/codec genérico son candidatos y pueden incluir falsos positivos.\n")
            summary.write("Las filas XLC/EMES se decodificaron mediante los parsers de FrenchTools.\n")
            summary.write("Los TSV se escribieron incrementalmente; si el proceso se interrumpe, contienen el trabajo completado hasta ese momento.\n")
        log("\n=== INVENTARIO TERMINADO ===")
        log(f"Candidatos totales: {all_count:,}")
        log(f"Candidatos no encontrados en CSV: {missing_count:,}")
        log(f"Textos XLC/EMES: {known_count:,}")
        log(f"Hojas examinadas: {leaf_count:,} | recursos/fragmentos: {resource_count:,}")
        log(f"Tiempo: {elapsed:.1f} s")
        log("Informes:")
        log(f"  {all_path}")
        log(f"  {missing_path}")
        log(f"  {known_path}")
        log(f"  {summary_path}")
        log(f"  {progress_path}")
        log("No se modificó ningún archivo original.")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nINTERRUMPIDO por el usuario. Los TSV contienen los resultados guardados hasta el último recurso completado.", file=sys.stderr, flush=True)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        raise
