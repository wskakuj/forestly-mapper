# -*- coding: utf-8 -*-
"""Automatyczny, bezpieczny przebieg dla całej mapy GEO-MAP.

Uruchamia zwykły silnik bez sztucznego limitu ośmiu grup, potem
samodzielnie próbuje wspólnie poprawić ograniczoną liczbę najtrudniejszych
skupisk. Nie zapisuje źródłowego MAP. Nie przyjmuje nowej kolizji
jako ceny za naprawę istniejącej.
"""
from collections import Counter, defaultdict
import math

from app.core import geometria_ukladu as geo
from app.core import silnik_grupowy as engine
from app.core import estetyka_mapy as aesthetics


def _klucz_problemu(issue):
    return issue["typ"], tuple(sorted(issue["elementy"]))


def _problemy(elementy):
    return geo.waliduj_uklad(elementy)


def _id_problematycznych(problemy):
    return {ident for issue in problemy for ident in issue["elementy"]}


def _najblizsze_grupy(klucz, by_group, problemy, elem_by_id, limit=5):
    """Preferuj faktycznie kolidujące napisy, następnie bliskie etykiety."""
    counts = Counter()
    for issue in problemy:
        owners = {elem_by_id[ident]["wydzielenie"]
                  for ident in issue["elementy"] if ident in elem_by_id}
        if klucz in owners:
            counts.update(owners - {klucz})

    def punkt_grupy(k):
        rects = [e["prostokat"] for e in by_group[k]]
        return ((min(r[0] for r in rects)+max(r[2] for r in rects))/2,
                (min(r[1] for r in rects)+max(r[3] for r in rects))/2)

    origin = punkt_grupy(klucz)
    near = sorted((k for k in by_group if k != klucz),
                  key=lambda k: (-counts[k],
                                 math.dist(origin, punkt_grupy(k)),str(k)))
    return near[:limit]


def _skutecznosc(przed, po, elementy, names):
    """Raport liczby napisów i grup, nie tylko liczby zgłoszeń kolizji."""
    labels_before = _id_problematycznych(przed)
    labels_after = _id_problematycznych(po)
    by_group = defaultdict(set)
    for e in elementy:
        by_group[e["wydzielenie"]].add(e["id"])
    bad_groups = {
        k for k, ids in by_group.items() if ids & labels_after
    }
    groups_before = {
        k for k, ids in by_group.items() if ids & labels_before
    }
    unresolved = []
    for k in sorted(bad_groups, key=lambda key: str(names.get(key,key))):
        errors = [
            {"typ":issue["typ"], "elementy":issue["elementy"]}
            for issue in po if set(issue["elementy"]) & by_group[k]
        ]
        unresolved.append({"uuid":k, "etykieta": names.get(k,k),
                           "rodzaje_problemow":dict(Counter(
                               e["typ"] for e in errors)),
                           "liczba_problemow":len(errors)})
    return {
        "napisy_razem":len(elementy),
        "napisy_bez_problemow_przed":len(elementy)-len(labels_before),
        "napisy_bez_problemow_po":len(elementy)-len(labels_after),
        "napisy_naprawione":len(labels_before-labels_after),
        "napisy_nowe_z_problemem":len(labels_after-labels_before),
        "wydzielenia_razem":len(by_group),
        "wydzielenia_bez_problemow_przed":len(by_group)-len(groups_before),
        "wydzielenia_bez_problemow_po":len(by_group)-len(bad_groups),
        "wydzielenia_naprawione":len(groups_before-bad_groups),
        "wydzielenia_nowe_z_problemem":len(bad_groups-groups_before),
        "problemy_przed":len(przed),
        "problemy_po":len(po),
        "nierozwiazane_wydzielenia":unresolved,
        "uwaga":("Statystyka oparta na przybliżonych obrysach tekstu; "
                 "nie zastępuje walidacji GEO-MAP.")
    }


def uloz_cala_mape(elementy, poligony, *, nazwy=None,
                   szerokosc_wiazki=16, maks_grupa=3, przebiegi=2,
                   ocena_dodatkowa=None, maks_trudnych=24,
                   rundy_dodatkowe=2, postep=None,
                   maks_estetyka=36, maks_par_estetyka=12,
                   priorytety_estetyka=(), chronione_estetyka=()):
    """Wielostopniowa optymalizacja bez konieczności ręcznego V14, V15...

    Etap 1: wszystkie konfliktowe grupy, bez limitu liczby skupisk.
    Etap 2: automatycznie dobierane duety i trójki do lokalnego,
    dokładnego poszukiwania z adaptacją 24/72/112.
    Każdy rezultat lokalny musi ZMNIEJSZYĆ zbiór istniejących
    błędów bez tworzenia nowych. W przeciwnym razie jest odrzucany.
    """
    if maks_estetyka < 0 or maks_par_estetyka < 0:
        raise ValueError("Budzet estetyki musi byc nieujemny")
    if maks_trudnych < 0 or rundy_dodatkowe < 0:
        raise ValueError("Limity automatycznej optymalizacji musza byc nieujemne")
    if maks_grupa < 1 or szerokosc_wiazki < 1 or przebiegi < 1:
        raise ValueError("Parametry silnika musza byc dodatnie")
    start = _problemy(elementy)
    current, first = engine.optymalizuj(
        elementy, wszystkie_poligony=poligony,
        szerokosc_wiazki=szerokosc_wiazki, maks_grupa=maks_grupa,
        przebiegi=przebiegi, limit_grup=None,
        ocena_dodatkowa=ocena_dodatkowa, postep=postep)
    current_errors = _problemy(current)
    initial_keys = {_klucz_problemu(issue) for issue in start}
    if {_klucz_problemu(issue) for issue in current_errors} - initial_keys:
        # Unikamy automatycznego publikowania mapy, która pomogła
        # kilku wydzieleniom kosztem stworzenia NOWEGO konfliktu.
        current = [dict(e) for e in elementy]
        current_errors = start
        rolled_back = True
    else:
        rolled_back = False

    attempts = 0
    accepted = 0
    rejected = 0
    reviewed = set()
    seen_attempts = set()
    rounds_done = 0
    names = nazwy or {}
    if maks_grupa >= 2:
        for round_no in range(rundy_dodatkowe):
            if attempts >= maks_trudnych:
                break
            rounds_done += 1
            by_group = defaultdict(list)
            for e in current:
                by_group[e["wydzielenie"]].append(e)
            by_id = {e["id"]:e for e in current}
            weight = Counter()
            for issue in current_errors:
                for owner in {by_id[ident]["wydzielenie"]
                              for ident in issue["elementy"]
                              if ident in by_id}:
                    weight[owner] += 1
            todo = sorted(weight,key=lambda k:(-weight[k],str(k)))
            improved_round = 0
            for key in todo:
                if attempts >= maks_trudnych:
                    break
                if not any(e["id"] in _id_problematycznych(current_errors)
                           for e in by_group[key]):
                    continue
                attempts += 1
                reviewed.add(key)
                if postep:
                    postep({"etap":"dopracowanie","runda":round_no+1,
                           "rozpatrzone_lacznie":attempts,
                           "liczba_grup":len(todo),"wydzielenie":key})
                neighbors = _najblizsze_grupy(
                    key,by_group,current_errors,by_id,limit=3)
                selections = [frozenset((key,n)) for n in neighbors]
                if maks_grupa >= 3:
                    for i in range(min(2,len(neighbors))):
                        for j in range(i+1,min(3,len(neighbors))):
                            selections.append(frozenset(
                                (key,neighbors[i],neighbors[j])))
                for selected in selections:
                    # Nie próbuj tej samej konfiguracji dwa razy,
                    # chyba że otoczenie zmieniło się po udanej próbie.
                    signature = (frozenset(selected),accepted)
                    if signature in seen_attempts:
                        continue
                    seen_attempts.add(signature)
                    attempt, _ = engine.optymalizuj(
                        current, wszystkie_poligony=poligony,
                        szerokosc_wiazki=szerokosc_wiazki,
                        maks_grupa=max(maks_grupa,len(selected)),
                        przebiegi=1, limit_grup=len(selected),
                        wybrane_wydzielenia=selected,
                        ocena_dodatkowa=ocena_dodatkowa)
                    errors = _problemy(attempt)
                    old_keys = {_klucz_problemu(e) for e in current_errors}
                    new_keys = {_klucz_problemu(e) for e in errors}
                    if new_keys < old_keys:
                        current = attempt
                        current_errors = errors
                        accepted += 1
                        improved_round += 1
                        break
                    rejected += 1
            if not improved_round:
                break

    # Oddzielny przebieg do POPRAWIANIA ESTETYKI, także tam, gdzie
    # etap kolizji zakończył pracę. Kontroluje ponownie pełen układ.
    estetyka = None
    if maks_estetyka:
        current, estetyka = aesthetics.dopracuj(
            current, poligony, nazwy=names,
            ocena_dodatkowa=ocena_dodatkowa,
            maks_grup=maks_estetyka, maks_par=maks_par_estetyka,
            priorytety=priorytety_estetyka,
            chronione=chronione_estetyka, postep=postep)
        current_errors = _problemy(current)

    report = {
        "tryb":"cala_mapa",
        "skan_calej_mapy":True,
        "etap_wstepny":{k:v for k,v in first.items() if k!="nierozwiazane"},
        "etap_wstepny_odrzucony_przez_nowe_problemy":rolled_back,
        "rundy_dodatkowe":rounds_done,
        "dopracowanie_estetyki": estetyka,
        "trudne_grupy_przebadane":attempts,
        "limit_trudnych_grup":maks_trudnych,
        "grupy_ulepszone_w_dopracowaniu":accepted,
        "proby_dopracowania_odrzucone":rejected,
        "dopracowanie_niepelne":bool(
            attempts>=maks_trudnych and current_errors),
        "przed":dict(Counter(e["typ"] for e in start)),
        "po":dict(Counter(e["typ"] for e in current_errors)),
        "przesuniete":sum(
            e["prostokat"]!=original["prostokat"] or
            e.get("wysiegnik")!=original.get("wysiegnik")
            for e,original in zip(current,elementy)),
        "nierozwiazane":current_errors,
        "analiza_czesciowa":False,
        "skutecznosc":_skutecznosc(start,current_errors,current,names),
        "ostrzezenie":("Skan wszystkich wydzieleń; skończona liczba "
                       "wariantów i niepełna topologia GEO-MAP. "
                       "Nierozwiązane grupy wymagają kontroli.")
    }
    return current,report
