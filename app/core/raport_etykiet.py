# -*- coding: utf-8 -*-
"""Lokalizator problematycznych liter GEO-MAP na podstawie raportu solvera.

Odbywa się bez ponownego układania mapy. Czyta wejściową MAP oraz raport
JSON z diagnozy; niczego nie zapisuje. Identyfikatory UUID tłumaczy na
nazwy wydzieleń A1, np. 3g, 3h, 3r.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from app.core import diagnostyka_map as dm
from app.core import opisy_na_mape as onm


def pokaz_problemowe(mapa_path, raport_path, szukane=(), limit=15):
    """Podsumowanie problemów pogrupowanych po A1, bez zmian plików."""
    mapa_path = Path(mapa_path)
    raport_path = Path(raport_path)
    raport = json.loads(raport_path.read_text(encoding="utf-8"))
    report_source = Path(raport.get("plik_wejsciowy", "")).name
    if report_source.casefold() != mapa_path.name.casefold():
        raise ValueError("Raport powstal dla innej mapy: %s" % report_source)
    elements, warnings = dm.elementy_z_mapy(
        onm.wczytaj_mape(mapa_path),
        skala=raport.get("skala"),
        wysokosc_mm=raport.get("wysokosc_mm", 2.5))
    expected = raport.get("liczba_napisow")
    if expected is not None and len(elements) != expected:
        raise ValueError(
            "Liczba napisow jest inna niz w raporcie; sprawdz wersje MAP")
    grouped = defaultdict(list)
    for e in elements:
        grouped[e["wydzielenie"]].append(e)

    full_problems = raport.get("raport_silnika", {}).get("nierozwiazane")
    complete = isinstance(full_problems, list)
    problems = full_problems if complete else raport.get("przyklady_problemow", [])
    problems_by_group = defaultdict(list)
    for p in problems:
        involved = {part.rsplit(":", 1)[0] for part in p.get("elementy", [])}
        for uuid in involved:
            problems_by_group[uuid].append(p)
    changed = {e["id"]: e for e in raport.get("zmiany", [])}
    summary = []
    for uuid, group in grouped.items():
        letter = next((e["tekst"] for e in group if e["rodzaj"] == "litera"), "")
        descr = next((e["tekst"] for e in group if e["rodzaj"] == "opis"), "")
        collisions = problems_by_group.get(uuid, [])
        changes = [changed[e["id"]] for e in group if e["id"] in changed]
        summary.append({
            "uuid": uuid,
            "litera": letter,
            "opis": descr,
            "liczba_problemow": len(collisions),
            "problemy": dict(Counter(p["typ"] for p in collisions)),
            "szczegoly": collisions,
            "zmienione_napisy": [c["id"] for c in changes],
            "nowe_wysiegniki": sum(bool(c.get("wysiegnik")) for c in changes),
            "pozycje_poczatkowe": {
                e["rodzaj"]: list(e["prostokat"]) for e in group},
        })
    if szukane:
        term = {str(s).strip().casefold() for s in szukane}
        summary = [x for x in summary if x["litera"].strip().casefold() in term]
        found = {x["litera"].strip().casefold() for x in summary}
        missing = sorted(term - found)
    else:
        summary.sort(key=lambda x: (-x["liczba_problemow"], x["litera"], x["uuid"]))
        summary = summary[:max(0, limit)]
        missing = []
    return {
        "mapa": str(mapa_path),
        "raport": str(raport_path),
        "kompletny_zestaw_problemow": complete,
        "wyniki": summary,
        "nieznalezione": missing,
        "ostrzezenia_parsowania": warnings,
        "uwaga": ("UUID przyporzadkowano do A1 w MAP. "
                  "Bez wzorca GEO-MAP nie mozna potwierdzic wygladu napisow."),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Powiaz nazwy wydzielen (np. 3g 3h 3r) z nierozwiazanymi problemami")
    parser.add_argument("mapa", help="MAP wykorzystana do diagnostyki (tylko odczyt)")
    parser.add_argument("raport", help="JSON z diag_silnik_grupowy (tylko odczyt)")
    parser.add_argument("--etykiety", nargs="+", default=(),
                        help="Nazwy A1 wydzielen, np. --etykiety 3g 3h 3r")
    parser.add_argument("--top", type=int, default=15,
                        help="Liczba wydzielen do wypisania bez --etykiety")
    args = parser.parse_args(argv)
    result = pokaz_problemowe(args.mapa, args.raport, args.etykiety, args.top)
    print("Pliki tylko do odczytu; brak nowej optymalizacji.", flush=True)
    if not result["kompletny_zestaw_problemow"]:
        print("UWAGA: raport zawiera tylko probke problemow.", flush=True)
    for x in result["wyniki"]:
        print("%s | %s | problemy: %s | zmiany: %d | wysiegniki: %d | UUID: %s"
              % (x["litera"], x["opis"], x["problemy"],
                 len(x["zmienione_napisy"]), x["nowe_wysiegniki"], x["uuid"]),
              flush=True)
        for issue in x["szczegoly"][:8]:
            print("   -", issue["typ"], ":", ", ".join(issue["elementy"]))
    if result["nieznalezione"]:
        print("Nie znaleziono A1:", ", ".join(result["nieznalezione"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
