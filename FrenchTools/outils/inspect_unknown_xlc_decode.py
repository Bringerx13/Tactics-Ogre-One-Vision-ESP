#!/usr/bin/env python3
"""Detailed read-only decoder diagnostics for unsupported One Vision XLC."""
import os, sys, struct
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
from tree import Game
from codec import decode

def main():
    if len(sys.argv)!=5:
        print('Uso: python inspect_unknown_xlc_decode.py "<USRDIR>" <dir> <file> <leaf>')
        return 2
    root=os.path.abspath(sys.argv[1])
    did,fid,leaf=(int(x,0) for x in sys.argv[2:])
    game=Game(root)
    target=(did,fid,leaf)
    b=next((data for path,data in game.leaves() if path==target),None)
    if b is None: raise RuntimeError("No se encontro la hoja: "+repr(target))
    if b[:4]!=b"xlce": raise RuntimeError("No tiene firma xlce")
    n,do,es=struct.unpack_from("<III",b,4); hend=16+n*es
    print(f"RECURSO={target} bytes={len(b)} n={n} es={es} hend=0x{hend:X}",flush=True)
    cols={}
    for c in range(0,es-3,4):
        cols[c]=[struct.unpack_from("<I",b,16+r*es+c)[0] for r in range(n)]
    for c,vals in cols.items():
        nz=[(r,v) for r,v in enumerate(vals) if v]
        if not nz: continue
        valid=[(r,v) for r,v in nz if hend<=v<len(b) and (v==hend or b[v-1]==0 or b[v]==0)]
        ok=[]; errors=[]; first_text=[]
        for r,v in valid:
            try:
                s,e=decode(b,v)
                ok.append((r,v,s,e))
                if len(first_text)<4: first_text.append((r,v,s[:90]))
            except Exception as ex:
                errors.append((r,v,type(ex).__name__,str(ex)))
        invalid=[(r,v) for r,v in nz if not (hend<=v<len(b) and (v==hend or b[v-1]==0 or b[v]==0))]
        print(f"\nCOL {c:02X}: nonzero={len(nz)} valid_pointer={len(valid)} decode_ok={len(ok)} decode_errors={len(errors)} invalid_pointer={len(invalid)}",flush=True)
        print("  sample decoded:",first_text,flush=True)
        print("  invalid pointers:",[(r,f"0x{v:X}", (b[v-1] if v>0 else None), (b[v] if v<len(b) else None)) for r,v in invalid[:30]],flush=True)
        for r,v,etype,msg in errors[:100]:
            lo=max(hend,v-12); hi=min(len(b),v+80)
            print(f"  DECODE_ERROR row={r} ptr=0x{v:X} prev={b[v-1] if v>0 else None} here={b[v]} {etype}: {msg}",flush=True)
            print("    HEX:",b[lo:hi].hex(" "),flush=True)
        # How often pointer aliases an identical offset from another string column.
        if c in (4,8):
            for r,v,s,e in ok:
                if s and ("INDIRECT spell that SHACKLES" in s or "deals ICE damage in an AREA" in s):
                    print(f"  TARGET row={r} ptr=0x{v:X} end=0x{e:X} text={s[:130]!r}",flush=True)
    # Exact parser outcomes, to compare against the manual test.
    from xlc import parse_xlc
    from xlc_fixed import parse_xlc as parse_fixed
    for name,fn in (("normal",parse_xlc),("fixed",parse_fixed)):
        try:
            result=fn(b)
            print(f"\nPARSER {name}: {'OK' if result is not None else 'NONE'}",flush=True)
            if result: print("  strcols=",result['strcols'],"slots=",len(result['slots']),"aliases=",len(result.get('aliases',{})),flush=True)
        except Exception as ex:
            print(f"\nPARSER {name}: ERROR {type(ex).__name__}: {ex}",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
