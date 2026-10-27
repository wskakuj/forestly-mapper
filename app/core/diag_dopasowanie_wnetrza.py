# -*- coding: utf-8 -*-
"""Diagnostyka obrysu pisma L2/L3 w prawdziwym konturze GEO-MAP.

UWAGA: mniejsze współczynniki wyłącznie diagnozują BŁĄD modelu.
Nie zmieniają faktycznej czcionki, rozmiaru w MAP ani globalnych
zabezpieczeń. Raport jest tylko do odczytu.
"""
import argparse
from collections import Counter

from app.core import diagnostyka_map as dm
from app.core import opisy_na_mape as onm
from app.core import geometria_ukladu as geo
from app.core import silnik_grupowy as engine
from app.core import wznow_raport as resume


def _centra_wlasnego_poligonu(e, wspolczynnik, krok=2.0, margines=0.5):
    """Rozmieszczenia obwiedni we własnym poligonie, bez ingerencji GIS."""
    w=(e["prostokat"][2]-e["prostokat"][0])*wspolczynnik
    h=(e["prostokat"][3]-e["prostokat"][1])*wspolczynnik
    x0,y0,x1,y1=engine.bbox(e["poligon"])
    if min(w,h)<=0 or min(x1-x0-w,y1-y0-h)<0:
        return []
    valid=[]
    nx=int((x1-x0-w)/krok)+1
    ny=int((y1-y0-h)/krok)+1
    for i in range(nx+1):
        cx=x0+w/2+i*krok
        for j in range(ny+1):
            cy=y0+h/2+j*krok
            r=engine.prost((cx,cy),(w,h))
            if geo.prostokat_w_poligonie(
                    engine.powieksz(r,margines),e["poligon"]):
                valid.append(r)
    return valid


def _para_w_srodku(opcje_a,opcje_b,otoczenie=(),odstep=2.5):
    """Zwarta niekolidująca para: najpierw bez sprawdzania otoczenia."""
    candidates=0
    for ra in opcje_a:
        for rb in opcje_b:
            if geo.prostokaty_koliduja(
                    engine.powieksz(ra,odstep/2),
                    engine.powieksz(rb,odstep/2)):
                continue
            candidates+=1
            yield ra,rb


def raport_wydzielenia(elementy, nazwa, wspolczynniki=(1.,.9,.85,.8),
                       krok=2.0):
    litery=[e for e in elementy
            if e["rodzaj"]=="litera" and e["tekst"].casefold()==nazwa.casefold()]
    if len(litery)!=1:
        raise ValueError("Etykieta A1 nie jest jednoznaczna: %s (%d wynikow)" %
                         (nazwa,len(litery)))
    own=litery[0]["wydzielenie"]
    group=[e for e in elementy if e["wydzielenie"]==own]
    if len(group)!=2:
        raise ValueError("Wydzielenie nie zawiera dokladnie L2 i L3")
    letter=next(e for e in group if e["rodzaj"]=="litera")
    description=next(e for e in group if e["rodzaj"]=="opis")
    neighbors=[e for e in elementy if e["wydzielenie"]!=own]
    result={"wydzielenie":nazwa,
            "poligon_bbox":tuple(round(x,2) for x in engine.bbox(letter["poligon"])),
            "etykiety":[{"tekst":e["tekst"],"rodzaj":e["rodzaj"],
                         "modelowy_prostokat_rozmiar":[
                            round(e["prostokat"][2]-e["prostokat"][0],2),
                            round(e["prostokat"][3]-e["prostokat"][1],2)]}
                        for e in group],
            "proby":[]}
    for factor in wspolczynniki:
        if factor<=0 or factor>1:
            raise ValueError("Wspolczynnik diagnostyczny musi nalezec do (0,1]")
        a=_centra_wlasnego_poligonu(letter,factor,krok)
        b=_centra_wlasnego_poligonu(description,factor,krok)
        example=None
        alone_pair_count=0
        without_neighbor_hit=0
        blockers=Counter()
        # Ograniczamy testy otoczenia, ale samą liczbę par
        # niekolidujących w poligonie liczymy bez przycinania.
        for ra,rb in _para_w_srodku(a,b):
            alone_pair_count+=1
            # Pary licz w całości, lecz otoczenie sprawdzaj dla
            # ograniczonej próbki, żeby nie robić 10^7 porównań.
            if alone_pair_count>250:
                continue
            pair=[{**letter,"prostokat":ra,"wysiegnik":None},
                  {**description,"prostokat":rb,"wysiegnik":None}]
            obstacle=next((e for e in neighbors
                           if engine._kolizja_miedzy(pair,[e],2.5)),None)
            if obstacle is None:
                without_neighbor_hit+=1
                if example is None:
                    example={"litera":[round(x,2) for x in ra],
                             "opis":[round(x,2) for x in rb]}
            else:
                blockers[obstacle["wydzielenie"]]+=1
        result["proby"].append({
            "wspolczynnik_wylacznie_do_diagnozy":factor,
            "pozycje_litery_wewnatrz":len(a),
            "pozycje_opisu_wewnatrz":len(b),
            "pary_niekolidujace_w_poligonie":alone_pair_count,
            "pary_bez_kolizji_z_innymi_napisami_przy_probie":without_neighbor_hit,
            "maks_pierwszych_par_do_testu_otoczenia":250,
            "przykladowa_para_modelowa":example,
            "uwaga":"Zmniejszony obrys NIE jest poprawka czcionki. Nie zapisuj tych pozycji do MAP bez kalibracji realnego fontu."
        })
    return result


def main(argv=None):
    p=argparse.ArgumentParser(
        description="Tylko odczyt: sprawdz, dlaczego silnik nie miesci L2/L3 we wlasnym poligonie.")
    p.add_argument("mapa")
    p.add_argument("--wydzielenie",required=True)
    p.add_argument("--skala",type=int,default=4000)
    p.add_argument("--wysokosc-mm",type=float,default=2.5)
    p.add_argument("--bazowy-json",help="Dopasuj aktualne propozycje z poprzedniego raportu.")
    p.add_argument("--krok",type=float,default=2.0)
    args=p.parse_args(argv)
    if args.krok<=0:
        p.error("--krok musi byc dodatni")
    mapa=onm.wczytaj_mape(args.mapa)
    labels,_=dm.elementy_z_mapy(mapa,args.skala,args.wysokosc_mm)
    if args.bazowy_json:
        labels,_=resume.odtworz(labels,mapa,args.skala,args.wysokosc_mm,
                                args.bazowy_json)
    report=raport_wydzielenia(labels,args.wydzielenie,krok=args.krok)
    print("WYDZIELENIE:",report["wydzielenie"])
    print("BBOX poligonu:",report["poligon_bbox"])
    for e in report["etykiety"]:
        print(e["rodzaj"],e["tekst"],"wymiary obrysu [m]:",
              e["modelowy_prostokat_rozmiar"])
    for row in report["proby"]:
        print("Model %5.0f%%: pozycje L2=%d, L3=%d; pary w poligonie=%d; bez kolizji z otoczeniem=%d" % (
            100*row["wspolczynnik_wylacznie_do_diagnozy"],
            row["pozycje_litery_wewnatrz"],
            row["pozycje_opisu_wewnatrz"],
            row["pary_niekolidujace_w_poligonie"],
            row["pary_bez_kolizji_z_innymi_napisami_przy_probie"]))
    print("DIAGNOZA WYŁĄCZNIE — MAP BEZ ZMIAN. Skalowanie obrysu nie zmienia czcionki GEO-MAP.")


if __name__=="__main__":
    main()
