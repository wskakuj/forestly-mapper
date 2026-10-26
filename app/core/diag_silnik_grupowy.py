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


def diagnozuj(sciezka, skala=None, wysokosc_mm=2.5,
              szerokosc_wiazki=8, maks_grupa=3, przebiegi=1,
              limit_grup=8, postep=None):
    """Wczytanie danych i układ w pamięci, bez zapisu MAP."""
    path = Path(sciezka)
    mapa = onm.wczytaj_mape(path)
    scale = skala if skala is not None else dm.skala_naglowka(mapa)
    przed, ostrzezenia = dm.elementy_z_mapy(mapa, scale, wysokosc_mm)
    wszystkie = [o["punkty"] for o in uk.wszystkie_poligony(mapa)]
    if postep:
        postep({"etap": "odczyt", "napisy": len(przed),
                "wydzielenia": len({e["wydzielenie"] for e in przed})})
    po, raport = engine.optymalizuj(
        przed, wszystkie_poligony=wszystkie,
        szerokosc_wiazki=szerokosc_wiazki,
        maks_grupa=maks_grupa, przebiegi=przebiegi,
        limit_grup=limit_grup, postep=postep)
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

    def postep(event):
        if event.get("etap") == "odczyt":
            print("Wczytano:", event["napisy"], "napisow;",
                  event["wydzielenia"], "wydzielen; rozpoczynam analize...",
                  flush=True)
        else:
            print("Grupa %d/%d, przebieg %d; analizuje wydzielenie %s" % (
                event["indeks"], event["liczba_grup"],
                event["przebieg"], event["wydzielenie"]), flush=True)

    print("Start diagnostyki GEO-MAP (MAP tylko do odczytu)...", flush=True)
    result = diagnozuj(
        args.mapa, args.skala, args.wysokosc_mm,
        args.wiazka, args.maks_grupa, args.przebiegi,
        limit_grup=None if args.limit_grup == 0 else args.limit_grup,
        postep=postep)
    print("MAP (tylko odczyt):", result["plik_wejsciowy"])
    print("Skala: 1:%s | etykiety: %d | wydzielenia: %d" % (
        result["skala"], result["liczba_napisow"], result["liczba_wydzielen"]))
    print("Problemy przed:", result["przed"])
    print("Problemy po:   ", result["po"])
    print("Zmienione etykiety:", result["zmienione_napisy"])
    print("Nierozwiazane problemy:", result["liczba_nierozwiazanych"])
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
