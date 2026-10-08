"""Forestly Mapper — układanie opisów na mapach GEO-MAP.

Osobny program z oknem (jak Forestly), ale niezależny od Forestly:
wczytuje .MAP (albo cały folder), układa opisy tym samym algorytmem
i zapisuje wynik w podfolderze „ułożone" obok wejścia.

Po spakowaniu przez PyInstaller ten plik staje się Forestly_Mapper.exe.
"""
import os
import sys
import pathlib
import threading
import traceback

# Gdy program działa jako EXE, PyInstaller rozpakowuje zasoby do _MEIPASS.
# Importujemy konfigurację z app.config (lekką — bez ciężkich bibliotek).
_KAT = pathlib.Path(__file__).resolve().parent
if str(_KAT) not in sys.path:
    sys.path.insert(0, str(_KAT))

try:
    from app import config as cfg
except Exception:                                    # noqa: BLE001
    cfg = None

ROOT = cfg.katalog_zasobow() if cfg else _KAT            # zasoby (ui.html)
PROGRAM = cfg.katalog_programu() if cfg else _KAT        # miejsce na log
NAZWA = cfg.APP_NAME if cfg else "Forestly Mapper"
TYTUL = cfg.APP_TITLE if cfg else "Forestly Mapper"
WERSJA = cfg.CURRENT_VERSION if cfg else "?"

try:
    import webview
except ImportError:
    print("Brak biblioteki pywebview. Zainstaluj:  python -m pip install pywebview")
    sys.exit(1)

import uklad_core as core      # noqa: E402


def _html():
    """Wczytuje interfejs (ui.html) leżący obok programu (albo w EXE)."""
    for nazwa in ("ui.html", "UI.HTML"):
        for baza in (ROOT, _KAT, PROGRAM):
            p = pathlib.Path(baza) / nazwa
            if p.exists():
                tekst = p.read_text(encoding="utf-8")
                tekst = (tekst.replace("{{NAZWA}}", NAZWA)
                              .replace("{{WERSJA}}", WERSJA)
                              .replace("{{TYTUL}}", TYTUL))
                return tekst
    raise FileNotFoundError("Brak pliku ui.html obok programu.")


class Api:
    def __init__(self):
        self._win = None
        # stan zadania „Opisy na mapę" (uruchamianego w tle)
        self._onm = {"running": False, "log": [], "idx": 0, "total": 0,
                     "plik": "", "wynik": None}

    def wersja(self):
        return WERSJA

    # ------------------------------------------------------ aktualizacje
    def sprawdz_aktualizacje(self):
        """Sprawdza najnowsze wydanie na GitHubie (wywoływane przy starcie
        i z przycisku „Sprawdź aktualizacje")."""
        try:
            from app import updater
            return updater.sprawdz()
        except Exception as e:                              # noqa: BLE001
            return {"ok": False, "blad": str(e), "obecna": WERSJA}

    def pobierz_aktualizacje(self, pliki, wersja, opis=""):
        """Pobiera i instaluje nową wersję, potem zamyka program
        (instalator czeka na zakończenie procesu i sam uruchamia nowy plik)."""
        try:
            from app import updater
        except Exception as e:                              # noqa: BLE001
            return {"ok": False, "blad": str(e)}
        pary = [(p[0], p[1]) for p in (pliki or []) if len(p) >= 2]
        ok, blad = updater.pobierz_i_zainstaluj(pary, wersja, opis)
        if not ok:
            return {"ok": False, "blad": blad}
        # zamykamy okno — instalator podmieni plik i uruchomi program od nowa
        try:
            if self._win is not None:
                self._win.destroy()
        except Exception:                                   # noqa: BLE001
            pass
        os._exit(0)

    def co_nowego(self):
        """Treść changelogu zapisana przez instalator (pokazywana po aktualizacji)."""
        try:
            from app import updater
            return updater.zjedz_pending_changelog(PROGRAM) or {}
        except Exception:                                   # noqa: BLE001
            return {}

    def otworz(self):
        """Wybór pliku .MAP. Filtr podajemy w kilku wariantach — różne wersje
        pywebview wymagają różnego zapisu, a gdy żaden nie przejdzie,
        otwieramy okno bez filtra (wtedy widać wszystkie pliki)."""
        warianty = [
            ("Mapy GEO-MAP (*.MAP;*.map)", "Wszystkie pliki (*.*)"),
            ("*.MAP;*.map", "Mapy GEO-MAP"),
            ("MAP files (*.map)",),
            None,
        ]
        r = None
        for ft in warianty:
            try:
                if ft is None:
                    r = self._win.create_file_dialog(webview.OPEN_DIALOG,
                                                     allow_multiple=False)
                else:
                    r = self._win.create_file_dialog(webview.OPEN_DIALOG,
                                                     allow_multiple=False,
                                                     file_types=ft)
                break
            except Exception:                        # noqa: BLE001
                r = None
        if not r:
            return ""
        return r[0] if isinstance(r, (list, tuple)) else r

    def otworz_folder(self):
        r = self._win.create_file_dialog(webview.FOLDER_DIALOG)
        if not r:
            return ""
        return r[0] if isinstance(r, (list, tuple)) else r

    def uloz(self, sciezka, skala=3500):
        """Uruchamia układanie w TLE — dzięki temu działa przycisk „Stop".

        Wynik i log odbiera się przez uloz_postep(). Stop: zatrzymaj().
        """
        if getattr(self, "_uloz_stan", {}).get("running"):
            return {"ok": False, "error": "układanie już trwa"}
        try:
            from app.core import uklad_opisow as _uk
            _uk.wyzeruj_zatrzymanie()
        except Exception:                                   # noqa: BLE001
            pass
        self._uloz_stan = {"running": True, "log": [], "wynik": None}

        def _run():
            try:
                w = self._uloz(sciezka, skala)
            except Exception as e:                          # noqa: BLE001
                w = {"ok": False, "error": str(e), "log": [str(e)]}
            self._uloz_stan["wynik"] = w
            self._uloz_stan["log"] = w.get("log", [])
            self._uloz_stan["running"] = False

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True, "started": True}

    def uloz_postep(self):
        """Stan układania: running, log, wynik."""
        return dict(getattr(self, "_uloz_stan", {"running": False}))

    def zatrzymaj(self):
        """Przycisk „Stop" — przerywa układanie po bieżącym kroku."""
        try:
            from app.core import uklad_opisow as _uk
            _uk.ZATRZYMAJ.set()
        except Exception:                                   # noqa: BLE001
            pass
        return {"ok": True}

    def _uloz(self, sciezka, skala=3500):
        """Układa opisy i ZAWSZE zapisuje wynik w podfolderze „ułożone"."""
        log = []
        try:
            skala = int(skala or 3500)
        except (TypeError, ValueError):
            skala = 3500
        try:
            p = pathlib.Path(sciezka)
            if p.is_dir():
                wyniki = core.uloz_folder(p, skala=skala, zapisz=True, log=log)
                ok = [w for w in wyniki if w.get("ok")]
                if not wyniki:
                    log.append("W tym folderze nie znalazłem żadnego pliku .MAP "
                               "(ani w podfolderach).")
                    return {"ok": False, "error": "nie znaleziono plików .MAP",
                            "log": log}
                if not ok:
                    log.append("Znalazłem %d plik(ów) .MAP, ale żadnego nie udało się "
                               "ułożyć — najczęściej brak opisów (znak |) do ułożenia."
                               % len(wyniki))
                    return {"ok": False, "error": "brak map z opisami do ułożenia",
                            "log": log}
                foldery = []
                for w in ok:
                    wv = w.get("wynik")
                    if wv:
                        foldery.append(str(pathlib.Path(wv).parent))
                folder = foldery[0] if foldery else ""
                return {"ok": True, "log": log, "ile_plikow": len(ok),
                        "folder": folder,
                        "opisow": sum(w["opisow"] for w in ok),
                        "wewnatrz": sum(w["wewnatrz"] for w in ok),
                        "wysiegnik": sum(w["wysiegnik"] for w in ok)}
            r = core.uloz_plik(p, skala=skala, zapisz=True, log=log)
            if r.get("ok") and r.get("wynik"):
                log.append("Zapisano w: %s" % r["wynik"])
                r["folder"] = str(pathlib.Path(r["wynik"]).parent)
            else:
                # nic nie zapisano — NIE otwieramy żadnego folderu
                r["folder"] = ""
                log.append("Nie zapisano żadnego pliku — mapa nie ma opisów "
                           "do ułożenia (brak napisów ze znakiem |) albo plik "
                           "jest uszkodzony.")
            r["log"] = log
            return r
        except Exception as e:                              # noqa: BLE001
            log.append("BŁĄD: %s" % e)
            return {"ok": False, "error": str(e), "log": log}

    def otworz_raport(self, sciezka):
        """Otwiera plik raportu (albo jego folder, gdy pliku brak)."""
        try:
            p = pathlib.Path(sciezka)
            if p.is_dir():
                p = p / "Opisy na mapę - raport.txt"
            if not p.exists():
                return {"ok": False, "error": "Nie znalazłem raportu."}
            if sys.platform == "win32":
                os.startfile(str(p))                        # noqa: S606
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(p)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(p)])
            return {"ok": True}
        except Exception as e:                              # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def otworz_folder_wynikow(self, sciezka):
        """Otwiera folder z plikami finalnymi w Eksploratorze systemowym."""
        try:
            p = pathlib.Path(sciezka)
            if p.is_file():
                p = p.parent
            if not p.exists():
                return {"ok": False, "error": "Folder nie istnieje."}
            if sys.platform == "win32":
                os.startfile(str(p))                        # noqa: S606
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", str(p)])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(p)])
            return {"ok": True}
        except Exception as e:                              # noqa: BLE001
            return {"ok": False, "error": str(e)}

    # ============================================== zakładka „Opisy na mapę"
    # filtry plików dla poszczególnych pól
    # filtry plików: pywebview oczekuje PAR (opis, rozszerzenia) — nie odwrotnie
    _ONM_FILTRY = {
        "mapy": (("Mapy GEO-MAP", "*.map"), ("Wszystkie pliki", "*.*")),
        "mietki": (("Bazy MIETEK (DBF)", "*.dbf"), ("Wszystkie pliki", "*.*")),
        "excel": (("Arkusze Excel", "*.xlsx;*.xls"), ("Wszystkie pliki", "*.*")),
        "mdb": (("Bazy Access", "*.mdb;*.accdb"), ("Wszystkie pliki", "*.*")),
    }

    def _onm_wybierz(self, rodzaj, jeden=False):
        """Wybór ścieżki. `jeden=True` → pojedynczy PLIK (jedna mapa),
        `jeden=False` → FOLDER (wiele map)."""
        if not jeden:
            return self.otworz_folder()
        # 1) z filtrem; 2) gdyby filtr nie zadziałał — okno bez filtra
        for ft in (self._ONM_FILTRY.get(rodzaj), None):
            try:
                if ft is None:
                    r = self._win.create_file_dialog(webview.OPEN_DIALOG,
                                                     allow_multiple=False)
                else:
                    r = self._win.create_file_dialog(webview.OPEN_DIALOG,
                                                     allow_multiple=False,
                                                     file_types=ft)
            except Exception:                               # noqa: BLE001
                continue                                    # filtr odrzucony — próbuj bez
            if r:
                return r[0] if isinstance(r, (list, tuple)) else r
            return ""                                       # anulowano
        return ""

    def onm_wybierz(self, rodzaj, jeden=False):
        return self._onm_wybierz(rodzaj, jeden)

    def _onm_start(self, u, funkcja):
        self._onm = {"running": True, "log": [], "idx": 0, "total": 0,
                     "plik": "", "wynik": None}

        def _run():
            try:
                from app.opisy_na_mape_service import SerwisOpisow
                s = SerwisOpisow(
                    log=lambda t: self._onm["log"].append(t),
                    postep=lambda i, t, f: self._onm.update(idx=i, total=t, plik=f))
                w = funkcja(s, u)
            except Exception as e:                          # noqa: BLE001
                w = {"ok": False, "blad": str(e)}
            self._onm["wynik"] = w
            self._onm["running"] = False

        threading.Thread(target=_run, daemon=True).start()
        return {"ok": True}

    def auto_uruchom(self, u):
        """PEŁEN AUTOMAT: najpierw zaczytuje opisy, potem układa je na mapach
        i zapisuje wynik w folderze „zaczytane i ułożone"."""
        return self._onm_start(u, lambda s, x: s.zaczytaj_i_uloz(x))

    def onm_uruchom(self, u):
        """Wpisuje opisy do map (w tle). Postęp przez onm_postep()."""
        return self._onm_start(u, lambda s, x: s.wpisz(x))

    def onm_sprawdz(self, u):
        """Sprawdza braki/różnice (w tle)."""
        return self._onm_start(u, lambda s, x: s.sprawdz(x))

    def onm_postep(self):
        """Stan zadania: running, log, idx/total/plik, wynik."""
        return dict(self._onm)


def main():
    api = Api()
    win = webview.create_window(TYTUL, html=_html(),
                                js_api=api, width=1100, height=760,
                                min_size=(860, 600))
    api._win = win
    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception:                                       # noqa: BLE001
        # przy uruchomieniu bez konsoli (pythonw / EXE) błąd zapisujemy do pliku
        try:
            (PROGRAM / "forestly_mapper_blad.log").write_text(
                traceback.format_exc(), encoding="utf-8")
        except Exception:                                   # noqa: BLE001
            pass
        raise
