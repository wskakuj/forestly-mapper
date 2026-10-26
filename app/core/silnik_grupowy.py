# -*- coding: utf-8 -*-
"""Grupowy silnik rozmieszczania L2/L3 — bez operacji na plikach.

Etap 1 silnika docelowego. Ograniczone wyszukiwanie (beam search) wykonuje
wspólne decyzje dla sąsiednich wydzieleń. Nie gwarantuje znalezienia rozwiązania
w każdym gęstym fragmencie: nierozwiązane elementy pozostają w raporcie.
Obrysy tekstu są szacowane przez diagnostyka_map, nie przez GEO-MAP.
"""
from collections import defaultdict
import math

from app.core import geometria_ukladu as geo

KOLIZJE = {"napis_napis", "wysiegnik_napis", "wysiegnik_wysiegnik"}


def srodek(r):
    return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)


def powieksz(r, m):
    return (r[0] - m, r[1] - m, r[2] + m, r[3] + m)


def prost(c, rozmiar):
    w, h = rozmiar
    return (c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2)


def bbox(pts):
    # Wydzielenie może mieć wiele rozłącznych pierścieni i dziury.
    rings = geo.kontury_poligonu(pts)
    return (min(p[0] for ring in rings for p in ring),
            min(p[1] for ring in rings for p in ring),
            max(p[0] for ring in rings for p in ring),
            max(p[1] for ring in rings for p in ring))


def odleglosc_boxow(a, b):
    return math.hypot(max(0, a[0] - b[2], b[0] - a[2]),
                      max(0, a[1] - b[3], b[1] - a[3]))


def krawedzie(poligony):
    """Prawdziwe krawędzie, bez fikcyjnego domykania otwartych polilinii.

    Parametr może zawierać dawne listy wierzchołków (traktowane jako
    poligony), lub obiekty {"punkty": ..., "zamkniety": bool}. Wartość
    False jest istotna dla otwartych obiektów GEO-MAP *4214 i podobnych.
    Nie wolno dodawać do nich odcinka ostatni -> pierwszy.
    """
    seen = set()
    for item in poligony:
        if isinstance(item, dict) and "kontury" in item:
            fragments = [(ring, True) for ring in item["kontury"]]
        elif isinstance(item, dict):
            fragments = [(item["punkty"], item["zamkniety"])]
        else:
            fragments = [(item, True)]
        for pts, zamkniety in fragments:
            if len(pts) < 2:
                continue
            edges = list(zip(pts, pts[1:]))
            if zamkniety and pts[-1] != pts[0]:
                edges.append((pts[-1], pts[0]))
            for a, b in edges:
                if a == b:
                    continue
                key = tuple(sorted((tuple(a), tuple(b))))
                if key not in seen:
                    seen.add(key)
                    yield (a, b, (min(a[0], b[0]), min(a[1], b[1]),
                                  max(a[0], b[0]), max(a[1], b[1])))


class Granice:
    """Indeks krawędzi w regularnej siatce, bez dodatkowych bibliotek."""

    def __init__(self, poligony, krok=80):
        self.krok = krok
        self.grid = defaultdict(list)
        for index, edge in enumerate(krawedzie(poligony)):
            self._dodaj(edge)

    def _cells(self, r):
        k = self.krok
        for x in range(math.floor(r[0] / k), math.floor(r[2] / k) + 1):
            for y in range(math.floor(r[1] / k), math.floor(r[3] / k) + 1):
                yield (x, y)

    def _dodaj(self, edge):
        for cell in self._cells(edge[2]):
            self.grid[cell].append(edge)

    def przecina(self, r):
        seen = set()
        for cell in self._cells(r):
            for a, b, box in self.grid.get(cell, ()):
                ident = (a, b)
                if ident in seen:
                    continue
                seen.add(ident)
                if odleglosc_boxow(box, r) <= geo.EPS and (
                        geo.odcinek_przecina_prostokat(a, b, r)):
                    return True
        return False


def lider(r, cel):
    """GEO-MAP dopuszcza start z góry (133) albo dołu (69) napisu."""
    y = r[1] if cel[1] < srodek(r)[1] else r[3]
    return ((srodek(r)[0], y), cel)


def _wariant(e, r, cel=None):
    return {**e, "prostokat": r, "wysiegnik": lider(r, cel) if cel else None}


def _pozycje_wewnatrz(e, granice, margines, n=9, limit=9):
    box, poly = e["prostokat"], e["poligon"]
    w, h = box[2] - box[0], box[3] - box[1]
    bounds = bbox(poly)
    centers = [srodek(box), srodek(bounds)]
    for i in range(n):
        for j in range(n):
            centers.append((bounds[0] + (i + .5) * (bounds[2] - bounds[0]) / n,
                            bounds[1] + (j + .5) * (bounds[3] - bounds[1]) / n))
    for ring in geo.kontury_poligonu(poly):
        # Globalna siatka może ominąć wąski rozłączny obszar lub
        # fragment pierścienia. Każdy pierścień ma dodatkową lokalną
        # siatkę, nadal filtrowaną przez CAŁE wydzielenie (dziury).
        if len(ring) < 3:
            continue
        local = bbox(ring)
        centers.append(srodek(local))
        for i in range(7):
            for j in range(7):
                centers.append((
                    local[0] + (i + .5) * (local[2] - local[0]) / 7,
                    local[1] + (j + .5) * (local[3] - local[1]) / 7))
        for a, b, c in zip(
                ring, ring[1:] + ring[:1], ring[2:] + ring[:2]):
            centers.append(((a[0] + b[0] + c[0]) / 3,
                            (a[1] + b[1] + c[1]) / 3))
    centers.sort(key=lambda c: math.dist(c, srodek(box)))
    found = set()
    for c in centers:
        r = prost(c, (w, h))
        key = tuple(round(v, 3) for v in r)
        if key in found:
            continue
        found.add(key)
        if (geo.prostokat_w_poligonie(powieksz(r, margines), poly)
                and not granice.przecina(powieksz(r, margines))):
            yield r
            limit -= 1
            if not limit:
                return


def _pozycje_zewnetrzne(e, granice, poligony, margines,
                        max_odleglosc=None, limit=48):
    """Zewnętrzne kandydaty wokół całego obszaru i osobnych konturów.

    Rozłączne części GEO-MAP nie powinny tracić bliskich pozycji przez
    przeszukiwanie wyłącznie globalnego bbox. Kolejki po stronie i
    konturze zachowują różnorodność bez zmian dla 1-konturowych map.
    """
    old, poly = e["prostokat"], e["poligon"]
    w, h = old[2] - old[0], old[3] - old[1]
    distances = sorted({round(max(margines + 3, h * factor), 3)
                        for factor in (.20, .45, .80, 1.20, 1.80)})
    if max_odleglosc is not None:
        distances = [d for d in distances if d <= max_odleglosc]
    boxes = [bbox(poly)]
    if isinstance(poly, dict) and len(geo.kontury_poligonu(poly)) > 1:
        for ring in geo.kontury_poligonu(poly):
            bounds = bbox(ring)
            if bounds not in boxes:
                boxes.append(bounds)
    queues = []
    for index, (x0, y0, x1, y1) in enumerate(boxes):
        points = []
        for d in distances:
            for t in (0, .175, .35, .5, .65, .825, 1):
                x = x0 + (x1 - x0) * t
                y = y0 + (y1 - y0) * t
                points.extend(((x, y0 - h / 2 - d),
                               (x, y1 + h / 2 + d),
                               (x0 - w / 2 - d, y),
                               (x1 + w / 2 + d, y)))
        if index == 0:
            ox, oy = srodek(old)
            for d in distances:
                points.extend(((ox, oy + d), (ox, oy - d),
                               (ox + d, oy), (ox - d, oy)))
        strony = {"gora": [], "dol": [], "lewo": [], "prawo": []}
        for p in points:
            if p[1] > y1 + h / 2:
                strony["gora"].append(p)
            elif p[1] < y0 - h / 2:
                strony["dol"].append(p)
            elif p[0] < x0 - w / 2:
                strony["lewo"].append(p)
            else:
                strony["prawo"].append(p)
        for candidates in strony.values():
            candidates.sort(key=lambda p: math.dist(p, srodek(old)))
        ordered = []
        for i in range(max(map(len, strony.values()), default=0)):
            for side in ("gora", "dol", "lewo", "prawo"):
                if i < len(strony[side]):
                    ordered.append(strony[side][i])
        queues.append(ordered)
    # Przeplataj obrys globalny i poszczególne kontury. Wszystkie
    # pozycje i tak muszą przejść walidację granic oraz własności.
    seen = set()
    for index in range(max(map(len, queues), default=0)):
        for queue in queues:
            if index >= len(queue):
                continue
            p = queue[index]
            r = prost(p, (w, h))
            key = tuple(round(v, 3) for v in r)
            if key in seen:
                continue
            seen.add(key)
            if granice.przecina(powieksz(r, margines)):
                continue
            if geo.punkt_w_poligonie(p, poly):
                continue
            yield r
            limit -= 1
            if not limit:
                return


def _cele(poly, n=7):
    x0, y0, x1, y1 = bbox(poly)
    centers = [srodek((x0, y0, x1, y1))]
    for i in range(n):
        for j in range(n):
            centers.append((x0 + (i + .5) * (x1 - x0) / n,
                            y0 + (j + .5) * (y1 - y0) / n))
    seen = set()
    for c in centers:
        if c in seen:
            continue
        seen.add(c)
        if geo.prostokat_w_poligonie(powieksz((c[0], c[1], c[0], c[1]), 1.2), poly):
            yield c


def _poprawne(elementy, odstep=2.5):
    if geo.waliduj_uklad(elementy):
        return False
    for i, e in enumerate(elementy):
        for f in elementy[i + 1:]:
            if geo.prostokaty_koliduja(
                    powieksz(e["prostokat"], odstep / 2),
                    powieksz(f["prostokat"], odstep / 2)):
                return False
    return True


def _koszt(wariant, oryginaly):
    """Skala niezależna od jednostki mapy: odległość w wysokościach napisu.

    Każde dalsze przesunięcie ma większy koszt. Nie ucinamy go po 100 m:
    wcześniej przesunięcie o 120 m i 260 m było oceniane identycznie.
    """
    score = 0.0
    for e in wariant:
        r = e["prostokat"]
        wysokosc = max(r[3] - r[1], geo.EPS)
        outside = e["wysiegnik"] is not None
        score += (180 if e["rodzaj"] == "litera" else 120) if outside else 0
        displacement = math.dist(srodek(r), srodek(oryginaly[e["id"]]["prostokat"]))
        score += 8.0 * displacement / wysokosc
        if outside:
            score += 6.0 * math.dist(*e["wysiegnik"]) / wysokosc

    # Estetyka pary L2/L3 jest osobna od poprawności geometrycznej.
    # Dwa napisy tego samego wydzielenia powinny pozostać blisko siebie
    # o ile nie wymaga to kolizji. V6 dla 4a było poprawne, lecz
    # litera znajdowała się daleko poniżej opisu. Wysokość napisów
    # normalizuje koszt dla różnych skal MAP.
    letter = next((e for e in wariant if e["rodzaj"] == "litera"), None)
    desc = next((e for e in wariant if e["rodzaj"] == "opis"), None)
    if letter is not None and desc is not None:
        height = max(
            ((letter["prostokat"][3] - letter["prostokat"][1])
             + (desc["prostokat"][3] - desc["prostokat"][1])) / 2,
            geo.EPS)
        gap = odleglosc_boxow(letter["prostokat"], desc["prostokat"])
        external_count = sum(bool(e.get("wysiegnik"))
                             for e in (letter, desc))
        # Największy nacisk na parę z dwoma wysięgnikami; litera
        # wewnątrz i opis poza również korzystają z bliskości.
        strength = (7.0, 12.0, 18.0)[external_count]
        score += strength * gap / height
    return score


def _rozlozone(probki, ile):
    """Równomiernie reprezentuj cały porządek kandydatów, nie tylko początek."""
    if len(probki) <= ile:
        return probki
    if ile <= 1:
        return probki[:ile]
    indexes = sorted({round(i * (len(probki) - 1) / (ile - 1))
                      for i in range(ile)})
    return [probki[i] for i in indexes]


def opcje_wydzielenia(grupa, granice, poligony, margines=2.5,
                      odstep=2.5, limit=24):
    """Jedna decyzja obejmuje wszystkie L2/L3, ze wspólnym celem na zewnątrz."""
    grupa = sorted(grupa, key=lambda e: e["id"])
    inside = {e["id"]: list(_pozycje_wewnatrz(e, granice, margines)) for e in grupa}
    rozszerzone = limit > 24
    outside = {e["id"]: list(_pozycje_zewnetrzne(
        e, granice, poligony, margines,
        limit=(96 if rozszerzone else 48))) for e in grupa}
    anchors = list(_cele(grupa[0]["poligon"],
                         n=(9 if rozszerzone else 7)))
    all_options = []
    if len(grupa) > 2:
        return []

    def add(boxes, target=None):
        # Jeśli litera jest w poligonie, zewnętrzny opis musi kończyć
        # linię na obwodzie TEJ litery, nie w dowolnym punkcie wydzielenia.
        inner_letter = next(
            (r for e, r, external in boxes
             if e['rodzaj'] == 'litera' and not external), None)
        plan = []
        for e, r, external in boxes:
            goal = None
            if external:
                if e['rodzaj'] == 'opis' and inner_letter is not None:
                    goal = geo.cel_na_literze(inner_letter, r)
                else:
                    goal = target
            plan.append(_wariant(e, r, goal))
        if _poprawne(plan, odstep):
            # Klasy wariantow musza zachowac reprezentacje w ograniczonej
            # wiazce: bez tego najlepsze 24 pozycje czesto byly tylko
            # wewnetrzne, mimo ze bezpieczny wysiegnik byl mozliwy.
            kinds = tuple(sorted(
                e["rodzaj"] for e in plan if e.get("wysiegnik") is not None))
            all_options.append((kinds, plan))

    if len(grupa) == 1:
        e = grupa[0]
        for r in inside[e["id"]]:
            add([(e, r, False)])
        for r in outside[e["id"]]:
            for c in sorted(anchors, key=lambda a: math.dist(a, srodek(r)))[:8]:
                add([(e, r, True)], c)
    else:
        a, b = grupa
        for ra in inside[a["id"]]:
            for rb in inside[b["id"]]:
                add([(a, ra, False), (b, rb, False)])
        for e, f in ((a, b), (b, a)):
            for ri in inside[e["id"]][:7]:
                # Dla opisu wskazującego literę cel jest determinowany
                # przez obwód litery, więc nie generuj niepotrzebnych
                # wariantów z losowymi punktami w poligonie.
                for ro in outside[f["id"]][:24]:
                    if e["rodzaj"] == "litera" and f["rodzaj"] == "opis":
                        add([(e, ri, False), (f, ro, True)])
                    else:
                        for c in sorted(
                                anchors, key=lambda p: math.dist(p, srodek(ro)))[:7]:
                            add([(e, ri, False), (f, ro, True)], c)
        lit_a = (_rozlozone(outside[a["id"]], 20) if rozszerzone
                 else outside[a["id"]][:10])
        lit_b = (_rozlozone(outside[b["id"]], 20) if rozszerzone
                 else outside[b["id"]][:10])
        # Sąsiednie L2/L3 stanowią ważną rodzinę estetyczną.
        # Dotychczasowy iloczyn dwóch niezależnych list pozycji
        # pomijał proste układy litera obok opisu (np. 4a).
        # Generujemy je tylko w szerszym trybie i filtrujemy dokładnie
        # tak samo jak wszystkie inne warianty.
        if rozszerzone:
            letter = next((e for e in (a, b) if e["rodzaj"] == "litera"), None)
            desc = next((e for e in (a, b) if e["rodzaj"] == "opis"), None)
            if letter is not None and desc is not None:
                wl = outside[letter["id"]]
                dw = desc["prostokat"][2] - desc["prostokat"][0]
                dh = desc["prostokat"][3] - desc["prostokat"][1]
                gap = max(odstep + margines, 4.0)
                for rl in _rozlozone(wl, 35):
                    lx, ly = srodek(rl)
                    for rx, ry in (
                        (rl[0] - gap - dw / 2, ly),
                        (rl[2] + gap + dw / 2, ly),
                        (lx, rl[1] - gap - dh / 2),
                        (lx, rl[3] + gap + dh / 2)):
                        rd = prost((rx, ry), (dw, dh))
                        if (granice.przecina(powieksz(rd, margines))
                                or geo.prostokat_w_poligonie(rd, desc["poligon"])):
                            continue
                        for c in sorted(
                                anchors, key=lambda p: math.dist(p,srodek(rl))
                                + math.dist(p,srodek(rd)))[:9]:
                            add([(letter, rl, True), (desc, rd, True)], c)
        for ra in lit_a:
            for rb in lit_b:
                if geo.prostokaty_koliduja(powieksz(ra, odstep / 2),
                                           powieksz(rb, odstep / 2)):
                    continue
                for c in sorted(anchors, key=lambda p:
                        math.dist(p, srodek(ra)) + math.dist(p, srodek(rb)))[:9]:
                    add([(a, ra, True), (b, rb, True)], c)

    unique = {}
    original = {e["id"]: e for e in grupa}
    for kind, plan in all_options:
        key = tuple((e["id"], tuple(round(v, 2) for v in e["prostokat"]),
                     tuple(round(v, 2) for v in e["wysiegnik"][1])
                     if e["wysiegnik"] else None) for e in plan)
        score = _koszt(plan, original)
        if key not in unique or score < unique[key][0]:
            unique[key] = (score, kind, plan)
    ordered = sorted(unique.items(), key=lambda item: (item[1][0], item[0]))
    # Przy gęstych skupiskach 24 najtańsze warianty mogą przypaść
    # tylko jednej stronie wydzielenia. Oprócz strategii (L2/L3
    # wewnątrz/poza) rezerwuj wariant z różnych kierunków wyprowadzenia
    # opisu. Pozostałe miejsca zostaną przydzielone według kosztu.
    def rodzina(entry):
        _, (cost, kind, plan) = entry
        exterior = next((e for e in plan if e["rodzaj"] == "opis"
                         and e.get("wysiegnik")), None)
        if exterior is None:
            exterior = next((e for e in plan if e.get("wysiegnik")), None)
        if exterior is None:
            return (kind, "wewnatrz")
        cx, cy = srodek(exterior["prostokat"])
        ox, oy = srodek(bbox(exterior["poligon"]))
        if abs(cx - ox) >= abs(cy - oy):
            return (kind, "prawo" if cx >= ox else "lewo")
        return (kind, "gora" if cy >= oy else "dol")
    def rodzina_rozszerzona(entry):
        # Przy większym limicie nie wystarczy rozróżniać strony opisu.
        # Zewnętrzna litera może potrzebować innej strony poligonu.
        base = rodzina(entry)
        if not rozszerzone:
            return base
        plan = entry[1][2]
        letter = next((e for e in plan if e["rodzaj"] == "litera"
                       and e.get("wysiegnik")), None)
        if letter is None:
            return base + ("litera_wewnatrz",)
        cx, cy = srodek(letter["prostokat"])
        ox, oy = srodek(bbox(letter["poligon"]))
        if abs(cx - ox) >= abs(cy - oy):
            side = "prawo" if cx >= ox else "lewo"
        else:
            side = "gora" if cy >= oy else "dol"
        return base + (side,)
    groups = sorted({rodzina_rozszerzona(entry) for entry in ordered})
    if not groups:
        return []
    # Rezerwuj udzial dla kazdej wykrytej strategii, niezaleznie od jej
    # ceny. W przeciwnym razie brakuje np. "litera wewnatrz, opis poza".
    minimum = max(1, limit // len(groups))
    picked = []
    used = set()
    for kind in groups:
        selected = 0
        for key, (cost, family, plan) in ordered:
            if (family != kind[0] or
                    rodzina_rozszerzona((key, (cost, family, plan))) != kind or
                    key in used):
                continue
            picked.append(plan)
            used.add(key)
            selected += 1
            if selected >= minimum or len(picked) >= limit:
                break
    # Reszte limitu przydziel wedlug kosztu, bez gubienia roznorodnosci.
    for key, (_, family, plan) in ordered:
        if len(picked) >= limit:
            break
        if key not in used:
            picked.append(plan)
            used.add(key)
    return picked


def _kolizja_miedzy(first, second, odstep):
    for a in first:
        for b in second:
            if geo.prostokaty_koliduja(
                    powieksz(a["prostokat"], odstep / 2),
                    powieksz(b["prostokat"], odstep / 2)):
                return True
            for own, other in ((a, b), (b, a)):
                w = own.get("wysiegnik")
                if w and geo.odcinek_przecina_prostokat(
                        *w, powieksz(other["prostokat"], .5)):
                    return True
            if (a.get("wysiegnik") and b.get("wysiegnik") and
                    geo.wysiegniki_koliduja(
                        a["wysiegnik"], b["wysiegnik"],
                        to_samo_wydzielenie=(a["wydzielenie"] == b["wydzielenie"]))):
                return True
    return False


def _obwiednia_elementu(e, odstep):
    r = powieksz(e["prostokat"], max(odstep / 2, .5))
    w = e.get("wysiegnik")
    if not w:
        return r
    return (min(r[0], w[0][0], w[1][0]),
            min(r[1], w[0][1], w[1][1]),
            max(r[2], w[0][0], w[1][0]),
            max(r[3], w[0][1], w[1][1]))


def _obwiednia_planu(plan, odstep):
    boxes = [_obwiednia_elementu(e, odstep) for e in plan]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _obwiednie_nachodza(a, b):
    return not (a[2] < b[0] or b[2] < a[0]
                or a[3] < b[1] or b[3] < a[1])


def _blokady_planow(plany, obecne, wydzielenie, odstep):
    """Rzeczywiste grupy blokujące każdy gotowy plan w danym otoczeniu.

    Zwraca (frozenset UUID, plan). W przeciwieństwie do bliskości
    poligonów uwzględnia także rzeczywiste pozycje napisów i wysięgników.
    Używa obwiedni do ograniczenia kosztu.
    """
    fixed = [(e, _obwiednia_elementu(e, odstep))
             for e in obecne.values() if e["wydzielenie"] != wydzielenie]
    results = []
    for plan in plany:
        bounds = _obwiednia_planu(plan, odstep)
        blockers = frozenset(e["wydzielenie"] for e, box in fixed
                             if _obwiednie_nachodza(bounds, box)
                             and _kolizja_miedzy(plan, [e], odstep))
        results.append((blockers, plan))
    return results


def _sasiedztwo(grupy, klucz, ile=5):
    """Wybieraj grupy faktycznie bliskie geometrycznie, w skali etykiet.

    Kryterium uwzględnia również napisy już wypchnięte poza swoje poligony.
    Nie używa stałego promienia w metrach zależnego od konkretnej mapy.
    """
    own = grupy[klucz]
    a = bbox(own[0]["poligon"])
    pozycje = []
    for other, items in grupy.items():
        if other == klucz:
            continue
        b = bbox(items[0]["poligon"])
        sep = odleglosc_boxow(a, b)
        labels_sep = min(odleglosc_boxow(e["prostokat"], f["prostokat"])
                         for e in own for f in items)
        rozmiar = max(
            max(e["prostokat"][2] - e["prostokat"][0],
                e["prostokat"][3] - e["prostokat"][1])
            for e in own + items)
        if min(sep, labels_sep) <= 3 * rozmiar:
            pozycje.append((min(sep, labels_sep), sep, str(other), other))
    return [klucz] + [x[3] for x in sorted(pozycje)[:max(0, ile - 1)]]



def _wspolny_plan_dokladny(klucze, warianty, obecne, oryginaly, odstep):
    """Znajdź najtańszy bezkolizyjny układ z ograniczonych list kandydatów.

    Pełny przegląd kombinacji <=3 małych grup (zwykle 24^3) usuwa
    efekt obcinania dobrych częściowych planów przez wiązkę. Otoczenie
    pozostaje nieruchome. Brak wyniku dotyczy TYLKO tego zbioru planów,
    nie dowodzi braku możliwego rozmieszczenia.
    """
    keys = tuple(sorted(klucze, key=str))
    if not 2 <= len(keys) <= 3:
        raise ValueError("Dokładna wspólna próba wymaga 2–3 wydzieleń")
    fixed = [(e, _obwiednia_elementu(e, odstep))
             for e in obecne.values() if e["wydzielenie"] not in keys]
    valid = []
    counts = {}
    for key in keys:
        available = []
        for plan in warianty(key):
            bounds = _obwiednia_planu(plan, odstep)
            if any(_obwiednie_nachodza(bounds, b)
                   and _kolizja_miedzy(plan, [e], odstep)
                   for e, b in fixed):
                continue
            available.append((_koszt(plan, oryginaly), plan, bounds))
        available.sort(key=lambda x: (x[0],
                        tuple((e["id"], e["prostokat"]) for e in x[1])))
        counts[str(key)] = len(available)
        if not available:
            return None, {"sukces": False, "liczba_planow_po_otoczeniu": counts,
                          "ocenione_kompletne_uklady": 0}
        valid.append((key, available))
    valid.sort(key=lambda pair: (len(pair[1]), str(pair[0])))
    # Oddzielnie raportuj, czy dany duet ma choć jedną zgodną
    # kombinację. Gdy trzy pary są zgodne, ale brak pełnej trójki,
    # problemem jest wspólna konfiguracja, nie brak miejsca dla par.
    compatible_pairs = []
    for i, (first_key, first_plans) in enumerate(valid):
        for second_key, second_plans in valid[i + 1:]:
            count = sum(
                1 for _, left, left_bounds in first_plans
                  for _, right, right_bounds in second_plans
                  if (not _obwiednie_nachodza(left_bounds, right_bounds)
                      or not _kolizja_miedzy(left, right, odstep)))
            compatible_pairs.append({
                "wydzielenia": [str(first_key), str(second_key)],
                "zgodne_pary_planow": count})
    remaining = [0.0] * (len(valid) + 1)
    for i in range(len(valid) - 1, -1, -1):
        remaining[i] = remaining[i + 1] + valid[i][1][0][0]
    best, best_cost = None, math.inf
    checked = 0

    def visit(i, selected, bounds, score):
        nonlocal best, best_cost, checked
        if score + remaining[i] >= best_cost:
            return
        if i == len(valid):
            checked += 1
            best, best_cost = list(selected), score
            return
        for cost, plan, area in valid[i][1]:
            if score + cost + remaining[i + 1] >= best_cost:
                break
            if any(_obwiednie_nachodza(area, b) and
                   _kolizja_miedzy(plan, prev, odstep)
                   for prev, b in bounds):
                continue
            visit(i + 1, selected + plan, bounds + [(plan, area)],
                  score + cost)

    visit(0, [], [], 0.0)
    return best, {"sukces": best is not None,
                  "liczba_planow_po_otoczeniu": counts,
                  "zgodne_pary_planow": compatible_pairs,
                  "ocenione_kompletne_uklady": checked}


def _maks_odstep_pary(plan):
    """Największy odstęp L2–L3 w wysokościach napisów.

    Służy WYŁĄCZNIE do stwierdzenia, czy warto poszerzyć pulę planów
    po pierwszym bezkolizyjnym sukcesie. Nie zastępuje funkcji kosztu.
    """
    grouped = defaultdict(dict)
    for e in plan:
        grouped[e["wydzielenie"]][e["rodzaj"]] = e
    worst = 0.0
    for pair in grouped.values():
        if "litera" not in pair or "opis" not in pair:
            continue
        letter, desc = pair["litera"], pair["opis"]
        # Zwłaszcza para z dwoma wysięgnikami powinna być blisko.
        if not (letter.get("wysiegnik") and desc.get("wysiegnik")):
            continue
        height = max(((letter["prostokat"][3] - letter["prostokat"][1])
                      + (desc["prostokat"][3] - desc["prostokat"][1])) / 2,
                     geo.EPS)
        worst = max(worst, odleglosc_boxow(
            letter["prostokat"], desc["prostokat"]) / height)
    return worst


def optymalizuj(elementy, *, wszystkie_poligony=None, margines=2.5, odstep=2.5,
                szerokosc_wiazki=24, maks_grupa=5, przebiegi=2,
                limit_grup=None, postep=None,
                wybrane_wydzielenia=None):
    """Deterministycznie poprawia ciasne lokalne skupiska, nie psując reszty.

    Zwraca nową listę elementów i raport; nigdy nie zmienia wejścia.
    Jeśli ograniczone przeszukiwanie nie znajduje bezkolizyjnego układu,
    pozostawia problem jawnie nierozwiązany, zamiast produkować błędne linie.
    """
    wybrane = (None if wybrane_wydzielenia is None
               else frozenset(wybrane_wydzielenia))
    if len({e["id"] for e in elementy}) != len(elementy):
        raise ValueError("Powtórzone identyfikatory etykiet")
    if not elementy:
        return [], {"przed": {}, "po": {}, "przesuniete": 0, "nierozwiazane": []}
    poligony = list(wszystkie_poligony or [])
    if not poligony:
        poligony = [e["poligon"] for e in elementy]
    granice = Granice(poligony)
    by_group = defaultdict(list)
    for e in elementy:
        by_group[e["wydzielenie"]].append(dict(e))
    obecne = {e["id"]: dict(e) for e in elementy}
    old = {e["id"]: dict(e) for e in elementy}
    # Opcje powstają dopiero dla rzeczywiście dotkniętego skupiska,
    # nie dla wszystkich 200+ wydzieleń już na starcie.
    opcje = {}

    def warianty(k):
        if k not in opcje:
            opcje[k] = opcje_wydzielenia(
                by_group[k], granice, poligony, margines, odstep)
        return opcje[k]

    def issues():
        return geo.waliduj_uklad(list(obecne.values()))

    przed = issues()
    wykonane = 0
    rozpatrzone = 0
    pominiete_przez_limit = 0
    pominiete_przez_wybor = set()
    wspolna_proba = None
    # Dla małego jawnie wskazanego skupiska spróbuj rozwiązać wszystkie
    # wydzielenia jednocześnie, ZANIM najłatwiejsze zajmą wolną przestrzeń.
    # Nie zmienia to trybu pełnej mapy ani ograniczenia liczby grup.
    if (wybrane is not None and 2 <= len(wybrane) <= min(3, maks_grupa)
            and all(k in by_group for k in wybrane)
            and (limit_grup is None or limit_grup >= len(wybrane))):
        if any(set(issue["elementy"]) &
               {e["id"] for e in elementy if e["wydzielenie"] in wybrane}
               for issue in przed):
            trial_results = []
            selected = None
            best_cost, chosen_limit = math.inf, None
            # Wcześniej kończyliśmy na PIERWSZEJ poprawnej trójce.
            # To rozwiązało kolizje V6, ale nie poprawiało długich
            # wysięgników i odległości pary L2/L3 w V7.
            # Poszerzamy dalej WYŁĄCZNIE przy zbyt rozciągniętych
            # dwóch zewnętrznych napisach albo braku rozwiązania.
            for width in (24, 72, 112):
                def candidates(key):
                    if width == 24:
                        return warianty(key)
                    return opcje_wydzielenia(
                        by_group[key], granice, poligony, margines,
                        odstep, limit=width)
                attempt, report = _wspolny_plan_dokladny(
                    wybrane, candidates, obecne, old, odstep)
                report["limit_planow_na_wydzielenie"] = width
                if attempt is not None:
                    candidate_cost = _koszt(attempt, old)
                    report["koszt_znalezionego_ukladu"] = candidate_cost
                    report["maks_odstep_pary"] = _maks_odstep_pary(attempt)
                    if candidate_cost < best_cost - 1e-7:
                        selected = attempt
                        best_cost, chosen_limit = candidate_cost, width
                        report["poprawiono_najlepszy"] = True
                    else:
                        report["poprawiono_najlepszy"] = False
                trial_results.append(report)
                if selected is not None and _maks_odstep_pary(selected) <= .75:
                    break
            wspolna_proba = dict(trial_results[-1])
            wspolna_proba["sukces"] = selected is not None
            wspolna_proba["liczba_wydzielen"] = len(wybrane)
            wspolna_proba["proby"] = trial_results
            wspolna_proba["wybrany_limit_planow"] = chosen_limit
            wspolna_proba["koszt_wybranego_ukladu"] = (
                best_cost if selected is not None else None)
            wspolna_proba["maks_odstep_wybranego_ukladu"] = (
                _maks_odstep_pary(selected) if selected is not None else None)
            if selected:
                for e in selected:
                    obecne[e["id"]] = e
                wykonane += 1
    for przebieg in range(max(1, przebiegi)):
        problems = issues()
        touched = {ident for problem in problems for ident in problem["elementy"]}
        touched.update(e["id"] for e in obecne.values()
                       if e.get("wysiegnik") is None
                       and not geo.prostokat_w_poligonie(
                           powieksz(e["prostokat"], margines), e["poligon"]))
        # Kolejność UUID nie ma związku z trudnością mapy. Najpierw
        # rozpatruj wydzielenia dotknięte największą liczbą aktualnych
        # kolizji; pozostawienie ich na koniec sprawiało, że wcześniejsze
        # ruchy łatwiejszych sąsiadów odbierały im wolną przestrzeń.
        obciazenie = defaultdict(int)
        for issue in problems:
            for ident in set(issue["elementy"]):
                if ident in obecne:
                    obciazenie[obecne[ident]["wydzielenie"]] += 1
        todo = sorted((k for k, v in by_group.items()
                       if any(e["id"] in touched for e in v)),
                      key=lambda k: (-obciazenie[k], str(k)))
        if wybrane is not None:
            pominiete_przez_wybor.update(k for k in todo if k not in wybrane)
            todo = [k for k in todo if k in wybrane]
        if limit_grup is not None:
            # Limit dotyczy całego wywołania, a nie każdego przebiegu.
            budget = max(0, limit_grup - rozpatrzone)
            pominiete_przez_limit += max(0, len(todo) - budget)
            todo = todo[:budget]
        improved = 0
        for index, key in enumerate(todo, 1):
            rozpatrzone += 1
            if postep is not None:
                postep({"przebieg": przebieg + 1,
                       "indeks": index, "liczba_grup": len(todo),
                       "wydzielenie": key,
                       "rozpatrzone_lacznie": rozpatrzone})
            # Najpierw napraw samo wydzielenie. Dopiero gdy zderza sie
            # z nieprzesuwalnym sasiadem, dolacz do rozwiazywania kolejny
            # najblizszy poligon. Dawniej pojedynczy niemozliwy sasiad
            # uniewaznial nawet poprawne samodzielne rozwiazanie celu.
            neighbors = _sasiedztwo(by_group, key, max(1, maks_grupa))[1:]
            if not warianty(key):
                continue
            # Najpierw próbuj naprawy samotnej, potem wspólnie z tymi
            # grupami, których NAPISY rzeczywiście blokują wariant celu.
            # Bliskość geometryczna jest tylko planem rezerwowym.
            blockage = _blokady_planow(warianty(key), obecne, key, odstep)
            candidates = []
            for blockers, plan in sorted(
                    blockage, key=lambda x: (len(x[0]), _koszt(x[1], old),
                                            tuple(sorted(map(str, x[0]))))):
                if 0 < len(blockers) < maks_grupa:
                    candidates.append(tuple(sorted(blockers, key=str)))
            for n in neighbors:
                candidates.append((n,))
            for length in range(2, len(neighbors) + 1):
                candidates.append(tuple(neighbors[:length]))
            # Nie próbuj dwukrotnie tych samych zestawów; ogranicz
            # rozmiar poszukiwań i nie generuj wszystkich kombinacji.
            unique_sets = []
            seen_sets = set()
            for group_set in [()] + candidates:
                canonical = tuple(sorted(group_set, key=str))
                if (len(canonical) >= maks_grupa or canonical in seen_sets):
                    continue
                if any(k not in by_group for k in canonical):
                    continue
                seen_sets.add(canonical)
                unique_sets.append(canonical)
            repaired = False
            for group_set in unique_sets:
                selected = [key] + list(group_set)
                if any(not warianty(k) for k in selected):
                    continue
                fixed = [e for e in obecne.values()
                         if e["wydzielenie"] not in selected]
                current = [e for e in obecne.values()
                           if e["wydzielenie"] in selected]
                # Nie ruszaj w pelni poprawnego ukladu: moze juz zostal
                # naprawiony przez poprzednia operacje w tym przebiegu.
                if (_poprawne(current, odstep)
                        and not any(_kolizja_miedzy(current, [f], odstep)
                                    for f in fixed)):
                    repaired = True
                    break
                beam = [(0.0, [])]
                fixed_bounds = [(f, _obwiednia_elementu(f, odstep))
                                for f in fixed]
                for k in sorted(selected, key=lambda k:
                                (len(warianty(k)), str(k))):
                    next_beam = []
                    approved = []
                    for plan in warianty(k):
                        area = _obwiednia_planu(plan, odstep)
                        if any(_obwiednie_nachodza(area, b)
                               and _kolizja_miedzy(plan, [f], odstep)
                               for f, b in fixed_bounds):
                            continue
                        approved.append((plan, _koszt(plan, old)))
                    for cost, placed in beam:
                        for plan, score in approved:
                            if _kolizja_miedzy(plan, placed, odstep):
                                continue
                            next_beam.append((cost + score, placed + plan))
                    beam = sorted(next_beam, key=lambda x: x[0])[:szerokosc_wiazki]
                    if not beam:
                        break
                if not beam:
                    continue
                _, best = beam[0]
                if all(e["prostokat"] == obecne[e["id"]]["prostokat"] and
                       e.get("wysiegnik") == obecne[e["id"]].get("wysiegnik")
                       for e in best):
                    repaired = True
                    break
                for e in best:
                    obecne[e["id"]] = e
                improved += 1
                wykonane += 1
                repaired = True
                break
        if not improved:
            break

    po = issues()
    changed = sum(1 for ident, e in obecne.items()
                  if e["prostokat"] != old[ident]["prostokat"] or
                  e.get("wysiegnik") != old[ident].get("wysiegnik"))
    return [obecne[e["id"]] for e in elementy], {
        "przed": dict(_counts(przed)), "po": dict(_counts(po)),
        "przesuniete": changed, "udane_grupy": wykonane,
        "rozpatrzone_grupy": rozpatrzone,
        "wspolna_proba": wspolna_proba,
        "pominiete_przez_limit": pominiete_przez_limit,
        "pominiete_przez_wybor": len(pominiete_przez_wybor),
        "analiza_czesciowa": (pominiete_przez_limit > 0
                              or bool(pominiete_przez_wybor)),
        "nierozwiazane": po,
        "ostrzezenie": ("Skończona siatka i wiązka: brak rozwiązania nie dowodzi "
                        "braku miejsca. Przy aktywnym limicie grup "
                        "raport dotyczy jedynie częściowej optymalizacji.")
    }


def _counts(problems):
    from collections import Counter
    return Counter(p["typ"] for p in problems)
