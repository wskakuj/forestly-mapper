# -*- coding: utf-8 -*-
"""Diagnostyka ułożenia podpisów 5310 w GEO-MAP .MAP (tylko odczyt).

Nie układa napisów ani nie zmienia mapy. Wykorzystuje istniejący parser
Mazowii i geometrię z etapu 1. Rozmiary tekstu to nadal przybliżenie z
uklad_opisow.py, więc wyniki są przesłanką do przeglądu, nie pomiarem
rzeczywistych obrysów fontu GEO-MAP.
"""
import argparse
from collections import Counter
import json
import re

from app.core import geometria_ukladu as geo
from app.core import opisy_na_mape as onm
from app.core import uklad_opisow as uk


def skala_naglowka(mapa, domyslna=5000):
    """Pierwsza liczba po EXT; użytkownik może nadpisać ją przez --skala."""
    for line in mapa["lines"][:10]:
        m = re.match(r"^;#\s*EXT\s+(\d+)", line)
        if m:
            return int(m.group(1))
    return domyslna


def _atrybut(blok, nazwa):
    poczatek = ":" + nazwa + "["
    return next((l[len(poczatek):-1] for l in blok
                 if l.startswith(poczatek) and l.endswith("]")), "")


def _linie_podpisow(blok):
    result = {}
    for line in blok:
        if not line.startswith("L "):
            continue
        q = line.split()
        if len(q) >= 7 and q[1] in ("2", "3"):
            result[int(q[1])] = q
    return result


def _prostokat(srodek, rozmiar):
    return (srodek[0] - rozmiar[0] / 2, srodek[1] - rozmiar[1] / 2,
            srodek[0] + rozmiar[0] / 2, srodek[1] + rozmiar[1] / 2)


def _wysiegnik(l, punkt_bazowy, prostokat):
    """GEO-MAP: 69 to dolna krawędź w osi Y, 133 to górna.

    Końcowe współrzędne w L2/L3 są offsetem względem punktu bazowego
    poligonu, a nie względem środka napisu.
    """
    if len(l) < 9 or l[6] not in ("69", "133"):
        return None
    try:
        koniec = (punkt_bazowy[0] + float(l[7]),
                  punkt_bazowy[1] + float(l[8]))
        y_start = prostokat[1] if l[6] == "69" else prostokat[3]
        start = ((prostokat[0] + prostokat[2]) / 2, y_start)
        return start, koniec
    except (ValueError, IndexError):
        return None


def elementy_z_mapy(mapa, skala=None, wysokosc_mm=2.5):
    """Zwraca litery (L2) i opisy A2 zawierające | (L3), plus ostrzeżenia.

    Litery wydzieleń bez zaimportowanego opisu także są przeszkodami
    dla pozostałych napisów i dlatego są uwzględniane.
    """
    if skala is None:
        skala = skala_naglowka(mapa)
    out, ostrzezenia = [], []
    for o in uk.wszystkie_poligony(mapa):
        if not mapa["lines"][o["start"]].startswith("*5310 "):
            continue
        blok = o["linie"]
        ident = _atrybut(blok, "ID") or str(o["start"])
        litera = _atrybut(blok, "A1")
        opis = _atrybut(blok, "A2")
        linie = _linie_podpisow(blok)
        punkty = o["punkty"]
        if len(punkty) < 3:
            continue
        baza = uk.srodek_bazowy(punkty)
        for rodzaj, tekst, nr in (("litera", litera, 2),
                                 ("opis", opis if "|" in opis else "", 3)):
            if not tekst:
                continue
            l = linie.get(nr)
            if not l:
                ostrzezenia.append({"typ": "brak_linii_podpisu",
                                    "uuid": ident, "rodzaj": rodzaj})
                continue
            try:
                dx, dy = float(l[2]), float(l[3])
                kat = float(l[4])
                rozmiar = (uk.rozmiar_litery(tekst, wysokosc_mm, skala, kat)
                           if rodzaj == "litera"
                           else uk.rozmiar_opisu(tekst, wysokosc_mm, skala, kat))
                if min(rozmiar) <= 0:
                    continue
                prost = _prostokat((baza[0] + dx, baza[1] + dy), rozmiar)
                wys = _wysiegnik(l, baza, prost)
            except (ValueError, IndexError, ZeroDivisionError):
                ostrzezenia.append({"typ": "niepoprawna_linia_podpisu",
                                    "uuid": ident, "rodzaj": rodzaj})
                continue
            out.append({"id": ident + ":L" + str(nr),
                        "uuid": ident, "wydzielenie": ident,
                        "rodzaj": rodzaj, "tekst": tekst,
                        "prostokat": prost, "poligon": punkty,
                        "wysiegnik": wys})
            if len(l) >= 9 and l[6] not in ("69", "133"):
                ostrzezenia.append({"typ": "nieznany_styl_wysiegnika",
                                    "uuid": ident, "rodzaj": rodzaj,
                                    "styl": l[6]})
    return out, ostrzezenia


def raport_mapa(sciezka, skala=None, wysokosc_mm=2.5):
    """Zwróć raport JSON-serializowalny, bez jakichkolwiek zmian pliku."""
    mapa = onm.wczytaj_mape(sciezka)
    skala = skala if skala is not None else skala_naglowka(mapa)
    elementy, ostrzezenia = elementy_z_mapy(mapa, skala, wysokosc_mm)
    problemy = geo.waliduj_uklad(elementy)
    licznik = Counter(p["typ"] for p in problemy)
    wewnatrz = Counter()
    poza = Counter()
    wysiegniki = Counter()
    for e in elementy:
        rodzaj = e["rodzaj"]
        (wewnatrz if geo.prostokat_w_poligonie(e["prostokat"], e["poligon"])
         else poza)[rodzaj] += 1
        if e["wysiegnik"]:
            wysiegniki[rodzaj] += 1
    return {
        "plik": str(sciezka),
        "skala": skala,
        "wysokosc_mm": wysokosc_mm,
        "elementy": len(elementy),
        "opisy": sum(e["rodzaj"] == "opis" for e in elementy),
        "litery": sum(e["rodzaj"] == "litera" for e in elementy),
        "wewnatrz": dict(wewnatrz),
        "poza": dict(poza),
        "wysiegniki": dict(wysiegniki),
        "liczby_problemow": dict(licznik),
        "problemy": problemy,
        "ostrzezenia": ostrzezenia,
        "uwaga": ("Wymiary etykiet są szacowane, a bez aktywnej biblioteki "
                  "fontów GEO-MAP wyniki kolizji należy zweryfikować wizualnie."),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Diagnostyka rozmieszczenia podpisów GEO-MAP")
    p.add_argument("mapa", help="Plik .MAP do odczytu (nie jest modyfikowany)")
    p.add_argument("--skala", type=int, default=None,
                   help="Skala 1:N; domyślnie EXT z nagłówka mapy")
    p.add_argument("--wysokosc-mm", type=float, default=2.5)
    p.add_argument("--json", dest="wyjscie", help="Zapisz raport do JSON (mapa bez zmian)")
    p.add_argument("--pokaz", type=int, default=12,
                   help="Liczba pierwszych błędów do pokazania")
    a = p.parse_args(argv)
    raport = raport_mapa(a.mapa, a.skala, a.wysokosc_mm)
    print("MAPA:", raport["plik"])
    print("Skala 1:%s | litery: %d | opisy: %d" %
          (raport["skala"], raport["litery"], raport["opisy"]))
    print("W poligonie:", raport["wewnatrz"], "| poza:", raport["poza"])
    print("Wysięgniki:", raport["wysiegniki"])
    print("Wykryte problemy:", raport["liczby_problemow"])
    if raport["ostrzezenia"]:
        print("Ostrzeżenia o danych:", len(raport["ostrzezenia"]))
    for b in raport["problemy"][:max(a.pokaz, 0)]:
        print("  -", b["typ"], ":", ", ".join(b["elementy"]))
    print("UWAGA:", raport["uwaga"])
    if a.wyjscie:
        from pathlib import Path
        Path(a.wyjscie).write_text(
            json.dumps(raport, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Raport JSON:", a.wyjscie)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
