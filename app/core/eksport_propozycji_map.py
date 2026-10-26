# -*- coding: utf-8 -*-
"""Eksport wyłącznie testowej kopii GEO-MAP po pełnym skanie mapy.

Zmienia tylko offsety etykiet L2/L3 i ich proste wysięgniki w obiektach
5310. Wszystkie inne obiekty i atrybuty zachowuje bajtowo po ponownym
kodowaniu MAZOWIA. Ponownie parsuje wynik PRZED zapisaniem nowej kopii.
"""
from pathlib import Path
import math

from app.core import diagnostyka_map as dm
from app.core import opisy_na_mape as onm
from app.core import uklad_opisow as uk


def _centrum(r):
    return ((r[0]+r[2])/2.0,(r[1]+r[3])/2.0)


def _nowa_linia(stara, zmiana):
    tokens=stara.split()
    if (len(tokens)<7 or tokens[0]!="L"
            or tokens[1] not in ("2","3")):
        raise ValueError("Niespodziewany rekord L GEO-MAP")
    nr=2 if zmiana["id"].endswith(":L2") else 3
    if tokens[1]!=str(nr):
        raise ValueError("Nieprawidlowa etykieta dla rekordu L")
    old, new=zmiana["przed"],zmiana["po"]
    old_center,new_center=_centrum(old),_centrum(new)
    dx0,dy0=float(tokens[2]),float(tokens[3])
    dx=dx0+(new_center[0]-old_center[0])
    dy=dy0+(new_center[1]-old_center[1])
    # Zachowujemy pierwotny kąt i skalę (pola 4 i 5).
    prefix="L %d %.3f %.3f %s %s" % (
        nr,dx,dy,tokens[4],tokens[5])
    line=zmiana.get("wysiegnik")
    if line is None:
        return prefix+" 5"
    start,target=line
    top=abs(start[1]-new[1])
    bottom=abs(start[1]-new[3])
    if min(top,bottom)>.02 or abs(start[0]-new_center[0])>.02:
        raise ValueError("Wysiegnik nie wychodzi z krawedzi napisu")
    style=69 if top<=bottom else 133
    # W MAP cel zapisywany jest względem punktu bazowego obiektu.
    base_x=old_center[0]-dx0
    base_y=old_center[1]-dy0
    wx=target[0]-base_x
    wy=target[1]-base_y
    return prefix+" %d %.3f %.3f" % (style,wx,wy)


def _mapowanie_linii(mapa):
    result={}
    for obj in uk.wszystkie_poligony(mapa):
        if not mapa["lines"][obj["start"]].startswith("*5310 "):
            continue
        uid=next((x[4:-1] for x in obj["linie"]
                  if x.startswith(":ID[") and x.endswith("]")),
                 str(obj["start"]))
        for offset,line in enumerate(obj["linie"]):
            if line.startswith("L 2 ") or line.startswith("L 3 "):
                nr=line.split()[1]
                ident=uid+":L"+nr
                if ident in result:
                    raise ValueError("Powtorzona linia "+ident)
                # obj["linie"] pomija naglowek '*' obiektu; offset
                # jest wiec liczony od start+1 (zwraca absolutny indeks).
                result[ident]=obj["start"]+1+offset
    return result


def _weryfikuj_kopie(source_map, newbytes, changes, skala, wysokosc_mm):
    raw_map={"path":source_map["path"],"raw":newbytes,
             "lines":onm.maz_na_tekst(newbytes).split("\r\n")}
    original_labels,_=dm.elementy_z_mapy(source_map,skala,wysokosc_mm)
    actual_labels,warnings=dm.elementy_z_mapy(raw_map,skala,wysokosc_mm)
    if len(actual_labels)!=len(original_labels):
        raise ValueError("Eksport zmienil liczbe rozpoznanych napisow")
    actual={e["id"]:e for e in actual_labels}
    for edit in changes:
        parsed=actual.get(edit["id"])
        if not parsed:
            raise ValueError("Nie odnaleziono napisu po eksporcie: "+edit["id"])
        center=_centrum(parsed["prostokat"])
        wanted=_centrum(edit["po"])
        if math.dist(center,wanted)>.01:
            raise ValueError("Niepoprawne odtworzenie przesuniecia "+edit["id"])
        leader=edit.get("wysiegnik")
        if leader:
            if (not parsed.get("wysiegnik") or
                    math.dist(parsed["wysiegnik"][1],leader[1])>.01 or
                    math.dist(parsed["wysiegnik"][0],leader[0])>.01):
                raise ValueError("Niepoprawnie zapisany wysiegnik "+edit["id"])
        elif parsed.get("wysiegnik"):
            raise ValueError("Niepotrzebny wysiegnik po eksporcie: "+edit["id"])
    return {"napisy_po_odczycie":len(actual),
            "ostrzezenia_odczytu":len(warnings)}


def eksportuj_kopie(sciezka_map, raport, sciezka_wynikowa):
    """Waliduj cały wynik w pamięci, następnie utwórz NOWĄ kopię MAP."""
    source=Path(sciezka_map)
    dest=Path(sciezka_wynikowa)
    if dest.suffix.lower()!=".map":
        raise ValueError("Kopia musi miec rozszerzenie .MAP")
    if source.resolve()==dest.resolve():
        raise ValueError("Nie wolno nadpisywac pliku oryginalnego")
    if dest.exists():
        raise FileExistsError("Kopia juz istnieje; podaj nowa nazwe")
    if not raport.get("tryb_automatyczny_calej_mapy"):
        raise ValueError("Eksport wymaga raportu z --cala-mapa")
    if raport.get("analiza_czesciowa"):
        raise ValueError("Nie wolno eksportowac czesciowego skanu")
    if Path(raport.get("plik_wejsciowy","")).name != source.name:
        raise ValueError("Raport pochodzi z innego pliku MAP")
    source_map=onm.wczytaj_mape(source)
    lines=list(source_map["lines"])
    positions=_mapowanie_linii(source_map)
    edits=raport.get("zmiany",[])
    if len(set(e["id"] for e in edits))!=len(edits):
        raise ValueError("Powtarzaja sie identyfikatory zmian")
    for edit in edits:
        ident=edit["id"]
        i=positions.get(ident)
        if i is None:
            raise ValueError("Nie mozna bezpiecznie zapisac napisu "+ident)
        lines[i]=_nowa_linia(lines[i],edit)
    contents=onm.przelicz_naglowek(lines)
    check=_weryfikuj_kopie(source_map,contents,edits,
                           raport["skala"],raport["wysokosc_mm"])
    # Plik oryginalny jest tylko czytany. 'xb' zabezpiecza przed
    # nadpisaniem nawet w wyścigu dwóch procesów.
    with dest.open("xb") as handle:
        handle.write(contents)
    return {"sciezka_kopii":str(dest),"zapisane_napisy":len(edits),
            "bajty":len(contents),**check,
            "ostrzezenie":"Tylko testowa kopia; otworz i zweryfikuj w GEO-MAP."}
