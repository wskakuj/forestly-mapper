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

## Raport nazewniczy A1/UUID — bez ponownego uruchamiania optymalizatora

Jeżeli diagnostyka wygenerowała już JSON, do wyszukania wydzieleń 3h,
3g i 3r wystarczy połączyć go z wejściową mapą (oba pliki czytane są
bez modyfikacji):

```cmd
py -m app.core.raport_etykiet "01_BYSŁAW_z_opisami.MAP" "byslaw_silnik_grupowy.json" --etykiety 3g 3h 3r
```

Skrypt wyświetla oryginalny A1 i A2, UUID, podział problemów
oraz liczbę zmienionych napisów i wysięgników. Bez filtra wypisze 15
najbardziej konfliktowych wydzieleń:

```cmd
py -m app.core.raport_etykiet "01_BYSŁAW_z_opisami.MAP" "byslaw_silnik_grupowy.json" --top 15
```

Raport musi pochodzić z mapy o tej samej nazwie i liczbie etykiet;
same te kontrole nie wykrywają każdej możliwej podmiany zawartości.

## Obserwacje z pierwszego, pełniejszego raportu BYSŁAW

Raport użytkownika przed aktualizacją profilowania: 416 etykiet
w 268 wydzieleniach, 2369 poligonów mapy. Liczba kolizji napisów
88 -> 70; napisów poza swoim poligonem bez wysięgnika 193 -> 124.
Sto pozycji etykiet uległo zmianie, z czego 35 zyskało wysięgnik.
Pięć wydzieleń ma dwa wysięgniki ze wspólnym punktem docelowym.
Największe przesunięcie napisu około 267 m — dlatego usunięto
sztuczne ucięcie kosztu przesunięcia po 100 m i zastosowano koszt
unormowany wysokością napisu. Te wyniki są z poprzedniej implementacji,
nie stanowią benchmarku nowej funkcji kosztu.

## Celowane przeliczenie skupisk (bez zapisu MAP)

Silnik potrafi ograniczyć **modyfikacje** do wskazanych etykiet A1, np.
`3h` lub `4a 4b 4c`, ale pozostałe napisy i krawędzie mapy nadal
traktuje jako przeszkody. Sąsiednie wydzielenia mogą być dodatkowo
przesuwane tylko jeśli mieszczą się w limicie `--maks-grupa` i są
niezbędne do wspólnego, bezkolizyjnego rozwiązania.

```cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 3h --maks-grupa 3 --wiazka 12 --przebiegi 1 --json "byslaw_3h_etap4.json"
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 4 --wiazka 12 --przebiegi 1 --json "byslaw_4abc_etap4.json"
```

W odróżnieniu od pierwszego raportu nowa funkcja diagnostyczna nazywa
postęp nazwą A1 i UUID. `wybrane_etykiety`, `wybrane_uuid`,
`pominiete_przez_wybor` i `analiza_czesciowa` odróżniają częściową
symulację od kompleksowej. Dla celowanego uruchomienia statystyki
`po` dotyczą całej mapy, lecz nie oznaczają, że pozostałe grupy
zostały zoptymalizowane.

Wybór sąsiednich grup jest adaptacyjny: algorytm najpierw sprawdza
samą docelową grupę, dopiero potem sąsiadów. Przy limitowaniu liczby
wariantów zachowuje reprezentację rozwiązań: wszystkie napisy w środku,
litera w środku z opisem na zewnątrz, opis w środku z literą na zewnątrz
oraz dwa napisy na zewnątrz ze wspólnym celem.

**Ograniczenie:** bez rzeczywistego pliku GEO-MAP i jego wizualnej
inspekcji nie jest możliwe potwierdzenie, że wydzielenia 3h lub 4a/b/c
zostały naprawione. Wynik algorytmu jest jedynie symulacją geometrii.

## Diagnoza rzeczywistego BYSŁAW — odblokowanie 3h

Po analizie oryginalnego pliku GEO-MAP `01_BYSŁAW_z_opisami.MAP`
wykryto ogólną blokadę generatora: wykluczał wszystkie pozycje
zewnętrzne, których środek znajdował się **w dowolnym poligonie**.
Nie wynika to z zasad rozmieszczenia. Pozycja może leżeć w pustym
wnętrzu innego poligonu, o ile prostokąt nie przecina żadnej granicy
ani etykiety, a wysięgnik jest prawidłowy.

Na 80 pozycjach proponowanych w każdym wariancie dla `3h`
szacunkowa próba geometrii mapy wykazała dla litery 54 kolizje z granicą
i 26 odrzuceń z powodu obcego wnętrza; dla opisu odpowiednio 76 i 4.
Żaden wariant nie pozostawał. Zmieniono ten filtr na kontrolę
**własnego poligonu**, zachowując walidację granic i wzajemnych
przecięć. Samo istnienie kandydatów nadal nie gwarantuje kompletnego
rozwiązania.

Ponadto w mapie wykryto 11 obiektów `5310` z wieloma konturami
zapisanymi liniami `P 0` (m.in. `4a` i `4c`). Dotychczasowy parser
scalał punkty w jeden obrys; jego wynik dla takiego obiektu **nie jest
wiarygodną topologią**. Diagnostyka raportuje
`wydzielenia_wielokonturowe` oraz `pelna_walidacja_topologii=false`.
Do czasu wdrożenia modelu wielokonturowego wyniki takich wydzieleń
nie powinny być eksportowane automatycznie.

Nowa kontrola tylko do odczytu:

```cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 3h --maks-grupa 3 --wiazka 12 --przebiegi 1 --json "byslaw_3h_etap4b.json"
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 4 --wiazka 12 --przebiegi 1 --json "byslaw_4abc_etap4b.json"
```
