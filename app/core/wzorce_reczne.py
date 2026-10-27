# -*- coding: utf-8 -*-
"""Bezpieczny import JAWNIE zaakceptowanych przez operatora pozycji MAP.

Wzorcowy plik nie jest dodawany do repozytorium. Musi mieć dokładnie
te same UUID, podpisy, obrysy i wymiary pisma co MAP źródłowy.
Wszystkie napisy POZA wskazanymi wydzieleniami muszą odpowiadać
ostatniemu odtworzonemu raportowi, z tolerancją zapisu 0.001 m.

Wzorzec umożliwia odtworzenie rzeczywistego położenia podpisu
z GEO-MAP, którego przybliżony pełny prostokąt fontu może nie
mieścić się w nieregularnym poligonie. Nie jest to globalne
poluzowanie geometrii, ani automatyczne uznanie dowolnego MAP.
"""
from pathlib import Path

from app.core import opisy_na_mape as onm
from app.core import diagnostyka_map as dm


def _roznica_pozycji(a, b):
    return max(abs((a["prostokat"][i]+a["prostokat"][i+2])/2 -
                   (b["prostokat"][i]+b["prostokat"][i+2])/2)
               for i in (0, 1))


def _wymiary(box):
    return (box[2]-box[0], box[3]-box[1])


def wczytaj_wzorce(sciezka, elementy_bazowe, nazwy, skala,
                   wysokosc_mm, zaakceptowane, tolerancja=0.03):
    """Zwraca plany wyłącznie dla wskazanych nazw A1.

    `elementy_bazowe` to odtworzony, aktualny stan MAP, nie
    oryginalne nieułożone pozycje. Dzięki temu można wykryć
    przypadkową zmianę dowolnego innego wydzielenia.
    """
    accepted={str(x).strip().casefold() for x in zaakceptowane
              if str(x).strip()}
    if not accepted:
        raise ValueError("Wskaz --wzor-wydzielenia razem z --wzor-map")
    selected={uuid for uuid,label in nazwy.items()
              if str(label).strip().casefold() in accepted}
    present={str(nazwy[k]).strip().casefold() for k in selected}
    if present != accepted:
        raise ValueError("Nieznane lub niejednoznaczne wzorce A1: "+
                         ", ".join(sorted(accepted-present)))
    if len(selected)!=len(accepted):
        raise ValueError("Powtorzona nazwa A1 wzorca; wybierz jednoznaczny UUID")
    wzor,_=dm.elementy_z_mapy(onm.wczytaj_mape(Path(sciezka)),
                              skala,wysokosc_mm)
    source={e["id"]:e for e in elementy_bazowe}
    reference={e["id"]:e for e in wzor}
    if len(reference)!=len(wzor) or set(reference)!=set(source):
        raise ValueError("Wzor MAP ma inne UUID lub liczbe etykiet niz raport bazowy")
    plans={k:[] for k in selected}
    other_differences=[]
    for ident,old in source.items():
        new=reference[ident]
        if (old["wydzielenie"]!=new["wydzielenie"] or
                old["tekst"]!=new["tekst"] or
                old["rodzaj"]!=new["rodzaj"] or
                old["poligon"]!=new["poligon"]):
            raise ValueError("Wzor zmienia tekst, UUID lub obrys: "+ident)
        if any(abs(x-y)>0.01 for x,y in zip(
                _wymiary(old["prostokat"]),_wymiary(new["prostokat"]))):
            raise ValueError("Wzor zmienia wymiar fontu/obrot napisu: "+ident)
        deviation=_roznica_pozycji(old,new)
        if old["wydzielenie"] not in selected:
            if deviation>tolerancja:
                other_differences.append((ident,round(deviation,3)))
            # Sprawdź także wysięgniki innych wydzieleń. Rozbieżności
            # < 0.1 m są możliwe po zapisaniu do 3 miejsc po przecinku.
            a,b=old.get("wysiegnik"),new.get("wysiegnik")
            if bool(a)!=bool(b):
                raise ValueError("Wzor zmienia wysiegnik poza zatwierdzonym wydzieleniem: "+ident)
            if a and b and max(abs(a[i][j]-b[i][j])
                               for i in (0,1) for j in (0,1))>0.1:
                raise ValueError("Wzor przesuwa wysiegnik poza zatwierdzonym wydzieleniem: "+ident)
        else:
            plans[old["wydzielenie"]].append(new)
    if other_differences:
        detail=", ".join(x+" ("+str(d)+" m)" for x,d in other_differences[:5])
        raise ValueError("Wzor zmienia takze inne wydzielenia: "+detail)
    if any(not v for v in plans.values()):
        raise ValueError("Zatwierdzone wydzielenie nie zawiera zadnego napisu")
    return plans
