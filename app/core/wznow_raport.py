# -*- coding: utf-8 -*-
"""Wznów estetyczne dopracowanie z wcześniejszego wyniku całej mapy.

Stary raport jest źródłem propozycji, NIE źródłem geometrii GIS:
poligony i oryginalne prostokąty ponownie czytamy z tego samego MAP.
Walidujemy SHA-256 i odtwarzamy wszystkie zapisane edycje, zanim
uruchomimy nowy przebieg. Dane wejściowe pozostają nienaruszone.
"""
import hashlib
import json
import math
from pathlib import Path

from app.core import geometria_ukladu as geo


def odtworz(przed, mapa, skala, wysokosc_mm, sciezka_raportu):
    data=json.loads(Path(sciezka_raportu).read_text(encoding="utf-8"))
    if not data.get("tryb_automatyczny_calej_mapy"):
        raise ValueError("Raport bazowy nie pochodzi z --cala-mapa")
    if data.get("analiza_czesciowa"):
        raise ValueError("Nie mozna wznowic niepelnego raportu")
    digest=hashlib.sha256(mapa["raw"]).hexdigest()
    if not data.get("sha256_zrodla") or data["sha256_zrodla"]!=digest:
        raise ValueError("SHA-256 oryginalnego MAP rozni sie od raportu bazowego")
    if (data.get("skala")!=skala
            or data.get("wysokosc_mm")!=wysokosc_mm):
        raise ValueError("Skala lub wielkosc czcionki nie zgadza sie z raportem")
    if data.get("liczba_napisow")!=len(przed):
        raise ValueError("Raport dotyczy innej liczby napisow")
    by_id={e["id"]:e for e in przed}
    modified={}
    for change in data.get("zmiany",[]):
        name=change["id"]
        if name in modified or name not in by_id:
            raise ValueError("Powtorzony lub nieznany napis w raporcie: "+name)
        e=by_id[name]
        if (change["rodzaj"]!=e["rodzaj"] or
                change.get("tekst")!=e["tekst"]):
            raise ValueError("Opis etykiety nie zgadza sie z mapa: "+name)
        old=change["przed"]
        if len(old)!=4 or max(
                abs(float(a)-b) for a,b in zip(old,e["prostokat"]))>1e-5:
            raise ValueError("Pozycja zrodlowa nie zgadza sie z mapa: "+name)
        updated=dict(e,prostokat=tuple(change["po"]))
        leader=change.get("wysiegnik")
        updated["wysiegnik"]=(tuple(leader[0]),tuple(leader[1])
                              ) if leader is not None else None
        modified[name]=updated
    result=[modified.get(e["id"],dict(e)) for e in przed]
    errors=geo.waliduj_uklad(result)
    if len(errors)!=data.get("liczba_nierozwiazanych"):
        raise ValueError("Nie mozna odtworzyc poprzednich kolizji z raportu")
    return result,data
