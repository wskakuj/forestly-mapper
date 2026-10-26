# -*- coding: utf-8 -*-
"""Szybki, tylko-odczytowy indeks przecięć wysięgników z obiektami GEO-MAP.

Wiele klas linii może współdzielić ten sam geometryczny punkt
przecięcia; karę naliczamy raz za fizyczny punkt, nie za każdą warstwę.
Nie zakładamy, że wszystkie warstwy są bezwzględnymi przeszkodami.
"""
from collections import defaultdict
from math import floor

from app.core import geometria_ukladu as geo
from app.core import kontury_map as km


class IndeksPrzeciec:
    def __init__(self, obiekty, lines, krok=80):
        if krok <= 0:
            raise ValueError("Krok indeksu musi być dodatni")
        self.krok = krok
        self.grid = defaultdict(list)
        self.odcinki = []
        self.cache = {}
        for obj in obiekty:
            header = lines[obj["start"]].split()
            typ = header[0] if header else "?"
            owner = next((line[4:-1] for line in obj["linie"]
                          if line.startswith(":ID[") and line.endswith("]")),
                         None)
            for fragment in km.fragmenty_z_linii(obj["linie"]):
                pts = fragment["punkty"]
                edges = list(zip(pts, pts[1:]))
                if fragment["zamkniety"] and pts[-1] != pts[0]:
                    edges.append((pts[-1], pts[0]))
                for a, b in edges:
                    if a == b:
                        continue
                    area = (min(a[0], b[0]), min(a[1], b[1]),
                            max(a[0], b[0]), max(a[1], b[1]))
                    idx = len(self.odcinki)
                    self.odcinki.append((a, b, area, typ, owner))
                    for cell in self._komorki(area):
                        self.grid[cell].append(idx)

    def _komorki(self, rect):
        x0, y0, x1, y1 = rect
        for x in range(floor(x0/self.krok), floor(x1/self.krok)+1):
            for y in range(floor(y0/self.krok), floor(y1/self.krok)+1):
                yield x, y

    def raport(self, wysiegnik, owner):
        if not wysiegnik:
            return {"liczba_punktow_przeciec": 0,
                    "liczba_dodatkowych_przeciec": 0,
                    "liczba_nakladajacych_sie_odcinkow": 0,
                    "punkty": [], "nakladanie": []}
        a, b = wysiegnik
        key = (tuple(round(v, 5) for p in (a,b) for v in p), owner)
        if key in self.cache:
            return self.cache[key]
        area = (min(a[0],b[0]), min(a[1],b[1]),
                max(a[0],b[0]), max(a[1],b[1]))
        candidates = set()
        for cell in self._komorki(area):
            candidates.update(self.grid.get(cell, ()))
        grouped, overlaps = {}, []
        for idx in candidates:
            c, d, box, typ, ident = self.odcinki[idx]
            if (box[0] > area[2] + geo.EPS
                    or box[2] < area[0] - geo.EPS
                    or box[1] > area[3] + geo.EPS
                    or box[3] < area[1] - geo.EPS):
                continue
            status, point = geo.przeciecie_odcinkow(a,b,c,d)
            if status == "brak":
                continue
            if status == "nakladanie":
                overlaps.append((typ,ident))
                continue
            xy = (round(point[0],2),round(point[1],2))
            row = grouped.setdefault(xy, {"punkt": list(xy),
                                            "typy": set(),
                                            "wlasna_granica": False})
            row["typy"].add(typ)
            if ident == owner and typ == "*5310":
                row["wlasna_granica"] = True
        points = sorted(grouped.values(),key=lambda x:tuple(x["punkt"]))
        result = {
            "liczba_punktow_przeciec": len(points),
            "liczba_dodatkowych_przeciec": sum(
                not p["wlasna_granica"] for p in points),
            "liczba_nakladajacych_sie_odcinkow": len(overlaps),
            "punkty": [{"punkt":p["punkt"],
                        "typy_obiektow": sorted(p["typy"]),
                        "wlasna_granica": p["wlasna_granica"]}
                       for p in points],
            "nakladanie": [
                {"typ":typ,"id_obiektu":ident}
                for typ,ident in sorted(overlaps)[:5]],
        }
        if len(self.cache) >= 50000:
            self.cache.clear()
        self.cache[key] = result
        return result

    def kara_planu(self, plan, za_punkt=25.0):
        """Koszt MIĘKKI: nie zastępuje twardej walidacji geometrii."""
        if za_punkt < 0:
            raise ValueError("Kara nie może być ujemna")
        total = 0.0
        for e in plan:
            if e.get("wysiegnik"):
                entry = self.raport(e["wysiegnik"],e["wydzielenie"])
                total += za_punkt * (
                    entry["liczba_dodatkowych_przeciec"]
                    + entry["liczba_nakladajacych_sie_odcinkow"])
        return total
