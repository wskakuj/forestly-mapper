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
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))


def odleglosc_boxow(a, b):
    return math.hypot(max(0, a[0] - b[2], b[0] - a[2]),
                      max(0, a[1] - b[3], b[1] - a[3]))


def krawedzie(poligony):
    """Deduplicacja krawędzi bez założenia orientacji wielokąta."""
    seen = set()
    for pts in poligony:
        for a, b in zip(pts, pts[1:] + pts[:1]):
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
    for a, b, c in zip(poly, poly[1:] + poly[:1], poly[2:] + poly[:2]):
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
                        max_odleglosc=70.0, limit=14):
    old, poly = e["prostokat"], e["poligon"]
    w, h = old[2] - old[0], old[3] - old[1]
    x0, y0, x1, y1 = bbox(poly)
    points = []
    for d in (margines + 4, 15, 30, max_odleglosc):
        for t in (.1, .3, .5, .7, .9):
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            points.extend(((x, y0 - h / 2 - d), (x, y1 + h / 2 + d),
                           (x0 - w / 2 - d, y), (x1 + w / 2 + d, y)))
    # Zachowuj różne kierunki. Same najbliższe punkty mogą wszystkie
    # wypaść po jednej stronie, uniemożliwiając dwa wspólne wysięgniki.
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
    for lista in strony.values():
        lista.sort(key=lambda p: math.dist(p, srodek(old)))
    # Round-robin: reprezentacja każdej strony, bez uprzywilejowania
    # orientacji konkretnej mapy.
    kolejka = []
    for i in range(max(map(len, strony.values()))):
        for strona in ("gora", "dol", "lewo", "prawo"):
            if i < len(strony[strona]):
                kolejka.append(strony[strona][i])
    seen = set()
    for p in kolejka:
        r = prost(p, (w, h))
        key = tuple(round(v, 3) for v in r)
        if key in seen:
            continue
        seen.add(key)
        padded = powieksz(r, margines)
        if granice.przecina(padded):
            continue
        # Zewnętrzne napisy nie mogą leżeć wewnątrz obcego wydzielenia.
        if any(geo.punkt_w_poligonie(p, pts) for pts in poligony):
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
    return score


def opcje_wydzielenia(grupa, granice, poligony, margines=2.5,
                      odstep=2.5, limit=24):
    """Jedna decyzja obejmuje wszystkie L2/L3, ze wspólnym celem na zewnątrz."""
    grupa = sorted(grupa, key=lambda e: e["id"])
    inside = {e["id"]: list(_pozycje_wewnatrz(e, granice, margines)) for e in grupa}
    outside = {e["id"]: list(_pozycje_zewnetrzne(
        e, granice, poligony, margines)) for e in grupa}
    anchors = list(_cele(grupa[0]["poligon"]))
    all_options = []
    if len(grupa) > 2:
        return []

    def add(boxes, target=None):
        plan = [_wariant(e, r, target if external else None)
                for e, r, external in boxes]
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
                for ro in outside[f["id"]][:12]:
                    for c in sorted(anchors, key=lambda p: math.dist(p, srodek(ro)))[:7]:
                        add([(e, ri, False), (f, ro, True)], c)
        for ra in outside[a["id"]][:10]:
            for rb in outside[b["id"]][:10]:
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
    groups = sorted({entry[1][1] for entry in ordered})
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
            if family != kind or key in used:
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


def optymalizuj(elementy, *, wszystkie_poligony=None, margines=2.5, odstep=2.5,
                szerokosc_wiazki=24, maks_grupa=5, przebiegi=2,
                limit_grup=None, postep=None):
    """Deterministycznie poprawia ciasne lokalne skupiska, nie psując reszty.

    Zwraca nową listę elementów i raport; nigdy nie zmienia wejścia.
    Jeśli ograniczone przeszukiwanie nie znajduje bezkolizyjnego układu,
    pozostawia problem jawnie nierozwiązany, zamiast produkować błędne linie.
    """
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
    for przebieg in range(max(1, przebiegi)):
        problems = issues()
        touched = {ident for problem in problems for ident in problem["elementy"]}
        touched.update(e["id"] for e in obecne.values()
                       if e.get("wysiegnik") is None
                       and not geo.prostokat_w_poligonie(
                           powieksz(e["prostokat"], margines), e["poligon"]))
        todo = sorted((k for k, v in by_group.items()
                       if any(e["id"] in touched for e in v)), key=str)
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
            selected = _sasiedztwo(by_group, key, max(1, maks_grupa))
            selected = [k for k in selected if warianty(k)]
            if key not in selected:
                continue
            fixed = [e for e in obecne.values() if e["wydzielenie"] not in selected]
            # Ograniczona wiązka: zamiast greedy etykieta po etykiecie,
            # wybieramy wspólne warianty całych wydzieleń.
            beam = [(0.0, [])]
            # Szybki test obwiedni pozwala ominąć setki odległych obiektów
            # bez rezygnacji ze ścisłego walidatora kolizji.
            fixed_bounds = [(f, _obwiednia_elementu(f, odstep))
                            for f in fixed]
            for k in sorted(selected, key=lambda k: (len(warianty(k)), str(k))):
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
            current = [e for e in obecne.values() if e["wydzielenie"] in selected]
            # Nie przesuwaj poprawnego układu bez przyczyny.
            if _poprawne(current, odstep) and not any(
                    _kolizja_miedzy(current, [e], odstep) for e in fixed):
                continue
            if all(e["prostokat"] == obecne[e["id"]]["prostokat"] and
                   e.get("wysiegnik") == obecne[e["id"]].get("wysiegnik")
                   for e in best):
                continue
            for e in best:
                obecne[e["id"]] = e
            improved += 1
            wykonane += 1
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
        "pominiete_przez_limit": pominiete_przez_limit,
        "analiza_czesciowa": pominiete_przez_limit > 0,
        "nierozwiazane": po,
        "ostrzezenie": ("Skończona siatka i wiązka: brak rozwiązania nie dowodzi "
                        "braku miejsca. Przy aktywnym limicie grup "
                        "raport dotyczy jedynie częściowej optymalizacji.")
    }


def _counts(problems):
    from collections import Counter
    return Counter(p["typ"] for p in problems)
