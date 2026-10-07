"""Forestly — układanie opisów na mapach GEO-MAP.

Osobny program z oknem (jak Forestly), ale niezależny od Forestly:
wczytuje .MAP (albo cały folder), układa opisy tym samym algorytmem
i zapisuje wynik w podfolderze „ułożone” obok wejścia.
"""
import sys
import pathlib
import traceback

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    import webview
except ImportError:
    print("Brak biblioteki pywebview. Zainstaluj:  python -m pip install pywebview")
    sys.exit(1)

import uklad_core as core      # noqa: E402


def _html():
    """Wczytuje interfejs (ui.html) leżący obok programu."""
    for nazwa in ("ui.html", "UI.HTML"):
        p = ROOT / nazwa
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError("Brak pliku ui.html obok programu.")


class Api:
    def __init__(self):
        self._win = None

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
            except Exception:
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
        """Układa opisy i ZAWSZE zapisuje wynik w podfolderze „ułożone”."""
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
                return {"ok": True, "log": log, "ile_plikow": len(ok),
                        "opisow": sum(w["opisow"] for w in ok),
                        "wewnatrz": sum(w["wewnatrz"] for w in ok),
                        "wysiegnik": sum(w["wysiegnik"] for w in ok)}
            r = core.uloz_plik(p, skala=skala, zapisz=True, log=log)
            if r.get("ok") and r.get("wynik"):
                log.append("Zapisano w: %s" % r["wynik"])
            r["log"] = log
            return r
        except Exception as e:                              # noqa: BLE001
            log.append("BŁĄD: %s" % e)
            return {"ok": False, "error": str(e), "log": log}


def main():
    api = Api()
    win = webview.create_window("Forestly — układanie opisów", html=_html(),
                                js_api=api, width=1100, height=760,
                                min_size=(860, 600))
    api._win = win
    webview.start()


if __name__ == "__main__":
    try:
        main()
    except Exception:                                       # noqa: BLE001
        # przy uruchomieniu bez konsoli (pythonw) błąd zapisujemy do pliku
        try:
            (ROOT / "uklad_blad.log").write_text(traceback.format_exc(),
                                                 encoding="utf-8")
        except Exception:
            pass
        raise
