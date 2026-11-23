#!/usr/bin/env python3
"""Read-only analysis of all string offsets in an unsupported XLC leaf."""
import os, sys, struct
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
from tree import Game
from codec import decode, encode

def main():
    if len(sys.argv)!=5:
        print('Uso: python analyze_unknown_xlc_offsets.py "<USRDIR>" <dir> <file> <leaf>')
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
    candidates=[]
    for c in (4,8):
        for r,v in enumerate(cols[c]):
            if v and hend<=v<len(b):
                candidates.append((v,c,r))
    starts=sorted(set(v for v,_,_ in candidates))
    decoded={}
    for v in starts:
        try:
            s,e=decode(b,v)
            raw=b[v:e-1]
            rebuilt,_=encode(s)
            decoded[v]=(s,e,raw==rebuilt,None)
        except Exception as ex:
            decoded[v]=(None,None,False,f"{type(ex).__name__}: {ex}")
    print("OFFSETS_UNICOS:",len(starts),"DECODE_OK:",sum(x[1] is not None for x in decoded.values()),
          "DECODE_ERROR:",sum(x[1] is None for x in decoded.values()),
          "BYTE_ROUNDTRIP_OK:",sum(x[2] for x in decoded.values()),flush=True)

    for c in (4,8):
        vals=cols[c]
        nz=[(r,v) for r,v in enumerate(vals) if v]
        clean=[(r,v) for r,v in nz if v>=hend and v<len(b) and (v==hend or b[v-1]==0)]
        odd=[(r,v) for r,v in nz if v>=hend and v<len(b) and not (v==hend or b[v-1]==0)]
        outside=[(r,v) for r,v in nz if not (hend<=v<len(b))]
        odd_dec=[(r,v) for r,v in odd if decoded.get(v,(None,None,False,"x"))[1] is not None]
        odd_err=[(r,v) for r,v in odd if decoded.get(v,(None,None,False,"x"))[1] is None]
        print(f"\nCOL {c:02X}: total={len(nz)} clean_boundary={len(clean)} nonzero_prevbyte={len(odd)} outside={len(outside)}",
              f"odd_decode_ok={len(odd_dec)} odd_decode_error={len(odd_err)}",flush=True)
        print("  FIRST 30 ODD OFFSETS:",flush=True)
        for r,v in odd[:30]:
            s,e,rt,err=decoded.get(v,(None,None,False,"missing"))
            prev=starts[starts.index(v)-1] if v in starts and starts.index(v)>0 else None
            covering=[]
            for p in starts:
                if p>=v: break
                ps,pe,_,perr=decoded[p]
                if pe is not None and p < v < pe:
                    covering.append((p,pe))
            pref=b[max(0,v-8):v]
            span_candidates=[]
            for back in range(1,9):
                q=v-back
                if q>=hend and b[q]==0xFC:
                    try:
                        ss,ee=decode(b,q)
                        if ee>=e if e is not None else False:
                            span_candidates.append((q,ss[:55],ee))
                    except Exception:
                        pass
            print(f"    row={r:4d} ptr=0x{v:06X} prev=0x{b[v-1]:02X} next=0x{b[v]:02X} "
                  f"decode={'OK' if e is not None else 'ERR'} roundtrip={'YES' if rt else 'NO'} "
                  f"end={('0x%X'%e) if e is not None else '-'}",flush=True)
            print("      prefix[-8:]",pref.hex(" "),
                  "text=",repr((s or err or '')[:100]),flush=True)
            if covering:
                print("      INSIDE_OTHER_STRING:",[(hex(a),hex(z)) for a,z in covering[:5]],flush=True)
            if span_candidates:
                print("      POSSIBLE_SPAN_PREFIX:",[(hex(a),t,z) for a,t,z in span_candidates[:3]],flush=True)
        if outside:
            print("  OUTSIDE POINTERS:",outside[:20],flush=True)

    # Show ranges where decoded strings overlap.
    intervals=sorted((v,decoded[v][1]) for v in starts if decoded[v][1] is not None)
    overlaps=[]
    furthest_start=furthest_end=None
    for v,e in intervals:
        if furthest_end is not None and v < furthest_end - 1:
            overlaps.append((v,e,furthest_start,furthest_end))
        if furthest_end is None or e>furthest_end:
            furthest_start,furthest_end=v,e
    print(f"\nOVERLAPPING_DECODE_RANGES={len(overlaps)}",flush=True)
    for v,e,p,pe in overlaps[:40]:
        s=decoded[v][0]
        print(f"  0x{v:X}-0x{e:X} overlaps prior 0x{p:X}-0x{pe:X}: {s[:70]!r}",flush=True)

    return 0

if __name__=="__main__":
    raise SystemExit(main())
