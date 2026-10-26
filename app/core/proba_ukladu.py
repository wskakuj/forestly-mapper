# -*- coding: utf-8 -*-
"""Eksperymentalne układanie napisów wewnątrz poligonów GEO-MAP.

Nie tworzy wysięgników. Nie nadpisuje oryginalnej mapy; eksport jest
opcjonalny i trafia do jawnie wskazanego, osobnego pliku MAP.
To bezpieczna próba, nie zastępstwo pełnej optymalizacji grup wydzieleń.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from app.core import diagnostyka_map as dm
from app.core import geometria_ukladu as geom
from app.core import opisy_na_mape as onm
from app.core import uklad_opisow as uk


def _komorki(r, krok=90.0):
    return ((x, y) for x in range(int(r[0] // krok), int(r[2] // krok) + 1)
            for y in range(int(r[1] // krok), int(r[3] // krok) + 1))


class IndeksNapisow:
    """Indeks przestrzenny używany do szybkiego wykrywania nakładek napisów."""

    def __init__(self, elementy):
        self.boxy = {e['id']: e['prostokat'] for e in elementy}
        self.siatka = defaultdict(set)
        for key, r in self.boxy.items():
            for kom in _komorki(r):
                self.siatka[kom].add(key)

    def sasiedzi(self, r, pomin=None):
        ids = set()
        for kom in _komorki(r):
            ids.update(self.siatka.get(kom, ()))
        ids.discard(pomin)
        return ids

    def kolizje(self, ident, r=None):
        if r is None:
            r = self.boxy[ident]
        return [k for k in self.sasiedzi(r, ident)
                if geom.prostokaty_koliduja(r, self.boxy[k])]

    def przestaw(self, ident, r):
        old = self.boxy[ident]
        for kom in _komorki(old):
            self.siatka[kom].discard(ident)
        self.boxy[ident] = r
        for kom in _komorki(r):
            self.siatka[kom].add(ident)


def _prost(cx, cy, dx, dy):
    return (cx - dx / 2, cy - dy / 2, cx + dx / 2, cy + dy / 2)


def _kandydaci(element, rozdzielczosc=25):
    """Kandydaci wewnętrzni od najbliższych obecnej pozycji napisu.

    Nie znaleziono kandydata na skończonej siatce NIE znaczy, że brak miejsca
    wewnątrz wydzielenia. To rozpoznanie należy ulepszyć w przyszłym silniku.
    """
    r = element['prostokat']
    dx, dy = r[2] - r[0], r[3] - r[1]
    pts = element['poligon']
    if len(pts) < 3 or dx <= 0 or dy <= 0:
        return
    x0 = min(p[0] for p in pts) + dx / 2
    x1 = max(p[0] for p in pts) - dx / 2
    y0 = min(p[1] for p in pts) + dy / 2
    y1 = max(p[1] for p in pts) - dy / 2
    if x0 > x1 or y0 > y1:
        return
    n = max(5, min(60, int(rozdzielczosc)))
    cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
    coords = [(x0 + (x1 - x0) * (i + .5) / n,
               y0 + (y1 - y0) * (j + .5) / n)
              for i in range(n) for j in range(n)]
    coords.extend([((x0 + x1) / 2, (y0 + y1) / 2), (cx, cy)])
    coords.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    for x, y in coords:
        if not geom.punkt_w_poligonie((x, y), pts):
            continue
        prost = _prost(x, y, dx, dy)
        if geom.prostokat_w_poligonie(prost, pts):
            yield prost


def statystyka(elementy, indeks):
    outside = Counter()
    for e in elementy:
        if not geom.prostokat_w_poligonie(indeks.boxy[e['id']], e['poligon']):
            outside[e['rodzaj']] += 1
    collisions = sum(len(indeks.kolizje(e['id'])) for e in elementy) // 2
    return {'poza': dict(outside), 'kolizje_napisow': collisions}


def uloz_wewnatrz(elementy, rozdzielczosc=25, przebiegi=3):
    """Przyjmuj tylko pozycje w poligonie, bez nowych kolizji tekstów.

    Sąsiednie litery/opisy (również te bez zaimportowanych opisów) pozostają
    przeszkodami. Nie tworzy zewnętrznych napisów ani wysięgników.
    """
    indeks = IndeksNapisow(elementy)
    przed = statystyka(elementy, indeks)
    zmiany = {}

    def kolejnosc(e):
        r = e['prostokat']
        p = e['poligon']
        pw = max(0.0, max(x[0] for x in p) - min(x[0] for x in p))
        ph = max(0.0, max(x[1] for x in p) - min(x[1] for x in p))
        return (-len(indeks.kolizje(e['id'])),
                (pw * ph) / max((r[2] - r[0]) * (r[3] - r[1]), 1e-9), e['id'])

    for _ in range(max(1, min(10, int(przebiegi)))):
        udane = 0
        for e in sorted(elementy, key=kolejnosc):
            ident = e['id']
            obecny = indeks.boxy[ident]
            w_srodku = geom.prostokat_w_poligonie(obecny, e['poligon'])
            konflikty = indeks.kolizje(ident)
            if w_srodku and not konflikty:
                continue
            for r in _kandydaci({**e, 'prostokat': obecny}, rozdzielczosc):
                if r == obecny or indeks.kolizje(ident, r):
                    continue
                indeks.przestaw(ident, r)
                zmiany[ident] = r
                udane += 1
                break
        if not udane:
            break

    po = statystyka(elementy, indeks)
    if (po['kolizje_napisow'] > przed['kolizje_napisow'] or
            sum(po['poza'].values()) > sum(przed['poza'].values())):
        raise AssertionError('Próbny układ pogorszył statystyki wejściowe')
    return zmiany, {'przed': przed, 'po': po, 'przeniesione': len(zmiany),
                    'uwaga': ('Próbne przesunięcia wewnętrzne; pozostałe napisy '
                              'zewnętrzne nadal potrzebują optymalizacji wysięgników.')}


def zapisz_kopie_mapy(mapa, elementy, zmiany, zrodlo, wyjscie):
    """Zapisz osobną kopię MAP z nowymi offsetami i poprawnym CHK/N."""
    src, dst = Path(zrodlo), Path(wyjscie)
    if src.resolve() == dst.resolve():
        raise ValueError('Nie wolno nadpisać oryginalnej mapy')
    index = {}
    for obj in uk.wszystkie_poligony(mapa):
        if not mapa['lines'][obj['start']].startswith('*5310 '):
            continue
        uuid = next((q[4:-1] for q in obj['linie'] if q.startswith(':ID[')), None)
        if not uuid:
            continue
        for pos in range(obj['start'] + 1, obj['start'] + 1 + len(obj['linie'])):
            q = mapa['lines'][pos].split()
            if len(q) >= 7 and q[0] == 'L' and q[1] in ('2', '3'):
                index[uuid + ':L' + q[1]] = pos
    elementy_id = {e['id']: e for e in elementy}
    nowa = list(mapa['lines'])
    faktycznie = []
    for ident, r in zmiany.items():
        if ident not in index:
            continue
        e = elementy_id[ident]
        if e.get('wysiegnik'):
            continue
        pos = index[ident]
        q = nowa[pos].split()
        podstawa = uk.srodek_bazowy(e['poligon'])
        x, y = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        q[2], q[3] = f'{x - podstawa[0]:.3f}', f'{y - podstawa[1]:.3f}'
        nowa[pos] = ' '.join(q)
        faktycznie.append(ident)
    raw = onm.przelicz_naglowek(nowa)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(raw)
    return faktycznie


def main(argv=None):
    p = argparse.ArgumentParser(
        description='Próbne układanie wewnątrz poligonów (bez zmiany wejścia)')
    p.add_argument('mapa')
    p.add_argument('--skala', type=int, default=4000)
    p.add_argument('--rozdzielczosc', type=int, default=25)
    p.add_argument('--przebiegi', type=int, default=3)
    p.add_argument('--json', default=None)
    p.add_argument('--map-wynik', default=None,
                   help='Zapisz osobną testową mapę z nowymi offsetami L2/L3')
    args = p.parse_args(argv)
    mapa = onm.wczytaj_mape(args.mapa)
    elementy, ostrzezenia = dm.elementy_z_mapy(mapa, args.skala)
    zmiany, wynik = uloz_wewnatrz(
        elementy, args.rozdzielczosc, args.przebiegi)
    wynik['ostrzezenia_parsowania'] = ostrzezenia
    print('Próba układania wewnątrz wydzieleń | skala 1:%d' % args.skala)
    print('Przed:', wynik['przed'])
    print('Po:', wynik['po'])
    print('Przeniesionych napisów:', wynik['przeniesione'])
    if args.map_wynik:
        faktycznie = zapisz_kopie_mapy(
            mapa, elementy, zmiany, args.mapa, args.map_wynik)
        wynik['mapa_wynikowa'] = str(args.map_wynik)
        wynik['przeniesione_zapisane'] = len(faktycznie)
        print('Zapisano testową mapę:', args.map_wynik)
    if args.json:
        wynik['zmiany'] = [
            {'id': id, 'prostokat': list(r)} for id, r in zmiany.items()]
        Path(args.json).write_text(
            json.dumps(wynik, indent=2, ensure_ascii=False), encoding='utf-8')
        print('Zapisano raport:', args.json)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
