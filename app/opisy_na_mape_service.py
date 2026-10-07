# -*- coding: utf-8 -*-
"""
Forestly Mapper — usługa „Opisy na mapę" (bez GUI)
==================================================
Wpisuje opisy taksacyjne do poligonów map GEO-MAP (.MAP) — pola A1/A2/A5.
To ta sama logika, co zakładka „Opisy na mapę" w Forestly, wyjęta z GUI,
żeby mogła działać w oknie Forestly Mapper (pywebview).

Trzy źródła opisów:
  * MIETEK    — pliki DBF (O*.DBF, R*.DBF) w folderze mietka,
  * EXCEL     — arkusze z Forestly GO (kolumna „opis_gotowy"),
  * TAKSATOR  — baza Access (.mdb).

Dopasowanie mapy do źródła odbywa się po nazwie (bez ogonków, małe litery).
Mapy wynikowe zapisywane są jako „<NAZWA>_z_opisami.MAP" obok mapy wejściowej.
"""

import csv
import datetime as _dt
import math
import re
import traceback
import unicodedata
from pathlib import Path

from app.core import opisy_na_mape as onm
from app.core.dbf_io import czytaj_dbf, znajdz_dbf


def klucz_nazwy(s):
    """Nazwa do porównań: bez ogonków, małe litery, tylko [a-z0-9]."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("ł", "l").replace("Ł", "L")
    return re.sub(r"[^a-z0-9]+", "", s.lower())


class SerwisOpisow:
    """Wykonuje wpisywanie opisów i sprawdzanie braków.

    log(tekst)          — linia dziennika dla interfejsu,
    postep(idx, total, plik) — postęp dla paska.
    """

    def __init__(self, log=None, postep=None):
        self.log = log or (lambda _s: None)
        self.postep = postep or (lambda _i, _t, _f: None)

    # ------------------------------------------------- dopasowanie źródeł
    @staticmethod
    def _mapy_w_folderze(folder):
        folder = Path(folder)
        mapa = {}
        for p in sorted(folder.rglob("*")):
            if p.is_file() and p.suffix.lower() == ".map":
                # pomijamy własne wyniki z poprzednich przebiegów, żeby ich
                # nie przetwarzać ponownie (inaczej powstałyby „_z_opisami_z_opisami")
                if p.stem.lower().endswith("_z_opisami"):
                    continue
                mapa.setdefault(klucz_nazwy(p.stem), p)
        return mapa

    @staticmethod
    def _dopasuj(nazwa, kandydaci):
        k = klucz_nazwy(nazwa)
        if not k:
            return None
        if k in kandydaci:
            return kandydaci[k]
        for kk, sc in kandydaci.items():
            if kk and (kk in k or k in kk):
                return sc
        return None

    @staticmethod
    def _arkusze_w_folderze(folder):
        folder = Path(folder)
        out = {}
        for p in sorted(folder.rglob("*.xls*")):
            if p.is_file() and not p.name.startswith("~$"):
                out.setdefault(klucz_nazwy(p.stem), p)
        return out

    @staticmethod
    def _obreby_w_folderze(folder):
        folder = Path(folder)
        out = {}
        for dbf in sorted(folder.rglob("O*.DBF")) + sorted(folder.rglob("O*.dbf")):
            d = dbf.parent
            for nm in (d.name, d.parent.name):
                if nm:
                    out.setdefault(klucz_nazwy(nm), d)
        return out

    @staticmethod
    def _zrodla_excel(sciezka):
        """Folder z arkuszami ALBO pojedynczy plik .xlsx/.xls."""
        p = Path(sciezka)
        if p.is_file():
            return {klucz_nazwy(p.stem): p}
        return SerwisOpisow._arkusze_w_folderze(p)

    @staticmethod
    def _zrodla_mietek(sciezka):
        """Folder z mietkiem ALBO pojedynczy plik DBF (bierzemy jego folder)."""
        p = Path(sciezka)
        if p.is_file():
            d = p.parent
            out = {}
            for nm in (d.name, d.parent.name):
                if nm:
                    out.setdefault(klucz_nazwy(nm), d)
            return out
        return SerwisOpisow._obreby_w_folderze(p)

    @staticmethod
    def _mapy_ze_sciezki(sciezka):
        p = Path(sciezka)
        if p.is_file() and p.suffix.lower() == ".map":
            return {klucz_nazwy(p.stem): p}
        return SerwisOpisow._mapy_w_folderze(p)

    @staticmethod
    def _bazy_ze_sciezki(sciezka):
        if not sciezka:
            return {}
        p = Path(sciezka)
        if p.is_file() and p.suffix.lower() == ".mdb":
            return {klucz_nazwy(p.stem): p}
        if p.is_dir():
            return {klucz_nazwy(q.stem): q for q in sorted(p.glob("*.mdb"))}
        return {}

    def _baza_dla_mapy(self, nazwa_mapy, bazy, cache):
        if not bazy:
            return None, None
        sciezka = self._dopasuj(nazwa_mapy, bazy)
        if sciezka is None and len(bazy) == 1:
            sciezka = next(iter(bazy.values()))
        if sciezka is None:
            return None, None
        if sciezka not in cache:
            from app.core import opisy_na_mape_taksator as tk
            cache[sciezka] = tk.czytaj_baze(str(sciezka)) or {}
        return sciezka, cache[sciezka]

    def _zrodlo_dla_mapy(self, sciezka_mapy, zrodla, u):
        sc = self._dopasuj(sciezka_mapy.stem, zrodla)
        if sc is None:
            return None, None, ("nie znaleziono %s dla tej mapy"
                                % ("arkusza Excel" if u["tryb"] == "excel"
                                   else "obrębu w Mietku"))
        if u["tryb"] == "excel":
            x = onm.czytaj_xlsx(sc)
            if not x["naglowki"]:
                return sc, None, "arkusz jest pusty"
            return sc, {"naglowki": x["naglowki"], "wiersze": x["wiersze"]}, ""
        o_path = znajdz_dbf(sc, "O")
        r_path = znajdz_dbf(sc, "R")
        o_recs = czytaj_dbf(o_path) if o_path else []
        r_recs = czytaj_dbf(r_path) if r_path else []
        ob_o, rby = {}, {}
        for o in o_recs:
            ob_o[onm._czysc(o.get("ODDZIAL")) + onm._czysc(o.get("PODODDZ"))] = o
        for r in r_recs:
            k = onm._czysc(r.get("ODDZIAL")) + onm._czysc(r.get("PODODDZ"))
            rby.setdefault(k, []).append(r)
        return sc, {"obO": ob_o, "rby": rby}, ""

    # ---------------------------------------------------------- wiersze
    def _wiersze_dla_mapy(self, sciezka_mapy, zrodla, u):
        sc_zrodlo, zrodlo, blad = self._zrodlo_dla_mapy(sciezka_mapy, zrodla, u)
        if blad:
            return None, None, blad
        mapa = onm.wczytaj_mape(sciezka_mapy)
        pom = []
        wiersze = onm.zbuduj_wiersze(mapa, u["tryb"], zrodlo,
                                     klucz=u["klucz"], kol_nr=u["kol_nr"],
                                     pominiete=pom)
        if pom:
            self.log("  %s: pominięto %d obiektów bez oznaczenia wydzielenia."
                     % (sciezka_mapy.name, len(pom)))
        return mapa, wiersze, ""

    # ------------------------------------------- wyśrodkowanie i obrót
    def _wysrodkuj_plik(self, sciezka, obr, font_mm=2.5, skala=5000.0,
                        rozsuwaj=False):
        from app.core import uklad_opisow as uk
        mapa = onm.wczytaj_mape(sciezka)
        el = uk.uloz(mapa, wysokosc_mm=font_mm, skala=skala, obrot=obr,
                     tylko_srodek=not rozsuwaj)
        if not el:
            self.log("  %s: brak opisów do ułożenia." % sciezka.name)
            return 0
        lines, _zmiany = uk.ustaw_offsety(mapa, el, obrot_rad=obr)
        sciezka.write_bytes(onm.przelicz_naglowek(lines))
        return len(el)

    # ============================================================ WPISYWANIE
    def wpisz(self, u):
        """Wpisuje opisy do map. Zwraca słownik z podsumowaniem."""
        if u["tryb"] == "taksator":
            return self._wpisz_taksator(u)

        mapy = self._mapy_ze_sciezki(u["mapy"])
        if not mapy:
            return {"ok": False, "blad": "nie znaleziono plików .MAP"}
        if u["tryb"] == "excel":
            zrodla = self._zrodla_excel(u["excel"])
            self.log("Map: %d, arkuszy Excel: %d" % (len(mapy), len(zrodla)))
        else:
            zrodla = self._zrodla_mietek(u["mietki"])
            self.log("Map: %d, obrębów w Mietku: %d" % (len(mapy), len(zrodla)))

        try:
            obr = float(str(u.get("p3", "-0.25")).replace(",", ".")) * math.pi / 200.0
        except (TypeError, ValueError):
            obr = -0.25 * math.pi / 200.0
        try:
            font_mm = float(str(u.get("font_mm", "2.5")).replace(",", ".") or 2.5)
            skala = float(str(u.get("skala", "5000")).replace(",", ".") or 5000)
        except (TypeError, ValueError):
            font_mm, skala = 2.5, 5000.0

        total = len(mapy)
        wyniki = []
        for idx, (klucz, sciezka_mapy) in enumerate(sorted(mapy.items()), start=1):
            self.postep(idx, total, sciezka_mapy.name)
            w = {"mapa": sciezka_mapy.name, "poligonow": 0, "dopasowano": 0,
                 "zmiany": 0, "plik": "", "blad": "", "niedopasowane": []}
            try:
                mapa, wiersze, blad = self._wiersze_dla_mapy(sciezka_mapy, zrodla, u)
                if blad:
                    w["blad"] = blad
                else:
                    w["poligonow"] = len(wiersze)
                    w["dopasowano"] = sum(1 for r in wiersze if r["ok"])
                    w["niedopasowane"] = [r["wydz"] for r in wiersze if not r["ok"]]
                    if w["dopasowano"]:
                        res = onm.zapisz_mape(mapa, mapa["path"].parent,
                                              a2=u["a2"], a5=u["a5"],
                                              wiersze=wiersze, obrot_srodek=obr)
                        w["zmiany"] = res["zmiany"]
                        w["plik"] = res["nazwa"]
                        try:
                            n = self._wysrodkuj_plik(res["sciezka"], obr,
                                                     font_mm=font_mm, skala=skala,
                                                     rozsuwaj=bool(u.get("rozsuwaj")))
                            self.log("  ✔ %s: wyśrodkowano i obrócono %d opisów"
                                     % (sciezka_mapy.name, n))
                        except Exception as e:               # noqa: BLE001
                            self.log("  ⚠ %s: nie udało się wyśrodkować: %s"
                                     % (sciezka_mapy.name, e))
            except Exception as e:                           # noqa: BLE001
                w["blad"] = str(e)
            wyniki.append(w)
            if w.get("blad"):
                self.log("  ⚠ %s: %s" % (sciezka_mapy.name, w["blad"]))
            elif w["dopasowano"]:
                self.log("  • %s: dopasowano %d/%d → %s"
                         % (sciezka_mapy.name, w["dopasowano"], w["poligonow"],
                            w["plik"] or "(podgląd)"))
            else:
                self.log("  ⚠ %s: nie dopasowano żadnego poligonu."
                         % sciezka_mapy.name)

        return self._raport(wyniki, u, "OPISY NA MAPĘ (GEO-MAP)")

    # ---------------------------------------------------------- TAKSATOR
    def _wpisz_taksator(self, u):
        from app.core import opisy_na_mape_taksator as tk
        bazy = self._bazy_ze_sciezki(u["mdb"])
        cache = {}
        mapy = self._mapy_ze_sciezki(u["mapy"])
        if not mapy:
            return {"ok": False, "blad": "nie znaleziono plików .MAP"}
        total = len(mapy)
        wyniki = []
        for idx, (klucz, sciezka) in enumerate(sorted(mapy.items()), start=1):
            self.postep(idx, total, sciezka.name)
            w = {"mapa": sciezka.name, "poligonow": 0, "dopasowano": 0,
                 "zmiany": 0, "plik": "", "blad": "", "niedopasowane": [],
                 "bez_oznaczenia": []}
            try:
                sc_b, baza = self._baza_dla_mapy(sciezka.stem, bazy, cache)
                if not baza:
                    w["blad"] = "brak bazy .mdb o tej nazwie"
                else:
                    mapa = onm.wczytaj_mape(sciezka)
                    pom = []
                    wiersze = tk.zbuduj_wiersze(mapa, baza, pominiete=pom)
                    w["poligonow"] = len(wiersze)
                    w["dopasowano"] = sum(1 for r in wiersze if r["ok"])
                    w["niedopasowane"] = [r["wydz"] for r in wiersze if not r["ok"]]
                    w["bez_oznaczenia"] = [r["wydz"] for r in wiersze
                                           if r["ok"] and not r["noweA2"]]
                    if pom:
                        self.log("  %s: pominięto %d obiektów bez wydzielenia."
                                 % (sciezka.name, len(pom)))
                    if w["dopasowano"]:
                        res = tk.zapisz_mape(mapa, sciezka.parent, wiersze=wiersze)
                        w["zmiany"] = res["zmiany"]
                        w["plik"] = res["nazwa"]
                    self.log("  • %s: dopasowano %d/%d → %s"
                             % (sciezka.name, w["dopasowano"], w["poligonow"],
                                w["plik"] or "(podgląd)"))
            except Exception as e:                           # noqa: BLE001
                w["blad"] = str(e)
                self.log("  ⚠ %s: %s" % (sciezka.name, e))
            wyniki.append(w)
        return self._raport(wyniki, u, "OPISY TAKSACYJNE Z TAKSATORA DO MAPY",
                            taksator=True)

    # ============================================================ SPRAWDZANIE
    def sprawdz(self, u):
        """Szuka braków/różnic (bez zapisu). Zwraca słownik z tabelą."""
        if u["tryb"] == "taksator":
            return self._sprawdz_taksator(u)
        mapy = self._mapy_ze_sciezki(u["mapy"])
        if not mapy:
            return {"ok": False, "blad": "nie znaleziono plików .MAP"}
        zrodla = (self._zrodla_excel(u["excel"]) if u["tryb"] == "excel"
                  else self._zrodla_mietek(u["mietki"]))
        total = len(mapy)
        wszystkie = []
        for idx, (klucz, sciezka_mapy) in enumerate(sorted(mapy.items()), start=1):
            self.postep(idx, total, sciezka_mapy.name)
            try:
                mapa, wiersze, blad = self._wiersze_dla_mapy(sciezka_mapy, zrodla, u)
                if blad:
                    self.log("  ⚠ %s: %s" % (sciezka_mapy.name, blad))
                else:
                    wszystkie += onm.braki_do_przegladu(sciezka_mapy.name, wiersze,
                                                        u["a2"], u["a5"])
            except Exception as e:                           # noqa: BLE001
                self.log("  ⚠ %s: %s" % (sciezka_mapy.name, e))
        return self._wynik_braki(wszystkie, u, len(mapy))

    def _sprawdz_taksator(self, u):
        from app.core import opisy_na_mape_taksator as tk
        bazy = self._bazy_ze_sciezki(u["mdb"])
        cache = {}
        mapy = self._mapy_ze_sciezki(u["mapy"])
        if not mapy:
            return {"ok": False, "blad": "nie znaleziono plików .MAP"}
        total = len(mapy)
        wszystkie = []
        for idx, (klucz, sciezka) in enumerate(sorted(mapy.items()), start=1):
            self.postep(idx, total, sciezka.name)
            try:
                sc_b, baza = self._baza_dla_mapy(sciezka.stem, bazy, cache)
                if not baza:
                    self.log("  ⚠ %s: brak bazy .mdb — pomijam." % sciezka.name)
                    continue
                mapa = onm.wczytaj_mape(sciezka)
                wiersze = tk.zbuduj_wiersze(mapa, baza)
                wszystkie += tk.braki_do_przegladu(sciezka.name, wiersze)
            except Exception as e:                           # noqa: BLE001
                self.log("  ⚠ %s: %s" % (sciezka.name, e))
        return self._wynik_braki(wszystkie, u, len(mapy))

    # ---------------------------------------------------------- raporty
    def _wynik_braki(self, wszystkie, u, ile_map):
        podsum = onm.podsumuj_braki(wszystkie)
        csvp = self._zapisz_braki_csv(u["mapy"], wszystkie)
        if csvp:
            self.log("Zapisano różnice do CSV: %s" % csvp)
        if wszystkie:
            self.log("Pozycje do sprawdzenia: %d (%s)."
                     % (len(wszystkie),
                        ", ".join("%s: %d" % (k, v) for k, v in podsum.items())))
        else:
            self.log("Brak uwag — wszystko dopasowane i zgodne.")
        return {"ok": True, "rows": wszystkie[:2000], "razem": len(wszystkie),
                "podsumowanie": podsum, "map": ile_map}

    @staticmethod
    def _zapisz_braki_csv(folder, wszystkie):
        if not wszystkie:
            return None
        out = Path(folder)
        if out.is_file():
            out = out.parent
        plik = out / "Opisy na mapę - braki.csv"
        try:
            with open(plik, "w", newline="", encoding="utf-8-sig") as f:
                wr = csv.writer(f, delimiter=";")
                wr.writerow(["Mapa", "Wydzielenie", "Pole", "Co jest (mapa)",
                             "Co da reguła", "Uwaga"])
                for r in wszystkie:
                    wr.writerow([r.get("mapa", ""), r.get("wydz", ""),
                                 r.get("pole", ""), r.get("obecne", ""),
                                 r.get("nowe", ""), r.get("typ", "")])
            return plik
        except OSError:
            return None

    def _raport(self, wyniki, u, tytul, taksator=False):
        linie = [
            "FORESTLY MAPPER — %s" % tytul,
            "Data: %s" % _dt.datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Źródło opisów: %s" % {
                "excel": "Excel z Forestly GO",
                "mietek": "dane MIETKA",
                "taksator": "baza TAKSATORA (.mdb)"}.get(u["tryb"], u["tryb"]),
            "Tryb: ZAPIS map _z_opisami.MAP",
            "-" * 70,
        ]
        sp = sd = sz = 0
        for w in wyniki:
            sp += w["poligonow"]
            sd += w["dopasowano"]
            sz += w["zmiany"]
            if w.get("blad"):
                linie.append("  ✗ %-28s BŁĄD: %s" % (w["mapa"], w["blad"]))
            else:
                linie.append("  • %-28s poligonów: %4d, dopasowano: %4d%s"
                             % (w["mapa"], w["poligonow"], w["dopasowano"],
                                (", zapisano: %s" % w["plik"]) if w["plik"] else ""))
                if w.get("niedopasowane"):
                    linie.append("      niedopasowane: %s"
                                 % ", ".join(w["niedopasowane"]))
                if w.get("bez_oznaczenia"):
                    linie.append("      bez oznaczenia w bazie: %s"
                                 % ", ".join(w["bez_oznaczenia"]))
        linie += ["-" * 70,
                  "Razem map: %d, poligonów: %d, dopasowanych: %d, zmian: %d"
                  % (len(wyniki), sp, sd, sz)]
        out = Path(u["mapy"])
        if out.is_file():
            out = out.parent
        try:
            out.mkdir(parents=True, exist_ok=True)
            plik = out / "Opisy na mapę - raport.txt"
            plik.write_text("\n".join(linie), encoding="utf-8-sig")
            self.log("Raport: %s" % plik)
        except OSError as e:
            self.log("Nie udało się zapisać raportu: %s" % e)
        self.log("Razem map: %d, poligonów: %d, dopasowanych: %d, zmian: %d"
                 % (len(wyniki), sp, sd, sz))
        return {"ok": True, "wyniki": wyniki, "map": len(wyniki),
                "poligonow": sp, "dopasowano": sd, "zmiany": sz,
                "folder": str(out)}
