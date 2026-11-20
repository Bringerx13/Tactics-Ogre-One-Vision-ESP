#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Exporta un lote de textos únicos pendientes en formato JSON hash -> inglés."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

def first_location(item):
    locations=item.get("ubicaciones") or [{}]
    loc=locations[0]
    try: row=int(loc.get("fila") or 0)
    except (TypeError, ValueError): row=0
    try: col=int(loc.get("columna") or 0)
    except (TypeError, ValueError): col=0
    return (loc.get("archivo") or "", row, col, item.get("hash") or "")

def main():
    p=argparse.ArgumentParser(description="Crea un bloque JSON de textos ingleses únicos pendientes.")
    p.add_argument("--catalogo",default="JSON_Translation/catalogo_textos.json")
    p.add_argument("--traducciones",default="JSON_Translation/traducciones.json")
    p.add_argument("--limite",type=int,default=200)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--archivo",default=None,help="Filtra por una parte de la ruta del archivo.")
    p.add_argument("--incluir-conflictos",action="store_true",help="Incluye grupos con variantes por contexto; úsalos solo para revisión.")
    p.add_argument("--salida",default="JSON_Translation/lote_para_traducir.json")
    a=p.parse_args()
    catalogo=json.loads(Path(a.catalogo).read_text(encoding="utf-8"))
    traducciones=json.loads(Path(a.traducciones).read_text(encoding="utf-8"))
    candidatos=[]
    for h,item in catalogo.items():
        if h in traducciones:
            continue
        estado=item.get("estado")
        if estado!="pendiente" and not (a.incluir_conflictos and estado=="conflicto_contexto"):
            continue
        if a.archivo and not any(a.archivo.lower() in f.lower() for f in item.get("archivos",[])):
            continue
        texto=item.get("texto_ingles","")
        # Mantiene el criterio de FrenchTools: al menos una letra fuera de marcadores.
        visible=re.sub(r"\{[^}]*\}","",texto)
        if not re.search(r"[A-Za-z]",visible):
            continue
        candidatos.append((first_location(item),h,texto))
    candidatos.sort(key=lambda x:x[0])
    lote=candidatos[a.offset:a.offset+a.limite]
    datos={h:texto for _,h,texto in lote}
    salida=Path(a.salida)
    salida.parent.mkdir(parents=True,exist_ok=True)
    salida.write_text(json.dumps(datos,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Textos pendientes elegibles: {len(candidatos)}")
    print(f"Lote exportado: {len(lote)}")
    print(f"Rango: {a.offset+1}–{a.offset+len(lote)}")
    print(f"Archivo: {salida}")
    print("El valor de cada clave es el inglés que se debe traducir.")
if __name__=="__main__":
    main()
