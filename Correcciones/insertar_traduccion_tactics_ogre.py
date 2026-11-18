#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inserta Tactics_Ogre_espanol_neutral.csv en una ISO PSP de Tactics Ogre.

Usa la estructura de FrenchTools y los manifiestos de una extracción Gibbed.
En XLC conserva el bloque original y añade cadenas nuevas para las celdas traducidas,
por lo que admite punteros compartidos o referencias a subcadenas.
No modifica la ISO de entrada ni el CSV. La salida se escribe en otro archivo.

Ejemplo:
  python insertar_traduccion_tactics_ogre.py ^
    --iso "E:\\Tactics ogre\\One Vision.iso" ^
    --csv "E:\\Tactics ogre\\Tactics_Ogre_espanol_neutral.csv" ^
    --gibbed-root "E:\\Tactics ogre\\Gibbed_Extracted_English_Original" ^
    --french-tools "E:\\Tactics ogre\\FrenchTools" ^
    --output "E:\\Tactics ogre\\One Vision - Español v1.iso" ^
    --dry-run

Quita --dry-run para crear la ISO.
"""
from __future__ import annotations

import argparse
import csv
import re
import struct
import sys
import tempfile
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any

MARKER_RE = re.compile(r"\{[^{}]*\}|\\n|\n")
REQUIRED_COLUMNS = {
    "archivo", "tipo", "fila", "columna", "id_entrada", "nid",
    "texto_ingles", "texto_espanol"
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def norm_path(value: str) -> str:
    value = value.replace("\\", "/").strip()
    while value.startswith("./"):
        value = value[2:]
    return value.casefold()


def read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        fail(f"No se encontró el manifiesto Gibbed: {path}")
    return tomllib.loads(path.read_text(encoding="utf-8-sig"))


def safe_manifest_child(root: Path, parent: Path, relative: str) -> Path:
    rel = relative.replace("\\", "/")
    candidate = (parent / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        fail(f"Ruta fuera de la extracción Gibbed: {relative}")
    # Algunos manifiestos pueden señalar la carpeta de un pack en lugar del archivo de manifiesto.
    if candidate.is_dir():
        candidate = candidate / "@manifest.toml"
    return candidate


def build_gibbed_path_map(gibbed_root: Path) -> dict[str, tuple[int, ...]]:
    """Mapea ruta legible de Gibbed -> (dir_id, file_id, indices pakd...)."""
    gibbed_root = gibbed_root.resolve()
    root_manifest = gibbed_root / "@manifest.toml"
    root_data = read_toml(root_manifest)
    directories = root_data.get("directories")
    if not isinstance(directories, list):
        fail("El @manifest.toml raíz no contiene la lista 'directories'.")

    path_map: dict[str, tuple[int, ...]] = {}
    display_for_key: dict[str, str] = {}

    def walk_container(manifest_path: Path, prefix: tuple[int, ...], is_top: bool) -> None:
        data = read_toml(manifest_path)
        entries = data.get("files", [])
        if not isinstance(entries, list):
            fail(f"El manifiesto no contiene una lista 'files': {manifest_path}")
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            if is_top:
                if "id" not in entry:
                    fail(f"Falta el id de un archivo de primer nivel en {manifest_path}")
                child_id = int(entry["id"])
            else:
                # Dentro de PAKD, FrenchTools identifica cada entrada por su índice físico.
                child_id = index
            loc = prefix + (child_id,)
            relative_path = entry.get("path")
            if not relative_path:
                continue
            if entry.get("pack") is True:
                nested_manifest = safe_manifest_child(gibbed_root, manifest_path.parent, str(relative_path))
                walk_container(nested_manifest, loc, False)
            else:
                leaf = safe_manifest_child(gibbed_root, manifest_path.parent, str(relative_path))
                try:
                    rel = leaf.relative_to(gibbed_root).as_posix()
                except ValueError:
                    fail(f"La ruta de archivo sale de la extracción Gibbed: {leaf}")
                key = norm_path(rel)
                if key in path_map and path_map[key] != loc:
                    fail(
                        "Una misma ruta de Gibbed apunta a dos ubicaciones internas: "
                        f"{display_for_key[key]} -> {path_map[key]} y {rel} -> {loc}"
                    )
                path_map[key] = loc
                display_for_key[key] = rel

    for directory in directories:
        if not isinstance(directory, dict) or "file_manifest" not in directory:
            continue
        did = int(directory["id"])
        manifest_path = safe_manifest_child(gibbed_root, gibbed_root, str(directory["file_manifest"]))
        walk_container(manifest_path, (did,), True)

    if not path_map:
        fail("No se pudo construir el mapa de rutas desde los manifiestos Gibbed.")
    return path_map



def validate_charset(row: dict[str, str], line: int, supported_chars: set[str]) -> None:
    """Rechaza grafías que el codec de FrenchTools no puede representar."""
    value = row.get("texto_espanol", "")
    # Los marcadores de control no son glifos de la fuente.
    value = re.sub(r"\{[^{}]*\}", "", value)
    value = value.replace("\\n", "").replace("\n", "")
    for char in value:
        if char not in supported_chars and char not in "\r\t":
            fail(
                f"Carácter no compatible con la fuente PSP en la línea {line}: "
                f"{char!r} (U+{ord(char):04X}) en {row.get('archivo')}. "
                f"Texto: {row.get('texto_espanol', '')!r}"
            )


def read_translation_csv(csv_path: Path, supported_chars: set[str]) -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]], dict[str, int]]:
    if not csv_path.is_file():
        fail(f"No se encontró el CSV: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            fail("El CSV no tiene encabezados.")
        names = {name.strip().lower() for name in reader.fieldnames if name}
        missing = sorted(REQUIRED_COLUMNS - names)
        if missing:
            fail("Faltan columnas requeridas en el CSV: " + ", ".join(missing))
        # Normalizar nombres de columnas sin modificar los valores originales.
        rows: list[dict[str, str]] = []
        by_file: dict[str, list[dict[str, str]]] = defaultdict(list)
        seen: set[tuple[str, ...]] = set()
        blank_es = 0
        filled = 0
        type_counts: dict[str, int] = defaultdict(int)
        for line, source in enumerate(reader, start=2):
            row = {str(k).strip().lower(): (v or "") for k, v in source.items() if k is not None}
            file_name = row.get("archivo", "").strip()
            kind = row.get("tipo", "").strip().upper()
            if not file_name:
                fail(f"La columna archivo está vacía en la línea {line}.")
            if kind not in {"XLC", "EMES"}:
                fail(f"Tipo no reconocido en la línea {line}: {kind!r}")
            key = (
                norm_path(file_name), kind, row.get("fila", "").strip(),
                row.get("columna", "").strip(), row.get("id_entrada", "").strip(),
                row.get("nid", "").strip()
            )
            if key in seen:
                fail(f"Fila duplicada en el CSV (línea {line}): {key}")
            seen.add(key)
            row["_line"] = str(line)
            row["_kind"] = kind
            row["_path"] = file_name.replace("\\", "/")
            rows.append(row)
            by_file[norm_path(file_name)].append(row)
            type_counts[kind] += 1
            if row.get("texto_espanol", "").strip():
                filled += 1
                validate_markers(row, line)
                validate_charset(row, line, supported_chars)
            else:
                blank_es += 1
        stats = {
            "rows": len(rows), "translated": filled, "blank_es": blank_es,
            "XLC": type_counts.get("XLC", 0), "EMES": type_counts.get("EMES", 0),
            "unique_files": len(by_file)
        }
        return rows, dict(by_file), stats


def marker_tokens(value: str) -> list[str]:
    return sorted(token for token in MARKER_RE.findall(value) if token != "{w}")


def validate_markers(row: dict[str, str], line: int) -> None:
    en = marker_tokens(row.get("texto_ingles", ""))
    es = marker_tokens(row.get("texto_espanol", ""))
    if en != es:
        fail(
            f"Los marcadores no coinciden en la línea {line} ({row.get('archivo')}):\n"
            f"  inglés: {en}\n  español: {es}"
        )


def encode_translation(english: str, spanish: str, norm, encode, spanmod, mode: str) -> bytes:
    """Codifica la traducción siguiendo {w} automático y recalculando {span}."""
    original_header, autowrap, _ = norm(english)
    translated_header, _, translated_body = norm(spanish)
    if original_header and translated_header and original_header != translated_header:
        fail("El marcador {span} del español no coincide con el del inglés.")
    if not original_header and translated_header:
        fail("La traducción contiene un marcador {span} que no existe en el original.")
    encoded_body, _ = encode(translated_body, autowrap=autowrap)
    if original_header:
        return spanmod.make_header(original_header, translated_body, mode) + encoded_body
    return encoded_body


def choose_xlc_parser(
    blob: bytes, rows: list[dict[str, str]], file_path: str = "", decode_func=None,
):
    """Lee la tabla XLC sin exigir que cada puntero comience tras un byte NUL.

    Algunas ISO ya traducidas conservan punteros válidos a subcadenas: el byte
    anterior puede ser un espacio u otro carácter, aunque decode(blob, ptr)
    termine correctamente. Los analizadores clásicos descartan esa columna.
    Para la inserción solo necesitamos verificar las columnas solicitadas y
    decodificar cada puntero no nulo.
    """
    if len(blob) < 16 or blob[:4] != b"xlce":
        fail(f"Recurso XLC inválido{(' en ' + file_path) if file_path else ''}: falta cabecera xlce.")
    if decode_func is None:
        fail("Falta el decodificador para validar las referencias XLC.")

    n, data_offset, element_size = struct.unpack_from("<III", blob, 4)
    header_end = 16 + n * element_size
    context = f" en {file_path}" if file_path else ""
    if element_size < 4 or header_end > len(blob):
        fail(
            f"Cabecera XLC inválida{context}: n={n}, tamaño_registro={element_size}, "
            f"fin_tabla=0x{header_end:X}, tamaño=0x{len(blob):X}."
        )

    required_cols = sorted({int(row["columna"]) for row in rows})
    cols: dict[int, list[int]] = {}
    errors = []
    for col in required_cols:
        if col < 0 or element_size < col + 4:
            errors.append(f"columna {col}: fuera del registro (tamaño={element_size})")
            continue
        values = [
            struct.unpack_from("<I", blob, 16 + r * element_size + col)[0]
            for r in range(n)
        ]
        cols[col] = values
        for row_index, pointer in enumerate(values):
            if pointer == 0:
                continue
            if not (header_end <= pointer < len(blob)):
                errors.append(
                    f"columna {col}, fila {row_index}: puntero fuera de rango 0x{pointer:X}"
                )
                continue
            try:
                decode_func(blob, pointer)
            except Exception as exc:
                errors.append(
                    f"columna {col}, fila {row_index}: no se puede decodificar "
                    f"0x{pointer:X} ({type(exc).__name__}: {exc})"
                )

    if errors:
        fail(f"No se pudieron validar las referencias XLC{context}: " + " | ".join(errors[:20]))

    # La tabla conserva también las columnas que no se solicitan si se usan
    # después para verificar el recurso; aquí solo se leen las columnas del CSV.
    for row in rows:
        rr, cc = int(row["fila"]), int(row["columna"])
        if not (0 <= rr < n):
            fail(f"Fila XLC fuera de rango{context}: fila {rr} (n={n}).")
        pointer = cols[cc][rr]
        if pointer == 0:
            fail(f"Puntero XLC vacío{context}: fila {rr}, columna {cc}.")

    return {
        "n": n,
        "es": element_size,
        "hend": header_end,
        "strcols": required_cols,
        "cols": cols,
        "data_offset": data_offset,
    }


def rebuild_xlc_by_cell(
    blob: bytes, info: dict[str, Any], rows: list[dict[str, str]], norm, encode,
    spanmod, mode: str,
) -> tuple[bytes, int]:
    """Inserta cada traducción en una cadena nueva y redirige solo su celda.

    Este método append-only conserva intactos todos los bytes originales del
    bloque de cadenas. También admite referencias originales a subcadenas,
    punteros compartidos y alias: no necesita reconstruir ni reordenar slots.
    Las celdas sin traducción permanecen apuntando al texto que ya había en la ISO.
    """
    n, esize, hend = info["n"], info["es"], info["hend"]
    out = bytearray(blob)
    encoded_offsets: dict[bytes, int] = {}
    changed_records = 0
    seen_cells: set[tuple[int, int]] = set()

    for row in rows:
        if not row.get("texto_espanol", "").strip():
            continue
        col, row_index = int(row["columna"]), int(row["fila"])
        cell = (col, row_index)
        if cell in seen_cells:
            fail(f"Celda XLC repetida: columna {col}, fila {row_index}.")
        seen_cells.add(cell)
        if col not in info["cols"]:
            fail(f"Columna XLC inexistente: {col}.")
        if not (0 <= row_index < n):
            fail(f"Fila XLC fuera de rango: {row_index} (n={n}).")
        old_pointer = info["cols"][col][row_index]
        if old_pointer == 0:
            fail(f"Puntero XLC vacío en fila {row_index}, columna {col}.")

        encoded = encode_translation(
            row["texto_ingles"], row["texto_espanol"], norm, encode, spanmod, mode
        )
        new_pointer = encoded_offsets.get(encoded)
        if new_pointer is None:
            new_pointer = len(out)
            if new_pointer > 0xFFFFFFFF:
                fail("El recurso XLC supera el límite de punteros de 32 bits.")
            encoded_offsets[encoded] = new_pointer
            out.extend(encoded)
            out.append(0)

        struct.pack_into("<I", out, 16 + row_index * esize + col, new_pointer)
        changed_records += 1

    return bytes(out), changed_records


def rebuild_emes_by_entry(blob: bytes, parsed, rows: list[dict[str, str]], norm, encode, spanmod, mode: str, build_emes) -> tuple[bytes, int]:
    idmap, slots, tail, idpad = parsed
    translations: dict[tuple[int, int], dict[str, str]] = {}
    for row in rows:
        entry_id = int(row["id_entrada"])
        nid = int(row["nid"])
        key = (entry_id, nid)
        if key in translations:
            fail(f"Entrada EMES repetida: id_entrada={entry_id}, nid={nid}.")
        translations[key] = row

    refs_by_slot: dict[int, list[int]] = defaultdict(list)
    indexes_by_key: dict[tuple[int, int], list[int]] = defaultdict(list)
    for entry_index, (entry_id, slot_index) in enumerate(idmap):
        if not (0 <= slot_index < len(slots)):
            fail(f"Índice de cadena EMES fuera de rango: {slot_index}.")
        refs_by_slot[slot_index].append(entry_index)
        indexes_by_key[(int(entry_id), int(slots[slot_index]["nid"]))].append(entry_index)

    missing = sorted(set(translations) - set(indexes_by_key))
    if missing:
        fail(f"No se encontraron {len(missing)} pares id_entrada/nid en EMES. Ejemplos: {missing[:8]}")

    new_slots: list[dict[str, Any]] = []
    encoded_slots: list[bytes] = []
    new_idmap: list[tuple[int, int]] = list(idmap)
    changed_records = 0

    for old_index, slot in enumerate(slots):
        entry_indexes = refs_by_slot.get(old_index, [])
        groups: dict[bytes, list[int]] = {}
        original_encoded = blob[slot["start"]:slot["end"] - 1]
        for entry_index in entry_indexes:
            entry_id = int(idmap[entry_index][0])
            row = translations.get((entry_id, int(slot["nid"])))
            if row and row.get("texto_espanol", "").strip():
                encoded = encode_translation(
                    row["texto_ingles"], row["texto_espanol"], norm, encode, spanmod, mode
                )
                changed_records += 1
            else:
                encoded = original_encoded
            groups.setdefault(encoded, []).append(entry_index)
        if not groups:
            groups[original_encoded] = []

        group_items = list(groups.items())
        for group_index, (encoded, indexes) in enumerate(group_items):
            new_slot_index = len(new_slots)
            new_slot = dict(slot)
            # El espacio de separación original se conserva una sola vez al final de las copias.
            new_slot["gap"] = slot.get("gap", b"") if group_index == len(group_items) - 1 else b""
            new_slots.append(new_slot)
            encoded_slots.append(encoded)
            for entry_index in indexes:
                new_idmap[entry_index] = (idmap[entry_index][0], new_slot_index)

    rebuilt = build_emes(new_idmap, new_slots, tail, idpad, encoded_slots)
    return rebuilt, changed_records


def extract_usrdir(iso_path: Path, out_dir: Path, tools_dir: Path) -> Any:
    """Extrae los BIN del USRDIR y las fuentes necesarias para recalcular {span}."""
    sys.path.insert(0, str(tools_dir))
    from isopatch import walk_iso, SECTOR
    from tree import Game

    out_dir.mkdir(parents=True, exist_ok=True)
    with iso_path.open("rb") as source:
        files = walk_iso(source)
        for iso_path_name, (_record, extent, size) in files.items():
            if iso_path_name.startswith("/PSP_GAME/USRDIR/"):
                source.seek(extent * SECTOR)
                target = out_dir / Path(iso_path_name).name
                target.write_bytes(source.read(size))

    game = Game(str(out_dir))
    normal_font = None
    for did, fid, data in game.files():
        if did == 600 and fid == 8:
            normal_font = data
            break
    if normal_font is None:
        fail("No se encontró la fuente normal.font (directorio 600, archivo 8) en la ISO.")
    return game, normal_font


def sync_preload_blob(game, builder) -> None:
    """Actualiza las copias precargadas de los BIN modificados dentro de 0000.BIN."""
    blob_dir = game.ft.dir(0)
    if not blob_dir.get("files"):
        fail("No se encontró el archivo preload 0/0 en FILETABLE.BIN.")
    preload_file = blob_dir["files"][0]
    raw = game.bin(0)
    offset = game.ft.offset(blob_dir, preload_file)
    raw0 = raw[offset:offset + preload_file["size"]]
    if len(raw0) < 4:
        fail("El blob preload 0/0 está truncado.")
    count = struct.unpack_from("<I", raw0, 0)[0]
    header_end = 4 + 8 * count
    if header_end > len(raw0):
        fail("La tabla del blob preload 0/0 es inválida.")
    entries = [list(struct.unpack_from("<II", raw0, 4 + 8 * i)) for i in range(count)]
    pos = header_end
    data_parts = []
    for _file_id, size in entries:
        data_parts.append(raw0[pos:pos + size])
        pos += size
    if pos > len(raw0):
        fail("Los datos del blob preload 0/0 están truncados.")

    changed = False
    for i, (raw_id, _size) in enumerate(entries):
        did, fid = raw_id & 0xFFFF, raw_id >> 16
        if (did, fid) in builder.leaf_mods:
            new_bytes = builder.file_bytes(did, fid)
            data_parts[i] = new_bytes
            entries[i][1] = len(new_bytes)
            changed = True
    if changed:
        new_blob = struct.pack("<I", count)
        new_blob += b"".join(struct.pack("<II", *entry) for entry in entries)
        new_blob += b"".join(data_parts)
        builder.leaf_mods[(0, 0)] = {(): new_blob}



def verify_output_iso(
    iso_path: Path,
    temp_parent: Path,
    tools_dir: Path,
    rows_by_file: dict[str, list[dict[str, str]]],
    path_map: dict[str, tuple[int, ...]],
    parse_emes,
    decode,
    norm,
) -> int:
    """Reabre la ISO terminada y verifica el texto español de cada celda insertada."""
    verify_dir = temp_parent / "VERIFY_USRDIR"
    game, _font = extract_usrdir(iso_path, verify_dir, tools_dir)
    leaves = {tuple(path): blob for path, blob in game.leaves()}
    verified = 0

    for path_key, file_rows in rows_by_file.items():
        translated = [r for r in file_rows if r.get("texto_espanol", "").strip()]
        if not translated:
            continue
        loc = path_map[path_key]
        blob = leaves.get(loc)
        if blob is None:
            fail(f"VERIFICACIÓN: no aparece el recurso {file_rows[0]['_path']} en la ISO final.")
        kind = file_rows[0]["_kind"]
        if kind == "XLC":
            info = choose_xlc_parser(blob, file_rows, file_rows[0]["_path"], decode)
            for row in translated:
                row_index, col = int(row["fila"]), int(row["columna"])
                pointer = info["cols"][col][row_index]
                if not pointer:
                    fail(f"VERIFICACIÓN: puntero vacío en {row['_path']}, fila {row_index}, columna {col}.")
                decoded, _end = decode(blob, pointer)
                actual_body = norm(decoded)[2]
                expected_body = norm(row["texto_espanol"])[2]
                if actual_body != expected_body:
                    fail(
                        f"VERIFICACIÓN: el texto no coincide en {row['_path']} "
                        f"(fila {row_index}, columna {col}).\n"
                        f"Esperado: {expected_body[:160]!r}\nEncontrado: {actual_body[:160]!r}"
                    )
                verified += 1
        elif kind == "EMES":
            idmap, slots, _tail, _idpad = parse_emes(blob)
            indexes_by_key: dict[tuple[int, int], list[int]] = defaultdict(list)
            for entry_id, slot_index in idmap:
                indexes_by_key[(int(entry_id), int(slots[slot_index]["nid"]))].append(slot_index)
            for row in translated:
                key = (int(row["id_entrada"]), int(row["nid"]))
                slot_indexes = indexes_by_key.get(key, [])
                if not slot_indexes:
                    fail(f"VERIFICACIÓN: no se encuentra id_entrada/nid {key} en {row['_path']}.")
                expected_body = norm(row["texto_espanol"])[2]
                for slot_index in slot_indexes:
                    actual_body = norm(slots[slot_index]["text"])[2]
                    if actual_body != expected_body:
                        fail(
                            f"VERIFICACIÓN: texto EMES distinto en {row['_path']}, id/nid {key}.\n"
                            f"Esperado: {expected_body[:160]!r}\nEncontrado: {actual_body[:160]!r}"
                        )
                verified += 1
        else:
            fail(f"VERIFICACIÓN: tipo no compatible {kind} en {file_rows[0]['_path']}.")
    return verified


def main() -> int:
    parser = argparse.ArgumentParser(description="Inserta el CSV de español neutral en una ISO One Vision.")
    parser.add_argument("--iso", required=True, help="ISO One Vision que ya conserva tu traducción anterior.")
    parser.add_argument("--csv", required=True, help="Tactics_Ogre_espanol_neutral.csv")
    parser.add_argument("--gibbed-root", required=True, help="Carpeta extraída por Gibbed que contiene @manifest.toml")
    parser.add_argument("--french-tools", required=True, help="Carpeta FrenchTools (contiene la subcarpeta outils)")
    parser.add_argument("--output", required=True, help="ISO nueva de salida; no debe ser la ISO de entrada.")
    parser.add_argument("--dry-run", action="store_true", help="Valida y calcula todo, pero no crea la ISO.")
    parser.add_argument("--span-mode", choices=("recompute", "keep"), default="recompute", help="Tratamiento de los encabezados {span}.")
    args = parser.parse_args()

    iso_path = Path(args.iso).expanduser().resolve()
    csv_path = Path(args.csv).expanduser().resolve()
    gibbed_root = Path(args.gibbed_root).expanduser().resolve()
    french_root = Path(args.french_tools).expanduser().resolve()
    tools_dir = french_root / "outils"
    output_path = Path(args.output).expanduser().resolve()
    if not iso_path.is_file(): fail(f"No existe la ISO de entrada: {iso_path}")
    if not tools_dir.is_dir(): fail(f"No existe la carpeta FrenchTools/outils: {tools_dir}")
    if output_path == iso_path: fail("La ISO de salida no puede ser la misma que la ISO de entrada.")
    if output_path.exists(): fail(f"La ISO de salida ya existe. Cambia el nombre o muévela: {output_path}")

    sys.path.insert(0, str(tools_dir))
    from tree import parse_emes, build_emes
    from build import Builder
    from codec import decode, encode, U2B, FALLBACK
    from export import norm
    import span as spanmod
    from isopatch import rebuild_iso

    rows, rows_by_file, csv_stats = read_translation_csv(csv_path, set(U2B) | set(FALLBACK))
    print("CSV leído:", csv_path)
    print("  Registros:", csv_stats["rows"])
    print("  Traducciones no vacías:", csv_stats["translated"])
    print("  Celdas sin traducción (se conservarán como están en la ISO base):", csv_stats["blank_es"])
    print("  Recursos XLC/EMES:", csv_stats["XLC"], "/", csv_stats["EMES"])
    print("  Archivos únicos:", csv_stats["unique_files"])

    print("Leyendo manifiestos Gibbed...")
    path_map = build_gibbed_path_map(gibbed_root)
    csv_paths = set(rows_by_file)
    missing_manifest = sorted(csv_paths - set(path_map))
    if missing_manifest:
        fail(
            f"El manifiesto Gibbed no contiene {len(missing_manifest)} rutas del CSV. "
            f"Ejemplos: {missing_manifest[:15]}"
        )
    print("  Rutas encontradas:", len(csv_paths))

    temp_dir_obj = tempfile.TemporaryDirectory(prefix="TO_OneVision_ES_v1_")
    temp_dir = Path(temp_dir_obj.name)
    font_path = tools_dir / "normal.font"
    old_font = font_path.read_bytes() if font_path.exists() else None
    try:
        print("Extrayendo USRDIR desde la ISO base...")
        game, normal_font = extract_usrdir(iso_path, temp_dir / "USRDIR", tools_dir)
        font_path.write_bytes(normal_font)

        leaves = {tuple(p): b for p, b in game.leaves()}
        builder = Builder(game)
        changed_files = 0
        changed_records = 0
        processed_xlc = processed_emes = 0
        total_expected = csv_stats["translated"]
        found_expected = 0

        for path_key, file_rows in rows_by_file.items():
            file_path = file_rows[0]["_path"]
            loc = path_map[path_key]
            blob = leaves.get(loc)
            if blob is None:
                fail(f"La ruta de Gibbed existe, pero no aparece en FrenchTools/Game: {file_path} -> {loc}")
            kind_set = {r["_kind"] for r in file_rows}
            if len(kind_set) != 1:
                fail(f"El mismo archivo aparece con más de un tipo en el CSV: {file_path}")
            kind = next(iter(kind_set))

            translated_rows = [r for r in file_rows if r.get("texto_espanol", "").strip()]
            found_expected += len(translated_rows)
            if kind == "XLC":
                if blob[:4] != b"xlce":
                    fail(f"El CSV marca XLC, pero el recurso no comienza con xlce: {file_path} -> {loc}")
                info = choose_xlc_parser(blob, file_rows, file_rows[0]["_path"], decode)
                # Verificar también las filas vacías para detectar desajustes de versión/ubicación.
                for r in file_rows:
                    rr, cc = int(r["fila"]), int(r["columna"])
                    if not (0 <= rr < info["n"]) or cc not in info["cols"] or not info["cols"][cc][rr]:
                        fail(f"Ubicación XLC inválida en línea {r['_line']}: {file_path}, fila {rr}, columna {cc}.")
                if translated_rows:
                    new_blob, n_changed = rebuild_xlc_by_cell(
                        blob, info, translated_rows, norm, encode, spanmod, args.span_mode
                    )
                    if new_blob != blob:
                        builder.set_leaf(loc, new_blob)
                        changed_files += 1
                        changed_records += n_changed
                    processed_xlc += len(translated_rows)
            elif kind == "EMES":
                if blob[:4] != b"EMES":
                    fail(f"El CSV marca EMES, pero el recurso no comienza con EMES: {file_path} -> {loc}")
                parsed = parse_emes(blob)
                if translated_rows:
                    new_blob, n_changed = rebuild_emes_by_entry(
                        blob, parsed, translated_rows, norm, encode, spanmod, args.span_mode, build_emes
                    )
                    if new_blob != blob:
                        builder.set_leaf(loc, new_blob)
                        changed_files += 1
                        changed_records += n_changed
                    processed_emes += len(translated_rows)
            else:
                fail(f"Tipo no compatible: {kind}")

        if found_expected != total_expected:
            fail(f"No se procesaron todas las traducciones: {found_expected}/{total_expected}.")

        print("Validación de recursos completada:")
        print("  XLC con traducción:", processed_xlc)
        print("  EMES con traducción:", processed_emes)
        print("  Registros traducidos aplicables:", changed_records)
        print("  Recursos BIN/PAKD con cambios:", changed_files)

        if args.dry_run:
            print("\nDRY-RUN correcto: no se creó ni modificó ninguna ISO.")
            return 0

        print("Sincronizando copias preload...")
        sync_preload_blob(game, builder)
        replacements = builder.build()
        iso_replacements = {"/PSP_GAME/USRDIR/" + name: data for name, data in replacements.items()}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print("Reconstruyendo ISO de salida...")
        rebuild_iso(str(iso_path), str(output_path), iso_replacements)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            fail("No se pudo verificar el archivo ISO de salida.")
        print("Verificando la ISO reconstruida...")
        verified = verify_output_iso(
            output_path, temp_dir, tools_dir, rows_by_file, path_map,
            parse_emes, decode, norm
        )
        if verified != total_expected:
            fail(f"La verificación final encontró {verified}/{total_expected} textos.")
        print("  Textos verificados:", verified)
        print("\nISO creada correctamente:", output_path)
        print("Tamaño:", output_path.stat().st_size, "bytes")
        print("ISO de entrada intacta:", iso_path)
        return 0
    finally:
        if old_font is None:
            try: font_path.unlink(missing_ok=True)
            except Exception: pass
        else:
            font_path.write_bytes(old_font)
        temp_dir_obj.cleanup()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("\nERROR:", exc, file=sys.stderr)
        raise SystemExit(1)
