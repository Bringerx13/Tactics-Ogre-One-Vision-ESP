#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Integra un lote JSON traducido en el diccionario principal, validando hashes."""
from __future__ import annotations
import argparse, json, re, shutil
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description="Fusiona un lote de traducciones JSON.")
    p.add_argument("lote",help="JSON con hash -> español.")
    p.add_argument("--traducciones",default="JSON_Translation/traducciones.json")
    p.add_argument("--catalogo",default="JSON_Translation/catalogo_textos.json")
    p.add_argument("--permitir-conflictos",action="store_true")
    p.add_argument("--sobrescribir",action="store_true")
    a=p.parse_args()
    lote_path=Path(a.lote); dict_path=Path(a.traducciones); cat_path=Path(a.catalogo)
    for path in (lote_path,dict_path,cat_path):
        if not path.is_file(): p.error(f"No existe el archivo: {path}")
    lote=json.loads(lote_path.read_text(encoding="utf-8"))
    traducciones=json.loads(dict_path.read_text(encoding="utf-8"))
    catalogo=json.loads(cat_path.read_text(encoding="utf-8"))
    if not isinstance(lote,dict): p.error("El lote debe ser un objeto JSON hash -> traducción.")
    invalid=[]; unknown=[]; conflicts=[]; already=[]; merged=0
    for h,es in lote.items():
        if not re.fullmatch(r"[0-9a-f]{12}",h):
            invalid.append(h); continue
        if h not in catalogo:
            unknown.append(h); continue
        if not isinstance(es,str) or not es.strip():
            invalid.append(h); continue
        if catalogo[h].get("estado")=="conflicto_contexto" and not a.permitir_conflictos:
            conflicts.append(h); continue
        if h in traducciones and not a.sobrescribir:
            already.append(h); continue
        traducciones[h]=es
        merged+=1
    if invalid or unknown or conflicts:
        print("No se modificó el diccionario: el lote contiene entradas que requieren revisión.")
        if invalid: print("Claves/valores inválidos:",len(invalid),invalid[:10])
        if unknown: print("Hashes inexistentes en el catálogo:",len(unknown),unknown[:10])
        if conflicts: print("Hashes con conflicto contextual:",len(conflicts),conflicts[:10])
        return 2
    backup=dict_path.with_suffix(dict_path.suffix+".bak")
    shutil.copy2(dict_path,backup)
    dict_path.write_text(json.dumps(traducciones,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Traducciones agregadas/actualizadas: {merged}")
    print(f"Ya existentes sin sobrescribir: {len(already)}")
    print(f"Copia de seguridad: {backup}")
    print(f"Diccionario actualizado: {dict_path}")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
