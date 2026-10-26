# -*- coding: utf-8 -*-
"""Próba v3: naprawa nakładających się par L2/L3 za pomocą prostego wysięgnika.

Uruchamia eksperymentalne etapy v1 i v2, następnie próbuje przenieść opis
na zewnątrz, pozostawiając literę wewnątrz poligonu. Gdy nie ma bezpiecznej
pozycji, nie wprowadza zmiany. Oryginalny MAP nigdy nie jest nadpisywany.
Wymiary tekstu są przybliżone — plik wynikowy wymaga kontroli w GEO-MAP.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import tempfile

from app.core import diagnostyka_map as dm
from app.core import geometria_ukladu as geo
from app.core import opisy_na_mape as onm
from app.core import proba_ukladu as v1
from app.core import proba_ukladu_v2 as v2
from app.core import uklad_opisow as uk


def _center(r):
    return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)


def _expand(r, m):
    return (r[0]-m, r[1]-m, r[2]+m, r[3]+m)


def _safe_anchors(pts, own_letter, original, resolution=16):
    """Points strictly inside the owner polygon and away from own letter."""
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    result = []
    for i in range(resolution):
        x = x0 + (x1-x0)*(i+.5)/resolution
        for j in range(resolution):
            y = y0 + (y1-y0)*(j+.5)/resolution
            if not geo.prostokat_w_poligonie((x-.8, y-.8, x+.8, y+.8), pts):
                continue
            if geo.odcinek_przecina_prostokat((x,y),(x,y),_expand(own_letter,2)):
                continue
            result.append((x,y))
    result.sort(key=lambda p: math.dist(p,original))
    return result[:35]


def _outside_candidates(pts, r, max_distance):
    w,h = r[2]-r[0],r[3]-r[1]
    bx0,bx1=min(p[0] for p in pts),max(p[0] for p in pts)
    by0,by1=min(p[1] for p in pts),max(p[1] for p in pts)
    loc=[]
    for distance in (11.,24.,40.,61.,max_distance):
        for t in (-1.,-.65,-.3,0.,.3,.65,1.):
            x=bx0+(bx1-bx0)*(t+1)/2
            y=by0+(by1-by0)*(t+1)/2
            loc.extend(((x,by0-h/2-distance),(x,by1+h/2+distance),
                        (bx0-w/2-distance,y),(bx1+w/2+distance,y)))
    cx,cy=_center(r)
    for distance in (25,40,60,90):
        for dx,dy in ((0,distance),(0,-distance),(distance,0),(-distance,0)):
            loc.append((cx+dx,cy+dy))
    unique={}
    for p in loc:
        unique[(round(p[0],2),round(p[1],2))]=p
    return sorted(unique.values(),key=lambda p:math.dist(p,(cx,cy)))


def _start_from_box(rect, anchor):
    midy=(rect[1]+rect[3])/2
    if anchor[1]<midy:
        return ((rect[0]+rect[2])/2,rect[1]),69
    return ((rect[0]+rect[2])/2,rect[3]),133


def _leader_hits_labels(segment, ident, index):
    a,b=segment
    bounds=(min(a[0],b[0]),min(a[1],b[1]),
            max(a[0],b[0]),max(a[1],b[1]))
    for other in index.sasiedzi(_expand(bounds,3),ident):
        if geo.odcinek_przecina_prostokat(
                a,b,_expand(index.boxy[other],1.0)):
            return True
    return False


def _border_hits_box(r, edges, cell):
    expanded=_expand(r,1.0)
    return any(geo.odcinek_przecina_prostokat(a,b,expanded)
               for a,b in uk._krawedzie_w(expanded,edges,cell))


def popraw_pary(elementy, index, border_index=None, max_distance=90.0):
    """Only fix OWN letter/description overlaps with an exterior description.

    Never puts leader through labels or polygon borders through label boxes.
    Other defects are intentionally left for a later group optimizer.
    """
    groups=defaultdict(dict)
    for e in elementy:
        groups[e['wydzielenie']][e['rodzaj']]=e
    leaders={};changed={}
    repaired=[];unresolved=[]
    for group in sorted(groups.values(),key=lambda v:v.get('litera',{}).get('id','')):
        lit,opis=group.get('litera'),group.get('opis')
        if not lit or not opis:
            continue
        lid,did=lit['id'],opis['id']
        lr,dr=index.boxy[lid],index.boxy[did]
        if not geo.prostokaty_koliduja(lr,dr):
            continue
        if not geo.prostokat_w_poligonie(lr,lit['poligon']):
            unresolved.append({'id':did,'reason':'letter_outside'})
            continue
        anchors=_safe_anchors(opis['poligon'],lr,_center(dr))
        if not anchors:
            unresolved.append({'id':did,'reason':'no_safe_anchor'})
            continue
        w,h=dr[2]-dr[0],dr[3]-dr[1]
        best=None
        for px,py in _outside_candidates(opis['poligon'],dr,max_distance):
            candidate=(px-w/2,py-h/2,px+w/2,py+h/2)
            # A fully external description cannot sit over its own polygon.
            corners=((candidate[0],candidate[1]),(candidate[0],candidate[3]),
                     (candidate[2],candidate[1]),(candidate[2],candidate[3]))
            if any(geo.punkt_w_poligonie(p,opis['poligon']) for p in corners):
                continue
            if border_index:
                edges,cell=border_index
                if _border_hits_box(candidate,edges,cell):
                    continue
            if any(geo.prostokaty_koliduja(
                    _expand(candidate,1.25),_expand(index.boxy[k],1.25))
                   for k in index.sasiedzi(_expand(candidate,2.5),did)):
                continue
            for anchor in anchors:
                start,flag=_start_from_box(candidate,anchor)
                line=(start,anchor)
                if geo.odcinek_przecina_prostokat(
                        *line,candidate,wnetrze=True):
                    continue
                if _leader_hits_labels(line,did,index):
                    continue
                if any(uk._odcinki(start,anchor,old[0],old[1])
                       for old in leaders.values()):
                    continue
                length=math.dist(start,anchor)
                if length>max_distance*2:
                    continue
                score=length+.10*math.dist((px,py),_center(dr))
                if best is None or score<best[0]:
                    best=(score,candidate,line,flag)
            if best and best[0]<35:
                break
        if not best:
            unresolved.append({'id':did,'reason':'no_collision_free_exterior'})
            continue
        _,newbox,line,flag=best
        index.przestaw(did,newbox)
        changed[did]=newbox
        leaders[did]=line
        repaired.append({'id':did,'flag':flag,
                         'anchor':[round(v,3) for v in line[1]],
                         'length_m':round(math.dist(*line),2)})
    return changed,leaders,{'leads_added':len(leaders),
                             'repaired_pairs':repaired,
                             'unresolved_pairs':unresolved}


def zapisz_kopie(mapa,items,changes,leaders,source,destination):
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():
        raise ValueError('Nie wolno nadpisywać wejściowego MAP')
    # Preserve the source through original tested offset exporter, then add
    # GEO-MAP leader flag and anchor offset (relative to POLYGON BBOX center).
    with tempfile.TemporaryDirectory() as temp:
        middle=Path(temp)/'intermediate.MAP'
        v1.zapisz_kopie_mapy(mapa,items,changes,source,middle)
        output=onm.wczytaj_mape(middle)
        lookup={}
        for o in uk.wszystkie_poligony(output):
            if not output['lines'][o['start']].startswith('*5310 '):
                continue
            uuid=next((s[4:-1] for s in o['linie'] if s.startswith(':ID[')),None)
            if not uuid:
                continue
            for i in range(o['start']+1,o['start']+len(o['linie'])+1):
                parts=output['lines'][i].split()
                if len(parts)>=7 and parts[0]=='L' and parts[1] in ('2','3'):
                    lookup[uuid+':L'+parts[1]]=(i,uk.srodek_bazowy(o['punkty']))
        for ident,line in leaders.items():
            if ident not in lookup:
                continue
            idx,base=lookup[ident]
            q=output['lines'][idx].split()
            _,flag=_start_from_box(changes[ident],line[1])
            dx,dy=line[1][0]-base[0],line[1][1]-base[1]
            output['lines'][idx]=' '.join(q[:6]+[str(flag),f'{dx:.3f}',f'{dy:.3f}'])
        raw=onm.przelicz_naglowek(output['lines'])
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(raw)
    return destination


def run(path,skala=4000,outpath=None,jsonpath=None,max_distance=90.0):
    mapa=onm.wczytaj_mape(path)
    items,warnings=dm.elementy_z_mapy(mapa,skala)
    original={e['id']:e['prostokat'] for e in items}
    first,firstreport=v1.uloz_wewnatrz(items,25,3)
    for e in items:
        if e['id'] in first:
            e['prostokat']=first[e['id']]
    optimizer=v2.UkladOstrozny(items,2.5,2.5,19)
    _,secondreport=optimizer.run()
    cell=80.0
    edges=uk._siatka_krawedzi(uk._wydzielenia(
        uk.wszystkie_poligony(mapa)),cell)
    _,leaders,thirdreport=popraw_pary(
        items,optimizer.indeks,(edges,cell),max_distance)
    changes={ident:rect for ident,rect in optimizer.indeks.boxy.items()
             if max(abs(a-b) for a,b in zip(rect,original[ident]))>1e-5}
    finalstats=v1.statystyka(items,optimizer.indeks)
    result={'przed':firstreport['przed'],'po_v2':secondreport['po'],
            'po_v3':finalstats,'v3':thirdreport,'przesuniete_lacznie':len(changes),
            'warnings':warnings,
            'uwaga':'Eksperyment, rozmiar tekstu przyblizony; kontrola GEO-MAP wymagana.'}
    if outpath:
        zapisz_kopie(mapa,items,changes,leaders,path,outpath)
        result['mapa_wynikowa']=str(outpath)
    if jsonpath:
        Path(jsonpath).write_text(json.dumps(result,ensure_ascii=False,indent=2),
                                  encoding='utf-8')
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description='Eksperyment v3: proste wysiegniki')
    p.add_argument('mapa')
    p.add_argument('--skala',type=int,default=4000)
    p.add_argument('--map-wynik')
    p.add_argument('--json')
    p.add_argument('--maks-dlugosc',type=float,default=90.0)
    a=p.parse_args(argv)
    res=run(a.mapa,a.skala,a.map_wynik,a.json,a.maks_dlugosc)
    print('PRZED:',res['przed'])
    print('PO v2:',res['po_v2'])
    print('PO v3:',res['po_v3'])
    print('Nowe wysiegniki:',res['v3']['leads_added'])
    print('Nierozwiazane wlasne pary:',len(res['v3']['unresolved_pairs']))
    if a.map_wynik:
        print('Mapa testowa:',a.map_wynik)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
