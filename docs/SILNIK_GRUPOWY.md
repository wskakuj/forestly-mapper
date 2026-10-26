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

## Regresja 3h — generator zewnętrzny, próba 4c

W raporcie `byslaw_3h_etap4b.json` po odblokowaniu wnętrz sąsiednich
poligonów nie było poprawy: 0 przesuniętych napisów, 0 udanych grup,
pozostały dwa problemy `3h`. Analiza rzeczywistej geometrii pokazała,
że w dotychczasowych 80 próbkach na każdy rodzaj napisu dla opisu
przechodziły test granic tylko cztery pozycje, ale każda nachodziła na
inny napis. To nie dowodzi braku miejsca: po rozszerzeniu próbek
wzdłuż krawędzi i odległości proporcjonalnych do wysokości etykiety
udało się wskazać wolną pozycję z możliwym prostym wysięgnikiem
(w niezależnej kontroli geometrycznej, nadal do potwierdzenia solverem).
Warianty nie używają na sztywno nazw, UUID ani współrzędnych BYSŁAW.

Diagnostyka pozwala teraz sprawdzić etap eliminacji wariantów
(`--sprawdz-warianty`, wymaga `--etykiety`):

```cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 3h --maks-grupa 3 --wiazka 12 --przebiegi 1 --sprawdz-warianty --json "byslaw_3h_etap4c.json"
```

Raport `diagnostyka_wariantow` zawiera: liczbę generowanych pozycji
wewnętrznych i zewnętrznych, liczbę kompletnych konfiguracji dla
wydzielenia oraz liczbę takich konfiguracji, które nie kolidują
z pozostałymi oryginalnymi napisami. To ograniczona próbka do 24
wariantów na grupę, nie dowód optymalności i nie zamiennik sprawdzenia
wyglądu w GEO-MAP. Plik wejściowy .MAP jest tylko odczytywany.


## Diagnoza 3h — fałszywa granica z otwartej polilinii (etap 4D)

Raport `byslaw_3h_etap4c.json`: 48 zewnętrznych kandydatów
litery, 11 dla opisu, **zero wewnętrznych** dla obu;
24 plany `litera+opis`, żaden zgodny z otoczeniem. Mapa bez zmian.

Przy weryfikacji rzeczywistej `01_BYSŁAW_z_opisami.MAP`
odkryto, że indeks `Granice` bezwarunkowo domykał każdą
geometrię przez ostatni->pierwszy wierzchołek. Otwarte polilinie
`*4214` NIE są poligonami. W szczególności obiekt
`96EDF087-1AA4-49C7-AB10-759823916B05` miał
fikcyjne zamknięcie biegnące przez `3h`.
Sprawdzenie rzeczywistych segmentów źródła pokazało 4 wewnętrzne
położenia litery (siatka 9×9), z których żadne nie przecina
realnych linii mapy (na tym etapie jedynie badanie krawędzi).

**Poprawka uniwersalna:** indeks obsługuje teraz
`{"punkty": points, "zamkniety": bool}`; otwarte linie nie
otrzymują dodatkowego segmentu. Diagnostyka odczytuje
`zamkniety` z faktycznego zamknięcia w źródle GEO-MAP
(pierwszy wierzchołek równy ostatniemu).
Stare wywołania z samymi listami punktów pozostają
zgodne jako deklarowane poligony. Testy syntetyczne
sprawdzają brak fikcyjnego przekątnego odcinka.

Test po aktualizacji:

```cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 3h --maks-grupa 3 --wiazka 12 --przebiegi 1 --sprawdz-warianty --json "byslaw_3h_etap4d.json"
```

Oczekujemy większej liczby kandydatów wewnętrznych litery,
ale to nie jest jeszcze potwierdzenie pełnego rozwiązania:
walidator może odrzucić nadal wszystkie kompletne plany
z powodu innych napisów, wysięgników albo ograniczonej siatki.


## Etap 5A — podgląd wizualny przed/po (SVG)

Podgląd porównawczy jest **wyłącznie do odczytu**: wymaga źródłowego
GEO-MAP \`.MAP\` i istniejącego raportu \`.json\` z optymalizacji.
Otwiera oba pliki, odtwarza proponowane pozycje po identyfikatorach L2/L3,
rysuje je na wspólnym obszarze mapy w dwóch panelach (przed/po)
i tworzy **nowy** plik \`.svg\`, bez modyfikowania mapy. Nie generuje
ani nie nadpisuje \`.MAP\`. Plik wynikowy \`.svg\` również nie jest
nadpisywany — przy ponownym uruchomieniu użyj kolejnej nazwy.

Przykład w katalogu z mapą i raportem etapu 4D:

\`\`\`cmd
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_3h_etap4d.json" --etykiety 3h --svg "byslaw_3h_podglad.svg"
start "" "byslaw_3h_podglad.svg"
\`\`\`

Dla wielu sąsiednich wydzieleń można użyć \`--etykiety 4a 4b 4c\`,
podając raport optymalizacji, który zawiera zmiany dla tych wydzieleń.
\`--kontekst 60\` poszerza widoczny margines mapy w metrach.

- Kontury \`P 0\` są oddzielane, a otwarte polilinie pozostają otwarte;
  rysowane są także legalne przeszkody o **dwóch** wierzchołkach.
- Błękitny prostokąt to litera, pomarańczowy — opis; wysięgnik
  ma ten sam kolor co napis, z zaznaczonym punktem docelowym.
  Szare prostokąty to etykiety sąsiednich wydzieleń.
- Podgląd weryfikuje nazwę źródłowego MAP, liczbę napisów oraz
  pierwotne współrzędne **zmienionych** napisów; nie sprawdza
  kryptograficznej zgodności plików.
- Rysunki są wyłącznie poglądowe: font, jego wymiar i obrót są
  **szacowane**, a topologia wielokonturowych obiektów jeszcze
  nie jest kompletna. SVG nie jest formatem GEO-MAP.

**Brama przed eksportem:** sprawdzić układ na SVG, następnie poprawić
parser wielokonturowy i dopiero potem tworzyć eksperymentalne kopie MAP
do wizualnej weryfikacji w GEO-MAP. PR nie trafia do main bez testów.
