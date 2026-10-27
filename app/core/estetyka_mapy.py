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
    # W grupie kilku sąsiadów licz tylko pary Z TEGO SAMEGO
    # wydzielenia, nigdy litery 6j do opisu 6k.
    owners=defaultdict(list)
    for e in group:
        owners[e["wydzielenie"]].append(e)
    for entries in owners.values():
        letter=next((e for e in entries if e["rodzaj"]=="litera"),None)
        desc=next((e for e in entries if e["rodzaj"]=="opis"),None)
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
            maks_grup=36, maks_par=12, postep=None,
            priorytety=(), chronione=(), maks_trojek=6):
    """Maksymalizuj jakość tylko gdy nie gorsza od bieżącego układu.

    Pierwszeństwo mają najdłuższe wysięgniki w jednostkach rozmiaru
    napisu oraz wydzielenia nadal błędne. Najpierw lokalne próby,
    potem ograniczona liczba zmian sąsiadujących par.
    """
    if maks_grup<0 or maks_par<0 or maks_trojek<0:
        raise ValueError("Budzet estetyki nie moze byc ujemny")
    current={e["id"]:dict(e) for e in elementy}
    all_errors=geo.waliduj_uklad(list(current.values()))
    old_keys={_issue_key(i) for i in all_errors}
    granice=engine.Granice(poligony)
    before=_metrics(elementy)
    names=nazwy or {}
    # Zatwierdzonych przez kartografa wydzieleń nie ruszaj ani jako
    # głównego celu, ani jako sąsiada wspólnej optymalizacji.
    locked_names={str(name).strip().casefold() for name in chronione
                  if str(name).strip()}
    attempts=accepted=0
    improved_labels=[]
    grouped=defaultdict(list)
    for e in current.values():
        grouped[e["wydzielenie"]].append(e)

    def pair_group(keys):
        return [current[e["id"]] for k in keys for e in grouped[k]]

    protected={key for key in grouped if
               str(names.get(key,key)).strip().casefold() in locked_names}

    def attractiveness(key):
        group=pair_group([key])
        score=_quality(group)
        if any(e["id"] in {i for p in all_errors for i in p["elementy"]}
               for e in group):
            score+=500.0
        return score

    todo=sorted((key for key in grouped if key not in protected),
                key=lambda k:(-attractiveness(k),str(k)))
    # Wskazane przez kartografa wydzielenia analizuj jako pierwsze,
    # ale pozostały budżet wciąż przeznaczaj automatycznie na całą mapę.
    priority_labels={str(name).strip().casefold()
                     for name in priorytety if str(name).strip()}
    priority_keys=sorted(
        (k for k in todo
         if str(names.get(k,k)).strip().casefold() in priority_labels),
        key=lambda k:str(names.get(k,k)))
    target=list(priority_keys[:maks_grup])
    target+=([k for k in todo if k not in target and attractiveness(k)>0]
             [:max(0,maks_grup-len(target))])
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
        if keys & protected:
            return False
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
        has_issues=any(e["id"] in {
            ident for issue in all_errors for ident in issue["elementy"]
        } for e in group)
        plans=engine.opcje_wydzielenia(
            group,granice,poligony,limit=72,
            ocena_dodatkowa=ocena_dodatkowa,
            ocena_planu=_quality,ratunek=has_issues)
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
    attempts_per_key=Counter()
    # Przed kolejnym skracaniem poprawnych wysięgników przejdź
    # do wydzieleń wciąż z błędami, od największej liczby błędów.
    # Wcześniej 24 próby mogły zostać wyczerpane na pierwszym
    # jednym/dwóch wydzieleniach.
    remaining_count=Counter(
        current[ident]["wydzielenie"]
        for issue in all_errors
        for ident in issue["elementy"] if ident in current)
    repair_first=sorted(target,key=lambda k:(
        -remaining_count[k],target.index(k)))
    bad_count=sum(bool(remaining_count[k]) for k in repair_first)
    # Przy kilku trudnych wydzieleniach gwarantujemy każdemu
    # dostęp do solvera, zachowując łączny limit prób.
    per_group_limit=max(1,min(8,maks_par//max(1,bad_count)))
    for key in repair_first:
        if pair_attempts>=maks_par:
            break
        if attempts_per_key[key]>=per_group_limit:
            continue
        group=pair_group([key])
        # Kolizja bez wysięgnika też jest problemem! Wcześniej
        # pomijaliśmy tutaj np. 6s, gdzie litera zasłania własny opis,
        # chociaż w pojedynkę nie da się naprawić tej pary.
        unresolved_ids={ident for issue in all_errors
                        for ident in issue["elementy"]}
        needs_repair=any(e["id"] in unresolved_ids for e in group)
        if not needs_repair and not any(e.get("wysiegnik") for e in group):
            continue
        # Szukaj sąsiadów blokujących KONKRETNE lepsze warianty.
        # Same poligony mogą być odległe, lecz opis jednego z nich
        # może blokować najbliższe miejsce przy drugim (np. 6j/6k).
        candidate_plans=engine.opcje_wydzielenia(
            group,granice,poligony,limit=72,
            ocena_dodatkowa=ocena_dodatkowa,
            ocena_planu=_quality,ratunek=needs_repair)
        blocks=Counter()
        by_group=current
        for blockers,plan in engine._blokady_planow(
                candidate_plans,by_group,key,2.5):
            if (_quality(plan)<_quality(group) or
                    any(e["id"] in {
                        ident for err in all_errors
                        for ident in err["elementy"]} for e in group)):
                for other in blockers:
                    blocks[other]+=1
        geometry=engine._sasiedztwo(grouped,key,ile=9)[1:]
        ranked_blockers=sorted(blocks,key=lambda k:(-blocks[k],str(k)))
        neighbors=list(dict.fromkeys(
            ranked_blockers+geometry))
        for neighbor in (n for n in neighbors if n not in protected):
            if pair_attempts>=maks_par or attempts_per_key[key]>=per_group_limit:
                break
            duo=frozenset((key,neighbor))
            if duo in duo_seen:
                continue
            duo_seen.add(duo)
            pair_attempts+=1
            attempts_per_key[key]+=1
            attempts+=1
            variants={k:engine.opcje_wydzielenia(
                pair_group([k]),granice,poligony,limit=72,
                ocena_dodatkowa=ocena_dodatkowa,
                ocena_planu=_quality,
                ratunek=any(e["id"] in unresolved_ids
                           for e in pair_group([k]))) for k in duo}
            # Bez zachowania bieżącej pozycji sąsiada dokładny duet
            # był ZAWSZE zmuszony do zmiany obu wydzieleń, nawet gdy
            # najlepiej było tylko oddać miejsce docelowemu opisowi.
            for k in duo:
                incumbent=pair_group([k])
                if not geo.waliduj_uklad(incumbent):
                    variants[k].append(incumbent)
            if any(not v for v in variants.values()):
                continue
            # Dokładna próba bierze pod uwagę nieruchome otoczenie,
            # a akceptacja pilnuje, żeby nie pogorszyć czystości MAP.
            solved,_=engine._wspolny_plan_dokladny(
                duo,variants.__getitem__,current,current,2.5,
                ocena_dodatkowa=ocena_dodatkowa,
                ocena_planu=_quality)
            if solved and acceptable(solved):
                successful_pairs+=1
                break

    # Dokładne rozwiązanie trzech faktycznie blokujących się wydzieleń.
    # Solver par nie mógł rozwiązać wariantu, który wymaga jednocześnie
    # zwolnienia przestrzeni przez DWA inne wydzielenia.
    triple_attempts=0
    successful_triples=0
    triple_per_group=Counter()
    triple_skip_counts=Counter()
    seen_triples=set()
    for key in repair_first:
        if triple_attempts>=maks_trojek:
            break
        bad_ids={ident for issue in all_errors for ident in issue["elementy"]}
        own=pair_group([key])
        if not any(e["id"] in bad_ids for e in own):
            continue
        proposals=engine.opcje_wydzielenia(
            own,granice,poligony,limit=72,
            ocena_dodatkowa=ocena_dodatkowa,
            ocena_planu=_quality,ratunek=True)
        situations=engine._blokady_planow(proposals,current,key,2.5)
        current_penalty=(ocena_dodatkowa(own)
                         if ocena_dodatkowa else 0.0)
        nearby=engine._sasiedztwo(grouped,key,ile=10)[1:]
        choices=[]
        for blockers,proposal in situations:
            if blockers & protected:
                triple_skip_counts["blokada_chroniona"]+=1
                continue
            if len(blockers)>2:
                triple_skip_counts["wiecej_niz_dwa_blokujace"]+=1
                continue
            if (ocena_dodatkowa is not None and
                    ocena_dodatkowa(proposal)>current_penalty+1e-6):
                triple_skip_counts["wzrost_kary_GIS"]+=1
                continue
            others=list(sorted(blockers,key=str))
            if len(others)==1:
                companion=next((n for n in nearby
                                if n!=others[0] and n not in protected),
                               None)
                if companion is not None:
                    others.append(companion)
            if len(others)!=2 or any(n not in grouped for n in others):
                triple_skip_counts["brak_podwojnego_sasiedztwa"]+=1
                continue
            trio=frozenset((key,others[0],others[1]))
            if trio in seen_triples:
                continue
            # Najpierw warianty blokowane przez najmniej sąsiadów,
            # a potem najkrótsze wysięgniki.
            choices.append((len(blockers),_quality(proposal),
                            tuple(sorted(trio,key=str)),trio,proposal))
        choices.sort(key=lambda x:(x[0],x[1],x[2]))
        for _,_,_,trio,favored in choices:
            if triple_attempts>=maks_trojek:
                break
            if trio in seen_triples:
                continue
            seen_triples.add(trio)
            triple_attempts+=1
            triple_per_group[str(names.get(key,key))]+=1
            if postep:
                postep({"etap":"trojki","indeks":triple_attempts,
                        "liczba_grup":maks_trojek,
                        "wydzielenie":key,
                        "sasiedzi":[str(names.get(n,n))
                                    for n in sorted(trio-{key},key=str)]})
            variants={}
            for member in trio:
                part=pair_group([member])
                has_problem=any(e["id"] in bad_ids for e in part)
                options=engine.opcje_wydzielenia(
                    part,granice,poligony,limit=32,
                    ocena_dodatkowa=ocena_dodatkowa,
                    ocena_planu=_quality,ratunek=has_problem)
                if member==key:
                    # Zachowaj konkretny wariant, który spowodował
                    # wybór tego trójkąta, nawet jeśli nie zmieścił
                    # się w ograniczonej puli 32 innych rodzin.
                    options=[favored]+options
                if not geo.waliduj_uklad(part):
                    options.append(part)
                variants[member]=options
            if any(not v for v in variants.values()):
                triple_skip_counts["brak_wariantow_czlonka"]+=1
                continue
            solved,_=engine._wspolny_plan_dokladny(
                trio,variants.__getitem__,current,current,2.5,
                ocena_dodatkowa=ocena_dodatkowa,
                ocena_planu=_quality)
            if solved and acceptable(solved):
                successful_triples+=1
                break

    # Informacja diagnostyczna dla ostatnich błędnych grup.
    # Nie interpretuje braku planu w skończonym zbiorze jako
    # dowodu, że układ poprawny geometrycznie nie istnieje.
    unresolved_diagnostics=[]
    remaining=Counter(current[i]["wydzielenie"]
                      for issue in all_errors for i in issue["elementy"]
                      if i in current)
    for key in sorted(remaining,key=lambda k:(-remaining[k],str(k)))[:8]:
        if key in protected:
            continue
        incumbent=pair_group([key])
        choices=engine.opcje_wydzielenia(
            incumbent,granice,poligony,limit=72,
            ocena_dodatkowa=ocena_dodatkowa,
            ocena_planu=_quality,ratunek=True)
        blockers=engine._blokady_planow(choices,current,key,2.5)
        clean=[p for blocked,p in blockers if not blocked]
        penalty_current=(ocena_dodatkowa(incumbent)
                         if ocena_dodatkowa else 0.0)
        penalty_clean=[
            ocena_dodatkowa(p) if ocena_dodatkowa else 0.0
            for p in clean]
        frequent=Counter(
            b for blocked,_ in blockers for b in blocked)
        unresolved_diagnostics.append({
            "wydzielenie":str(names.get(key,key)),
            "liczba_problemow":len([
                issue for issue in all_errors if any(
                    current.get(i,{}).get("wydzielenie")==key
                    for i in issue["elementy"])]),
            "liczba_wygenerowanych_planow":len(choices),
            "plany_bez_blokad_napisow":len(clean),
            "plany_bez_blokad_i_wzrostu_kary_GIS":
                sum(x<=penalty_current+1e-6 for x in penalty_clean),
            "biezaca_kara_GIS":round(penalty_current,2),
            "najmniejsza_kara_wolnego_planu_GIS":
                round(min(penalty_clean),2) if penalty_clean else None,
            "najczestsze_blokady_wariantow":[
                {"wydzielenie":str(names.get(k,k)), "ile":count}
                for k,count in frequent.most_common(5)],
            "uwaga":"Tryb ratunkowy i maksymalnie 72 warianty; brak nie dowodzi niemozliwosci poprawy."
        })
    result=[current[e["id"]] for e in elementy]
    return result,{
        "skanowane_grupy":len(target),
        "diagnostyka_nierozwiazanych":unresolved_diagnostics,
        "chronione_wydzielenia":sorted(names.get(k,str(k)) for k in protected),
        "proby_wariantow":attempts,
        "przyjete_poprawki":accepted,
        "ulepszone_pary_sasiadow":successful_pairs,
        "proby_trojek_sasiadow":triple_attempts,
        "ulepszone_trojki_sasiadow":successful_triples,
        "proby_trojek_na_wydzielenie":dict(triple_per_group),
        "pominiete_trojki_powody":dict(triple_skip_counts),
        "proby_par_sasiadow":pair_attempts,
        "proby_par_na_wydzielenie":{
            str(names.get(k,k)):int(attempts_per_key[k])
            for k in repair_first if attempts_per_key[k]},
        "zmodyfikowane_wydzielenia":sorted(set(improved_labels)),
        "przed":before,"po":_metrics(result),
        "problemy_po":len(all_errors),
        "gwarancja":"Bez nowych kolizji i bez wzrostu naliczonych kar GIS"
    }
