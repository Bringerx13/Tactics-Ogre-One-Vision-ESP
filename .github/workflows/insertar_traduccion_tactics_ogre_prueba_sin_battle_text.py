#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inserta el CSV de español neutral mediante XLC compactos cuando es seguro.

Los XLC con slots independientes se reconstruyen compactamente. Los recursos con
punteros solapados, compartidos con variantes o estructuras no compatibles conservan
el método append-only para evitar alterar otras celdas. EMES se reconstruye con FrenchTools.
Las correcciones específicas del PRELOAD se reaplican tras sincronizar los BIN.
No modifica la ISO de entrada ni el CSV. La salida se escribe en otro archivo.
Ignora {span ...} y {w} en la comparación, porque FrenchTools los genera automáticamente.

Ejemplo:
  python insertar_traduccion_tactics_ogre_compacta.py ^
    --iso "E:\\Tactics ogre\\One Vision.iso" ^
    --csv "E:\\Tactics ogre\\Tactics_Ogre_espanol_neutral_desde_hash.csv" ^
    --gibbed-root "E:\\Tactics ogre\\Gibbed_Extracted" ^
    --french-tools "E:\\Tactics ogre\\FrenchTools" ^
    --preload-tsv "E:\\Tactics ogre\\Correcciones\\preload_xlc_emes_traducido.tsv" ^
    --output "E:\\Tactics ogre\\One Vision - Español Compacta prueba.iso" ^
    --dry-run

Quita --dry-run para crear la ISO tras validar el informe.
"""
from __future__ import annotations

import argparse
import csv
import re
import struct
import sys
import tempfile
import tomllib
import unicodedata
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


def normalize_column_name(value: str) -> str:
    """Normaliza encabezados: acentos, espacios y mayúsculas, sin tocar los datos."""
    value = unicodedata.normalize("NFKD", (value or "").strip().lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[\s-]+", "_", value)
    return value


def detect_csv_dialect(stream) -> tuple[str, list[str]]:
    """Elige entre coma, punto y coma, tabulación o | según los encabezados requeridos."""
    candidates = [",", ";", "\t", "|"]
    best = None
    best_score = -1
    best_names: list[str] = []
    for delimiter in candidates:
        stream.seek(0)
        reader = csv.reader(stream, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            fail("El CSV está vacío.")
        normalized = [normalize_column_name(name) for name in header]
        score = len(REQUIRED_COLUMNS.intersection(normalized))
        if score > best_score or (score == best_score and len(normalized) > len(best_names)):
            best = delimiter
            best_score = score
            best_names = normalized
    stream.seek(0)
    missing = sorted(REQUIRED_COLUMNS - set(best_names))
    if best is None or best_score < len(REQUIRED_COLUMNS):
        shown_delimiter = {"\t": "TAB", ",": "coma", ";": "punto y coma", "|": "barra vertical"}.get(best, repr(best))
        fail(
            "No se reconocieron todos los encabezados requeridos del CSV. "
            f"Separador detectado: {shown_delimiter}. Encabezados leídos: {best_names}. "
            f"Faltan: {missing}. Comprueba que la primera fila contenga los nombres de columnas."
        )
    return best, best_names


def read_translation_csv(csv_path: Path, supported_chars: set[str]) -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]], dict[str, int]]:
    if not csv_path.is_file():
        fail(f"No se encontró el CSV: {csv_path}")
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        delimiter, normalized_header = detect_csv_dialect(stream)
        stream.seek(0)
        reader = csv.DictReader(stream, delimiter=delimiter)
        if reader.fieldnames is None:
            fail("El CSV no tiene encabezados.")
        # El nombre de columna puede tener acentos o estar separado por ; / TAB.
        header_map = {raw: normalize_column_name(raw) for raw in reader.fieldnames if raw is not None}
        canonical_names = list(header_map.values())
        if len(canonical_names) != len(set(canonical_names)):
            fail(f"Hay encabezados duplicados tras normalizarlos: {canonical_names}")

        rows: list[dict[str, str]] = []
        by_file: dict[str, list[dict[str, str]]] = defaultdict(list)
        seen: set[tuple[str, ...]] = set()
        blank_es = 0
        filled = 0
        type_counts: dict[str, int] = defaultdict(int)
        for line, source in enumerate(reader, start=2):
            row = {
                header_map[str(k)]: (v or "")
                for k, v in source.items()
                if k is not None and str(k) in header_map
            }
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
                if not row.get("texto_ingles", "").strip():
                    fail(f"Hay una traducción española sin texto inglés de referencia en la línea {line}.")
                filled += 1
                validate_markers(row, line)
                validate_charset(row, line, supported_chars)
            else:
                blank_es += 1
        delimiter_label = {"\t": "TAB", ",": "coma", ";": "punto y coma", "|": "barra vertical"}[delimiter]
        print(f"  Separador CSV detectado: {delimiter_label}")
        print(f"  Encabezados reconocidos: {', '.join(canonical_names)}")
        stats = {
            "rows": len(rows), "translated": filled, "blank_es": blank_es,
            "XLC": type_counts.get("XLC", 0), "EMES": type_counts.get("EMES", 0),
            "unique_files": len(by_file)
        }
        return rows, dict(by_file), stats


def marker_tokens(value: str) -> list[str]:
    """Devuelve marcadores que deben conservarse manualmente en el español.

    FrenchTools genera automáticamente {span ...} a partir del inglés y
    añade {w} durante el ajuste de palabras. Por eso esos dos marcadores
    no deben exigirse en texto_espanol ni provocar un falso error.
    El resto de los marcadores (por ejemplo {np}, {pp}, {hero} y {FF ...})
    se sigue comparando, incluidas sus repeticiones.
    """
    tokens = MARKER_RE.findall(value)
    return sorted(
        token for token in tokens
        if token != "{w}" and not re.fullmatch(r"\{span(?:\s+[^{}]*)?\}", token, flags=re.IGNORECASE)
    )


def validate_markers(row: dict[str, str], line: int) -> None:
    en = marker_tokens(row.get("texto_ingles", ""))
    es = marker_tokens(row.get("texto_espanol", ""))
    if en != es:
        fail(
            f"Los marcadores que deben conservarse no coinciden en la línea {line} "
            f"({row.get('archivo')}):\n"
            f"  inglés (sin {{span}} ni {{w}} automáticos): {en}\n  español: {es}"
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


def validate_emes_sources(parsed, rows, norm, file_path: str) -> None:
    """Comprueba id_entrada/nid y texto inglés antes de modificar un EMES."""
    idmap, slots, _tail, _idpad = parsed
    indexes_by_key: dict[tuple[int, int], list[int]] = defaultdict(list)
    for entry_id, slot_index in idmap:
        if not (0 <= slot_index < len(slots)):
            fail(f"Índice de cadena EMES fuera de rango en {file_path}: {slot_index}.")
        indexes_by_key[(int(entry_id), int(slots[slot_index]["nid"]))].append(slot_index)

    for row in rows:
        key = (int(row["id_entrada"]), int(row["nid"]))
        slot_indexes = indexes_by_key.get(key, [])
        if not slot_indexes:
            fail(f"No se encontró id_entrada/nid {key} en {file_path} (línea CSV {row.get('_line')}).")
        expected = row.get("texto_ingles", "")
        if not expected:
            if row.get("texto_espanol", "").strip():
                fail(f"Traducción EMES sin texto inglés de referencia en {file_path}, {key}.")
            continue
        for slot_index in slot_indexes:
            actual = slots[slot_index]["text"]
            if norm(actual)[2] != norm(expected)[2]:
                fail(
                    f"El inglés EMES no coincide con el CSV en {file_path}, id/nid {key}.\n"
                    f"CSV: {expected[:160]!r}\nEMES: {actual[:160]!r}"
                )


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




def xlc_source_matches(actual: str, expected: str, norm) -> bool:
    """Compara el inglés de la ISO con el CSV sin contar espacios de relleno finales.

    FrenchTools/XLC puede conservar uno o varios espacios ASCII al final de una
    cadena. Se ignoran solo para esta comprobación de identidad; no se modifican
    los bytes del recurso, el CSV ni los textos que se insertarán.
    """
    actual_body = norm(actual)[2]
    expected_body = norm(expected)[2]
    return actual_body.rstrip(" ") == expected_body.rstrip(" ")


def validate_xlc_sources(blob, info, rows, decode, norm, file_path):
    """Comprueba que cada coordenada CSV corresponde al texto inglés real del XLC."""
    for row in rows:
        try:
            rr, cc = int(row["fila"]), int(row["columna"])
        except Exception:
            fail(f"Fila/columna inválidas en {file_path}, línea {row.get('_line')}.")
        if cc not in info["cols"] or not (0 <= rr < info["n"]):
            fail(f"Coordenada fuera de rango en {file_path}: fila {rr}, columna {cc}.")
        pointer = info["cols"][cc][rr]
        if not pointer:
            fail(f"Puntero vacío en {file_path}: fila {rr}, columna {cc}.")
        actual, _end = decode(blob, pointer)
        expected = row.get("texto_ingles", "")
        if expected and not xlc_source_matches(actual, expected, norm):
            fail(
                f"El inglés del CSV no coincide con la ISO en {file_path}, "
                f"fila {rr}, columna {cc} (línea CSV {row.get('_line')}).\n"
                f"CSV: {expected[:180]!r}\nISO: {actual[:180]!r}"
            )


def rebuild_xlc_compact_safe(
    blob, rows, parse_xlc_fixed, build_xlc_fixed, decode, norm, encode,
    spanmod, mode, file_path,
):
    """Reconstruye el XLC sustituyendo su pool si la estructura es compactable.

    Devuelve (nuevo_blob, cantidad_celdas, None) si es seguro. Si hay punteros
    solapados, alias traducidos, referencias compartidas con traducciones distintas
    o celdas propietarias ausentes, devuelve (None, 0, motivo) para usar append-only.
    """
    try:
        info = parse_xlc_fixed(blob)
    except Exception as exc:
        return None, 0, f"parser compacto no compatible: {type(exc).__name__}: {exc}"
    if not info or not info.get("slots"):
        return None, 0, "no se pudo identificar un pool de cadenas XLC"

    cell_rows = {}
    for row in rows:
        cell = (int(row["fila"]), int(row["columna"]))
        if cell in cell_rows:
            fail(f"Celda repetida en {file_path}: fila {cell[0]}, columna {cell[1]}.")
        cell_rows[cell] = row

    required_columns = {int(row["columna"]) for row in rows}
    if not required_columns.issubset(set(info["strcols"])):
        missing = sorted(required_columns - set(info["strcols"]))
        return None, 0, f"columnas solicitadas no reconocidas como cadenas: {missing}"

    slot_by_offset = {slot["off"]: slot for slot in info["slots"]}
    owners = {}
    for col in info["strcols"]:
        for row_index, pointer in enumerate(info["cols"][col]):
            if pointer and pointer not in info.get("aliases", {}):
                owners.setdefault(pointer, set()).add((row_index, col))

    translated_by_pointer = {}
    translated_cell_count = 0
    for row in rows:
        spanish = row.get("texto_espanol", "")
        if not spanish.strip():
            continue
        rr, cc = int(row["fila"]), int(row["columna"])
        pointer = info["cols"][cc][rr]
        if pointer in info.get("aliases", {}):
            return None, 0, f"la celda ({rr},{cc}) apunta a un alias vacío"
        slot = slot_by_offset.get(pointer)
        if slot is None:
            return None, 0, f"no se encontró el slot del puntero {pointer:#x}"

        previous = translated_by_pointer.get(pointer)
        if previous is not None:
            if norm(previous["texto_espanol"])[2] != norm(spanish)[2]:
                return None, 0, f"un mismo puntero recibe traducciones distintas ({rr},{cc})"
        else:
            translated_by_pointer[pointer] = row
        translated_cell_count += 1

    # Reescribir un slot compartido solo es seguro cuando todas sus celdas
    # propietarias están en el CSV y reciben exactamente la misma traducción.
    for pointer, translation_row in translated_by_pointer.items():
        pointer_owners = owners.get(pointer, set())
        for owner in pointer_owners:
            owner_row = cell_rows.get(owner)
            if owner_row is None:
                return None, 0, f"faltan propietarios del puntero {pointer:#x}: {owner}"
            owner_spanish = owner_row.get("texto_espanol", "")
            if not owner_spanish.strip():
                return None, 0, f"el puntero {pointer:#x} también pertenece a una celda sin traducir {owner}"
            if norm(owner_spanish)[2] != norm(translation_row["texto_espanol"])[2]:
                return None, 0, f"el puntero {pointer:#x} tiene variantes por contexto"

    encoded_slots = []
    for slot in info["slots"]:
        row = translated_by_pointer.get(slot["off"])
        if row is None:
            # Mantener los bytes originales exactos para cadenas no traducidas.
            encoded_slots.append(blob[slot["off"]:slot["end"] - 1])
            continue
        spanish = row["texto_espanol"]
        if norm(slot["text"])[2] == norm(spanish)[2]:
            encoded_slots.append(blob[slot["off"]:slot["end"] - 1])
        else:
            encoded_slots.append(
                encode_translation(slot["text"], spanish, norm, encode, spanmod, mode)
            )

    try:
        rebuilt = build_xlc_fixed(blob, info, encoded_slots)
        new_info = parse_xlc_fixed(rebuilt)
    except Exception as exc:
        return None, 0, f"falló la reconstrucción compacta: {type(exc).__name__}: {exc}"
    if not new_info or (new_info["n"], new_info["es"], new_info["strcols"]) != (
        info["n"], info["es"], info["strcols"]
    ):
        return None, 0, "la estructura de la tabla cambió al reconstruir"

    # Verificación exhaustiva de todas las celdas en las columnas reconocidas.
    for col in info["strcols"]:
        for row_index, old_pointer in enumerate(info["cols"][col]):
            new_pointer = new_info["cols"][col][row_index]
            if bool(old_pointer) != bool(new_pointer):
                fail(f"La presencia de un puntero cambió en {file_path}, ({row_index},{col}).")
            if not old_pointer:
                continue
            old_text, _ = decode(blob, old_pointer)
            new_text, _ = decode(rebuilt, new_pointer)
            owner_translation = translated_by_pointer.get(old_pointer)
            if owner_translation is None:
                if new_text != old_text:
                    fail(f"Cambió una celda no traducida en {file_path}, ({row_index},{col}).")
            else:
                expected = owner_translation["texto_espanol"]
                if norm(new_text)[2] != norm(expected)[2]:
                    fail(f"La traducción compacta no coincide en {file_path}, ({row_index},{col}).")

    return rebuilt, translated_cell_count, None


def read_preload_overrides(tsv_path: Path):
    """Lee las correcciones especiales de las copias que difieren del BIN principal."""
    if not tsv_path.is_file():
        fail(f"No se encontró el TSV de correcciones PRELOAD: {tsv_path}")
    with tsv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not reader.fieldnames:
            fail("El TSV de PRELOAD no contiene encabezados.")
        header_map = {name: normalize_column_name(name) for name in reader.fieldnames if name is not None}
        required = {
            "preload_index", "dir_id", "file_id", "subpath_pakd", "ruta_gibbed", "tipo",
            "fila", "columna", "texto_preload", "texto_bin_principal", "texto_espanol_preload"
        }
        missing = sorted(required - set(header_map.values()))
        if missing:
            fail("Faltan columnas en el TSV de PRELOAD: " + ", ".join(missing))
        groups = defaultdict(list)
        pair_set = set()
        index_set = set()
        count = 0
        for line, source in enumerate(reader, start=2):
            row = {
                header_map[str(key)]: (value or "")
                for key, value in source.items()
                if key is not None and str(key) in header_map
            }
            spanish = row.get("texto_espanol_preload", "")
            if not spanish.strip():
                continue
            path_key = norm_path(row.get("ruta_gibbed", ""))
            if not path_key:
                fail(f"Ruta PRELOAD vacía en la línea {line}.")
            kind = row.get("tipo", "").strip().upper()
            if kind != "XLC":
                fail(f"Tipo PRELOAD no implementado en la línea {line}: {kind!r}.")
            try:
                pair = (int(row["dir_id"]), int(row["file_id"]))
                preload_index = int(row["preload_index"])
                int(row["fila"]); int(row["columna"])
                subpath_value = row.get("subpath_pakd", "").strip()
                if not re.fullmatch(r"\d+(?:[,\s/>]+\d+)*", subpath_value):
                    raise ValueError("subpath_pakd no tiene índices PAKD válidos")
                row["_subpath"] = tuple(int(x) for x in re.findall(r"\d+", subpath_value))
            except Exception:
                fail(f"Identificadores/coordenadas inválidos en TSV PRELOAD, línea {line}.")
            row["_line"] = str(line)
            row["_path"] = row["ruta_gibbed"].replace("\\", "/")
            row["_kind"] = kind
            row["texto_espanol"] = spanish
            pair_set.add(pair)
            index_set.add(preload_index)
            groups[path_key].append(row)
            count += 1
    if len(pair_set) != 1:
        fail(f"El TSV actual debe apuntar a una sola copia PRELOAD; pares encontrados: {sorted(pair_set)}")
    if len(index_set) != 1:
        fail(f"El TSV actual debe apuntar a un solo índice PRELOAD; índices encontrados: {sorted(index_set)}")
    if not groups or count == 0:
        fail("El TSV de PRELOAD no contiene correcciones españolas no vacías.")
    return dict(groups), next(iter(pair_set)), next(iter(index_set)), count


def read_preload_blob(game, builder):
    """Obtiene los bytes actuales del recurso 0/0 (incluidos cambios sincronizados)."""
    mods = builder.leaf_mods.get((0, 0), {})
    if () in mods:
        return mods[()]
    directory = game.ft.dir(0)
    if not directory.get("files"):
        fail("No existe el archivo preload 0/0 en FILETABLE.BIN.")
    entry = directory["files"][0]
    raw = game.bin(0)
    offset = game.ft.offset(directory, entry)
    return raw[offset:offset + entry["size"]]


def replace_pakd_leaf(blob: bytes, indices: tuple[int, ...], replacement: bytes, parse_pakd, build_pakd, is_pakd) -> bytes:
    """Reemplaza una hoja por índices físicos de contenedores PAKD."""
    if not indices:
        return replacement
    if not is_pakd(blob):
        fail(f"La ruta PRELOAD esperaba un PAKD antes del índice {indices[0]}.")
    entries, _has_ids, _total = parse_pakd(blob)
    index = indices[0]
    if index < 0 or index >= len(entries):
        fail(f"Índice PAKD fuera de rango: {index} (entradas={len(entries)}).")
    updated = []
    for i, (raw_id, data) in enumerate(entries):
        updated.append((raw_id, replace_pakd_leaf(data, indices[1:], replacement, parse_pakd, build_pakd, is_pakd) if i == index else data))
    return build_pakd(updated)


def extract_pakd_leaf(blob: bytes, indices: tuple[int, ...], parse_pakd, is_pakd) -> bytes:
    if not indices:
        return blob
    if not is_pakd(blob):
        fail(f"La ruta PRELOAD esperaba un PAKD antes del índice {indices[0]}.")
    entries, _has_ids, _total = parse_pakd(blob)
    index = indices[0]
    if index < 0 or index >= len(entries):
        fail(f"Índice PAKD fuera de rango: {index} (entradas={len(entries)}).")
    return extract_pakd_leaf(entries[index][1], indices[1:], parse_pakd, is_pakd)


def apply_preload_overrides(
    game, builder, tsv_path: Path, path_map, rows_by_file, decode, norm, encode,
    spanmod, mode, parse_pakd, build_pakd, is_pakd,
    choose_xlc_parser, rebuild_xlc_by_cell, supported_chars,
):
    """Reaplica los textos que son exclusivos de la copia PRELOAD 500/10241.

    Primero sincronizamos el BIN principal. Después estos 89 valores especiales
    sobrescriben únicamente sus coordenadas en la copia precargada.
    """
    if not tsv_path:
        return 0
    groups, target_pair, expected_preload_index, expected_count = read_preload_overrides(tsv_path)
    raw_blob = read_preload_blob(game, builder)
    if len(raw_blob) < 4:
        fail("El recurso preload 0/0 está truncado.")
    entry_count = struct.unpack_from("<I", raw_blob, 0)[0]
    table_end = 4 + 8 * entry_count
    if table_end > len(raw_blob):
        fail("La tabla de entradas PRELOAD es inválida.")
    entries = [list(struct.unpack_from("<II", raw_blob, 4 + 8 * i)) for i in range(entry_count)]
    position = table_end
    blocks = []
    for _raw_id, size in entries:
        if position + size > len(raw_blob):
            fail("Un bloque del PRELOAD excede el tamaño del recurso 0/0.")
        blocks.append(raw_blob[position:position + size])
        position += size

    target_indices = []
    for i, (raw_id, _size) in enumerate(entries):
        pair = (raw_id & 0xFFFF, raw_id >> 16)
        if pair == target_pair:
            target_indices.append(i)
    if len(target_indices) != 1:
        fail(f"Se esperaba una sola copia PRELOAD {target_pair}, encontradas: {len(target_indices)}.")
    target_index = target_indices[0]
    if target_index != expected_preload_index:
        fail(
            f"El TSV indica índice PRELOAD {expected_preload_index}, "
            f"pero el par {target_pair} aparece en el índice {target_index}."
        )
    payload = blocks[target_index]

    applied = 0
    for path_key, override_rows in groups.items():
        loc = path_map.get(path_key)
        if loc is None:
            fail(f"El manifiesto Gibbed no contiene la ruta PRELOAD: {override_rows[0]['_path']}.")
        if tuple(loc[:2]) != tuple(target_pair):
            fail(f"La ruta PRELOAD apunta a {loc[:2]}, no a la copia {target_pair}: {override_rows[0]['_path']}.")
        suffix = tuple(loc[2:])
        recorded_subpaths = {tuple(row["_subpath"]) for row in override_rows}
        if recorded_subpaths != {suffix}:
            fail(
                f"La ruta PRELOAD no coincide con subpath_pakd para "
                f"{override_rows[0]['_path']}: TSV={sorted(recorded_subpaths)}, Gibbed={suffix}."
            )
        leaf = extract_pakd_leaf(payload, suffix, parse_pakd, is_pakd)
        if leaf[:4] != b"xlce":
            fail(f"El recurso PRELOAD no es XLC: {override_rows[0]['_path']} -> {loc}.")

        info = choose_xlc_parser(leaf, override_rows, override_rows[0]["_path"], decode)
        main_rows = rows_by_file.get(path_key, [])
        main_by_cell = {
            (int(row["fila"]), int(row["columna"])): row
            for row in main_rows
        }
        prepared = []
        for override in override_rows:
            rr, cc = int(override["fila"]), int(override["columna"])
            pointer = info["cols"][cc][rr]
            current_text, _ = decode(leaf, pointer)
            main_row = main_by_cell.get((rr, cc))
            if main_row is not None:
                expected_current = (
                    main_row.get("texto_espanol", "").strip()
                    and main_row.get("texto_espanol", "")
                ) or main_row.get("texto_ingles", "")
            else:
                expected_current = override.get("texto_bin_principal", "")
            if expected_current and norm(current_text)[2] != norm(expected_current)[2]:
                fail(
                    f"La coordenada PRELOAD no coincide con el BIN reconstruido en "
                    f"{override['_path']} ({rr},{cc}).\n"
                    f"Esperado en BIN: {expected_current[:140]!r}\n"
                    f"Encontrado: {current_text[:140]!r}"
                )
            row = dict(override)
            # Usar el texto de la copia PRELOAD original como plantilla de {span}/{w};
            # el contenido actual puede ser ya la traducción de la versión principal.
            row["texto_ingles"] = override.get("texto_preload", "") or current_text
            row["texto_espanol"] = override["texto_espanol_preload"]
            validate_markers(row, int(row["_line"]))
            validate_charset(row, int(row["_line"]), supported_chars)
            prepared.append(row)

        # Las copias PRELOAD son una variante independiente: aquí usamos append-only
        # para redirigir solo estas celdas, sin alterar punteros compartidos del BIN.
        rebuilt_leaf, n_changed = rebuild_xlc_by_cell(
            leaf, info, prepared, norm, encode, spanmod, mode
        )
        verify_info = choose_xlc_parser(rebuilt_leaf, prepared, override_rows[0]["_path"], decode)
        for row in prepared:
            rr, cc = int(row["fila"]), int(row["columna"])
            decoded, _ = decode(rebuilt_leaf, verify_info["cols"][cc][rr])
            if norm(decoded)[2] != norm(row["texto_espanol"])[2]:
                fail(f"No se verificó la corrección PRELOAD en {row['_path']} ({rr},{cc}).")
        payload = replace_pakd_leaf(payload, suffix, rebuilt_leaf, parse_pakd, build_pakd, is_pakd)
        applied += n_changed
        print(f"  PRELOAD especial: {override_rows[0]['_path']} ({n_changed} celdas append-only aisladas)")

    if applied != expected_count:
        fail(f"Se aplicaron {applied}/{expected_count} correcciones PRELOAD.")

    blocks[target_index] = payload
    entries[target_index][1] = len(payload)
    new_blob = (
        struct.pack("<I", entry_count)
        + b"".join(struct.pack("<II", *entry) for entry in entries)
        + b"".join(blocks)
    )
    builder.leaf_mods[(0, 0)] = {(): new_blob}
    return applied

def verify_output_iso(
    iso_path: Path,
    temp_parent: Path,
    tools_dir: Path,
    rows_by_file: dict[str, list[dict[str, str]]],
    path_map: dict[str, tuple[int, ...]],
    parse_emes,
    decode,
    norm,
    preload_tsv_path: Path,
    choose_xlc_parser,
    parse_pakd,
    is_pakd,
    unchanged_originals: dict[str, bytes] | None = None,
) -> tuple[int, int]:
    """Reabre la ISO terminada y verifica el texto español de cada celda insertada."""
    verify_dir = temp_parent / "VERIFY_USRDIR"
    game, _font = extract_usrdir(iso_path, verify_dir, tools_dir)
    leaves = {tuple(path): blob for path, blob in game.leaves()}
    verified = 0

    for path_key, original_blob in (unchanged_originals or {}).items():
        loc = path_map.get(path_key)
        actual_blob = leaves.get(loc) if loc is not None else None
        if actual_blob is None:
            fail(f"VERIFICACIÓN: no aparece el recurso que debía quedar intacto: {path_key}.")
        if actual_blob != original_blob:
            fail(f"VERIFICACIÓN: el recurso excluido no conservó sus bytes originales: {path_key}.")
        print(f"  Recurso intacto verificado byte por byte: {path_key}")

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
    # Verificar también las correcciones exclusivas del PRELOAD dentro de 0000.BIN.
    preload_groups, target_pair, expected_preload_index, expected_preload_count = read_preload_overrides(preload_tsv_path)
    preload_dir = game.ft.dir(0)
    if not preload_dir.get("files"):
        fail("VERIFICACIÓN PRELOAD: no existe el archivo 0/0 dentro de 0000.BIN.")
    preload_file = preload_dir["files"][0]
    preload_raw = game.bin(0)
    preload_offset = game.ft.offset(preload_dir, preload_file)
    preload_blob = preload_raw[preload_offset:preload_offset + preload_file["size"]]
    if len(preload_blob) < 4:
        fail("VERIFICACIÓN PRELOAD: el blob 0/0 está truncado.")
    preload_count = struct.unpack_from("<I", preload_blob, 0)[0]
    preload_table_end = 4 + 8 * preload_count
    if preload_table_end > len(preload_blob):
        fail("VERIFICACIÓN PRELOAD: la tabla de entradas es inválida.")
    preload_entries = [
        list(struct.unpack_from("<II", preload_blob, 4 + 8 * i))
        for i in range(preload_count)
    ]
    preload_pos = preload_table_end
    preload_blocks = []
    for _raw_id, size in preload_entries:
        if preload_pos + size > len(preload_blob):
            fail("VERIFICACIÓN PRELOAD: un bloque supera el tamaño de 0/0.")
        preload_blocks.append(preload_blob[preload_pos:preload_pos + size])
        preload_pos += size

    matching_indexes = [
        i for i, (raw_id, _size) in enumerate(preload_entries)
        if (raw_id & 0xFFFF, raw_id >> 16) == target_pair
    ]
    if matching_indexes != [expected_preload_index]:
        fail(
            f"VERIFICACIÓN PRELOAD: se esperaba {target_pair} en índice "
            f"{expected_preload_index}; encontrado en {matching_indexes}."
        )
    preload_payload = preload_blocks[expected_preload_index]
    preload_verified = 0
    for path_key, override_rows in preload_groups.items():
        loc = path_map.get(path_key)
        if loc is None or tuple(loc[:2]) != tuple(target_pair):
            fail(f"VERIFICACIÓN PRELOAD: ruta no asignada a {target_pair}: {override_rows[0]['_path']}.")
        preload_leaf = extract_pakd_leaf(preload_payload, tuple(loc[2:]), parse_pakd, is_pakd)
        if preload_leaf[:4] != b"xlce":
            fail(f"VERIFICACIÓN PRELOAD: la hoja no es XLC: {override_rows[0]['_path']}.")
        preload_info = choose_xlc_parser(preload_leaf, override_rows, override_rows[0]["_path"], decode)
        for row in override_rows:
            rr, cc = int(row["fila"]), int(row["columna"])
            pointer = preload_info["cols"][cc][rr]
            actual, _ = decode(preload_leaf, pointer)
            expected = row["texto_espanol_preload"]
            if norm(actual)[2] != norm(expected)[2]:
                fail(
                    f"VERIFICACIÓN PRELOAD: texto distinto en {row['_path']} ({rr},{cc}).\n"
                    f"Esperado: {norm(expected)[2][:160]!r}\nEncontrado: {norm(actual)[2][:160]!r}"
                )
            preload_verified += 1
    if preload_verified != expected_preload_count:
        fail(f"VERIFICACIÓN PRELOAD: {preload_verified}/{expected_preload_count} textos comprobados.")

    return verified, preload_verified


def main() -> int:
    parser = argparse.ArgumentParser(description="Inserta el CSV de español neutral en una ISO One Vision.")
    parser.add_argument("--iso", required=True, help="ISO base One Vision; el archivo de entrada no se modifica.")
    parser.add_argument("--csv", required=True, help="CSV completo de traducciones por ubicación, por ejemplo *_desde_hash.csv.")
    parser.add_argument("--gibbed-root", required=True, help="Carpeta extraída por Gibbed que contiene @manifest.toml")
    parser.add_argument("--french-tools", required=True, help="Carpeta FrenchTools (contiene la subcarpeta outils)")
    parser.add_argument("--output", required=True, help="ISO nueva de salida; no debe ser la ISO de entrada.")
    parser.add_argument("--preload-tsv", required=True, help="Correcciones especiales de la copia PRELOAD (preload_xlc_emes_traducido.tsv).")
    parser.add_argument("--dry-run", action="store_true", help="Valida y calcula todo, pero no crea la ISO.")
    parser.add_argument("--span-mode", choices=("recompute", "keep"), default="recompute", help="Tratamiento de los encabezados {span}.")
    parser.add_argument(
        "--restore-english-files",
        nargs="+",
        default=[],
        metavar="RUTA_XLC",
        help=(
            "Para una prueba diagnóstica, restaura a su texto inglés original todas las celdas "
            "de los recursos indicados, incluso si el CSV contiene una traducción. "
            "Las rutas deben coincidir con la columna archivo."
        ),
    )
    parser.add_argument(
        "--leave-files-unchanged",
        nargs="+",
        default=[],
        metavar="RUTA_XLC",
        help=(
            "Prueba diagnóstica: deja los recursos indicados byte por byte como están en la ISO base. "
            "No se reconstruyen ni se reescriben. Las rutas deben coincidir con la columna archivo."
        ),
    )
    args = parser.parse_args()

    iso_path = Path(args.iso).expanduser().resolve()
    csv_path = Path(args.csv).expanduser().resolve()
    gibbed_root = Path(args.gibbed_root).expanduser().resolve()
    french_root = Path(args.french_tools).expanduser().resolve()
    tools_dir = french_root / "outils"
    output_path = Path(args.output).expanduser().resolve()
    preload_tsv_path = Path(args.preload_tsv).expanduser().resolve()
    if not preload_tsv_path.is_file(): fail(f"No existe el TSV de PRELOAD: {preload_tsv_path}")
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
    from xlc_fixed import parse_xlc as parse_xlc_fixed, build_xlc as build_xlc_fixed
    from pakd import is_pakd, parse_pakd, build_pakd

    rows, rows_by_file, csv_stats = read_translation_csv(csv_path, set(U2B) | set(FALLBACK))

    # Una celda española vacía significa "no sobrescribir la ISO base"; no significa
    # "restaurar el inglés". Para poder aislar recursos de una ISO que ya está traducida,
    # esta opción fuerza explícitamente el inglés original en todos los registros de
    # los archivos XLC seleccionados.
    restore_paths = {norm_path(value) for value in args.restore_english_files}
    unchanged_paths = {norm_path(value) for value in args.leave_files_unchanged}
    overlap = restore_paths & unchanged_paths
    if overlap:
        fail("Un recurso no puede restaurarse al inglés y dejarse intacto a la vez: " + ", ".join(sorted(overlap)))
    restore_count = 0
    if restore_paths:
        missing_restore = sorted(restore_paths - set(rows_by_file))
        if missing_restore:
            fail(
                "No se encontraron estos recursos de --restore-english-files en el CSV: "
                + ", ".join(missing_restore)
            )
        for path_key in sorted(restore_paths):
            file_rows = rows_by_file[path_key]
            if any(row["_kind"] != "XLC" for row in file_rows):
                fail(f"--restore-english-files solo admite XLC: {file_rows[0]['_path']}")
            restored_in_file = 0
            for row in file_rows:
                english = row.get("texto_ingles", "")
                if english.strip():
                    row["texto_espanol"] = english
                    line = int(row["_line"])
                    validate_markers(row, line)
                    validate_charset(row, line, set(U2B) | set(FALLBACK))
                    restore_count += 1
                    restored_in_file += 1
                else:
                    # Las celdas sin texto inglés permanecen vacías y no se reemplazan.
                    row["texto_espanol"] = ""
            print(f"  Restauración temporal al inglés: {file_rows[0]['_path']} ({restored_in_file} celdas)")

        csv_stats["translated"] = sum(1 for row in rows if row.get("texto_espanol", "").strip())
        csv_stats["blank_es"] = len(rows) - csv_stats["translated"]

    unchanged_row_count = 0
    if unchanged_paths:
        missing_unchanged = sorted(unchanged_paths - set(rows_by_file))
        if missing_unchanged:
            fail(
                "No se encontraron estos recursos de --leave-files-unchanged en el CSV: "
                + ", ".join(missing_unchanged)
            )
        for path_key in sorted(unchanged_paths):
            file_rows = rows_by_file[path_key]
            if any(row["_kind"] != "XLC" for row in file_rows):
                fail(f"--leave-files-unchanged solo admite XLC: {file_rows[0]['_path']}")
            unchanged_row_count += len(file_rows)
            for row in file_rows:
                row["texto_espanol"] = ""
            print(
                f"  Recurso dejado intacto (sin reescritura): {file_rows[0]['_path']} "
                f"({len(file_rows)} celdas del CSV)"
            )
        csv_stats["translated"] = sum(1 for row in rows if row.get("texto_espanol", "").strip())
        csv_stats["blank_es"] = len(rows) - csv_stats["translated"]

    print("CSV leído:", csv_path)
    print("  Registros:", csv_stats["rows"])
    if restore_paths:
        print("  Celdas que se escribirán (incluye inglés de prueba):", csv_stats["translated"])
        print("  Celdas restauradas temporalmente al inglés:", restore_count)
    else:
        print("  Traducciones no vacías:", csv_stats["translated"])
    if unchanged_paths:
        print("  Celdas de recursos excluidos (se conservan byte por byte):", unchanged_row_count)
    print("  Celdas vacías (se conservarán como están en la ISO base):", csv_stats["blank_es"])
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

    temp_dir_obj = tempfile.TemporaryDirectory(prefix="TO_OneVision_ES_v3_")
    temp_dir = Path(temp_dir_obj.name)
    font_path = tools_dir / "normal.font"
    old_font = font_path.read_bytes() if font_path.exists() else None
    try:
        print("Extrayendo USRDIR desde la ISO base...")
        game, normal_font = extract_usrdir(iso_path, temp_dir / "USRDIR", tools_dir)
        font_path.write_bytes(normal_font)

        leaves = {tuple(p): b for p, b in game.leaves()}
        unchanged_originals = {
            path_key: leaves[path_map[path_key]]
            for path_key in unchanged_paths
        }
        builder = Builder(game)
        changed_files = 0
        changed_records = 0
        processed_xlc = processed_emes = 0
        compact_xlc_files = append_xlc_files = 0
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
                # Verificar también las filas vacías y el inglés para detectar desajustes de versión.
                for r in file_rows:
                    rr, cc = int(r["fila"]), int(r["columna"])
                    if not (0 <= rr < info["n"]) or cc not in info["cols"] or not info["cols"][cc][rr]:
                        fail(f"Ubicación XLC inválida en línea {r['_line']}: {file_path}, fila {rr}, columna {cc}.")
                validate_xlc_sources(blob, info, file_rows, decode, norm, file_path)
                if translated_rows:
                    compact_blob, compact_count, compact_reason = rebuild_xlc_compact_safe(
                        blob, file_rows, parse_xlc_fixed, build_xlc_fixed, decode, norm,
                        encode, spanmod, args.span_mode, file_path
                    )
                    if compact_blob is not None:
                        new_blob, n_changed = compact_blob, compact_count
                        compact_xlc_files += 1
                        print(f"  XLC compacto: {file_path}")
                    else:
                        new_blob, n_changed = rebuild_xlc_by_cell(
                            blob, info, translated_rows, norm, encode, spanmod, args.span_mode
                        )
                        append_xlc_files += 1
                        print(f"  XLC append-only (estructura especial): {file_path} — {compact_reason}")
                    if new_blob != blob:
                        builder.set_leaf(loc, new_blob)
                        changed_files += 1
                        changed_records += n_changed
                    processed_xlc += len(translated_rows)
            elif kind == "EMES":
                if blob[:4] != b"EMES":
                    fail(f"El CSV marca EMES, pero el recurso no comienza con EMES: {file_path} -> {loc}")
                parsed = parse_emes(blob)
                validate_emes_sources(parsed, file_rows, norm, file_path)
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
        print("  XLC reconstruidos compactamente:", compact_xlc_files)
        print("  XLC conservados append-only por seguridad:", append_xlc_files)
        print("  Recursos BIN/PAKD con cambios:", changed_files)

        print("Sincronizando copias PRELOAD...")
        sync_preload_blob(game, builder)
        print("Aplicando correcciones especiales del PRELOAD...")
        preload_applied = apply_preload_overrides(
            game, builder, preload_tsv_path, path_map, rows_by_file, decode, norm,
            encode, spanmod, args.span_mode, parse_pakd, build_pakd, is_pakd,
            choose_xlc_parser, rebuild_xlc_by_cell, set(U2B) | set(FALLBACK)
        )
        print("  Correcciones especiales PRELOAD aplicadas:", preload_applied)

        if args.dry_run:
            # También se construyen los contenedores en memoria para detectar errores de empaquetado.
            preview = builder.build()
            print("  BIN/FILETABLE listos para reconstrucción:", ", ".join(sorted(preview)))
            print("\nDRY-RUN correcto: XLC/EMES, contenedores y PRELOAD validados; no se creó ninguna ISO.")
            return 0

        replacements = builder.build()
        iso_replacements = {"/PSP_GAME/USRDIR/" + name: data for name, data in replacements.items()}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print("Reconstruyendo ISO de salida...")
        rebuild_iso(str(iso_path), str(output_path), iso_replacements)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            fail("No se pudo verificar el archivo ISO de salida.")
        print("Verificando la ISO reconstruida...")
        verified, preload_verified = verify_output_iso(
            output_path, temp_dir, tools_dir, rows_by_file, path_map,
            parse_emes, decode, norm, preload_tsv_path, choose_xlc_parser,
            parse_pakd, is_pakd, unchanged_originals
        )
        if verified != total_expected:
            fail(f"La verificación final encontró {verified}/{total_expected} textos principales.")
        print("  Textos principales verificados:", verified)
        print("  Correcciones PRELOAD verificadas:", preload_verified)
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
