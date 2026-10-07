# -*- coding: utf-8 -*-
"""
Forestly — opisy taksacyjne z bazy TAKSATORA (.mdb) do mapy GEO-MAP.

Czyta bazę taksatora (Access, Jet4) i wpisuje do poligonów mapy GEO-MAP
pole A2 („Oznaczenie") w postaci:

    [udział]GATUNEK+WIEK|POWIERZCHNIA      np.  9SO30|3.9524

oraz pole A1 (sama litera wydzielenia, np. „fx"). Pole A6 zostaje bez zmian.

Skąd dane (tabele taksatora):
  * F_ARODES        — obiekty; pole ADRESS_FOREST koduje oddział i pododdział
                      (np. „C160420001-  04  -fx  -00" -> oddział „04",
                      pododdział „fx"); bierzemy tylko ARODES_TYP_CD = WYDZIEL,
  * F_SUBAREA       — powierzchnia (SUB_AREA) i typ powierzchni (AREA_TYPE_CD),
  * F_STOREY_SPECIES — skład: gatunek (SPECIES_CD), wiek (SPECIES_AGE),
                      udział (PART_CD) — piętro DRZEW, ranga 1.

Dopasowanie: poligon mapy -> wydzielenie po oddziale i pododdziale
(z A6 mapy, z pominięciem zer wiodących w oddziale).

Bazę czyta się przez pyodbc (sterownik MS Access — jak reszta programu);
gdy sterownik nie jest dostępny, jest zapasowy czytnik „access_parser".
"""

from pathlib import Path
import re

DRIVER_ACCESS = "Microsoft Access Driver (*.mdb, *.accdb)"

# Etykiety obiektów nieleśnych (typ powierzchni w bazie -> oznaczenie na mapie).
# Dla typów spoza tej mapy nic nie wpisujemy (pozycja trafia do „braków").
ETYKIETY_TYPOW = {
    "L ENERG": "L.ENERG",
    "ZRĄB": "zrąb",
    "SUKCESJA": "sukcesja",
    "INNE WYL": "inne wylesienie",
    # drogi (różne kody dróg w bazie) — na mapie krótko „droga”
    "DROGI L": "droga",
    "DROGI P": "droga",
    "DROGI I": "droga",
}


# --------------------------------------------------------------- czytanie bazy
def _tabela(path, nazwa):
    """Zwraca listę słowników {kolumna: wartość} dla tabeli z bazy .mdb."""
    try:
        import pyodbc
    except ImportError:
        pyodbc = None
    if pyodbc is not None:
        try:
            conn = pyodbc.connect(
                "DRIVER={%s};DBQ=%s;" % (DRIVER_ACCESS, path), readonly=True)
        except Exception:
            conn = None
        if conn is not None:
            try:
                cur = conn.cursor()
                cur.execute("SELECT * FROM [%s]" % nazwa)
                kol = [d[0] for d in cur.description]
                return [dict(zip(kol, row)) for row in cur.fetchall()]
            finally:
                conn.close()
    # zapas: pure-Python access_parser (gdy brak sterownika Access)
    from access_parser import AccessParser
    d = AccessParser(str(path)).parse_table(nazwa)
    if not d:
        return []
    n = max(len(v) for v in d.values())
    return [{k: (d[k][i] if i < len(d[k]) else None) for k in d} for i in range(n)]


def _oddzial_pododdzial(adres, order):
    """Zwraca (oddział, pododdział) niezależnie od wersji bazy.

    Oddział bierzemy z ORDER_KEY — jest stabilny między wersjami bazy
    (np. „041604200010007xd00” -> oddział „0007”). Różne wersje taksatora
    różnie zapisują pole oddziału w ADRESS_FOREST (raz „  07  ”, raz
    „1007  ”), dlatego na samym ADRESS nie można polegać. Pododdział
    bierzemy z ADRESS_FOREST (3. pole).
    """
    p = str(adres or "").split("-")
    pod = p[2].strip() if len(p) >= 3 else ""
    o = str(order or "").strip()
    odd = ""
    if len(o) >= 8 and o[-8:-4].strip().isdigit():
        odd = o[-8:-4].strip()
    if not odd and len(p) >= 2:
        cyfry = "".join(ch for ch in p[1] if ch.isdigit())
        odd = cyfry[-3:] if len(cyfry) > 3 else cyfry
    return odd, pod


def _klucz(oddzial, pododdzial):
    """Klucz wydzielenia do dopasowania (oddział jako liczba, małe litery)."""
    o = str(oddzial if oddzial is not None else "").strip()
    try:
        o = str(int(o)) if o else "0"
    except ValueError:
        o = o.lstrip("0") or "0"
    return o + (str(pododdzial) if pododdzial is not None else "").strip().lower()


def czytaj_baze(path):
    """Wczytuje bazę taksatora. Zwraca {klucz wydzielenia: rekord opisu}."""
    arodes = {}
    for r in _tabela(path, "F_ARODES"):
        if str(r.get("ARODES_TYP_CD") or "").strip() != "WYDZIEL":
            continue
        odd, pod = _oddzial_pododdzial(r.get("ADRESS_FOREST"), r.get("ORDER_KEY"))
        if not pod:
            continue
        arodes[str(r.get("ARODES_INT_NUM"))] = {"oddzial": odd, "pododdzial": pod}

    subarea = {}
    for r in _tabela(path, "F_SUBAREA"):
        subarea[str(r.get("ARODES_INT_NUM"))] = {
            "area": r.get("SUB_AREA"),
            "typ": str(r.get("AREA_TYPE_CD") or "").strip(),
            "siedlisko": str(r.get("SITE_TYPE_CD") or "").strip(),
            # „informacje różne" — np. Rola, Łąka, Bagno dla obiektów nieleśnych
            "info": str(r.get("SUBAREA_INFO") or "").strip(),
        }

    gatunek = {}
    for r in _tabela(path, "F_STOREY_SPECIES"):
        if str(r.get("STOREY_CD") or "").strip() != "DRZEW":
            continue
        if str(r.get("SPECIES_RANK_ORDER") or "").strip() != "1":
            continue
        gatunek[str(r.get("ARODES_INT_NUM"))] = {
            "gatunek": str(r.get("SPECIES_CD") or "").strip(),
            "wiek": r.get("SPECIES_AGE"),
            "udzial": str(r.get("PART_CD") or "").strip(),
        }

    # słownik typów powierzchni: kod -> nazwa (fallback, gdy nic innego nie ma)
    nazwy_typow = {}
    for r in _tabela(path, "F_AREA_TYPE_DIC"):
        cd = str(r.get("area_type_cd") or "").strip()
        nm = str(r.get("area_type_name") or "").strip()
        if cd and nm:
            nazwy_typow[cd] = nm

    baza = {}
    for num, info in arodes.items():
        sa = subarea.get(num) or {}
        ga = gatunek.get(num) or {}
        baza.setdefault(_klucz(info["oddzial"], info["pododdzial"]), {
            "arodes": num,
            "oddzial": info["oddzial"],
            "pododdzial": info["pododdzial"],
            "area": sa.get("area"),
            "typ": sa.get("typ", ""),
            "typ_nazwa": nazwy_typow.get(sa.get("typ", ""), ""),
            "siedlisko": sa.get("siedlisko", ""),
            "info": sa.get("info", ""),
            "gatunek": ga.get("gatunek", ""),
            "wiek": ga.get("wiek"),
            "udzial": ga.get("udzial", ""),
        })
    return baza


# ------------------------------------------------------------------ formatowanie
def format_pow(v):
    """Powierzchnia jak w mapie: min. 2 miejsca po przecinku, więcej gdy trzeba.

    0.3 -> „0.30",  3.9524 -> „3.9524",  0.51 -> „0.51".
    """
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = "%.4f" % f
    s = s.rstrip("0")
    if s.endswith("."):
        s += "00"
    elif len(s.split(".")[1]) == 1:
        s += "0"
    return s


def _wiek(v):
    if v is None or v == "":
        return ""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v).strip()
    return str(int(f)) if f.is_integer() else ("%g" % f)


def oznaczenie(rec):
    """Część A2 przed „|" (udział+gatunek+wiek albo etykieta obiektu nieleśnego).

    Dla obiektów bez gatunku: najpierw „informacje różne" z bazy (SUBAREA_INFO,
    np. „Rola", „Łąka", „Bagno"), a gdy puste — etykieta z typu powierzchni.
    """
    g = (rec.get("gatunek") or "").strip()
    if g:
        part = str(rec.get("udzial") or "").strip()
        if part == "10":
            part = ""          # udział pełny (10/10) bez cyfry z przodu
        return "%s%s%s" % (part, g, _wiek(rec.get("wiek")))
    info = (rec.get("info") or "").strip()
    if info:
        return info
    typ = (rec.get("typ") or "").strip()
    lab = ETYKIETY_TYPOW.get(typ)
    if lab:
        return lab
    # fallback: nazwa typu powierzchni ze słownika bazy (F_AREA_TYPE_DIC)
    # — dzięki temu KAŻDY nieleśny typ dostaje jakiś opis, a nie puste pole
    return (rec.get("typ_nazwa") or "").strip()


def a2_dla(rec):
    """Pełne A2: „oznaczenie|powierzchnia" (albo "" gdy brak oznaczenia)."""
    ozn = oznaczenie(rec)
    if not ozn:
        return ""
    return "%s|%s" % (ozn, format_pow(rec.get("area")))


def dopasuj(a6, baza):
    """Wydzielenie mapy (A6, np. „04fx" lub „4fx") -> rekord bazy albo None."""
    m = re.match(r"^0*(\d+)(.*)$", (a6 or "").strip())
    if not m:
        return None
    return baza.get(_klucz(m.group(1), m.group(2)))


# ------------------------------------------------------------------ złożenie mapy
def zbuduj_wiersze(mapa, baza, pominiete=None):
    """Wiersze podglądu dla jednej mapy (tryb TAKSATOR)."""
    from app.core import opisy_na_mape as onm
    from app.core import zamiany_opisow as _zam
    zamiany = _zam.wczytaj()
    wiersze = []
    for o in onm.znajdz_poligony(mapa["lines"]):
        a1 = (o.get("A1") or "").strip()
        a6 = (o.get("A6") or "").strip()
        if not (a1 or a6):
            if pominiete is not None:
                pominiete.append(o)
            continue
        wydz = a6 or a1
        rec = dopasuj(wydz, baza)
        r = {"wydz": wydz, "obecneA1": o.get("A1", ""),
             "obecneA2": o.get("A2", ""), "noweA1": "", "noweA2": "",
             "status": "", "ok": False, "o": o}
        if rec:
            r["ok"] = True
            r["noweA1"] = rec["pododdzial"]
            r["noweA2"] = a2_dla(rec)
            r["status"] = "dopasowano (%s)" % (
                str(rec["oddzial"]).lstrip("0") + rec["pododdzial"])
        else:
            r["status"] = "brak wydzielenia w bazie"
        if r["ok"]:
            r["noweA2"] = _zam.zastosuj(r["noweA2"], zamiany)
        wiersze.append(r)
    return wiersze


def wpisz_do_mapy(mapa, wiersze, a1=True, a2=True):
    """Wpisuje A1 i A2 dopasowanych wierszy (A6 zostaje bez zmian).

    Zwraca (liczba_zmian, bajty_wyniku).
    """
    from app.core import opisy_na_mape as onm
    lines = list(mapa["lines"])
    zmienione = 0
    do_zmiany = [w for w in wiersze if w["ok"]]
    do_zmiany.sort(key=lambda w: w["o"]["start"], reverse=True)
    for w in do_zmiany:
        start = w["o"]["start"]
        o = w["o"]
        a1_ob = (o.get("A1") or "").strip()
        a6_ob = (o.get("A6") or "").strip()
        # A6 puste, a A1 ma identyfikator wydzielenia (np. „2l”) -> skopiuj do A6
        if not a6_ob and a1_ob:
            k = onm.blok_koniec(lines, start)
            onm.ustaw_atrybut(lines, start, k, "A6", a1_ob)
            zmienione += 1
        if a2 and w.get("noweA2") and w["noweA2"] != (o.get("A2") or "").strip():
            k = onm.blok_koniec(lines, start)
            onm.ustaw_atrybut(lines, start, k, "A2", w["noweA2"])
            zmienione += 1
        if a1:
            lit = (w.get("noweA1") or "").strip()
            # A1 uzupełniamy tylko gdy jest PUSTE — nie nadpisujemy istniejącego
            # (w mapach bez A6 A1 jest identyfikatorem wydzielenia, np. „2l”).
            if lit and not a1_ob:
                k = onm.blok_koniec(lines, start)
                onm.ustaw_atrybut(lines, start, k, "A1", lit, zaraz_po="ID")
                zmienione += 1
    return zmienione, onm.przelicz_naglowek(lines)


def zapisz_mape(mapa, out_dir, wiersze=None, a1=True, a2=True):
    """Zapisuje mapę wynikową „<NAZWA>_z_opisami.MAP" do out_dir."""
    from app.core import opisy_na_mape as onm
    if wiersze is None:
        wiersze = []
    zmiany, out = wpisz_do_mapy(mapa, wiersze, a1=a1, a2=a2)
    nazwa = re.sub(r"\.map$", "", mapa["path"].name, flags=re.I) + "_z_opisami.MAP"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cel = out_dir / nazwa
    cel.write_bytes(out)
    return {"nazwa": nazwa, "sciezka": cel, "zmiany": zmiany,
            "poligonow": len(wiersze),
            "dopasowano": sum(1 for w in wiersze if w["ok"])}


def braki_do_przegladu(nazwa_mapy, wiersze):
    """Pozycje do sprawdzenia/uzupełnienia (brak wydzielenia, brak opisu)."""
    from app.core import opisy_na_mape as onm
    rows = []
    for w in wiersze:
        o = w["o"]
        if not w["ok"]:
            rows.append({"mapa": nazwa_mapy, "wydz": w["wydz"], "pole": "—",
                         "typ": "brak wydzielenia", "waga": "serious",
                         "obecne": "", "nowe": "", "status": w["status"]})
            continue
        if not w.get("noweA2"):
            rows.append({"mapa": nazwa_mapy, "wydz": w["wydz"], "pole": "A2",
                         "typ": "brak oznaczenia w bazie", "waga": "info",
                         "obecne": o.get("A2", ""), "nowe": "", "status": w["status"]})
        elif w["noweA2"] != (o.get("A2") or "").strip():
            rodz = onm.klasyfikuj_roznice(o.get("A2", ""), w["noweA2"])
            if rodz != "zgodne":
                rows.append({"mapa": nazwa_mapy, "wydz": w["wydz"], "pole": "A2",
                             "typ": rodz, "waga": onm.waga_pozycji(rodz),
                             "obecne": o.get("A2", ""), "nowe": w["noweA2"],
                             "status": w["status"]})
    return rows
