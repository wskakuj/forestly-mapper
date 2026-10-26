# Silnik grupowy — etap 4B (diagnostyka)

Nowy moduł `app/core/silnik_grupowy.py` jest niezależny od interfejsu oraz zapisu MAP.
Przyjmuje elementy w formacie `diagnostyka_map.elementy_z_mapy` i zwraca
`(nowe_elementy, raport)` bez zmiany wejścia. Opcjonalny argument
`wszystkie_poligony` powinien obejmować **wszystkie** granice mapy,
również obiekty bez etykiet.

Algorytm łączy:
- propozycje wewnętrzne z marginesem od granicy;
- zewnętrzne propozycje z czterech stron poligonu;
- prosty wysięgnik L2/L3, wspólny cel obu wysięgników wydzielenia;
- ograniczone przeszukiwanie grup bliskich wydzieleń (beam search);
- walidację wzajemnych przecięć, odrzucone kombinacje nie są zapisywane.

## Uruchomienie testów

```cmd
py -m unittest discover -s tests -v
```

Ten sam zestaw jest uruchamiany przez GitHub Actions na Windows i Ubuntu
dla PR (po synchronizacji nowej gałęzi).

## Diagnostyka BYSŁAW — całkowicie bez zapisu mapy

```cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --json "byslaw_silnik_grupowy.json"
```

`diag_silnik_grupowy.py` otwiera mapę tylko do odczytu i wykonuje symulację
położeń w pamięci. Do pliku zapisuje wyłącznie raport `.json`; odmawia
użycia pliku `.MAP` jako celu raportu. Raport zawiera statystyki problemów
sprzed i po symulacji, listę nowych pozycji oraz nierozwiązane kolizje.

**Bezpieczny profil startowy:** domyślnie rozpatrywane jest do 8 skupisk
(`--limit-grup 8`), `--wiazka 8`, `--maks-grupa 3`,
`--przebiegi 1`. Terminal pokazuje bieżący krok przed obliczeniami,
nie dopiero po ukończeniu całej mapy. Raport ma pola
`analiza_czesciowa`, `raport_silnika.rozpatrzone_grupy` i
`raport_silnika.pominiete_przez_limit`. Przy częściowej analizie
statystyki `po` obejmują całą mapę po modyfikacji tylko części grup,
nie są wynikiem pełnej optymalizacji.

Jeszcze mniejsza próbka dla dużej mapy:

```cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --limit-grup 2 --maks-grupa 2 --wiazka 4 --przebiegi 1 --json "byslaw_silnik_grupowy_probe.json"
```

Dopiero gdy próbka zadziała poprawnie, można zwiększać limit.
`--limit-grup 0` wyłącza ograniczenie (może być kosztowne).
Nie są dostępne jeszcze wyniki porównania z ręcznie ułożonym wzorcem.

## Ograniczenia i kolejne etapy

**Nie podłączamy jeszcze silnika do produkcyjnego GUI i nie generujemy MAP.**
Nie ma gwarancji znalezienia rozwiązania ani optymalności: siatka jest skończona,
liczba kandydatów i szerokość wiązki ograniczona, a font GEO-MAP szacowany.
Pomyślny wynik testów geometrycznych nie zastępuje kontroli w GEO-MAP.

Kolejny etap: analiza diagnostyki `3h`, `3g`, `3r` i całej mapy BYSŁAW,
poprawa ograniczonych przypadków, następnie transakcyjny eksporter L2/L3
z testami round-trip i bez nadpisywania oryginału.
