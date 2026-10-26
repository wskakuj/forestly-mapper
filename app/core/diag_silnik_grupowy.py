# -*- coding: utf-8 -*-
"""Bezpieczna diagnostyka nowego silnika na rzeczywistym GEO-MAP .MAP.

Nigdy nie zapisuje MAP. Opcjonalnie zapisuje wyłącznie raport .json.
Obrysy pisma GEO-MAP pozostają szacowane.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from app.core import diagnostyka_map as dm
from app.core import geometria_ukladu as geo
from app.core import opisy_na_mape as onm
from app.core import silnik_grupowy as engine
from app.core import uklad_opisow as uk


def _wykryj_wiele_konturow(poligony, lines):
    """Zgłoś podejrzane obiekty 5310 z kilkoma konturami P 0.

    Aktualny parser uklad_opisow.wszystkie_poligony splaszcza te kontury
    do jednej listy punktow. Nie wolno traktowac jego wyniku jako
    sprawdzonej topologii obiektow wieloczescowych.
    """
    out = []
    for obj in poligony:
        if not lines[obj["start"]].startswith("*5310 "):
            continue
        liczba = sum(
            len(line.split()) >= 2 and line.split()[0:2] == ["P", "0"]
            for line in obj["linie"])
        if liczba <= 1:
            continue
        def atr(key):
            prefix = ":" + key + "["
            return next((line[len(prefix):-1] for line in obj["linie"]
                         if line.startswith(prefix) and line.endswith("]")), "")
        out.append({"id": atr("ID"), "litera": atr("A1"),
                    "liczba_sekcji_p0": liczba})
    return out


def _statystyki_kandydatow(elementy, poligony, wydzielenia):
    """Oblicz, czy brak rozwiązania wynika z generacji czy z przeszkód.

    Raportuje wszystkie bezpieczne plany z ograniczonego zestawu
    24 wariantów na grupę, nie pełną przestrzeń możliwych pozycji.
    """
    index = engine.Granice(poligony)
    wynik = []
    for uuid in sorted(wydzielenia):
        group = [e for e in elementy if e["wydzielenie"] == uuid]
        if not group:
            continue
        counts = {
            e["rodzaj"]: {
                "wewnetrzne": len(list(engine._pozycje_wewnatrz(e, index, 2.5))),
                "zewnetrzne": len(list(engine._pozycje_zewnetrzne(
                    e, index, poligony, 2.5)))}
            for e in group
        }
        plans = engine.opcje_wydzielenia(group, index, poligony)
        strategies = Counter()
        viable = 0
        other = [e for e in elementy if e["wydzielenie"] != uuid]
        for plan in plans:
            style = "+".join(sorted(e["rodzaj"] for e in plan
                                    if e.get("wysiegnik")))
            strategies[style or "wszystko_wewnatrz"] += 1
            if not any(engine._kolizja_miedzy(plan, [f], 2.5)
                       for f in other):
                viable += 1
        wynik.append({
            "uuid": uuid, "liczba_etykiet": len(group),
            "kandydaci": counts,
            "liczba_planow_w_limicie": len(plans),
            "strategie_planow": dict(strategies),
            "plany_bez_kolizji_z_innymi_etykietami": viable,
            "uwaga": "Dane dla pierwotnego rozmieszczenia i 24 planow na wydzielenie."})
    return wynik


def diagnozuj(sciezka, skala=None, wysokosc_mm=2.5,
              szerokosc_wiazki=8, maks_grupa=3, przebiegi=1,
              limit_grup=8, postep=None, etykiety=(),
              sprawdz_warianty=False):
    """Wczytanie danych i układ w pamięci, bez zapisu MAP."""
    path = Path(sciezka)
    mapa = onm.wczytaj_mape(path)
    scale = skala if skala is not None else dm.skala_naglowka(mapa)
    przed, ostrzezenia = dm.elementy_z_mapy(mapa, scale, wysokosc_mm)
    obiekty = uk.wszystkie_poligony(mapa)
    wszystkie = [o["punkty"] for o in obiekty]
    wielokonturowe = _wykryj_wiele_konturow(obiekty, mapa["lines"])
    nazwy = {e["wydzielenie"]: e["tekst"] for e in przed
             if e["rodzaj"] == "litera"}
    szukane = {x.strip().casefold() for x in etykiety if x.strip()}
    znalezione = {uuid for uuid, name in nazwy.items()
                  if name.strip().casefold() in szukane}
    brak = szukane - {nazwy[uuid].strip().casefold()
                     for uuid in znalezione}
    if brak:
        raise ValueError("Nie znaleziono etykiet A1: " + ", ".join(sorted(brak)))

    def pokaz(event):
        if postep:
            identifier = event.get("wydzielenie")
            if identifier is not None:
                event = {**event, "nazwa": nazwy.get(identifier, "?")}
            postep(event)

    if postep:
        pokaz({"etap": "odczyt", "napisy": len(przed),
               "wydzielenia": len({e["wydzielenie"] for e in przed})})
    po, raport = engine.optymalizuj(
        przed, wszystkie_poligony=wszystkie,
        szerokosc_wiazki=szerokosc_wiazki,
        maks_grupa=maks_grupa, przebiegi=przebiegi,
        limit_grup=limit_grup, postep=pokaz,
        wybrane_wydzielenia=znalezione if szukane else None)
    statystyki_wariantow = (
        _statystyki_kandydatow(przed, wszystkie, znalezione)
        if sprawdz_warianty and znalezione else [])
    orig = {e["id"]: e for e in przed}
    zmiany = []
    for e in po:
        poprzedni = orig[e["id"]]
        if (e["prostokat"] == poprzedni["prostokat"] and
                e.get("wysiegnik") == poprzedni.get("wysiegnik")):
            continue
        zmiany.append({
            "id": e["id"], "tekst": e.get("tekst"), "rodzaj": e["rodzaj"],
            "przed": list(poprzedni["prostokat"]), "po": list(e["prostokat"]),
            "wysiegnik": e.get("wysiegnik"),
        })
    wczesniejsze = geo.waliduj_uklad(przed)
    pozniejsze = geo.waliduj_uklad(po)
    return {
        "plik_wejsciowy": str(path),
        "skala": scale, "wysokosc_mm": wysokosc_mm,
        "liczba_napisow": len(przed), "liczba_poligonow": len(wszystkie),
        "liczba_wydzielen": len({e["wydzielenie"] for e in przed}),
        "wybrane_etykiety": sorted(szukane),
        "wybrane_uuid": sorted(znalezione),
        "diagnostyka_wariantow": statystyki_wariantow,
        "wydzielenia_wielokonturowe": wielokonturowe,
        "pelna_walidacja_topologii": not wielokonturowe,
        "przed": dict(Counter(e["typ"] for e in wczesniejsze)),
        "po": dict(Counter(e["typ"] for e in pozniejsze)),
        "zmienione_napisy": len(zmiany),
        "liczba_nierozwiazanych": len(pozniejsze),
        "przyklady_problemow": pozniejsze[:150],
        "zmiany": zmiany,
        "raport_silnika": raport,
        "analiza_czesciowa": raport.get("analiza_czesciowa", False),
        "ostrzezenia_parsowania": ostrzezenia,
        "uwaga": ("Tylko symulacja w pamieci. MAP nie jest zapisywany. "
                  "Obrysy fontu sa szacowane; potrzebna walidacja GEO-MAP."),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Diagnostyka grupowego silnika (bez zapisu MAP)")
    p.add_argument("mapa", help="Zrodlowy plik GEO-MAP .MAP (tylko odczyt)")
    p.add_argument("--skala", type=int, default=None)
    p.add_argument("--wysokosc-mm", type=float, default=2.5)
    p.add_argument("--wiazka", type=int, default=8)
    p.add_argument("--maks-grupa", type=int, default=3)
    p.add_argument("--przebiegi", type=int, default=1)
    p.add_argument("--limit-grup", type=int, default=8,
                   help="Maks. liczba skupisk do rozpatrzenia (0 = bez limitu)")
    p.add_argument("--etykiety", nargs="+", default=(),
                   help="Analizuj tylko wskazane A1 (np. --etykiety 3h 4a 4b 4c); reszta pozostaje przeszkoda")
    p.add_argument("--sprawdz-warianty", action="store_true",
                   help="Policz odrzucone warianty (wymaga --etykiety)")
    p.add_argument("--json", help="Zapisz raport w osobnym pliku .json")
    args = p.parse_args(argv)
    if args.json:
        output = Path(args.json)
        if output.suffix.lower() != ".json":
            p.error("--json wymaga pliku z rozszerzeniem .json")
        if output.resolve() == Path(args.mapa).resolve():
            p.error("Nie wolno nadpisac MAP")
    for name in ("wiazka", "maks_grupa", "przebiegi"):
        if getattr(args, name) < 1:
            p.error("--%s musi byc dodatnie" % name)
    if args.limit_grup < 0:
        p.error("--limit-grup nie moze byc ujemny")
    if args.sprawdz_warianty and not args.etykiety:
        p.error("--sprawdz-warianty wymaga --etykiety")

    def postep(event):
        if event.get("etap") == "odczyt":
            print("Wczytano:", event["napisy"], "napisow;",
                  event["wydzielenia"], "wydzielen; rozpoczynam analize...",
                  flush=True)
        else:
            print("Grupa %d/%d, przebieg %d; wydzielenie %s (%s)" % (
                event["indeks"], event["liczba_grup"],
                event["przebieg"], event.get("nazwa", "?"),
                event["wydzielenie"]), flush=True)

    print("Start diagnostyki GEO-MAP (MAP tylko do odczytu)...", flush=True)
    try:
        result = diagnozuj(
            args.mapa, args.skala, args.wysokosc_mm,
            args.wiazka, args.maks_grupa, args.przebiegi,
            limit_grup=None if args.limit_grup == 0 else args.limit_grup,
            postep=postep, etykiety=args.etykiety,
            sprawdz_warianty=args.sprawdz_warianty)
    except ValueError as exc:
        p.error(str(exc))
    print("MAP (tylko odczyt):", result["plik_wejsciowy"])
    print("Skala: 1:%s | etykiety: %d | wydzielenia: %d" % (
        result["skala"], result["liczba_napisow"], result["liczba_wydzielen"]))
    print("Problemy przed:", result["przed"])
    print("Problemy po:   ", result["po"])
    print("Zmienione etykiety:", result["zmienione_napisy"])
    for info in result["diagnostyka_wariantow"]:
        print("DIAG wariantow %s: kandydaci=%s | plany=%s | bez kolizji z otoczeniem=%s" % (
            info["uuid"], info["kandydaci"], info["liczba_planow_w_limicie"],
            info["plany_bez_kolizji_z_innymi_etykietami"]))
    print("Nierozwiazane problemy:", result["liczba_nierozwiazanych"])
    if result["wydzielenia_wielokonturowe"]:
        print("UWAGA: wykryto %d wydzielen wielokonturowych; obecny parser"
              " nie waliduje ich topologii:" % len(result["wydzielenia_wielokonturowe"]))
        print(", ".join(e["litera"] or e["id"]
                        for e in result["wydzielenia_wielokonturowe"][:20]))
    if result["analiza_czesciowa"]:
        print("UWAGA: to CZESCIOWA symulacja, limit grup zostal osiagniety.")
    print("UWAGA:", result["uwaga"])
    if args.json:
        output = Path(args.json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Raport:", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
