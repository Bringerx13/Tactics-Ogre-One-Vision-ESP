
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exporta textos XLC y EMES de una carpeta extraida por Gibbed.

Uso:
    python export_gibbed_text_to_csv.py CARPETA_EXTRAIDA CARPETA_SALIDA

Requiere los modulos de FrenchTools en la misma carpeta:
    codec.py
    xlc_fixed.py
    xlc.py (opcional)
    charmap_en.json
"""

from __future__ import annotations

import csv
import re
import struct
import sys
from collections import Counter
from pathlib import Path

# Permite importar los modulos de FrenchTools desde esta carpeta.
HERE = Path(__file__).resolve().parent

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

try:
    from codec import decode
    from xlc_fixed import parse_xlc as parse_xlc_fixed

except Exception as exc:
    raise SystemExit(
        "No se pudieron cargar los modulos de FrenchTools.\n"
        "Coloca este script junto a codec.py, xlc_fixed.py "
        "y charmap_en.json.\n"
        f"Detalle: {type(exc).__name__}: {exc}"
    )

try:
    from xlc import parse_xlc as parse_xlc_legacy
except Exception:
    parse_xlc_legacy = None


PLACEHOLDER_RE = re.compile(r"\{[^}]*\}")


def placeholders(text: str) -> str:
    """Extrae los marcadores de control del texto."""
    found = sorted(PLACEHOLDER_RE.findall(text))
    return " | ".join(found)


def parse_xlc_resource(blob: bytes):
    """Interpreta un XLC y devuelve sus columnas de texto."""

    parsers = [
        ("xlc_fixed", parse_xlc_fixed)
    ]

    if parse_xlc_legacy is not None:
        parsers.append(("xlc", parse_xlc_legacy))

    errors = []

    for name, parser in parsers:

        try:
            info = parser(blob)

        except Exception as exc:
            errors.append(
                f"{name}: {type(exc).__name__}: {exc}"
            )
            continue

        if not info:
            continue

        cols = info.get("cols")

        if not isinstance(cols, dict):
            errors.append(
                f"{name}: el parser no devolvio columnas"
            )
            continue

        strcols = info.get("strcols")

        if strcols:
            return info, sorted(strcols)

        # Respaldo para parsers sin strcols.
        hend = info.get("hend")

        if hend is None:
            hend = 16 + info["n"] * info["es"]

        valid_cols = []

        for col, values in cols.items():

            offsets = {
                value for value in values if value
            }

            if not offsets:
                continue

            valid = all(
                hend <= off < len(blob)
                and (
                    off == hend
                    or blob[off - 1] == 0
                    or blob[off] == 0
                )
                for off in offsets
            )

            if not valid:
                continue

            try:
                for off in offsets:
                    decode(blob, off)

            except Exception:
                continue

            valid_cols.append(col)

        if valid_cols:
            return info, sorted(valid_cols)

    return None, errors


def decode_xlc_cell(
    blob: bytes,
    info: dict,
    col: int,
    row: int
) -> str:

    off = info["cols"][col][row]

    if not off:
        return ""

    value, _end = decode(blob, off)

    return value


def parse_emes_resource(blob: bytes):
    """Lee las entradas de un archivo EMES."""

    if len(blob) < 8 or blob[:4] != b"EMES":
        raise ValueError("cabecera EMES no valida")

    count = struct.unpack_from("<H", blob, 4)[0]

    ids_end = 8 + (2 * count)

    if ids_end > len(blob):
        raise ValueError("tabla de IDs incompleta")

    if count:
        ids = struct.unpack_from(
            f"<{count}H",
            blob,
            8
        )
    else:
        ids = ()

    offsets_pos = (ids_end + 3) & ~3
    offsets_end = offsets_pos + (4 * count)

    if offsets_end > len(blob):
        raise ValueError("tabla de offsets incompleta")

    if count:
        offsets = struct.unpack_from(
            f"<{count}I",
            blob,
            offsets_pos
        )
    else:
        offsets = ()

    entries = []

    for index, (entry_id, offset) in enumerate(
        zip(ids, offsets)
    ):

        if offset + 2 > len(blob):
            raise ValueError(
                f"offset fuera del archivo en entrada {index}"
            )

        nid = struct.unpack_from(
            "<H",
            blob,
            offset
        )[0]

        text, _end = decode(blob, offset + 2)

        entries.append(
            (index, entry_id, nid, text)
        )

    return entries


def scan_files(root: Path):
    """Busca archivos XLC y EMES por su cabecera binaria."""

    for path in sorted(root.rglob("*")):

        if not path.is_file():
            continue

        try:
            with path.open("rb") as file:
                magic = file.read(4)

            if magic in (b"xlce", b"EMES"):
                yield path, magic

        except OSError:
            yield path, b"READ"


def main() -> int:

    if len(sys.argv) != 3:

        print(
            "Uso:\n"
            "python export_gibbed_text_to_csv.py "
            "CARPETA_EXTRAIDA CARPETA_SALIDA"
        )

        return 2

    source_dir = Path(sys.argv[1]).expanduser()
    output_dir = Path(sys.argv[2]).expanduser()

    if not source_dir.is_dir():

        print(
            f"ERROR: no existe la carpeta extraida: {source_dir}"
        )

        return 2

    if source_dir.resolve() == output_dir.resolve():

        print(
            "ERROR: la carpeta de salida no puede "
            "ser la misma que la fuente."
        )

        return 2

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    csv_path = (
        output_dir
        / "Tactics_Ogre_Textos_English_Original.csv"
    )

    summary_path = (
        output_dir
        / "Tactics_Ogre_Export_Resumen.txt"
    )

    skipped_path = (
        output_dir
        / "Tactics_Ogre_Archivos_Sin_Texto_o_Error.txt"
    )

    fields = [
        "archivo",
        "tipo",
        "fila",
        "columna",
        "id_entrada",
        "nid",
        "texto_ingles",
        "caracteres",
        "marcadores",
        "estado"
    ]

    totals = Counter()
    by_file = Counter()
    by_type = Counter()

    skipped = []
    errors = []

    rows_written = 0

    print(f"Carpeta de origen: {source_dir}")
    print("Buscando recursos XLC y EMES...")

    with csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=fields
        )

        writer.writeheader()

        for file_path, magic in scan_files(source_dir):

            relative = str(
                file_path.relative_to(source_dir)
            ).replace("\\", "/")

            totals["recursos_detectados"] += 1

            if magic == b"READ":

                errors.append(
                    f"{relative}: no se pudo leer el archivo"
                )

                continue

            try:

                blob = file_path.read_bytes()

                # =====================================
                # ARCHIVOS XLC
                # =====================================

                if magic == b"xlce":

                    info, parsed = parse_xlc_resource(blob)

                    if info is None:

                        reason = (
                            "; ".join(parsed)
                            if parsed
                            else "sin columnas de texto detectables"
                        )

                        skipped.append(
                            f"{relative} [XLC]: {reason}"
                        )

                        totals[
                            "xlc_sin_texto_o_estructural"
                        ] += 1

                        continue

                    file_count = 0

                    for col in parsed:

                        for row in range(info["n"]):

                            text = decode_xlc_cell(
                                blob,
                                info,
                                col,
                                row
                            )

                            if not text.strip():
                                continue

                            writer.writerow({

                                "archivo": relative,
                                "tipo": "XLC",
                                "fila": row,
                                "columna": col,
                                "id_entrada": "",
                                "nid": "",
                                "texto_ingles": text,
                                "caracteres": len(text),
                                "marcadores": placeholders(text),
                                "estado":
                                    "ORIGINAL - PENDIENTE DE TRADUCCION"

                            })

                            rows_written += 1
                            file_count += 1

                    by_type["XLC"] += file_count
                    by_file[relative] += file_count

                    if file_count == 0:

                        skipped.append(
                            f"{relative} [XLC]: "
                            "no habia cadenas no vacias"
                        )

                        totals[
                            "xlc_sin_texto_o_estructural"
                        ] += 1

                    else:

                        totals["xlc_con_texto"] += 1

                # =====================================
                # ARCHIVOS EMES
                # =====================================

                elif magic == b"EMES":

                    entries = parse_emes_resource(blob)

                    file_count = 0

                    for index, entry_id, nid, text in entries:

                        if not text.strip():
                            continue

                        writer.writerow({

                            "archivo": relative,
                            "tipo": "EMES",
                            "fila": index,
                            "columna": "",
                            "id_entrada": entry_id,
                            "nid": nid,
                            "texto_ingles": text,
                            "caracteres": len(text),
                            "marcadores": placeholders(text),
                            "estado":
                                "ORIGINAL - PENDIENTE DE TRADUCCION"

                        })

                        rows_written += 1
                        file_count += 1

                    by_type["EMES"] += file_count
                    by_file[relative] += file_count

                    if file_count == 0:

                        skipped.append(
                            f"{relative} [EMES]: "
                            "no contiene cadenas no vacias"
                        )

                        totals["emes_sin_texto"] += 1

                    else:

                        totals["emes_con_texto"] += 1

            except Exception as exc:

                errors.append(
                    f"{relative}: "
                    f"{type(exc).__name__}: {exc}"
                )

                totals["errores"] += 1

    # =====================================
    # RESUMEN DE LA EXTRACCION
    # =====================================

    with summary_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "EXPORTACION DE TEXTOS GIBBED - SOLO LECTURA\n"
        )

        file.write(
            f"Carpeta de origen: {source_dir}\n"
        )

        file.write(
            f"Carpeta de salida: {output_dir}\n\n"
        )

        file.write(
            f"Recursos XLC/EMES detectados: "
            f"{totals['recursos_detectados']}\n"
        )

        file.write(
            f"Archivos XLC con texto: "
            f"{totals['xlc_con_texto']}\n"
        )

        file.write(
            f"Archivos EMES con texto: "
            f"{totals['emes_con_texto']}\n"
        )

        file.write(
            f"Celdas XLC exportadas: "
            f"{by_type['XLC']}\n"
        )

        file.write(
            f"Entradas EMES exportadas: "
            f"{by_type['EMES']}\n"
        )

        file.write(
            f"Total de textos exportados: "
            f"{rows_written}\n"
        )

        file.write(
            f"XLC estructurales/sin texto: "
            f"{totals['xlc_sin_texto_o_estructural']}\n"
        )

        file.write(
            f"EMES sin texto: "
            f"{totals['emes_sin_texto']}\n"
        )

        file.write(
            f"Errores: {totals['errores']}\n\n"
        )

        file.write("TEXTOS EXPORTADOS POR ARCHIVO\n")

        for name, count in sorted(by_file.items()):

            file.write(
                f"  {name}: {count}\n"
            )

        file.write(
            "\nNo se modifico ningun archivo fuente, BIN ni ISO.\n"
        )

    # =====================================
    # ARCHIVOS OMITIDOS Y ERRORES
    # =====================================

    with skipped_path.open(
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "ARCHIVOS SIN TEXTO DETECTABLE O CON ERRORES\n\n"
        )

        if not skipped and not errors:

            file.write(
                "No se encontraron archivos para listar.\n"
            )

        if skipped:

            file.write(
                "SIN TEXTO / ESTRUCTURALES\n"
            )

            for item in skipped:
                file.write(item + "\n")

        if errors:

            file.write("\nERRORES\n")

            for item in errors:
                file.write(item + "\n")

    # =====================================
    # RESULTADO FINAL
    # =====================================

    print("\nEXPORTACION TERMINADA")

    print(f"CSV: {csv_path}")

    print(f"Textos exportados: {rows_written}")

    print(f"XLC: {by_type['XLC']} textos")

    print(f"EMES: {by_type['EMES']} textos")

    print(f"Resumen: {summary_path}")

    print(
        f"Archivos sin texto/errores: {skipped_path}"
    )

    print(
        "No se modifico ningun archivo fuente, BIN ni ISO."
    )

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
