# -*- coding: utf-8 -*-
"""Transakcyjna naprawa kaskadowa etykiet GEO-MAP.

Nie wymaga, by każdy etap przejściowy był już bezkolizyjny:
przeniesienie A2 może wymagać kolejno zwolnienia miejsca przez 4-6
sąsiadów. Dopiero kompletny stan trafia do dotychczasowej walidacji.
Chronionych wydzieleń nie wolno przesuwać ani zasłaniać.
"""
from collections import Counter
import heapq
import math

from app.core import silnik_grupowy as engine


def napraw_kaskadowo(current, grouped, granice, poligony, *,
                    targets, protected=frozenset(), names=None,
                    ocena_dodatkowa=None, ocena_planu=None,
                    zaakceptuj, maks_przesuniec=7,
                    maks_poczatkow=4, maks_stanow=100,
                    postep=None):
    """Spróbuj przemieścić cel i kolejnych rzeczywistych blokujących.

    current: mapa id etykiety -> aktualny element (słownik).
    grouped: wydzielenie -> lista elementów (źródłowe identyfikatory).
    zaakceptuj: funkcja transakcyjnie przyjmująca całą poprawną
    propozycję albo odrzucająca ją (pełna walidacja GEO-MAP).
    """
    if min(maks_przesuniec,maks_poczatkow,maks_stanow)<0:
        raise ValueError("Limity kaskady musza byc nieujemne")
    if maks_przesuniec<2 or maks_poczatkow==0 or maks_stanow==0:
        return {"proby":0,"przyjete":0,"sprawdzone_stany":0,
                "przyczyny":{},"udane_wydzielenia":[]}

    names=names or {}
    protected=set(protected)
    boundaries=granice
    reasons=Counter()
    successes=[]
    attempts=expanded=0
    option_cache={}
    blocker_cache={}
    serial=0
    per_target={}

    def current_group(k):
        return [current[e["id"]] for e in grouped[k]]

    def quality(plan):
        if ocena_planu:
            return ocena_planu(plan)
        return sum(
            (100+math.dist(*e["wysiegnik"]) if e.get("wysiegnik")
             else 0) for e in plan)

    def alternatives(k):
        if k not in option_cache:
            original=current_group(k)
            opts=engine.opcje_wydzielenia(
                original,boundaries,poligony,limit=72,
                ocena_dodatkowa=ocena_dodatkowa,
                ocena_planu=ocena_planu,
                ratunek=True)
            # Dedup + reprezentacja różnych kierunków, dostarczona
            # przez opcje_wydzielenia. Maks. 24 planów na sąsiada,
            # bez wyznaczania pełnego iloczynu dla 268 jednostek.
            option_cache[k]=opts[:24]
        return option_cache[k]

    def blockages(k,plan):
        sig=(k,tuple((e["id"],tuple(e["prostokat"]),
                      tuple(e["wysiegnik"][1]) if e.get("wysiegnik")
                      else None) for e in plan))
        if sig not in blocker_cache:
            blockers,_=engine._blokady_planow(
                [plan],current,k,2.5)[0]
            blocker_cache[sig]=blockers
        return blocker_cache[sig]

    def conflict(assignments):
        keys=set(assignments)
        plans=list(assignments.values())
        for i,p in enumerate(plans):
            for q in plans[i+1:]:
                if engine._kolizja_miedzy(p,q,2.5):
                    return None
        blocking=set()
        for k,plan in assignments.items():
            blocking.update(blockages(k,plan)-keys)
        return blocking

    def state_score(assignments,blocking):
        penalty=sum(ocena_dodatkowa(p) for p in assignments.values()
                    ) if ocena_dodatkowa else 0.0
        aesthetic=sum(quality(p) for p in assignments.values())
        # Nie nagradzaj przeniesienia problemu na następnego sąsiada.
        return (len(blocking),len(assignments),penalty,aesthetic)

    for key in targets:
        if key in protected or key not in grouped:
            continue
        # Po udanej zmianie czytaj nowe położenia wszystkich sąsiadów.
        option_cache.clear()
        blocker_cache.clear()
        initial=[]
        for plan in alternatives(key):
            blocking=blockages(key,plan)
            if protected & blocking:
                reasons["kolizja_z_chronionym"]+=1
                continue
            if len(blocking)+1>maks_przesuniec:
                reasons["potrzeba_wiecej_przesuniec"]+=1
                continue
            initial.append((len(blocking),
                            ocena_dodatkowa(plan) if ocena_dodatkowa else 0,
                            quality(plan),plan))
        # Różne pozycje z TAKIM SAMYM zestawem blokujących sąsiadów
        # nie są równoważne. Wcześniej traciliśmy np. 39 z 42 planów
        # 6s zablokowanych przez 6r, w tym możliwe czyste rozwiązania.
        # Rozkładamy pulę między rodziny blokad zamiast odrzucać duplikaty.
        initial.sort(key=lambda x:x[:3])
        families={}
        for nblock,penalty,score,plan in initial:
            signature=tuple(sorted(blockages(key,plan),key=str))
            families.setdefault(signature,[]).append((penalty,score,plan))
        for plans in families.values():
            plans.sort(key=lambda x:(x[0],x[1]))
        start_plans=[]
        # Rotacja daje szansę różnym sąsiadom oraz różnym pozycjom
        # przed tym, jak limit wyszukiwania zużyje jedna rodzina.
        for rank in range(max(map(len,families.values()),default=0)):
            for signature in sorted(families,key=lambda k:(len(k),k)):
                rows=families[signature]
                if rank<len(rows):
                    start_plans.append(rows[rank][2])
                    if len(start_plans)>=maks_poczatkow:
                        break
            if len(start_plans)>=maks_poczatkow:
                break
        per_target[str(names.get(key,key))]={
            "wygenerowane_plany":len(initial),
            "rodziny_blokad":len(families),
            "przeanalizowane_poczatki":len(start_plans),
            "stany":0,
            "odrzucenia":0,
            "zaakceptowano":False}
        if not start_plans:
            reasons["brak_kandydata_startowego"]+=1
            continue

        attempts+=1
        if postep:
            postep({"etap":"kaskada","wydzielenie":key,
                    "maks_poczatkow":len(start_plans),
                    "maks_przesuniec":maks_przesuniec})
        heap=[]
        seen=set()
        for plan in start_plans:
            assigned={key:plan}
            blocking=conflict(assigned)
            if blocking is None:
                continue
            serial+=1
            heapq.heappush(heap,(state_score(assigned,blocking),
                                 serial,assigned,blocking))
        improved=False
        inspected=0
        while heap and inspected<maks_stanow:
            _,_,assigned,blocking=heapq.heappop(heap)
            inspected+=1
            expanded+=1
            per_target[str(names.get(key,key))]["stany"]+=1
            if not blocking:
                proposal=[e for plan in assigned.values() for e in plan]
                if zaakceptuj(proposal):
                    successes.append({
                        "wydzielenie":str(names.get(key,key)),
                        "liczba_przesunietych_wydzielen":len(assigned),
                        "przesuniete":[str(names.get(k,k))
                                      for k in sorted(assigned,key=str)]})
                    improved=True
                    per_target[str(names.get(key,key))]["zaakceptowano"]=True
                    break
                reasons["odrzucone_przez_walidacje"]+=1
                per_target[str(names.get(key,key))]["odrzucenia"]+=1
                continue
            if len(assigned)>=maks_przesuniec:
                reasons["limit_liczby_przesuniec"]+=1
                continue
            if protected & blocking:
                reasons["kolizja_z_chronionym"]+=1
                continue
            if len(assigned)+len(blocking)>maks_przesuniec:
                reasons["potrzeba_wiecej_przesuniec"]+=1
                continue
            # Rozwiąż najpierw grupę, która blokuje najwięcej
            # już przyjętych planów.
            freq=Counter(
                group for k,plan in assigned.items()
                for group in (blockages(k,plan)-set(assigned)))
            next_key=min(blocking,key=lambda k:(-freq[k],str(k)))
            if next_key not in grouped:
                reasons["brak_wydzielenia_blokujacego"]+=1
                continue
            for opt_idx,plan in enumerate(alternatives(next_key)):
                if any(engine._kolizja_miedzy(plan,placed,2.5)
                       for placed in assigned.values()):
                    continue
                added=dict(assigned)
                added[next_key]=plan
                pending=conflict(added)
                if pending is None or protected & pending:
                    continue
                if len(added)+len(pending)>maks_przesuniec:
                    continue
                signature=tuple(sorted(
                    (g,tuple((e["id"],tuple(e["prostokat"]),
                              tuple(e["wysiegnik"][1])
                              if e.get("wysiegnik") else None)
                             for e in plan)) for g,plan in added.items()))
                if signature in seen:
                    continue
                seen.add(signature)
                serial+=1
                heapq.heappush(heap,(state_score(added,pending),
                                     serial,added,pending))
            # Ograniczona wiązka dla gęstych skupisk 6gx.
            if len(heap)>max(16,2*maks_stanow):
                heap=heapq.nsmallest(max(16,maks_stanow//2),heap)
                heapq.heapify(heap)
        if not improved:
            reasons["bez_poprawy"]+=1
            if inspected>=maks_stanow:
                reasons["limit_sprawdzonych_stanow"]+=1
    return {"proby":attempts,"przyjete":len(successes),
            "sprawdzone_stany":expanded,"przyczyny":dict(reasons),
            "cele":per_target,
            "udane_wydzielenia":successes}
