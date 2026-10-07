# Forestly Mapper

Program do **układania opisów na mapach GEO-MAP** (pliki `.MAP`). Wczytuje
pojedynczą mapę albo cały folder, układa opisy algorytmem Forestly i zapisuje
wynik w podfolderze **`ułożone`** obok pliku wejściowego. Okno programu jest
takie samo jak w Forestly (HTML + pywebview), a program działa niezależnie
od Forestly.

Wersja programu jest w `app/config.py` (pole `CURRENT_VERSION`).

---

## Co jest w środku

| Plik / folder | Do czego służy |
|---|---|
| `uklad_app.py` | program z oknem (punkt wejścia; po spakowaniu staje się EXE) |
| `uklad_core.py` | rdzeń: czytanie `.MAP`, układanie, zapis do `ułożone` |
| `ui.html` | interfejs okna (ciemny motyw jak w Forestly) |
| `app/core/` | algorytm układania (`uklad_opisow.py`, `opisy_na_mape.py`) |
| `app/config.py` | **numer wersji** i dane repozytorium |
| `forestly_mapper.ico` | ikona programu (i pliku EXE) |
| `release.py` / `release.bat` | wypuszczanie nowej wersji (dwuklik na `.bat`) |
| `utworz_repo.py` | jednorazowe założenie repo na GitHubie i pierwszy push |
| `.github/workflows/build.yml` | GitHub Actions — budują `Forestly_Mapper.exe` |
| `start.bat` / `start.vbs` | uruchomienie ze źródeł (bez okna cmd) |

---

## Uruchomienie ze źródeł (do prób)

1. Zainstaluj Pythona 3 (z python.org, zaznacz „Add Python to PATH”).
2. Dwuklik na `start.bat` — sam doinstaluje bibliotekę okna (pywebview)
   i uruchomi program.

## Uruchomienie gotowego EXE

Pobierz `Forestly_Mapper.exe` z zakładki **Releases** tego repozytorium.
Program jest jednoplikowy — wystarczy zapisać go gdziekolwiek i uruchomić.

---

## Pierwsze wydanie: założenie repo na GitHubie (raz)

1. Ustaw swoje konto w `app/config.py`:
   ```python
   GITHUB_USER = "twoja-nazwa"
   GITHUB_REPO = "forestly-mapper"
   ```
2. Uruchom:
   ```
   python utworz_repo.py
   ```
   Skrypt założy repo i wrzuci projekt. Obsługuje dwa sposoby logowania:
   - **GitHub CLI (`gh`)** — jeśli masz zainstalowane i zalogowane
     (`gh auth login`); najprościej,
   - **token (PAT)** — jeśli nie masz `gh`; utwórz token na
     https://github.com/settings/tokens (zakres „repo”).

   Skrypt nie zapisuje tokenu nigdzie — używa go tylko w tej sesji.
3. Na koniec skrypt ustawia tag `v1.0.0`, co **od razu uruchamia budowę EXE**.
   Po kilku minutach plik pojawi się w zakładce **Releases**.

## Kolejne wersje (za każdym razem)

Dwuklik na **`release.bat`** (albo `python release.py`). Kreator:

1. pokaże zmienione pliki,
2. zaproponuje numer wersji (z `app/config.py`; gdy tag zajęty — następny),
3. otworzy Notatnik na changelog,
4. zapisze zmiany, wypchnie je na GitHub, ustawi tag,
5. tag uruchamia Actions → budowa `Forestly_Mapper.exe` → nowy Release.

---

## Uwagi

- Wyniki układania zapisywane są **zawsze** w podfolderze `ułożone`
  (podfolder `ułożone` jest pomijany przy kolejnym przebiegu folderu).
- Skala układania ustawiana jest w oknie programu (domyślnie 1:3500).
- Plik `app/core/uklad_opisow.py` to algorytm układania — jego numer wersji
  (`WERSJA_ALGORYTMU`) widać w dzienniku programu przy każdym uruchomieniu.

---

## Aktualizacje (jak w Forestly)

Program sam sprawdza na GitHubie, czy jest nowsze wydanie:

- **przy starcie** — cicho sprawdza wersję; gdy jest nowsza, pokazuje okno
  „Dostępna aktualizacja!" z numerem wersji i listą zmian, i pyta, czy pobrać
  i zainstalować. Gdy program jest aktualny, pokazuje dyskretne potwierdzenie.
- **z przycisku „Sprawdź aktualizacje"** w nagłówku — sprawdza na żądanie.

Po kliknięciu „Pobierz i zainstaluj" program uruchamia graficzny instalator
(okno postępu), który: czeka na zamknięcie programu, pobiera nowy
`Forestly_Mapper.exe`, robi kopię starego pliku, podmienia go i **uruchamia
nową wersję**. Po aktualizacji pokazywany jest changelog („Co nowego").

Działa to **tylko w wersji .exe** — uruchomiony ze źródeł program tego nie zrobi.

> Uwaga: obecne wydanie v1.0.0 powstało PRZED dodaniem aktualizatora, więc samo
> się nie zaktualizuje. Wypuść raz nową wersję (`release.bat` → v1.0.1) — od
> niej wzwyż program będzie już sam proponował aktualizacje.

Pliki odpowiedzialne za to: `app/updater.py` (logika) oraz `ui.html` i
`uklad_app.py` (okno i przyciski).

---

## Zakładka „Zaczytywanie opisów"

Program ma dwie zakładki (u góry okna): **Układanie opisów** (opisana wyżej)
oraz **Zaczytywanie opisów** — przeniesiona z Forestly. Wpisuje opisy taksacyjne do
poligonów map GEO-MAP (pola **A1/A2/A5**) i zapisuje wynik jako
**`<NAZWA>_z_opisami.MAP`** obok mapy wejściowej (oryginał zostaje nietknięty).

Trzy źródła opisów (do wyboru):

| Źródło | Co wskazać | Dopasowanie |
|---|---|---|
| **Baza MIETEK** | folder z mietkiem albo pojedynczy plik DBF (pliki `O*.DBF`, `R*.DBF`) | wydzielenie z mapy (A1/A6) = wydzielenie w mietku |
| **Excel z Forestly GO** | folder z arkuszami `.xlsx` | numer porządkowy mapy (pole `TX`) = kolumna `N` arkusza |
| **Baza TAKSATORA** | plik `.mdb` | oddział i pododdział wydzielenia |

Przy każdym wyborze ścieżki program pyta najpierw, czy chodzi o **jedną mapę**
(plik) czy o **wiele map** (folder) — i otwiera odpowiednie okno.

Przyciski:
* **Wpisz opisy do map** — wpisuje opisy i od razu wyrównuje/obraca je na mapie
  (jak w programie układania), zapisuje mapę wynikową i raport
  `Opisy na mapę - raport.txt`;
* **Sprawdź braki** — pokazuje różnice (co jest na mapie, co daje reguła),
  zapisuje je do `Opisy na mapę - braki.csv`.

Uwaga: tryb **Baza TAKSATORA** w wersji EXE korzysta ze sterownika MS Access
(`pyodbc`); gdy go nie ma, jest zapasowy czytnik `access_parser`.
