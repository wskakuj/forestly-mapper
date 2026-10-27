# -*- coding: utf-8 -*-
"""Drugi przebieg automatu: estetyka po usunięciu kolizji.

Tryb świadomie poprawia już formalnie POPRAWNE napisy: mniej wysięgników,
krótsze wysięgniki i umieszczanie par L2/L3 w poligonach. Każda zmiana
jest transakcyjna: nie może wytworzyć nowych błędów modelu ani zwiększyć
kosztu przecięć z mapą. Zbiór oryginalnych elementów nie jest zmieniany.
"""
from collections import Counter, defaultdict
import math

from app.core import geometria_ukladu as geo
from app.core import silnik_grupowy as engine


def _issue_key(issue):
    return issue["typ"], tuple(sorted(issue["elementy"]))


def _center(r):
    return ((r[0]+r[2])/2, (r[1]+r[3])/2)


def _quality(group):
    """Koszt absolutny, niezależny od oryginalnych przesunięć napisu."""
    value = 0.0
    for e in group:
        r=e["prostokat"]
        h=max(r[3]-r[1],geo.EPS)
        lead=e.get("wysiegnik")
        if lead:
            value += 155.0 if e["rodzaj"]=="litera" else 115.0
            length=math.dist(*lead)/h
            value += 14.0*length + 2.0*max(0,length-3)**2
    letter=next((e for e in group if e["rodzaj"]=="litera"),None)
    desc=next((e for e in group if e["rodzaj"]=="opis"),None)
    if letter and desc:
        h=max((letter["prostokat"][3]-letter["prostokat"][1]
               +desc["prostokat"][3]-desc["prostokat"][1])/2,geo.EPS)
        value+=10.0*engine.odleglosc_boxow(
            letter["prostokat"],desc["prostokat"])/h
    return value


def _metrics(elements):
    leaders=[e for e in elements if e.get("wysiegnik")]
    lengths=[math.dist(*e["wysiegnik"]) for e in leaders]
    return {"liczba_wysiegnikow":len(leaders),
            "laczna_dlugosc_wysiegnikow":round(sum(lengths),2),
            "maksymalna_dlugosc_wysiegnika":round(max(lengths,default=0),2),
            "najdluzsze_wysiegniki":[
                {"id":e["id"],"rodzaj":e["rodzaj"],
                 "dlugosc":round(math.dist(*e["wysiegnik"]),2)}
                for e in sorted(leaders,key=lambda x:
                    (-math.dist(*x["wysiegnik"]),x["id"]))[:20]]}


def dopracuj(elementy, poligony, *, nazwy=None, ocena_dodatkowa=None,
            maks_grup=36, maks_par=12, postep=None):
    """Maksymalizuj jakość tylko gdy nie gorsza od bieżącego układu.

    Pierwszeństwo mają najdłuższe wysięgniki w jednostkach rozmiaru
    napisu oraz wydzielenia nadal błędne. Najpierw lokalne próby,
    potem ograniczona liczba zmian sąsiadujących par.
    """
    if maks_grup<0 or maks_par<0:
        raise ValueError("Budzet estetyki nie moze byc ujemny")
    current={e["id"]:dict(e) for e in elementy}
    all_errors=geo.waliduj_uklad(list(current.values()))
    old_keys={_issue_key(i) for i in all_errors}
    granice=engine.Granice(poligony)
    before=_metrics(elementy)
    names=nazwy or {}
    attempts=accepted=0
    improved_labels=[]
    grouped=defaultdict(list)
    for e in current.values():
        grouped[e["wydzielenie"]].append(e)

    def pair_group(keys):
        return [current[e["id"]] for k in keys for e in grouped[k]]

    def attractiveness(key):
        group=pair_group([key])
        score=_quality(group)
        if any(e["id"] in {i for p in all_errors for i in p["elementy"]}
               for e in group):
            score+=500.0
        return score

    todo=sorted(grouped,key=lambda k:(-attractiveness(k),str(k)))
    target=[key for key in todo if attractiveness(key)>0][:maks_grup]
    ranked=set(target)
    # Same błędy L2/L3 też wymagają poprawy, np. 6s.
    remaining=[k for k in todo if k not in ranked and any(
        e["id"] in {ident for err in all_errors for ident in err["elementy"]}
        for e in grouped[k])]
    for key in remaining:
        if len(target)>=maks_grup:
            break
        target.append(key)

    def acceptable(changed):
        nonlocal all_errors, old_keys, accepted
        if not changed:
            return False
        keys={e["wydzielenie"] for e in changed}
        prior=pair_group(keys)
        cost_old=_quality(prior)
        cost_new=_quality(changed)
        penalty_old=(ocena_dodatkowa(prior)
                     if ocena_dodatkowa else 0.0)
        penalty_new=(ocena_dodatkowa(changed)
                     if ocena_dodatkowa else 0.0)
        if penalty_new>penalty_old+1e-6:
            return False
        updates={e["id"]:e for e in changed}
        if any(e["id"] not in current for e in changed):
            return False
        proposed=[updates.get(e["id"],e) for e in current.values()]
        problems=geo.waliduj_uklad(proposed)
        after_keys={_issue_key(i) for i in problems}
        if not after_keys.issubset(old_keys):
            return False
        # Samo naprawienie kolizji jest zawsze korzystne,
        # nawet jeśli wymaga wydłużenia linii. Gdy lista błędów
        # się nie zmniejsza, wymagamy poprawy estetyki.
        if not (after_keys<old_keys or cost_new<cost_old-1e-5):
            return False
        for e in changed:
            current[e["id"]]=dict(e)
        all_errors,old_keys=problems,after_keys
        accepted+=1
        improved_labels.extend(names.get(k,str(k)) for k in keys)
        return True

    for index,key in enumerate(target,1):
        attempts+=1
        if postep:
            postep({"etap":"estetyka","indeks":index,
                    "liczba_grup":len(target),"wydzielenie":key})
        group=pair_group([key])
        plans=engine.opcje_wydzielenia(
            group,granice,poligony,limit=72,
            ocena_dodatkowa=ocena_dodatkowa)
        fixed=[e for e in current.values() if e["wydzielenie"]!=key]
        # Testuj najlepsze po jakości, a nie po przesunięciu od oryginału.
        ordered=sorted(plans,key=lambda plan:(
            _quality(plan),ocena_dodatkowa(plan) if ocena_dodatkowa else 0))
        for plan in ordered:
            # Przy nierozwiązanych kolizjach (np. 6s) nawet plan
            # droższy wizualnie może być lepszy od obecnego.
            if (_quality(plan)>=_quality(group)-1e-5
                    and not any(
                        set(issue["elementy"]) &
                        {e["id"] for e in group} for issue in all_errors)):
                break
            if any(engine._kolizja_miedzy(plan,[f],2.5) for f in fixed):
                continue
            if acceptable(plan):
                break

    # Wspólne przestawianie dwóch sąsiadów umożliwia m.in.
    # przejęcie miejsca litery drugiego wydzielenia przez opis.
    successful_pairs=0
    pair_attempts=0
    duo_seen=set()
    for key in target:
        if pair_attempts>=maks_par:
            break
        group=pair_group([key])
        if not any(e.get("wysiegnik") for e in group):
            continue
        neighbors=engine._sasiedztwo(grouped,key,ile=7)[1:]
        for neighbor in neighbors[:3]:
            if pair_attempts>=maks_par:
                break
            duo=frozenset((key,neighbor))
            if duo in duo_seen:
                continue
            duo_seen.add(duo)
            pair_attempts+=1
            attempts+=1
            variants={k:engine.opcje_wydzielenia(
                pair_group([k]),granice,poligony,limit=48,
                ocena_dodatkowa=ocena_dodatkowa) for k in duo}
            if any(not v for v in variants.values()):
                continue
            # Dokładna próba bierze pod uwagę nieruchome otoczenie,
            # a akceptacja pilnuje, żeby nie pogorszyć czystości MAP.
            solved,_=engine._wspolny_plan_dokladny(
                duo,variants.__getitem__,current,current,2.5,
                ocena_dodatkowa=ocena_dodatkowa)
            if solved and acceptable(solved):
                successful_pairs+=1
                break

    result=[current[e["id"]] for e in elementy]
    return result,{
        "skanowane_grupy":len(target),
        "proby_wariantow":attempts,
        "przyjete_poprawki":accepted,
        "ulepszone_pary_sasiadow":successful_pairs,
        "proby_par_sasiadow":pair_attempts,
        "zmodyfikowane_wydzielenia":sorted(set(improved_labels)),
        "przed":before,"po":_metrics(result),
        "problemy_po":len(all_errors),
        "gwarancja":"Bez nowych kolizji i bez wzrostu naliczonych kar GIS"
    }
