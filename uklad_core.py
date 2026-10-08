"""Rdzeń programu: układanie opisów na mapach GEO-MAP (bez GUI)."""
import sys
import math
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core import opisy_na_mape as onm      # noqa: E402
from app.core import uklad_opisow as uk        # noqa: E402

WYSOKOSC_MM = 2.5
SKALA = 5000
P3 = -0.25


def statystyki(raw):
    """(w środku wydzielenia, z wysięgnikiem, ile opisów).

    Liczy tylko linie OPISÓW — czyli „L 3”, a gdy obiekt nie ma „L 3”,
    to „L 2” (tak jest w mapach, gdzie opis siedzi na L 2). Dzięki temu
    nie myli opisów z literami.
    """
    linie = raw.decode("cp1250", errors="replace").split("\r\n")
    wew = wys = razem = 0
    i, n = 0, len(linie)
    while i < n:
        if not linie[i].startswith("*"):
            i += 1
            continue
        j = i + 1
        while j < n and not linie[j].startswith("*"):
            j += 1
        blok = linie[i + 1:j]
        # opis = tekst A2 z „|” (np. „SO31|0.52”); litery i numery go nie mają
        a2 = next((l for l in blok if l.startswith(":A2[")), "")
        if "|" not in a2:
            i = j
            continue
        ma3 = any(l.startswith("L 3 ") for l in blok)
        opis = None
        for l in blok:
            if l.startswith("L 3 ") and ma3:
                opis = l
                break
            if l.startswith("L 2 ") and not ma3:
                opis = l
                break
        if opis:
            p = opis.split()
            razem += 1
            if len(p) >= 9:
                wys += 1
            elif p[-1] == "5":
                wew += 1
        i = j
    return wew, wys, razem


def uloz_plik(plik, mm=WYSOKOSC_MM, skala=SKALA, p3=P3, zapisz=True, log=None,
              podfolder="ułożone"):
    """Układa opisy w jednym pliku .MAP. Zwraca słownik z wynikiem."""
    def _log(s):
        if log is not None:
            log.append(s)

    plik = pathlib.Path(plik)
    _log("Algorytm: %s" % getattr(uk, "WERSJA_ALGORYTMU", "? (stary plik!)"))
    _log("Czytam: %s" % plik.name)
    mapa = onm.wczytaj_mape(plik)
    # Mapy po QGIS (opis w A2, bez linii „L 3”) też obsługujemy —
    # program sam dopisuje brakującą linię „L 3”, tak jak GEO-MAP.
    obrot = p3 * math.pi / 200.0
    _log("Układam (czcionka %s mm, skala 1:%s, obrót %s)…" % (mm, skala, p3))
    el = uk.uloz(mapa, wysokosc_mm=mm, skala=skala, obrot=obrot,
                 tylko_srodek=False)
    if uk.zatrzymano():
        _log("PRZERWANO (Stop) — ta mapa NIE została zapisana.")
        return {"ok": False, "zatrzymano": True, "opisow": 0, "wewnatrz": 0,
                "wysiegnik": 0, "error": "przerwano przez użytkownika"}
    if not el:
        _log("W tej mapie nie ma opisów do ułożenia — plik NIE został zmieniony.")
        _log("(Opisy to napisy w liniach „L 3”, np. „SO31|0.52”. Ta mapa ich nie ma.)")
        return {"ok": False, "opisow": 0, "wewnatrz": 0, "wysiegnik": 0,
                "error": "brak opisów do ułożenia (mapa nietknięta)"}
    nowe, zmiany = uk.ustaw_offsety(mapa, el, obrot_rad=obrot)
    raw = onm.przelicz_naglowek(nowe)
    wew, wys, razem = statystyki(raw)
    out = None
    if zapisz:
        # Wynik zapisujemy w podfolderze „ułożone” obok mapy wejściowej
        # (ten sam podfolder dla pliku i dla całego folderu).
        out_dir = plik.parent / podfolder
        out_dir.mkdir(parents=True, exist_ok=True)
        # nazwa pliku wynikowego z końcówką „_ulozone"
        out = out_dir / (plik.stem + "_ulozone.MAP")
        out.write_bytes(raw)
        _log("Zapisano: %s" % out)
    _log("Opisów: %d — w środku wydzielenia: %d, z wysięgnikiem: %d"
         % (razem, wew, wys))
    return {"ok": True, "wewnatrz": wew, "wysiegnik": wys, "opisow": razem,
            "zmiany": zmiany, "wynik": str(out) if out else "",
            "bajty": len(raw)}


def uloz_folder(folder, log=None, **kw):
    """Układa wszystkie mapy .MAP w folderze (także w podfolderach).

    Pomija tylko podfolder wynikowy „ułożone”. Bierze WSZYSTKIE pliki .MAP
    (także z „_ulozone” w nazwie — dawniej były pomijane i dlatego bywało
    „brak map”). Błąd jednej mapy nie przerywa całego folderu.
    """
    folder = pathlib.Path(folder)
    pliki = []
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.suffix.lower() != ".map":
            continue
        if "ułożone" in f.parts:      # pomiń folder wynikowy
            continue
        pliki.append(f)
    if log is not None:
        log.append("Znaleziono plików .MAP: %d (w: %s)" % (len(pliki), folder))
    wyniki = []
    for f in pliki:
        if uk.zatrzymano():
            if log is not None:
                log.append("PRZERWANO (Stop) — pozostałe mapy pominięte.")
            break
        try:
            wyniki.append(uloz_plik(f, log=log, **kw))
        except Exception as e:                              # noqa: BLE001
            if log is not None:
                log.append("  BŁĄD przy %s: %s" % (f.name, e))
            wyniki.append({"ok": False, "error": str(e), "opisow": 0,
                           "wewnatrz": 0, "wysiegnik": 0, "plik": f.name})
    return wyniki
