# -*- coding: utf-8 -*-
"""Eksperymentalny układ L2+L3 z bezpiecznym marginesem od granic.

Nie zmienia działającego algorytmu, nie dopisuje wysięgników i nie
nadpisuje wejściowego MAP. Elementy, których nie można bezpiecznie
zmieścić, pozostają bez zmian. Ten etap nie jest gotową mapą do wydruku.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path

from app.core import diagnostyka_map as dm
from app.core import geometria_ukladu as geo
from app.core import opisy_na_mape as onm
from app.core import proba_ukladu as v1


def _srodek(r):
    return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)


def _powieksz(r, margines):
    return (r[0] - margines, r[1] - margines,
            r[2] + margines, r[3] + margines)


def _wymiary(r):
    return (r[2] - r[0], r[3] - r[1])


def _prost(srodek, wym):
    return (srodek[0] - wym[0] / 2, srodek[1] - wym[1] / 2,
            srodek[0] + wym[0] / 2, srodek[1] + wym[1] / 2)


class UkladOstrozny:
    def __init__(self, elementy, margines_granicy=2.5,
                 odstep_napisow=2.5, siatka=19):
        self.elementy = [e for e in elementy if not e.get('wysiegnik')]
        self.by_id = {e['id']: e for e in self.elementy}
        self.indeks = v1.IndeksNapisow(self.elementy)
        self.granica = max(0.0, float(margines_granicy))
        self.odstep = max(0.0, float(odstep_napisow))
        self.siatka = max(7, min(35, int(siatka)))
        self.zmiany = {}
        self.zmiany_par = set()

    def _inside(self, e, r):
        # Wymagamy nie tylko zawarcia napisu, lecz także wolnego marginesu.
        return geo.prostokat_w_poligonie(_powieksz(r, self.granica), e['poligon'])

    def _conflicts(self, e, r, ignoruj=()):
        expanded = _powieksz(r, self.odstep / 2)
        ignore = set(ignoruj)
        ignore.add(e['id'])
        return [ident for ident in self.indeks.sasiedzi(
                    _powieksz(r, self.odstep), e['id'])
                if ident not in ignore and geo.prostokaty_koliduja(
                    expanded, _powieksz(self.indeks.boxy[ident], self.odstep / 2))]

    def _pair_clean(self, a, b):
        r1, r2 = self.indeks.boxy[a['id']], self.indeks.boxy[b['id']]
        return (self._inside(a, r1) and self._inside(b, r2)
                and not self._conflicts(a, r1) and not self._conflicts(b, r2))

    def _commit(self, proposals):
        for ident, r in proposals.items():
            old = self.indeks.boxy[ident]
            if max(abs(a - b) for a, b in zip(old, r)) < 1e-5:
                continue
            self.indeks.przestaw(ident, r)
            self.zmiany[ident] = r

    def _centra_kandydatow(self, poly, original, n):
        x0, x1 = min(p[0] for p in poly), max(p[0] for p in poly)
        y0, y1 = min(p[1] for p in poly), max(p[1] for p in poly)
        xs = [x0 + (x1 - x0) * (i + .5) / n for i in range(n)]
        ys = [y0 + (y1 - y0) * (i + .5) / n for i in range(n)]
        candidates = [(x, y) for x in xs for y in ys]
        candidates.extend([original, ((x0 + x1) / 2, (y0 + y1) / 2)])
        candidates.sort(key=lambda p: (p[0]-original[0])**2 + (p[1]-original[1])**2)
        for c in candidates:
            if geo.punkt_w_poligonie(c, poly):
                yield c

    def _pair_candidates(self, letter, desc):
        rl = self.indeks.boxy[letter['id']]
        rd = self.indeks.boxy[desc['id']]
        wl, wd = _wymiary(rl), _wymiary(rd)
        cl, cd = _srodek(rl), _srodek(rd)
        origin = ((cl[0]+cd[0])/2, (cl[1]+cd[1])/2)
        # Warianty: opis po jednej z dwóch stron litery w obu osiach.
        orientations = (('x', +1), ('x', -1), ('y', +1), ('y', -1))
        for central in self._centra_kandydatow(letter['poligon'], origin, self.siatka):
            for axis, sign in orientations:
                i = 0 if axis == 'x' else 1
                sep = (wl[i] + wd[i]) / 2 + self.odstep + .4
                lc, dc = list(central), list(central)
                lc[i] += sign * sep / 2
                dc[i] -= sign * sep / 2
                yield (_prost(lc, wl), _prost(dc, wd))

    def _place_pair(self, a, b):
        if self._pair_clean(a, b):
            return False
        for ra, rb in self._pair_candidates(a, b):
            if (not self._inside(a, ra) or not self._inside(b, rb)
                    or geo.prostokaty_koliduja(
                        _powieksz(ra, self.odstep / 2),
                        _powieksz(rb, self.odstep / 2))):
                continue
            if self._conflicts(a, ra, (b['id'],)) or self._conflicts(b, rb, (a['id'],)):
                continue
            self._commit({a['id']: ra, b['id']: rb})
            self.zmiany_par.add(a['wydzielenie'])
            return True
        return False

    def _repair_pair_with_neighbor(self, a, b):
        """Lokalny układ 3 napisów: para oraz jej pojedynczy bloker."""
        if self._pair_clean(a, b):
            return False
        attempts = 0
        for ra, rb in self._pair_candidates(a, b):
            if not self._inside(a, ra) or not self._inside(b, rb):
                continue
            if geo.prostokaty_koliduja(
                    _powieksz(ra, self.odstep / 2),
                    _powieksz(rb, self.odstep / 2)):
                continue
            blockers = set(self._conflicts(a, ra, (b['id'],)))
            blockers.update(self._conflicts(b, rb, (a['id'],)))
            if len(blockers) != 1:
                continue
            blocker = self.by_id.get(next(iter(blockers)))
            if blocker is None or blocker['wydzielenie'] == a['wydzielenie']:
                continue
            attempts += 1
            if attempts > 6:
                break
            for pos in self._single_candidates(blocker):
                if not self._inside(blocker, pos):
                    continue
                if self._conflicts(blocker, pos, (a['id'], b['id'])):
                    continue
                pr = _powieksz(pos, self.odstep / 2)
                if (geo.prostokaty_koliduja(pr, _powieksz(ra, self.odstep / 2))
                        or geo.prostokaty_koliduja(pr, _powieksz(rb, self.odstep / 2))):
                    continue
                self._commit({a['id']: ra, b['id']: rb, blocker['id']: pos})
                self.zmiany_par.add(a['wydzielenie'])
                return True
        return False

    def _single_candidates(self, e):
        r0 = self.indeks.boxy[e['id']]
        w, h = _wymiary(r0)
        pts = e['poligon']
        x0 = min(p[0] for p in pts) + w / 2 + self.granica
        x1 = max(p[0] for p in pts) - w / 2 - self.granica
        y0 = min(p[1] for p in pts) + h / 2 + self.granica
        y1 = max(p[1] for p in pts) - h / 2 - self.granica
        if x0 > x1 or y0 > y1:
            return
        orig = _srodek(r0)
        n = self.siatka + 5
        centres = [(x0 + (x1 - x0) * (i + .5) / n,
                    y0 + (y1 - y0) * (j + .5) / n)
                   for i in range(n) for j in range(n)]
        centres.append(orig)
        centres.sort(key=lambda p: (p[0] - orig[0])**2 + (p[1] - orig[1])**2)
        for point in centres:
            if geo.punkt_w_poligonie(point, pts):
                yield _prost(point, (w, h))

    def _place_single(self, e):
        r0 = self.indeks.boxy[e['id']]
        if self._inside(e, r0) and not self._conflicts(e, r0):
            return False
        for r in self._single_candidates(e):
            if not self._inside(e, r) or self._conflicts(e, r):
                continue
            self._commit({e['id']: r})
            return True
        return False

    def statystyka_marginesu(self):
        naruszenia = sum(1 for e in self.elementy if not self._inside(
            e, self.indeks.boxy[e['id']]))
        odstep = sum(len(self._conflicts(e, self.indeks.boxy[e['id']]))
                     for e in self.elementy) // 2
        pary = 0
        grupy = defaultdict(list)
        for e in self.elementy:
            grupy[e['wydzielenie']].append(e)
        for gr in grupy.values():
            if len(gr) != 2:
                continue
            r1, r2 = (self.indeks.boxy[e['id']] for e in gr)
            if geo.prostokaty_koliduja(r1, r2):
                pary += 1
        return {'za_blisko_granicy_lub_poza': naruszenia,
                'pary_napisow_za_blisko': odstep,
                'wlasna_litera_na_opisie': pary}

    def run(self, przebiegi=3):
        before = v1.statystyka(self.elementy, self.indeks)
        before_margins = self.statystyka_marginesu()
        groups = defaultdict(list)
        for e in self.elementy:
            groups[e['wydzielenie']].append(e)
        pairs = []
        for group in groups.values():
            letters = [e for e in group if e['rodzaj'] == 'litera']
            descs = [e for e in group if e['rodzaj'] == 'opis']
            if len(letters) == 1 and len(descs) == 1:
                pairs.append((letters[0], descs[0]))
        def pair_priority(pair):
            return (-sum(len(self.indeks.kolizje(e['id'])) for e in pair),
                    pair[0]['id'])
        count = 0
        for _ in range(max(1, min(8, int(przebiegi)))):
            changed = 0
            for a, b in sorted(pairs, key=pair_priority):
                if self._place_pair(a, b):
                    changed += 1
            items = sorted(self.elementy,
                           key=lambda e: (-len(self.indeks.kolizje(e['id'])), e['id']))
            for e in items:
                if self._place_single(e):
                    changed += 1
            count += 1
            if not changed:
                break
        groups_unlocked = 0
        for a, b in sorted(pairs, key=pair_priority):
            if self._repair_pair_with_neighbor(a, b):
                groups_unlocked += 1
        after = v1.statystyka(self.elementy, self.indeks)
        after_margins = self.statystyka_marginesu()
        if (sum(after['poza'].values()) > sum(before['poza'].values()) or
                after['kolizje_napisow'] > before['kolizje_napisow']):
            raise AssertionError('Eksperyment v2 pogorszył układ')
        clean_pairs = sum(1 for a, b in pairs if self._pair_clean(a, b))
        return self.zmiany, {
            'przed': before, 'po': after,
            'marginesy_przed': before_margins, 'marginesy_po': after_margins,
            'pary_razem': len(pairs),
            'pary_bez_kolizji_i_z_marginesem': clean_pairs,
            'pary_ulozone_wspolnie': len(self.zmiany_par),
            'grupy_3_elementowe_odblokowane': groups_unlocked,
            'przesuniete': len(self.zmiany), 'przebiegi': count,
            'margines_granicy_m': self.granica,
            'odstep_napisow_m': self.odstep,
            'uwaga': ('Obrysy tekstu są przybliżone. Wysięgniki nie są '
                      'tworzone, więc wynik nie jest jeszcze gotowy do wydruku.'),
        }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Próba v2: pary L2+L3, margines i odstępy')
    parser.add_argument('mapa')
    parser.add_argument('--skala', type=int, default=4000)
    parser.add_argument('--margines', type=float, default=2.5)
    parser.add_argument('--odstep', type=float, default=2.5)
    parser.add_argument('--siatka', type=int, default=19)
    parser.add_argument('--przebiegi', type=int, default=3)
    parser.add_argument('--map-wynik', default=None)
    parser.add_argument('--json', default=None)
    a = parser.parse_args(argv)
    mapa = onm.wczytaj_mape(a.mapa)
    elementy, warnings = dm.elementy_z_mapy(mapa, a.skala)
    wejscie = {e['id']: e['prostokat'] for e in elementy}
    # Pierwsza faza usuwa łatwe konflikty bez marginesów.
    pozycje_v1, raport_v1 = v1.uloz_wewnatrz(elementy, a.siatka + 6, a.przebiegi)
    for e in elementy:
        if e['id'] in pozycje_v1:
            e['prostokat'] = pozycje_v1[e['id']]
    # Druga faza wspólnie układa pary i wprowadza marginesy.
    optimizer = UkladOstrozny(elementy, a.margines, a.odstep, a.siatka)
    _, raport = optimizer.run(a.przebiegi)
    # Eksport zawiera łączny wynik względem niezmienionego pliku wejściowego.
    zmiany = {ident: box for ident, box in optimizer.indeks.boxy.items()
              if max(abs(a - b) for a, b in zip(wejscie[ident], box)) > 1e-5}
    raport['przed'] = raport_v1['przed']
    raport['po_fazie_wstepnej'] = raport_v1['po']
    raport['przeniesione_lacznie'] = len(zmiany)
    raport['ostrzezenia'] = warnings
    print('Układ eksperymentalny v2, skala 1:%d' % a.skala)
    print('Przed:', raport['przed'])
    print('Po fazie wstępnej:', raport['po_fazie_wstepnej'])
    print('Po:', raport['po'])
    print('Margines i odstępy przed fazą 2:', raport['marginesy_przed'])
    print('Margines i odstępy po fazie 2:', raport['marginesy_po'])
    print('Pary bez kolizji i z marginesem: %d/%d' %
          (raport['pary_bez_kolizji_i_z_marginesem'], raport['pary_razem']))
    print('Wspólnie ułożone pary:', raport['pary_ulozone_wspolnie'])
    print('Przesunięte napisy łącznie:', raport['przeniesione_lacznie'])
    if a.map_wynik:
        saved = v1.zapisz_kopie_mapy(mapa, elementy, zmiany, a.mapa, a.map_wynik)
        raport['zapisane_napisy'] = len(saved)
        raport['mapa_wynikowa'] = str(a.map_wynik)
        print('Zapisano kopię mapy:', a.map_wynik)
    if a.json:
        raport['zmiany'] = [{'id': k, 'prostokat': list(v)} for k, v in zmiany.items()]
        Path(a.json).write_text(
            json.dumps(raport, ensure_ascii=False, indent=2), encoding='utf-8')
        print('Zapisano raport:', a.json)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
