# -*- coding: utf-8 -*-
"""Eksperymentalne warianty dla ciasnego wydzielenia GEO-MAP.

Cel: znaleźć kilka rzeczywiście różnych, czytelnych pozycji L2/L3
w bardzo wąskim poligonie (np. 6gx) i oddać je do oceny w GEO-MAP.
Nigdy nie nadpisuje źródła ani nie uznaje uproszczonej obwiedni
fontu za rzeczywiste glify. Tylko wskazane L2/L3 są przesuwane.

Celowo osobny tryb, NIE automatyczna akceptacja: dla 6gx żaden
niewielki prostokąt pełnego fontu nie mieści się we wnętrzu
wąskiego poligonu; potrzebne mogą być proste wysięgniki.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import math

from app.core import diagnostyka_map as dm
from app.core import eksport_propozycji_map as export
from app.core import geometria_ukladu as geo
from app.core import kontury_map as km
from app.core import opisy_na_mape as onm
from app.core import silnik_grupowy as engine
from app.core import uklad_opisow as uk
from app.core import wznow_raport as resume


def _center(r):
    return ((r[0]+r[2])/2,(r[1]+r[3])/2)


def _compact(r, factor):
    """WYŁĄCZNIE eksperymentalna miara ryzyka, NIE geometria MAP."""
    cx,cy=_center(r)
    return (cx-(r[2]-r[0])*factor/2,
            cy-(r[3]-r[1])*factor/2,
            cx+(r[2]-r[0])*factor/2,
            cy+(r[3]-r[1])*factor/2)


def ocen_plan(plan, pozostale, factor=.75):
    """Wyżej karz kolizje glifów, niż konserwatywne prostokąty.

    Factor poniżej 1 jest PROBĄ wizualnego zajęcia miejsca, nie
    skalowaniem fontu i nie może automatycznie zatwierdzać mapy.
    """
    if not 0<factor<=1:
        raise ValueError("Wspolczynnik wizualny musi byc w (0,1]")
    hard=soft=lead_hits=0
    crossing_leaders=existing_leader_through_text=0
    for e in plan:
        r=e["prostokat"]
        visual=_compact(r,factor)
        for f in pozostale:
            if geo.prostokaty_koliduja(r,f["prostokat"]):
                hard+=1
            if geo.prostokaty_koliduja(visual,f["prostokat"]):
                soft+=1
            w=e.get("wysiegnik")
            other_leader=f.get("wysiegnik")
            if w and geo.odcinek_przecina_prostokat(
                    *w, f["prostokat"],wnetrze=True):
                lead_hits+=1
            if other_leader and geo.odcinek_przecina_prostokat(
                    *other_leader, r, wnetrze=True):
                existing_leader_through_text+=1
            if w and other_leader and geo.wysiegniki_koliduja(
                    w, other_leader,
                    to_samo_wydzielenie=(
                        e["wydzielenie"]==f["wydzielenie"])):
                crossing_leaders+=1
    own=0
    if len(plan)==2 and geo.prostokaty_koliduja(
            plan[0]["prostokat"],plan[1]["prostokat"]):
        own=1
    leader_length=sum(math.dist(*e["wysiegnik"])
                      for e in plan if e.get("wysiegnik"))
    return {
        "konflikty_pelnych_prostokatow":hard,
        "konflikty_probnych_obwiedni":soft,
        "wysiegniki_przez_inne_napisy":lead_hits,
        "przeciecia_z_cudzymi_wysiegnikami":crossing_leaders,
        "cudze_wysiegniki_przez_nowe_napisy":existing_leader_through_text,
        "nakladanie_wlasnych_prostokatow":own,
        "dlugosc_wysiegnikow_m":round(leader_length,2),
        "ocena":round(150*own+120*soft+25*hard+
                       130*lead_hits+600*crossing_leaders+
                       600*existing_leader_through_text+
                       0.09*leader_length,3)
    }


def _rodzina(plan, polygon):
    desc=next((e for e in plan if e["rodzaj"]=="opis"),plan[-1])
    c=_center(desc["prostokat"])
    b=engine.bbox(polygon)
    bx,by=_center(b)
    dx,dy=c[0]-bx,c[1]-by
    side=("prawo" if dx>0 else "lewo") if abs(dx)>abs(dy) else (
        "gora" if dy>0 else "dol")
    kinds=tuple(sorted(e["rodzaj"] for e in plan if e.get("wysiegnik")))
    return kinds,side


def _lokalne_plany_waskiego_poligonu(grupa, *, maks_odleglosc=145.0,
                                   maks_wysiegnik=130.0, limit=650):
    """Bezpośrednia próba ZWARTYCH układów przy własnym konturze.

    Ogólny silnik wymaga, aby cały długi prostokąt L3 nie przeciął
    żadnego obiektu mapy. W gęstej mapie odrzuca przez to każdą
    BLISKĄ propozycję, choć prawdziwe glify GEO-MAP zajmują mniejszy
    obszar. Tutaj nie omijamy walidacji L2/L3 ani kolizji z cudzymi
    napisami/wysięgnikami: jedynie przecięcia z podkładem mapy
    pozostają do oceny kartografa w pliku eksperymentalnym.
    """
    if len(grupa)!=2:
        return []
    letter=next((e for e in grupa if e["rodzaj"]=="litera"),None)
    desc=next((e for e in grupa if e["rodzaj"]=="opis"),None)
    if letter is None or desc is None:
        return []
    poly=letter["poligon"]
    x0,y0,x1,y1=engine.bbox(poly)
    mx,my=_center((x0,y0,x1,y1))
    dlw=desc["prostokat"][2]-desc["prostokat"][0]
    dlh=desc["prostokat"][3]-desc["prostokat"][1]
    lw=letter["prostokat"][2]-letter["prostokat"][0]
    lh=letter["prostokat"][3]-letter["prostokat"][1]
    targets=list(engine._cele(poly,n=11))
    if not targets:
        return []
    result=[]
    seen=set()
    for side in ("lewo","prawo","dol","gora"):
        sign=-1 if side in ("lewo","dol") else 1
        for distance in (5.0,12.0,22.0,36.0):
            for yf in (-.36,-.18,0.0,.18,.36):
                if side in ("dol","gora"):
                    dx=mx+yf*(x1-x0)
                    cy=(y0-dlh/2-distance if sign<0
                        else y1+dlh/2+distance)
                    closer_y=(y0-lh/2-9 if sign<0
                              else y1+lh/2+9)
                    letter_centers=[
                        (dx+d,closer_y)
                        for d in (-dlw/2-lw/2-9,dlw/2+lw/2+9)]
                    letter_centers += [
                        (dx+d,cy+sign*(dlh/2+lh/2+8))
                        for d in (-lw,0,lw)]
                else:
                    dx=(x0-dlw/2-distance if sign<0
                        else x1+dlw/2+distance)
                    cy=my+yf*(y1-y0)
                    toward=(dx+sign*(dlw/2+lw/2+5)*(-1))
                    letter_centers=[
                        (toward,cy+d) for d in (-lh*.5,0,lh*.5)]
                    letter_centers += [
                        (x0-10-lw/2 if sign<0 else x1+10+lw/2,
                         my+d*(y1-y0))
                        for d in (-.25,0,.25)]
                rd=engine.prost((dx,cy),(dlw,dlh))
                # Przy dlugim opisie srodek moze byc 170 m od
                # wydzielenia, chociaz koniec GLIFU lezy zaledwie
                # 5 m od jego granicy. Liczy sie dystans OBWIEDNI.
                if engine.odleglosc_boxow(rd,(x0,y0,x1,y1))>maks_odleglosc:
                    continue
                for lx,ly in letter_centers:
                    rl=engine.prost((lx,ly),(lw,lh))
                    if engine.odleglosc_boxow(
                            rl,(x0,y0,x1,y1))>maks_odleglosc:
                        continue
                    if geo.prostokaty_koliduja(
                            engine.powieksz(rl,1.25),
                            engine.powieksz(rd,1.25)):
                        continue
                    nearest=sorted(targets,key=lambda target:(
                        math.dist(target,(lx,ly))+
                        math.dist(target,(dx,cy)),target))
                    for target in nearest[:5]:
                        pair=[]
                        for e,r in ((letter,rl),(desc,rd)):
                            fully_inside=geo.prostokat_w_poligonie(
                                r,e["poligon"])
                            leader=None if fully_inside else engine.lider(r,target)
                            if leader and math.dist(*leader)>maks_wysiegnik:
                                break
                            pair.append({**e,"prostokat":r,
                                         "wysiegnik":leader})
                        if len(pair)!=2:
                            continue
                        if geo.waliduj_uklad(pair):
                            continue
                        signature=tuple(
                            (e["id"],
                             tuple(round(v,2) for v in e["prostokat"]),
                             tuple(round(v,2) for v in e["wysiegnik"][1])
                             if e.get("wysiegnik") else None)
                            for e in pair)
                        if signature in seen:
                            continue
                        seen.add(signature)
                        result.append(pair)
                        if len(result)>=limit:
                            return result
    return result


def wybierz_kandydatow(plans, remaining, polygon, *,
                       ile=4, factor=.75,
                       maks_odleglosc_srodka=145.0,
                       maks_dlugosc_wysiegnika=130.0,
                       diagnostyka=None):
    if ile<1:
        raise ValueError("Liczba prob musi byc dodatnia")
    ranked=[]
    rejected=Counter()
    box=engine.bbox(polygon)
    point=_center(box)
    for plan in plans:
        if not plan or len({e["id"] for e in plan})!=len(plan):
            rejected["niekompletny_plan"]+=1
            continue
        if (len(plan)!=2 or
                {e["rodzaj"] for e in plan}!={"litera","opis"}):
            rejected["brak_pary_L2_L3"]+=1
            continue
        if any(engine.odleglosc_boxow(
                e["prostokat"],box)>maks_odleglosc_srodka
                for e in plan):
            rejected["napisy_zbyt_daleko_od_wydzielenia"]+=1
            continue
        if any(e.get("wysiegnik") and
               math.dist(*e["wysiegnik"])>
               maks_dlugosc_wysiegnika for e in plan):
            rejected["za_dlugi_wysiegnik"]+=1
            continue
        score=ocen_plan(plan,remaining,factor)
        if (score["przeciecia_z_cudzymi_wysiegnikami"] or
                score["cudze_wysiegniki_przez_nowe_napisy"] or
                score["wysiegniki_przez_inne_napisy"]):
            rejected["kolizja_z_istniejacymi_wysiegnikami_lub_napisami"]+=1
            continue
        family=_rodzina(plan,polygon)
        identifier=tuple((e["id"],tuple(round(v,2) for v in e["prostokat"]))
                         for e in plan)
        ranked.append((score["ocena"],family,identifier,plan,score))
    ranked.sort(key=lambda t:(t[0],str(t[1]),t[2]))
    if diagnostyka is not None:
        diagnostyka.update({
            "wygenerowanych":len(plans),
            "przeszlo_filtry":len(ranked),
            "odrzucone_powody":dict(rejected),
            "maks_odleglosc_obrysu_od_bbox_poligonu_m":
                maks_odleglosc_srodka,
            "maks_dlugosc_wysiegnika_m":maks_dlugosc_wysiegnika})
    result=[]
    used=set()
    # Najpierw sprawdzamy różne strategie i strony wydzielenia.
    for row in ranked:
        if row[1] not in used:
            result.append(row)
            used.add(row[1])
            if len(result)>=ile:
                return result
    for row in ranked:
        if len(result)>=ile:
            break
        if row not in result:
            result.append(row)
    return result


def _zmiany_z_bazy(przed, obecne, plan):
    by_id={e["id"]:e for e in przed}
    updates={e["id"]:e for e in plan}
    out=[]
    for e in obecne:
        original=by_id[e["id"]]
        new=updates.get(e["id"],e)
        if (max(abs(a-b) for a,b in zip(
                original["prostokat"],new["prostokat"]))<1e-6
                and original.get("wysiegnik")==new.get("wysiegnik")):
            continue
        out.append({
            "id":e["id"],"tekst":e["tekst"],"rodzaj":e["rodzaj"],
            "przed":list(original["prostokat"]),
            "po":list(new["prostokat"]),
            "wysiegnik":new.get("wysiegnik")})
    return out


def przygotuj(mapa_path, baseline_json, nazwa, prefix, *,
              ile=4, factor=.75, candidate_limit=96,
              maks_odleglosc_srodka=145.0,
              maks_dlugosc_wysiegnika=130.0):
    mapa=onm.wczytaj_mape(mapa_path)
    data=json.loads(Path(baseline_json).read_text(encoding="utf-8"))
    skala=data["skala"]
    h=data["wysokosc_mm"]
    original,_=dm.elementy_z_mapy(mapa,skala,h)
    current,_=resume.odtworz(original,mapa,skala,h,baseline_json)
    letter=[e for e in current if
            e["rodzaj"]=="litera" and
            e["tekst"].casefold()==nazwa.casefold()]
    if len(letter)!=1:
        raise ValueError("Wydzielenie A1 musi byc jednoznaczne: "+nazwa)
    key=letter[0]["wydzielenie"]
    group=[e for e in current if e["wydzielenie"]==key]
    if len(group)!=2:
        raise ValueError("Oczekiwano pary L2/L3 w wydzieleniu: "+nazwa)
    others=[e for e in current if e["wydzielenie"]!=key]
    objects=uk.wszystkie_poligony(mapa)
    boundaries=[part for obj in objects
                for part in km.fragmenty_z_linii(obj["linie"])]
    strict_plans=engine.opcje_wydzielenia(
        group,engine.Granice(boundaries),boundaries,
        limit=candidate_limit,ratunek=True)
    local_plans=_lokalne_plany_waskiego_poligonu(
        group,maks_odleglosc=maks_odleglosc_srodka,
        maks_wysiegnik=maks_dlugosc_wysiegnika)
    plans=local_plans+strict_plans
    diagnostics={
        "plany_ogolnego_silnika":len(strict_plans),
        "plany_lokalne_przy_poligonie":len(local_plans)
    }
    selected=wybierz_kandydatow(
        plans,others,letter[0]["poligon"],ile=ile,factor=factor,
        maks_odleglosc_srodka=maks_odleglosc_srodka,
        maks_dlugosc_wysiegnika=maks_dlugosc_wysiegnika,
        diagnostyka=diagnostics)
    if not selected:
        raise ValueError(
            "Nie znaleziono czytelnego wariantu 6gx blisko poligonu,"
            " bez przeciec z cudzymi wysiegnikami i napisami."
            " Nic nie zapisano. Szczegoly: "+str(diagnostics))
    summary={
        "status":"TYLKO DO OCENY W GEO-MAP - NIE JEST TO GOTOWA POPRAWKA",
        "wydzielenie":nazwa,
        "uuid":key,
        "mapa_bazowa":str(baseline_json),
        "model_obwiedni_wizualnej":factor,
        "ostrzezenie":(
            "Wspolczynnik jest hipotetyczny i sluzy tylko do "
            "RANKINGU. Nie zmienia czcionki, nie dowodzi braku "
            "kolizji i nie znosi wymogu oceny kartografa."),
        "liczba_planow_wygenerowanych":len(plans),
        "filtry_jakosci":diagnostics,
        "warianty":[]
    }
    # Nie dopuszczaj nadpisywania starych testów nawet w razie
    # wcześniejszego przerwania działania programu.
    destination=Path(prefix)
    names=[destination.with_name(
        destination.name+"_"+str(i).zfill(2)+".MAP")
        for i in range(1,len(selected)+1)]
    detail=destination.with_name(destination.name+"_ocena.json")
    if any(p.exists() for p in names+[detail]):
        raise FileExistsError("Pliki testowe juz istnieja: podaj nowy --prefix")
    for idx,(_,family,_,plan,score) in enumerate(selected):
        report=copy.deepcopy(data)
        report["zmiany"]=_zmiany_z_bazy(original,current,plan)
        # To jest jedynie obiekt pośredni dla istniejącego eksportera
        # zapewniającego bezpieczny zapis offsetów i round-trip.
        export.eksportuj_kopie(mapa_path,report,names[idx])
        summary["warianty"].append({
            "numer":idx+1,"plik":str(names[idx]),
            "rodzina":{"wysiegniki":family[0],"strona":family[1]},
            "ryzyka":score,
            "pozycje":[{"id":e["id"],"rodzaj":e["rodzaj"],
                        "srodek":list(_center(e["prostokat"])),
                        "wysiegnik":e.get("wysiegnik")}
                       for e in plan]})
    detail.write_text(json.dumps(summary,ensure_ascii=False,indent=2),
                      encoding="utf-8")
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(
        description="4 niezalezne kopie GEO-MAP dla trudnego wydzielenia (TYLKO DO OCENY)")
    p.add_argument("mapa")
    p.add_argument("--bazowy-json",required=True)
    p.add_argument("--wydzielenie",default="6gx")
    p.add_argument("--prefix",default="BYSLAW_6GX_KANDYDAT")
    p.add_argument("--ile",type=int,default=4)
    p.add_argument("--wspolczynnik-oceny",type=float,default=.75)
    p.add_argument("--limit-opcji",type=int,default=96)
    p.add_argument("--maks-odleglosc",type=float,default=145.0,
                   help="Maksymalna odleglosc prostokata napisu od bbox poligonu [m] (nie odleglosc jego srodka)")
    p.add_argument("--maks-wysiegnik",type=float,default=130.0,
                   help="Maksymalna dlugosc wysiegnika [m]")
    a=p.parse_args(argv)
    if (not 0<a.wspolczynnik_oceny<=1 or a.limit_opcji<1 or a.ile<1
            or a.maks_odleglosc<=0 or a.maks_wysiegnik<=0):
        p.error("Nieprawidlowe limity/wspolczynnik")
    try:
        result=przygotuj(a.mapa,a.bazowy_json,a.wydzielenie,a.prefix,
                         ile=a.ile,factor=a.wspolczynnik_oceny,
                         candidate_limit=a.limit_opcji,
                         maks_odleglosc_srodka=a.maks_odleglosc,
                         maks_dlugosc_wysiegnika=a.maks_wysiegnik)
    except ValueError as exc:
        # Brak propozycji po rygorystycznej kontroli jest zwykłym
        # wynikiem diagnostyki, a nie awarią aplikacji.
        p.exit(2,"BRAK KANDYDATOW - nie zapisano kopii MAP.\n"+
               str(exc)+"\n")
    print("KANDYDACI do recznej oceny:",len(result["warianty"]))
    print("Wygenerowane plany:",result["liczba_planow_wygenerowanych"])
    print("Filtry:",result["filtry_jakosci"])
    for e in result["warianty"]:
        r=e["ryzyka"]
        print("  %s: %s / ryzyko wizualne=%s, pelne obrysy=%d,"
              " wysiegniki przez inne napisy=%d" % (
            e["numer"],e["plik"],r["konflikty_probnych_obwiedni"],
            r["konflikty_pelnych_prostokatow"],
            r["wysiegniki_przez_inne_napisy"]))
    print("UWAGA: kopie eksperymentalne. Ostateczna decyzja tylko w GEO-MAP.")


if __name__=="__main__":
    main()
