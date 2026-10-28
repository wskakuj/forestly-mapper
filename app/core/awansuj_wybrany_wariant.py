# -*- coding: utf-8 -*-
"""Promuj wybrany przez kartografa wariant testowy MAP do nowej bazy JSON.

Wybor "najlepszego" wariantu NIE jest równoznaczny z jego pełnym
zatwierdzeniem w GEO-MAP. Program nie generuje pozycji na nowo.
Weryfikuje zachowanie wszystkich pozostałych etykiet i geometrii,
a następnie zapisuje komplet zmian względem oryginalnego MAP.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
import math
from pathlib import Path
import re

from app.core import autouklad_calej_mapy as auto
from app.core import diagnostyka_map as dm
from app.core import diag_silnik_grupowy as diag
from app.core import eksport_propozycji_map as export
from app.core import geometria_ukladu as geo
from app.core import opisy_na_mape as onm
from app.core import przeciecia_map as pm
from app.core import uklad_opisow as uk
from app.core import wznow_raport as resume
from app.core import wzorce_reczne as manual


def _centrum(r):
    return ((r[0]+r[2])/2,(r[1]+r[3])/2)


def _klucze(errors):
    return {(e["typ"],tuple(sorted(e["elementy"]))) for e in errors}


def _sprawdz_nietekstowe_linie(source, example):
    """Ze źródła do kopii wolno zmienić tylko CHK i linie L2/L3 5310."""
    original=source["lines"]
    modified=example["lines"]
    if len(original)!=len(modified):
        raise ValueError("Wybrana mapa zmienia liczbe linii albo obiektow")
    allowed=set(export._mapowanie_linii(source).values())
    for i,(before,after) in enumerate(zip(original,modified)):
        if before==after:
            continue
        if i==0:
            a=re.sub(r"CHK=\[[^\]]+\]","CHK=[]",before)
            b=re.sub(r"CHK=\[[^\]]+\]","CHK=[]",after)
            if a==b and "CHK=[" in before and "CHK=[" in after:
                continue
        if i in allowed and (
                before.startswith("L 2 ") and after.startswith("L 2 ") or
                before.startswith("L 3 ") and after.startswith("L 3 ")):
            if before.split()[4:6]!=after.split()[4:6]:
                raise ValueError("Wybrana mapa zmienia obrot lub skale fontu")
            continue
        raise ValueError(
            "Wybrana MAP zmienia niezatwierdzona linie %d" %(i+1))


def _sprawdz_wysiegniki(selected, others):
    for e in selected:
        leader=e.get("wysiegnik")
        if not leader:
            raise ValueError(
                "Wybrany zewnetrzny napis nie ma wysiegnika: "+e["id"])
        if not geo.punkt_w_poligonie(leader[1],e["poligon"]):
            raise ValueError(
                "Wysiegnik nie wskazuje wnetrza swojego wydzielenia: "+e["id"])
        for other in others:
            foreign=other.get("wysiegnik")
            if (foreign and geo.wysiegniki_koliduja(
                    leader,foreign,to_samo_wydzielenie=False)):
                raise ValueError("Wysiegnik przecina cudzy wysiegnik: "
                                 +e["id"]+" / "+other["id"])
            if geo.odcinek_przecina_prostokat(
                    *leader,other["prostokat"],wnetrze=True):
                raise ValueError("Wysiegnik przecina cudzy napis: "
                                 +e["id"]+" / "+other["id"])
            if foreign and geo.odcinek_przecina_prostokat(
                    *foreign,e["prostokat"],wnetrze=True):
                raise ValueError("Cudzy wysiegnik przecina wybrany napis: "
                                 +e["id"]+" / "+other["id"])


def _zmiany(original, new):
    before={e["id"]:e for e in original}
    result=[]
    for e in new:
        old=before[e["id"]]
        if (e["prostokat"]==old["prostokat"] and
                e.get("wysiegnik")==old.get("wysiegnik")):
            continue
        result.append({
            "id":e["id"],"tekst":e["tekst"],"rodzaj":e["rodzaj"],
            "przed":list(old["prostokat"]),
            "po":list(e["prostokat"]),
            "wysiegnik":e.get("wysiegnik")})
    return result


def awansuj(mapa_zrodlowa, raport_bazowy, wybrana_mapa,
            nazwa, wyjsciowy_json, map_kopia=None):
    source=Path(mapa_zrodlowa)
    choice=Path(wybrana_mapa)
    destination=Path(wyjsciowy_json)
    extra=Path(map_kopia) if map_kopia else None
    inputs={p.resolve() for p in (source,choice,Path(raport_bazowy))}
    outputs=[destination]+([extra] if extra else [])
    if any(p.resolve() in inputs or p.exists() for p in outputs):
        raise ValueError("Nie wolno nadpisywac oryginalu, wariantu ani raportu")
    if len({p.resolve() for p in outputs})!=len(outputs):
        raise ValueError("Sciezki wyjsciowe sa identyczne")
    if destination.suffix.lower()!=".json" or (
            extra and extra.suffix.lower()!=".map"):
        raise ValueError("Podaj --json .json i opcjonalne --map-kopia .MAP")

    raw_map=onm.wczytaj_mape(source)
    example=onm.wczytaj_mape(choice)
    _sprawdz_nietekstowe_linie(raw_map,example)
    original,_=dm.elementy_z_mapy(raw_map,4000,2.5) if False else (None,None)
    base=json.loads(Path(raport_bazowy).read_text(encoding="utf-8"))
    scale=base["skala"]
    mm=base["wysokosc_mm"]
    original,_=dm.elementy_z_mapy(raw_map,scale,mm)
    previous,_=resume.odtworz(original,raw_map,scale,mm,raport_bazowy)
    names={e["wydzielenie"]:e["tekst"] for e in original
           if e["rodzaj"]=="litera"}
    accepted=manual.wczytaj_wzorce(
        choice,previous,names,scale,mm,[nazwa])
    if len(accepted)!=1:
        raise ValueError("Nieoczekiwana liczba wybranych wydzielen")
    key=next(iter(accepted))
    chosen=accepted[key]
    if len(chosen)!=2 or {e["rodzaj"] for e in chosen}!={"litera","opis"}:
        raise ValueError("Wybrany wariant nie ma dokladnie L2 i L3")
    prior={e["id"]:e for e in previous}
    selected_ids={e["id"] for e in chosen}
    if not any(
            math.dist(_centrum(prior[e["id"]]["prostokat"]),
                      _centrum(e["prostokat"]))>0.03
            for e in chosen):
        raise ValueError("Wariant nie zmienia zadnej pozycji wybranego wydzielenia")
    remaining=[e for e in previous if e["id"] not in selected_ids]
    _sprawdz_wysiegniki(chosen,remaining)
    target={e["id"]:e for e in chosen}
    final=[target.get(e["id"],e) for e in previous]
    before_errors=geo.waliduj_uklad(previous)
    after_errors=geo.waliduj_uklad(final)
    new_issues=_klucze(after_errors)-_klucze(before_errors)
    if any(not set(ids).issubset(selected_ids) for _,ids in new_issues):
        raise ValueError("Wybrany wariant tworzy nowe bledy z innymi napisami")
    # Nowe ostrzezenia modelowe w obrebie wybranego L2/L3
    # zapisz jawnie; wybor operatora nie oznacza ich ukrycia.
    changes=_zmiany(original,final)
    result=copy.deepcopy(base)
    result["zmiany"]=changes
    result["zmienione_napisy"]=len(changes)
    result["liczba_nierozwiazanych"]=len(after_errors)
    result["przyklady_problemow"]=after_errors[:150]
    result["po"]=dict(Counter(e["typ"] for e in after_errors))
    result["skutecznosc_calej_mapy"]=auto._skutecznosc(
        geo.waliduj_uklad(original),after_errors,final,names)
    result["raport_bazowy"]=str(raport_bazowy)
    result["wybrany_wariant_operatora"]={
        "wydzielenie":nazwa,"uuid":key,
        "plik_map":str(choice),
        "status":"NAJLEPSZY_WYBRANY_DO_DALSZEJ_OCENY",
        "liczba_zmienionych_etykiet_wydzielenia":len(chosen),
        "nowe_zgloszenia_modelu_dotyczace_tylko_wydzielenia":[
            {"typ":typ,"elementy":list(ids)}
            for typ,ids in sorted(new_issues)],
        "nienaruszone_pozostale_wydzielenia":True,
        "bez_przeciec_z_cudzymi_wysiegnikami":True}
    # Przelicz metryki GIS zamiast kopiowac nieaktualne dane
    # z poprzedniego raportu.
    objects=uk.wszystkie_poligony(raw_map)
    index=pm.IndeksPrzeciec(objects,raw_map["lines"])
    all_cross=diag._przeciecia_wysiegnikow_z_obiektami(
        final,objects,raw_map["lines"],indeks=index)
    result["przeciecia_wysiegnikow_obiekty_mapy"]=all_cross
    result["liczba_dodatkowych_przeciec_wysiegnikow"]=sum(
        item["liczba_dodatkowych_przeciec"] for item in all_cross)
    result["liczba_nadmiarowych_przeciec_wlasnej_granicy"]=sum(
        item["liczba_nadmiarowych_przeciec_wlasnej_granicy"]
        for item in all_cross)
    result["koszt_kary_wybranego_ukladu"]=index.kara_planu(
        final,result.get("kara_za_przeciecie",0),
        result.get("kara_wielokrotnej_granicy",0))
    result["raport_silnika"]={
        "tryb":"wybrany_wariant_GEO_MAP",
        "poprzedni_raport":str(raport_bazowy),
        "nierozwiazane":after_errors,
        "dopracowanie_estetyki":{
            "zastosowane_wzorce_reczne":[nazwa],
            "chronione_wydzielenia":[nazwa,"6s","3s",
                "4c","4a","7b","7a","7d","8j",
                "5g","5h","10r","10o","07h"]}}
    result["analiza_czesciowa"]=False
    # Zapis plikow tylko po sprawdzeniu cala mapy.
    if extra:
        with extra.open("xb") as fp:
            fp.write(choice.read_bytes())
    with destination.open("x",encoding="utf-8") as fp:
        json.dump(result,fp,ensure_ascii=False,indent=2)
    return {
        "plik_json":str(destination),
        "map_kopia":str(extra) if extra else None,
        "wydzielenie":nazwa,
        "zapisane_zmiany":len(changes),
        "wczesniejsze_zmiany":len(base["zmiany"]),
        "modelowe_problemy_przed":len(before_errors),
        "modelowe_problemy_po":len(after_errors),
        "status":result["wybrany_wariant_operatora"]["status"]}


def main(argv=None):
    p=argparse.ArgumentParser(
        description="Promuj wybrany wariant MAP do kontynuowalnej bazy JSON, bez zmiany oryginalu")
    p.add_argument("mapa_zrodlowa")
    p.add_argument("--bazowy-json",required=True)
    p.add_argument("--wybrany-map",required=True)
    p.add_argument("--wydzielenie",required=True)
    p.add_argument("--json",required=True)
    p.add_argument("--map-kopia")
    a=p.parse_args(argv)
    report=awansuj(
        a.mapa_zrodlowa,a.bazowy_json,a.wybrany_map,
        a.wydzielenie,a.json,a.map_kopia)
    print("WYBRANY WARIANT PRZENIESIONY DO BAZY:",report["wydzielenie"])
    print("Zmiany poprzednio:",report["wczesniejsze_zmiany"],
          "| teraz:",report["zapisane_zmiany"])
    print("Modelowe problemy przed:",report["modelowe_problemy_przed"],
          "| teraz:",report["modelowe_problemy_po"])
    print("Nowy JSON:",report["plik_json"])
    if report["map_kopia"]:
        print("Kopia MAP:",report["map_kopia"])
    print("UWAGA: wariant wybrany jako najlepszy, wymaga dalszej oceny GEO-MAP.")


if __name__=="__main__":
    main()
