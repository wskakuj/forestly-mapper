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
from app.core import kontury_map as km
from app.core import przeciecia_map as pm
from app.core import autouklad_calej_mapy as auto
from app.core import eksport_propozycji_map as export
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
        model = km.model_wydzielenia(obj["linie"])
        if len(model["kontury"]) <= 1 and liczba <= 1:
            continue
        def atr(key):
            prefix = ":" + key + "["
            return next((line[len(prefix):-1] for line in obj["linie"]
                         if line.startswith(prefix) and line.endswith("]")), "")
        out.append({"id": atr("ID"), "litera": atr("A1"),
                    "liczba_sekcji_p0": liczba,
                    "liczba_konturow": len(model["kontury"]),
                    "kompletne": model["kompletne"]})
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
        # Zidentyfikuj konkretnych właścicieli blokujących napisów,
        # aby odróżnić brak miejsca od konieczności przesunięcia
        # sąsiada. Uwzględnia również wysięgniki i przesunięte opisy.
        by_id = {e["id"]: e for e in elementy}
        blocked = engine._blokady_planow(plans, by_id, uuid, 2.5)
        hits = Counter(x for blocker_set, _ in blocked for x in blocker_set)
        by_uuid = {e["wydzielenie"]: e["tekst"] for e in elementy
                   if e["rodzaj"] == "litera"}
        minimal = min((len(blockers) for blockers, _ in blocked), default=None)
        closest = sorted({tuple(sorted(blockers))
                          for blockers, _ in blocked
                          if len(blockers) == minimal})[:5] if minimal is not None else []
        for plan, (blockers, _) in zip(plans, blocked):
            style = "+".join(sorted(e["rodzaj"] for e in plan
                                    if e.get("wysiegnik")))
            strategies[style or "wszystko_wewnatrz"] += 1
            if not blockers:
                viable += 1
        wynik.append({
            "uuid": uuid, "liczba_etykiet": len(group),
            "kandydaci": counts,
            "liczba_planow_w_limicie": len(plans),
            "strategie_planow": dict(strategies),
            "plany_bez_kolizji_z_innymi_etykietami": viable,
            "minimalna_liczba_blokujacych_grup": minimal,
            "najczestsze_blokady": [
                {"uuid": key, "etykieta": by_uuid.get(key, ""),
                 "blokowanych_planow": count}
                for key, count in sorted(hits.items(),
                                         key=lambda pair: (-pair[1], str(pair[0])))[:12]],
            "przykladowe_minimalne_zestawy_blokad": [
                [{"uuid": key, "etykieta": by_uuid.get(key, "")}
                 for key in groups] for groups in closest],
            "uwaga": "Ograniczone warianty w pierwotnym otoczeniu; nie dowodza optymalnosci."})
    return wynik



def _przeciecia_wysiegnikow_z_obiektami(elementy, obiekty, lines,
                                       wybrane=None, indeks=None):
    """Przecięcia z liniami MAP; własne granice są oznaczone osobno.

    Indeks jest współdzielony z opcjonalną karą planów. Powtarzające się
    obiekty o różnych typach liczą się jako jeden fizyczny punkt.
    """
    index = indeks if indeks is not None else pm.IndeksPrzeciec(obiekty, lines)
    result = []
    for e in elementy:
        w = e.get("wysiegnik")
        if not w or (wybrane is not None and
                     e["wydzielenie"] not in wybrane):
            continue
        result.append({"id_napisu":e["id"], "etykieta":e.get("tekst",""),
                       **index.raport(w, e["wydzielenie"])})
    return result


def diagnozuj(sciezka, skala=None, wysokosc_mm=2.5,
              szerokosc_wiazki=8, maks_grupa=3, przebiegi=1,
              limit_grup=8, postep=None, etykiety=(),
              sprawdz_warianty=False, kara_przeciecia=0.0,
              kara_wielokrotnej_granicy=0.0, cala_mapa=False,
              maks_trudnych=24, rundy_dodatkowe=2):
    """Wczytanie danych i układ w pamięci, bez zapisu MAP."""
    if cala_mapa and etykiety:
        raise ValueError('--cala-mapa nie moze byc laczona z --etykiety')
    if maks_trudnych < 0 or rundy_dodatkowe < 0:
        raise ValueError('Limity automatycznego dopracowania musza byc nieujemne')
    if kara_przeciecia < 0:
        raise ValueError('--kara-przeciecia nie moze byc ujemna')
    if kara_wielokrotnej_granicy < 0:
        raise ValueError('--kara-wielokrotnej-granicy nie moze byc ujemna')
    path = Path(sciezka)
    mapa = onm.wczytaj_mape(path)
    scale = skala if skala is not None else dm.skala_naglowka(mapa)
    przed, ostrzezenia = dm.elementy_z_mapy(mapa, scale, wysokosc_mm)
    obiekty = uk.wszystkie_poligony(mapa)
    # Każde P 0 zamyka bieżący pierścień. Nie twórz sztucznych
    # połączeń między pierścieniami ani z otwartą polilinią.
    wszystkie = [fragment for o in obiekty
                 for fragment in km.fragmenty_z_linii(o["linie"])]
    wielokonturowe = _wykryj_wiele_konturow(obiekty, mapa["lines"])
    niedomkniete = [o for o in obiekty
                    if mapa["lines"][o["start"]].startswith("*5310 ")
                    and not km.model_wydzielenia(o["linie"])["kompletne"]]
    indeks_przeciec = pm.IndeksPrzeciec(obiekty, mapa['lines'])
    dodatkowy_koszt = (lambda plan: indeks_przeciec.kara_planu(
        plan, kara_przeciecia, kara_wielokrotnej_granicy)) if (
            kara_przeciecia or kara_wielokrotnej_granicy) else None
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
    if cala_mapa:
        po, raport = auto.uloz_cala_mape(
            przed, wszystkie, nazwy=nazwy,
            szerokosc_wiazki=szerokosc_wiazki,
            maks_grupa=maks_grupa, przebiegi=przebiegi,
            maks_trudnych=maks_trudnych, rundy_dodatkowe=rundy_dodatkowe,
            postep=pokaz, ocena_dodatkowa=dodatkowy_koszt)
    else:
        po, raport = engine.optymalizuj(
            przed, wszystkie_poligony=wszystkie,
            szerokosc_wiazki=szerokosc_wiazki,
            maks_grupa=maks_grupa, przebiegi=przebiegi,
            limit_grup=limit_grup, postep=pokaz,
            wybrane_wydzielenia=znalezione if szukane else None,
            ocena_dodatkowa=dodatkowy_koszt)
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
    przeciecia = _przeciecia_wysiegnikow_z_obiektami(
        po, obiekty, mapa["lines"], znalezione if szukane else None,
        indeks=indeks_przeciec)
    return {
        "plik_wejsciowy": str(path),
        "skala": scale, "wysokosc_mm": wysokosc_mm,
        "liczba_napisow": len(przed), "liczba_poligonow": len(obiekty),
        "liczba_fragmentow_granic": len(wszystkie),
        "liczba_wydzielen": len({e["wydzielenie"] for e in przed}),
        "wybrane_etykiety": sorted(szukane),
        "tryb_automatyczny_calej_mapy": bool(cala_mapa),
        "skutecznosc_calej_mapy": raport.get("skutecznosc"),
        "wybrane_uuid": sorted(znalezione),
        "diagnostyka_wariantow": statystyki_wariantow,
        "wydzielenia_wielokonturowe": wielokonturowe,
        "wielokonturowe_w_modelu": [e["litera"] for e in wielokonturowe
                                  if e["liczba_konturow"] > 1 and e["kompletne"]],
        "niepelne_kontury_5310": len(niedomkniete),
        # Nawet zamkniete kontury nie dowodza zgodnosci dziur i pol
        # powierzchni z GEO-MAP. Pierwszy etap opiera sie na parzystosci.
        "pelna_walidacja_topologii": not wielokonturowe and not niedomkniete,
        "model_konturow": "osobne_pierscienie_parzystosc_niepotwierdzona_GEO_MAP",
        "przed": dict(Counter(e["typ"] for e in wczesniejsze)),
        "po": dict(Counter(e["typ"] for e in pozniejsze)),
        "zmienione_napisy": len(zmiany),
        "liczba_nierozwiazanych": len(pozniejsze),
        "przyklady_problemow": pozniejsze[:150],
        "przeciecia_wysiegnikow_obiekty_mapy": przeciecia,
        "liczba_dodatkowych_przeciec_wysiegnikow": sum(
            item["liczba_dodatkowych_przeciec"] for item in przeciecia),
        "liczba_nadmiarowych_przeciec_wlasnej_granicy": sum(
            item["liczba_nadmiarowych_przeciec_wlasnej_granicy"]
            for item in przeciecia),
        "kara_za_przeciecie": kara_przeciecia,
        "kara_wielokrotnej_granicy": kara_wielokrotnej_granicy,
        "koszt_kary_wybranego_ukladu": (
            dodatkowy_koszt([e for e in po
                             if not szukane or e['wydzielenie'] in znalezione])
            if dodatkowy_koszt else 0.0),
        "zmiany": zmiany,
        "raport_silnika": raport,
        "analiza_czesciowa": raport.get("analiza_czesciowa", False),
        "ostrzezenia_parsowania": ostrzezenia,
        "uwaga": ("Automatyczny skan wszystkich wydzielen. " if cala_mapa
                  else "Czesciowa diagnostyka wskazanych skupisk. ")
                 + ("Tylko symulacja w pamieci, MAP nie jest zapisywany. "
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
    p.add_argument('--cala-mapa',action='store_true',
                   help='Optymalizuj WSZYSTKIE problematyczne wydzielenia bez limitu 8 grup, potem automatycznie dopracuj najtrudniejsze')
    p.add_argument('--maks-trudnych',type=int,default=24,
                   help='Ile nierozwiazanych grup sprobowac dodatkowo (domyslnie 24)')
    p.add_argument('--rundy-dodatkowe',type=int,default=2,
                   help='Liczba dodatkowych rund dla trudnych grup (domyslnie 2)')
    p.add_argument("--etykiety", nargs="+", default=(),
                   help="Analizuj tylko wskazane A1 (np. --etykiety 3h 4a 4b 4c); reszta pozostaje przeszkoda")
    p.add_argument('--kara-przeciecia', type=float, default=0.0,
                   help='Miekka kara kosztowa za dodatkowe przeciecie linii MAP (0=bez kary)')
    p.add_argument('--kara-wielokrotnej-granicy',type=float,default=0.0,
                   help='Miekka kara za kazde przecięcie WLASNEJ granicy ponad pierwsze (0=bez kary)')
    p.add_argument("--sprawdz-warianty", action="store_true",
                   help="Policz odrzucone warianty (wymaga --etykiety)")
    p.add_argument("--json", help="Zapisz raport w osobnym pliku .json")
    p.add_argument("--map-kopia",help="Stworz osobna, weryfikowana i NIGDY nienadpisywana testowa kopie .MAP (tylko z --cala-mapa)")
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
    if args.kara_przeciecia < 0:
        p.error('--kara-przeciecia nie moze byc ujemna')
    if args.map_kopia and not args.cala_mapa:
        p.error('--map-kopia wymaga --cala-mapa')
    if args.map_kopia:
        dest=Path(args.map_kopia)
        if dest.suffix.lower()!='.map':
            p.error('--map-kopia wymaga pliku .MAP')
        if dest.resolve()==Path(args.mapa).resolve() or dest.exists():
            p.error('Kopia juz istnieje albo wskazano oryginal; podaj NOWA nazwe')
    if args.maks_trudnych < 0 or args.rundy_dodatkowe < 0:
        p.error('--maks-trudnych i --rundy-dodatkowe nie moga byc ujemne')
    if args.cala_mapa and args.etykiety:
        p.error('--cala-mapa nie moze byc laczona z --etykiety')
    if args.kara_wielokrotnej_granicy < 0:
        p.error('--kara-wielokrotnej-granicy nie moze byc ujemna')
    if args.sprawdz_warianty and not args.etykiety:
        p.error("--sprawdz-warianty wymaga --etykiety")

    def postep(event):
        if event.get("etap") == "odczyt":
            print("Wczytano:", event["napisy"], "napisow;",
                  event["wydzielenia"], "wydzielen; rozpoczynam analize...",
                  flush=True)
        elif event.get("etap") == "dopracowanie":
            print("Dopracowanie runda %d: grupa %d; %s (%s)" % (
                event["runda"], event["rozpatrzone_lacznie"],
                event.get("nazwa","?"), event["wydzielenie"]),flush=True)
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
            sprawdz_warianty=args.sprawdz_warianty,
            kara_przeciecia=args.kara_przeciecia,
            kara_wielokrotnej_granicy=args.kara_wielokrotnej_granicy,
            cala_mapa=args.cala_mapa,
            maks_trudnych=args.maks_trudnych,
            rundy_dodatkowe=args.rundy_dodatkowe)
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
    if result["skutecznosc_calej_mapy"] is not None:
        stats = result["skutecznosc_calej_mapy"]
        print("NAPISY BEZ PROBLEMOW: %d/%d (przed: %d)" % (
            stats["napisy_bez_problemow_po"],stats["napisy_razem"],
            stats["napisy_bez_problemow_przed"]))
        print("WYDZIELENIA BEZ PROBLEMOW: %d/%d (przed: %d)" % (
            stats["wydzielenia_bez_problemow_po"],
            stats["wydzielenia_razem"],
            stats["wydzielenia_bez_problemow_przed"]))
        print("Samodzielnie naprawione napisy: %d; wymagajace kontroli: %d" % (
            stats["napisy_naprawione"],
            stats["napisy_razem"]-stats["napisy_bez_problemow_po"]))
    if result["wydzielenia_wielokonturowe"]:
        print("UWAGA: wykryto %d obiektow z wieloma P0;"
              " liczba rzeczywistych konturow jest teraz rozpoznawana."
              " Semantyka dziur wymaga weryfikacji w GEO-MAP:"
              % len(result["wydzielenia_wielokonturowe"]))
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
    if args.map_kopia:
        try:
            saved=export.eksportuj_kopie(args.mapa,result,args.map_kopia)
        except (ValueError,OSError,KeyError,IndexError) as exc:
            p.error('Kopia MAP nie zostala zapisana: '+str(exc))
        print("TESTOWA KOPIA GEO-MAP:",saved["sciezka_kopii"])
        print("Weryfikacja odczytu: %d napisow; zapisano %d zmian" % (
            saved["napisy_po_odczycie"],saved["zapisane_napisy"]))
        print("UWAGA: kopia wymaga osobnej weryfikacji w GEO-MAP!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
