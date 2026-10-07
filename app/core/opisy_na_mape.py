# -*- coding: utf-8 -*-
"""
Forestly — wpisywanie opisów do poligonów mapy GEO-MAP (plik .MAP).

Moduł przenosi do Pythona logikę narzędzia „Opisy na mapę" (pierwotnie
samodzielny plik HTML). Wpisuje opisy w poligony typu 5310 mapy GEO-MAP:

  * A2 — „Oznaczenie"  (np. So85|III-0.5),
  * A5 — „Opis taks."  (pełny opis taksacyjny),

a źródłem danych może być:

  * arkusz Excel z Forestly GO (eksport „Taksacja"), albo
  * dane MIETKA (pliki DBF: O*.DBF — wydzielenia, R*.DBF — elementy).

Reguła Oznaczenia (A2):
    [udział]GATUNEK + WIEK + „|" + BONITACJA + „-" + ZADRZEWIENIE
(odtworzona na podstawie mapy i mietka obrębu — patrz zakładka „Opisy na mapę").

Format .MAP: plik tekstowy (CP1250), wiersze rozdzielone CRLF. Blok obiektu
zaczyna się wierszem „*<typ> ...", a atrybuty mają postać „:NAZWA[wartość]".
Nagłówek (pierwszy wiersz) zawiera licznik wierszy N=[...] oraz sumę kontrolną
CHK=[...] (MD5 treści) — po zmianie treści obie wartości są przeliczane, żeby
plik nadal otwierał się w programie do mapy (GMW).

WAŻNE: oryginalna mapa NIE jest modyfikowana — powstaje nowy plik
„<NAZWA>_z_opisami.MAP".
"""

from pathlib import Path
import hashlib
import re
import unicodedata

MAP_ENCODING = "cp1250"

# ---------------------------------------------------------------- Mazowia (CP667)
# GEO-MAP czyta i zapisuje mapy w kodowaniu MAZOWIA, nie CP1250.
# Dlatego "Ł" musi byc bajtem 0x9C, a "ą" bajtem 0x86 (nie 0xA3/0xB9).
# Tabela wg CP667 (potwierdzona na pliku uzytkownika: Ł->9C, ą->86).
_MAZOWIA_ZNAK = {
    0x86: "ą", 0x8D: "ć", 0x8F: "Ą", 0x90: "Ę", 0x91: "ę", 0x92: "ł",
    0x95: "Ć", 0x98: "Ś", 0x9C: "Ł", 0x9E: "ś", 0xA0: "Ź", 0xA1: "Ż",
    0xA2: "ó", 0xA3: "Ó", 0xA4: "ń", 0xA5: "Ń", 0xA6: "ź", 0xA7: "ż",
}
_MAZOWIA_BAJT = {v: k for k, v in _MAZOWIA_ZNAK.items()}

# bajt -> znak: polskie litery po mazowiańsku, reszta jak CP1250
_MAZ_NA_ZNAK = {
    b: (_MAZOWIA_ZNAK[b] if b in _MAZOWIA_ZNAK
        else bytes([b]).decode("cp1250", "surrogateescape"))
    for b in range(256)
}


def maz_na_tekst(raw: bytes) -> str:
    """Bajty pliku .MAP -> tekst (Mazowia + reszta CP1250)."""
    return "".join(_MAZ_NA_ZNAK[b] for b in raw)


def tekst_na_maz(tekst: str) -> bytes:
    """Tekst -> bajty pliku .MAP w Mazowii (polskie litery mazowiańskie)."""
    out = bytearray()
    for ch in tekst:
        b = _MAZOWIA_BAJT.get(ch)
        if b is not None:
            out.append(b)
            continue
        try:
            out += ch.encode("cp1250")
        except UnicodeEncodeError:
            # znak z surrogateescape (bajt nieznany) -> oddaj ten sam bajt
            o = ord(ch)
            out.append(o - 0xDC00 if 0xDC80 <= o <= 0xDCFF else 0x3F)
    return bytes(out)



TYP_POLIGONU = "5310"

# --- regexy ------------------------------------------------------------------
RE_ATR = re.compile(r"^:([A-Za-z0-9]+)\[(.*)\]\s*$")
# „8Ol" / „So/65-75/70l" / „3Brz" -> udział, gatunek, (opcjonalnie wiek)
RE_SEG = re.compile(
    r"^(\d*)\s*([A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ]{2,6})"
    r"\s*(?:/\s*(\d+)\s*-\s*(\d+)\s*/\s*(\d+)\s*l)?")
RE_GAT_EXCEL = re.compile(r"^(\d*)\s*([A-Za-ząćęłńóśźż]{2,6})")


def _czysc(v):
    """Wartość pola -> tekst bez spacji (None -> '')."""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


# ============================================================ MAPA: czytanie ==

def wczytaj_mape(path):
    """Czyta plik .MAP (CP1250, CRLF) i zwraca słownik z wierszami.

    Używamy „surrogateescape”, żeby zachować DOSŁOWNIE wszystkie bajty
    (w mapach zdarzają się pojedyncze znaki w innym kodowaniu) — inaczej
    przy zapisie zamieniłyby się na „?” i suma kontrolna by się rozjechała.
    """
    raw = Path(path).read_bytes()
    text = maz_na_tekst(raw)
    return {"path": Path(path), "raw": raw, "lines": text.split("\r\n")}


def blok_koniec(lines, i):
    """Indeks pierwszego wiersza po bloku obiektu zaczętym w i."""
    j = i + 1
    while j < len(lines) and not lines[j].startswith("*"):
        j += 1
    return j


def pobierz_atrybut(lines, start, koniec, nazwa):
    """Zwraca {'i': indeks, 'wartosc': ...} dla atrybutu w bloku albo None."""
    for j in range(start + 1, koniec):
        m = RE_ATR.match(lines[j])
        if m and m.group(1) == nazwa:
            return {"i": j, "wartosc": m.group(2)}
    return None


def ustaw_atrybut(lines, start, koniec, nazwa, wartosc, zaraz_po=None):
    """Ustawia atrybut w bloku (podmienia albo wstawia nowy wiersz).

    zaraz_po — jeśli podane (np. „ID”), nowy atrybut wstawiany jest tuż po nim.
    """
    for j in range(start + 1, koniec):
        m = RE_ATR.match(lines[j])
        if m and m.group(1) == nazwa:
            lines[j] = ":%s[%s]" % (nazwa, wartosc)
            return "podmieniono"
    cel = None
    if zaraz_po:
        for k in range(start + 1, koniec):
            mm = RE_ATR.match(lines[k])
            if mm and mm.group(1) == zaraz_po:
                cel = k
                break
    if cel is None:
        # brak atrybutu — wstaw po ID / A1..A4, inaczej po ostatnim atrybucie
        for k in range(start + 1, koniec):
            mm = RE_ATR.match(lines[k])
            if not mm:
                if lines[k][:2] in ("L ", "P ", "C "):
                    break
                continue
            nm = mm.group(1)
            if nm == "ID" or (len(nm) == 2 and nm[0] == "A" and "1" <= nm[1] <= "4"):
                cel = k
    if cel is None:
        for q in range(start + 1, koniec):
            if RE_ATR.match(lines[q]):
                cel = q
    if cel is None:
        cel = start
    lines.insert(cel + 1, ":%s[%s]" % (nazwa, wartosc))
    return "wstawiono"


def przelicz_naglowek(lines):
    """Przelicza N=[...] (liczba wierszy) i CHK=[...] (MD5 treści).

    Zwraca gotowe bajty pliku wynikowego (CP1250, CRLF).
    """
    body = "\r\n".join(lines[1:])
    body_bytes = tekst_na_maz(body)
    n = body.count("\n") + 1
    chk = hashlib.md5(body_bytes).hexdigest()
    hdr = lines[0]

    def _n(m):
        st = m.group(1)
        return "N=[" + str(n).rjust(len(st)) + "]"

    hdr = re.sub(r"N=\[(\s*\d+)\]", _n, hdr)
    hdr = re.sub(r"CHK=\[([0-9a-fA-F]+)\]", "CHK=[" + chk + "]", hdr)
    lines[0] = hdr
    return tekst_na_maz("\r\n".join(lines))


def znajdz_poligony(lines, typ=TYP_POLIGONU):
    """Zwraca listę poligonów danego typu z ich atrybutami A1/A2/A5/A6/TX."""
    obiekty = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("*") and ln[1:].split(" ")[0] == typ:
            k = blok_koniec(lines, i)

            def g(n):
                a = pobierz_atrybut(lines, i, k, n)
                return a["wartosc"] if a else ""

            obiekty.append({"start": i, "koniec": k,
                            "A1": g("A1"), "A2": g("A2"), "A4": g("A4"),
                            "A5": g("A5"), "A6": g("A6"), "TX": g("TX")})
            i = k
        else:
            i += 1
    return obiekty


# ------------------------------------------------- znaki czytelne w GEO-MAP

_OGONKI = {
    "ą": "a", "ć": "c", "ę": "e", "ł": "l", "ń": "n", "ó": "o", "ś": "s",
    "ź": "z", "ż": "z",
    "Ą": "A", "Ć": "C", "Ę": "E", "Ł": "L", "Ń": "N", "Ó": "O", "Ś": "S",
    "Ź": "Z", "Ż": "Z",
}


def bez_ogonkow(tekst):
    """Zamienia polskie znaki na czytelne litery (Ł->L, Ą->A, Ć->C ...).

    GEO-MAP nie wyświetla poprawnie Ł/Ó/Ą/Ę/Ć, więc opisy i litery piszemy
    zawsze bez ogonków.
    """
    if not tekst:
        return tekst
    return "".join(_OGONKI.get(ch, ch) for ch in tekst)


# ======================================================== reguły: MIETEK -> A2/A5

def optax_na_komorki(s):
    """Pole OP_TAX to siatka 7 komórek po 35 znaków (puste pomijane)."""
    s = s or ""
    cells = []
    for i in range(0, len(s), 35):
        if len(cells) >= 7:
            break
        cells.append(s[i:i + 35].rstrip())
    return [c for c in cells if c]


def rozbierz_segment(seg):
    """„8Ol" / „So/65-75/70l" / „3Brz" / „Halizna" -> składniki opisu."""
    seg = (seg or "").strip()
    if re.match(r"^halizna", seg, re.I):
        return {"specjalne": "halizna", "gat": ""}
    if re.match(r"^p[łl]azowina", seg, re.I):
        return {"specjalne": "plazowina", "gat": ""}
    if re.match(r"^d(rze)?stan|^drzewostan", seg, re.I):
        return {"specjalne": "drzewostan", "gat": ""}
    if re.match(r"^zaleg[łl]y", seg, re.I):
        return {"specjalne": "zrab", "gat": ""}
    m = RE_SEG.match(seg)
    if not m:
        pierwszy = re.split(r"[/;, ]", seg)[0] if seg else ""
        return {"udzial": "", "gat": pierwszy, "wiek": ""}
    return {"udzial": m.group(1) or "", "gat": m.group(2) or "",
            "wiek": m.group(5) or ""}


def _r_glowny(gat, r_recs):
    """Rekord elementu R dla gatunku głównego (albo pierwszy)."""
    for x in (r_recs or []):
        if _czysc(x.get("GATUNEK")) == gat:
            return x
    return (r_recs[0] if r_recs else {})


def zbuduj_a2_mietek(o_rec, r_recs):
    """A2 („Oznaczenie") z rekordu wydzielenia O i elementów R."""
    if not o_rec:
        return ""
    kom = optax_na_komorki(o_rec.get("OP_TAX"))
    seg = rozbierz_segment(kom[0] if kom else "")
    gat = seg.get("gat", "")
    r_gl = _r_glowny(gat, r_recs)
    spec = seg.get("specjalne")
    if spec == "halizna":
        return "Hal " + (_czysc(r_gl.get("GATUNEK")) or gat)
    if spec == "plazowina":
        return "Plaz"
    if spec in ("drzewostan", "zrab"):
        gat = _czysc(r_gl.get("GATUNEK"))
    wiek = _czysc(r_gl.get("WIEK")) or seg.get("wiek", "")
    bon = _czysc(r_gl.get("BONIT"))
    zad = _czysc(r_gl.get("ZADRZEW"))
    ogon = ("|%s-%s" % (bon, zad)) if (bon or zad) else ""
    return (seg.get("udzial", "") or "") + gat + str(wiek) + ogon


def zbuduj_a5_mietek(o_rec, prefix="", sep=";"):
    """A5 („Opis taks.") z pola OP_TAX (komórki 35-znakowe)."""
    if not o_rec:
        return ""
    kom = optax_na_komorki(o_rec.get("OP_TAX"))
    seg = [re.sub(r"\s*;\s*", ",", c).strip() for c in kom]
    seg = [c for c in seg if c]
    if not seg:
        return ""
    return (prefix or "") + (sep or ";").join(seg)


def _fmt_licz(v):
    v = float(v)
    return str(int(v)) if v.is_integer() else ("%g" % v)


def _rec_glowny_mietek(o_rec, r_recs):
    """Rekord R gatunku panującego (jak w A2)."""
    kom = optax_na_komorki((o_rec or {}).get("OP_TAX"))
    seg = rozbierz_segment(kom[0] if kom else "")
    return _r_glowny(seg.get("gat", ""), r_recs)


def zbuduj_wskazania(rec):
    """A4 („Wskazania") z rekordu R: pola WSK1..WSK6.

    Format: „#KW=1;” + elementy „<WSK>-<MIAZ>m3/ha” (gdy miąższość > 0) albo
    „<WSK>-<POW>%”, rozdzielone „;”, z końcowym „;” — np.
    „#KW=1;Rb I-100%;Magr.oczyś-100%;Odn.-100%;Piel.-100%;”.
    """
    if not rec:
        return ""
    czesci = []
    for i in range(1, 7):
        w = _czysc(rec.get("WSK%d" % i))
        if not w:
            continue
        try:
            miaz = float(rec.get("MIAZ%d" % i) or 0)
        except (TypeError, ValueError):
            miaz = 0.0
        try:
            pow_ = float(rec.get("POW_WSK%d" % i) or 0)
        except (TypeError, ValueError):
            pow_ = 0.0
        if miaz > 0:
            czesci.append("%s-%sm3/ha" % (w, _fmt_licz(miaz)))
        else:
            czesci.append("%s-%s%%" % (w, _fmt_licz(pow_)))
    if not czesci:
        return ""
    return "#KW=1;" + ";".join(czesci) + ";"


# ======================================================== reguły: EXCEL -> A2/A5

def kol_na_indeks(kol):
    """Litera kolumny („A", „N", „AA") -> indeks 0-based (albo None)."""
    kol = (kol or "").strip().upper()
    if not kol:
        return None
    n = 0
    for ch in kol:
        if not ("A" <= ch <= "Z"):
            return None
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _kol(row, idx, nazwa):
    i = idx.get(nazwa)
    if i is None or i >= len(row) or row[i] is None:
        return ""
    return _czysc(row[i])


def zbuduj_a2_excel(row, idx):
    """A2 z wiersza arkusza Forestly GO (nagłówki: sklad, wiek_przec, bon...)."""
    sklad = _kol(row, idx, "sklad")
    gat, udzial = "", ""
    if sklad:
        pierwszy = re.split(r"[;,]", sklad)[0].strip()
        m = RE_GAT_EXCEL.match(pierwszy)
        if m:
            udzial, gat = m.group(1) or "", m.group(2) or ""
        else:
            gat = pierwszy
    if not gat:
        gat = _kol(row, idx, "gatunek")
    wiek = _kol(row, idx, "wiek_przec") or _kol(row, idx, "wiek")
    bon = _kol(row, idx, "bon")
    zad = _kol(row, idx, "zad")
    if _kol(row, idx, "siedlisko").lower().startswith("hal") and not gat:
        return ""
    ogon = ("|%s-%s" % (bon, zad)) if (bon or zad) else ""
    return udzial + gat + wiek + ogon


def zbuduj_a5_excel(row, idx, prefix="", sep=";"):
    """A5 z kolumny „opis_gotowy" arkusza Forestly GO."""
    opis = _kol(row, idx, "opis_gotowy")
    if not opis:
        return ""
    linie = [s.strip() for s in re.split(r"\r\n|\r|\n", opis) if s.strip()]
    return (prefix or "") + (sep or ";").join(linie)


# ============================================================ XLSX: czytanie

def czytaj_xlsx(path):
    """Pierwszy arkusz -> {'naglowki': [...], 'wiersze': [[...], ...]}."""
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    if not rows:
        return {"naglowki": [], "wiersze": []}
    naglowki = [("" if h is None else str(h).strip()) for h in rows[0]]
    wiersze = [list(r) for r in rows[1:]]
    return {"naglowki": naglowki, "wiersze": wiersze}


def indeks_kolumn(naglowki):
    """Mapa nazwa nagłówka -> indeks kolumny (pierwsze wystąpienie)."""
    idx = {}
    for i, h in enumerate(naglowki):
        h = (h or "").strip()
        if h and h not in idx:
            idx[h] = i
    return idx


# ============================================================ złożenie wierszy

def zbuduj_wiersze(mapa, tryb, zrodlo, klucz="TX", kol_nr="N", pominiete=None):
    """Zwraca listę wierszy podglądu dla jednej mapy.

    mapa   — wynik wczytaj_mape()
    tryb   — "excel" albo "mietek"
    zrodlo — dla "excel": wynik czytaj_xlsx(); dla "mietek": {'obO':..., 'rby':...}
    klucz  — pole mapy z numerem porządkowym (tryb excel)
    kol_nr — litera kolumny z numerem porządkowym w arkuszu (tryb excel)
    """
    from app.core import zamiany_opisow as _zam
    zamiany = _zam.wczytaj()
    obiekty = znajdz_poligony(mapa["lines"])
    klucz = (klucz or "TX").strip().upper()
    wiersze = []
    i_nr = kol_na_indeks(kol_nr) if tryb == "excel" else None
    idx = indeks_kolumn(zrodlo["naglowki"]) if tryb == "excel" else {}

    for o in obiekty:
        # obiekty 5310 bez oznaczenia wydzielenia (np. kontenery granic) pomijamy
        if not (o.get("A1", "").strip() or o.get("A6", "").strip()):
            if pominiete is not None:
                pominiete.append(o)
            continue
        wydz = o.get("A6") or o.get("A1") or ""
        obecne_a2 = o.get("A2", "")
        r = {"wydz": wydz, "numer": "", "obecneA2": obecne_a2,
             "obecneA4": o.get("A4", ""), "obecneA5": o.get("A5", ""),
             "noweA2": "", "noweA4": "", "noweA5": "",
             "status": "", "ok": False, "o": o}

        if tryb == "excel":
            r["numer"] = o.get(klucz, "")
            row = None
            if i_nr is not None:
                cel = _czysc(r["numer"])
                for w in zrodlo["wiersze"]:
                    v = w[i_nr] if i_nr < len(w) else None
                    if v is not None and _czysc(v).replace(".0", "") == cel.replace(".0", ""):
                        row = w
                        break
            if row is not None:
                r["ok"] = True
                r["noweA2"] = zbuduj_a2_excel(row, idx)
                r["noweA5"] = zbuduj_a5_excel(row, idx, "#KW=1;", ";")
                r["status"] = "dopasowano"
            else:
                r["status"] = "brak numeru w arkuszu"
        else:
            r["numer"] = wydz
            o_rec = (zrodlo["obO"].get(wydz)
                     or zrodlo["obO"].get(o.get("A1", "")))
            if o_rec:
                r["ok"] = True
                key = _czysc(o_rec.get("ODDZIAL")) + _czysc(o_rec.get("PODODDZ"))
                r_recs = zrodlo["rby"].get(key, [])
                r["noweA2"] = zbuduj_a2_mietek(o_rec, r_recs)
                r["noweA5"] = zbuduj_a5_mietek(o_rec, "#KW=1;", ";")
                r["noweA4"] = zbuduj_wskazania(_rec_glowny_mietek(o_rec, r_recs))
                r["status"] = "dopasowano (%s)" % key
            else:
                r["status"] = "brak wydzielenia w MIETKU"
        if r["ok"]:
            # słownik zamian użytkownika („zapamiętać?" z tabeli braków)
            r["noweA2"] = _zam.zastosuj(r["noweA2"], zamiany)
            r["noweA5"] = _zam.zastosuj(r["noweA5"], zamiany)
        wiersze.append(r)
    return wiersze


def litera_z_oznaczenia(ozn):
    """„1m" -> „m", „2dx" -> „dx" — usuwa wiodącą liczbę oddziału."""
    s = (ozn or "").strip()
    m = re.match(r"^(\d+)(.*)$", s)
    return m.group(2) if m else s


def wpisz_do_mapy(mapa, wiersze, a2=True, a5=True, a1=True, a4=True,
                  obrot_srodek=None, tylko_opisy=True, prog_dalekiego=500.0):
    """Wpisuje opisy dopasowanych wierszy do mapy (od końca).

    A2/A4/A5 — z reguły; A1 — litera wydzielenia wyprowadzona z A6
    (np. A6 „1m” -> A1 „m”; A6 zostaje bez zmian).
    Zwraca (liczba_zmian, bajty_wyniku). Oryginalne wiersze mapy są kopiowane,
    więc można bezpiecznie odrzucić wynik bez zapisu.
    """
    lines = list(mapa["lines"])
    zmienione = 0
    do_zmiany = [w for w in wiersze if w["ok"]]
    do_zmiany.sort(key=lambda w: w["o"]["start"], reverse=True)
    for w in do_zmiany:
        start = w["o"]["start"]
        o = w["o"]
        if a5 and w["noweA5"] and w["noweA5"] != (o.get("A5") or "").strip():
            k5 = blok_koniec(lines, start)
            ustaw_atrybut(lines, start, k5, "A5", w["noweA5"])
            zmienione += 1
        if a4 and w.get("noweA4") and w["noweA4"] != (o.get("A4") or "").strip():
            k4 = blok_koniec(lines, start)
            ustaw_atrybut(lines, start, k4, "A4", w["noweA4"])
            zmienione += 1
        if a2 and w["noweA2"] and w["noweA2"] != (o.get("A2") or "").strip():
            k2 = blok_koniec(lines, start)
            ustaw_atrybut(lines, start, k2, "A2", w["noweA2"])
            zmienione += 1
        if a1:
            a6 = (o.get("A6") or "").strip()
            if a6:
                lit = litera_z_oznaczenia(a6)
                if (o.get("A1") or "").strip() != lit:
                    k1 = blok_koniec(lines, start)
                    ustaw_atrybut(lines, start, k1, "A1", lit, zaraz_po="ID")
                    zmienione += 1
    if obrot_srodek is not None:
        # wyśrodkuj i obróć opisy (tryb „na razie") zaraz po wpisaniu
        try:
            from app.core import uklad_opisow as _uk
            m2 = {"path": mapa["path"], "raw": b"", "lines": lines}
            el = _uk.uloz(m2, obrot=obrot_srodek, tylko_srodek=True,
                          tylko_opisy=tylko_opisy, prog_dalekiego=prog_dalekiego)
            if el:
                lines, _ = _uk.ustaw_offsety(m2, el, obrot_rad=obrot_srodek)
        except Exception:
            pass
    return zmienione, przelicz_naglowek(lines)


def zapisz_mape(mapa, out_dir, a2=True, a5=True, wiersze=None, a1=True, a4=True,
                obrot_srodek=None, tylko_opisy=True, prog_dalekiego=500.0):
    """Zapisuje mapę wynikową „<NAZWA>_z_opisami.MAP" do out_dir.

    Zwraca słownik z podsumowaniem (nazwa, ścieżka, zmiany, dopasowania).
    """
    if wiersze is None:
        wiersze = []
    zmiany, out = wpisz_do_mapy(mapa, wiersze, a2=a2, a5=a5, a1=a1, a4=a4,
                                obrot_srodek=obrot_srodek,
                                tylko_opisy=tylko_opisy,
                                prog_dalekiego=prog_dalekiego)
    nazwa = re.sub(r"\.map$", "", mapa["path"].name, flags=re.I) + "_z_opisami.MAP"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cel = out_dir / nazwa
    cel.write_bytes(out)
    return {"nazwa": nazwa, "sciezka": cel, "zmiany": zmiany,
            "poligonow": len(wiersze),
            "dopasowano": sum(1 for w in wiersze if w["ok"])}


# ============================================================ tester reguły

def _norm_tekst(s):
    """Do porównań: bez zbędnych spacji, wielkość liter bez znaczenia."""
    return re.sub(r"\s+", " ", (s or "").strip()).upper()


def _fold_diakrytyki(s):
    """Usuwa ogonki (ł->l, ą->a itd.)."""
    s = (s or "").replace("ł", "l").replace("Ł", "L")
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def _loose(s):
    """Tylko znaki alfanumeryczne, bez ogonków, małe litery."""
    return re.sub(r"[^a-z0-9]+", "", _fold_diakrytyki(s).lower())


def _sep_norm(s):
    """Traktuje interpunkcję i spacje jako ten sam separator."""
    return re.sub(r"\s+", " ", re.sub(r"[;,:.\-]", " ", s or "")).strip()


def _pojedynczy_znak_techniczny(a, b):
    """Czy różnica to dokładnie jeden znak, przy czym któryś jest „techniczny”."""
    import difflib
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    zmiany = 0
    techniczny = False
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        d1, d2 = a[i1:i2], b[j1:j2]
        zmiany += max(len(d1), len(d2))
        for ch in d1 + d2:
            if not ch.isalnum():
                techniczny = True
    return zmiany == 1 and techniczny


def klasyfikuj_roznice(obecne, nowe):
    """Rozróżnia rozbieżność merytoryczną od drobnych różnic.

    Zwraca jedną z etykiet:
      zgodne | spacje | interpunkcja | wielkość liter | literówka | rozbieżność
    """
    a = (obecne or "").strip()
    b = (nowe or "").strip()
    if a == b:
        return "zgodne"
    if re.sub(r"\s+", " ", a) == re.sub(r"\s+", " ", b):
        return "spacje"
    if _sep_norm(a) == _sep_norm(b):
        return "interpunkcja"
    if _sep_norm(a).lower() == _sep_norm(b).lower():
        return "wielkość liter"
    if _loose(a) == _loose(b):
        return "literówka"
    if _pojedynczy_znak_techniczny(a, b):
        return "literówka"
    return "rozbieżność"


KATEGORIE_DROBNE = ("spacje", "interpunkcja", "wielkość liter", "literówka")


def podsumuj_test(wiersze, pole="A2"):
    """Porównuje wynik reguły (nowe) z tym, co JEST w mapie (obecne).

    pole = "A2" albo "A5". Zwraca liczniki wg kategorii i listę różnic.
    """
    kat = {"zgodne": 0, "spacje": 0, "interpunkcja": 0, "wielkość liter": 0,
           "literówka": 0, "rozbieżność": 0}
    niedopasowane = puste = 0
    rozb = []
    for w in wiersze:
        if not w.get("ok"):
            niedopasowane += 1
            continue
        nowe = w.get("noweA2" if pole == "A2" else "noweA5", "") or ""
        obec = w.get("obecneA2" if pole == "A2" else "obecneA5", "") or ""
        if not obec.strip():
            puste += 1
            continue
        k = klasyfikuj_roznice(obec, nowe)
        kat[k] += 1
        if k != "zgodne":
            rozb.append({"wydz": w.get("wydz", ""), "numer": w.get("numer", ""),
                         "pole": pole, "obecne": obec, "nowe": nowe,
                         "rodzaj": k, "status": w.get("status", "")})
    rozbiezne = sum(v for kk, v in kat.items() if kk != "zgodne")
    return {"pole": pole, "kategorie": kat, "zgodne": kat["zgodne"],
            "rozbiezne": rozbiezne, "niedopasowane": niedopasowane,
            "puste": puste, "rozbieznosci": rozb, "razem": len(wiersze)}


def waga_pozycji(typ):
    """Waga pozycji w tabeli braków: serious / minor / info."""
    if typ in ("rozbieżność", "brak wydzielenia", "brak w źródle"):
        return "serious"
    if typ in KATEGORIE_DROBNE:
        return "minor"
    return "info"          # brak opisu


def braki_do_przegladu(nazwa_mapy, wiersze, a2=True, a5=True):
    """Lista pozycji do uzupełnienia / sprawdzenia przed wpisaniem opisów.

    typ: brak wydzielenia | rozbieżność | literówka | interpunkcja | spacje |
         wielkość liter | brak opisu | brak w źródle
    """
    rows = []
    for w in wiersze:
        wydz = w.get("wydz", "")
        if not w.get("ok"):
            rows.append({"mapa": nazwa_mapy, "wydz": wydz, "pole": "—",
                         "typ": "brak wydzielenia", "waga": "serious",
                         "obecne": "", "nowe": "", "status": w.get("status", "")})
            continue
        for pole, on in (("A2", a2), ("A5", a5)):
            if not on:
                continue
            nowe = (w.get("noweA2" if pole == "A2" else "noweA5", "") or "").strip()
            obec = (w.get("obecneA2" if pole == "A2" else "obecneA5", "") or "").strip()
            if not nowe and not obec:
                typ = "brak opisu"
            elif not nowe and obec:
                typ = "brak w źródle"
            elif nowe and not obec:
                continue            # zostanie uzupełnione przy wpisywaniu
            else:
                typ = klasyfikuj_roznice(obec, nowe)
                if typ == "zgodne":
                    continue
            rows.append({"mapa": nazwa_mapy, "wydz": wydz, "pole": pole,
                         "typ": typ, "waga": waga_pozycji(typ),
                         "obecne": obec, "nowe": nowe,
                         "status": w.get("status", "")})
    return rows


def podsumuj_braki(rows):
    """Liczniki braków wg typu."""
    s = {}
    for r in rows:
        s[r["typ"]] = s.get(r["typ"], 0) + 1
    return s
