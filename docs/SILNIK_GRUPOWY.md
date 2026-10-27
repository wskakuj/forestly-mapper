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


## Etap 5B — twarde cele wysięgników L2/L3

Zasady generatora **i** walidatora:
- oba napisy wewnątrz wydzielenia: nie generuj wysięgników;
- litera L2 wewnątrz, opis L3 na zewnątrz: opis musi mieć jeden
  prosty wysięgnik, który kończy się **na obwodzie prostokąta własnej
  litery**, po stronie zewnętrznego opisu; jedyny dopuszczalny kontakt
  z literą to jego punkt końcowy (linia nie przechodzi przez literę);
- litera L2 i opis L3 na zewnątrz: oba wysięgniki muszą wskazywać
  **dokładnie ten sam punkt wewnątrz własnego poligonu**;
- litera na zewnątrz, opis wewnątrz (nieobjęty nową szczególną zasadą):
  obowiązują dotychczasowe wymagania dla pojedynczego wysięgnika.

Przekroczenie któregokolwiek napisu przez wysięgnik nadal jest błędem;
walidator dopuszcza wyłącznie wskazane dotknięcie końca linii do
własnej litery i nie zmienia reguł dotyczących innych opisów,
wydzieleń ani przecinania odcinków. Zmieniono selekcję kandydatów:
dla opisu na zewnątrz i litery wewnątrz nie losujemy już punktów
w poligonie, a obliczamy kierunek z prostokąta litery do opisu i
jego przecięcie z obwodem litery. Obie etykiety na zewnątrz nadal
używają jednego wspólnego punktu docelowego.

**Walidacja regresyjna:** unit tests w GitHub Actions na Windows i
Ubuntu; obowiązkowy dodatkowy test na rzeczywistym 3h jest tylko
symulacją w pamięci i nie zmienia pliku MAP. Wystarczy zaktualizować
gałąź i wykonać:

\`\`\`cmd
py -m unittest discover -s tests -v
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 3h --maks-grupa 3 --wiazka 12 --przebiegi 1 --sprawdz-warianty --json "byslaw_3h_litera_cel.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_3h_litera_cel.json" --etykiety 3h --svg "byslaw_3h_litera_cel.svg"
\`\`\`

Plik SVG pokazuje odcinek do obwodu litery, a nie do jej środka,
oraz otaczające napisy. To **nie jest jeszcze dokładna wizualizacja
czcionek GEO-MAP**. Starszy \`proba_ukladu_v3.py\` zostaje jako
historyczny prototyp, nie jest źródłem docelowej reguły eksportu.

## Etap 6 — model wielokonturowych wydzieleń (P 0)

Nowy moduł `app/core/kontury_map.py` dzieli punktowe rekordy GEO-MAP
według zamknięcia `P 0`. Nie scala rozłącznych pierścieni ani
nie dopisuje krawędzi do otwartych polilinii. Osobny ostatni `P 0`,
który występuje **po** zamknięciu wcześniejszych konturów,
jest znacznikiem końca i **nie tworzy trzeciego pierścienia**.

W źródłowej mapie BYSŁAW jest 11 wydzieleń z takim wzorcem;
w szczególności `4a` i `4c` zawierają po **dwa rzeczywiste
zamknięte kontury**, choć po trzy linie `P 0`.
Znormalizowany model `poligon={"kontury":[...], "kompletne":true}`
jest teraz przekazywany przez `diagnostyka_map`, funkcje geometrii,
kandydatów i walidator. Zasada parzystości pierścieni:
rozłączne obszary są traktowane jak unia, wewnętrzny pierścień
jako dziura. Nie dopuszczamy prostokąta tekstu ponad segmentem
żadnego pierścienia; cel wysięgnika ma leżeć we wnętrzu
odpowiedniego wypełnionego obszaru.

Diagnostyka raportuje oddzielnie `liczba_poligonow` (liczba
obiektów wejściowych) i `liczba_fragmentow_granic` (faktyczne
kontury i otwarte odcinki), a także dla danego A1
`liczba_sekcji_p0` i `liczba_konturow`.
`wielokonturowe_w_modelu` wskazuje wdrożone wielopierścieniowe
wydzielenia. Dla mapy zawierającej wielokonturowe wydzielenia
`pelna_walidacja_topologii` pozostaje **false**: algorytm oparty
o parzystość potrzebuje jeszcze porównania z realnym
renderowaniem dziur, przecięć i warstw GEO-MAP. To świadomy
bezpiecznik przed pochopnym eksportem.

Regresje syntetyczne obejmują dwa oddzielne obszary, końcowy
samotny `P 0`, dziurę wewnętrzną, otwartą linię, generator
napisów i cały odczyt MAP bez nadpisywania.

Celowane sprawdzenie prawdziwej mapy bez eksportowania:

```cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 4 --wiazka 12 --przebiegi 1 --sprawdz-warianty --json "byslaw_4abc_kontury.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_kontury.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_kontury.svg"
```

Podgląd SVG zachowuje własne kontury już od poprzedniego etapu.


## Etap 6B — nienaprawione 4a i 4b na podglądzie SVG

Rzeczywisty raport \`byslaw_4abc_kontury.json\` miał 280 problemów
na całej mapie przed analizą i 273 po niej. Zmieniono **tylko dwa
napisy 4c** (L2 i L3), oba ze wspólnym wysięgnikiem w poligonie.
Wydzielenia \`4a\` i \`4b\` **nie zostały naprawione** — nachodzące
litery i opisy na planszy PO nie oznaczały nowo zaakceptowanej kolizji,
lecz pozostawienie pierwotnego nierozwiązanego układu. W diagnostyce
\`4a\` miało 0/24 planów wolnych wobec oryginalnego otoczenia;
\`4b\` miało 23/24, ale w miarę przechodzenia po UUID zmiana \`4c\`
mogła mu zablokować dostępne warianty.

Nie oznacza to, że poprawne pozycje na pewno nie istnieją.
Zmiana ogólna: iteruj najpierw po wydzieleniach o największej
liczbie zgłoszonych kolizji i problemów, zamiast arbitralnej
kolejności UUID. To heurystyka, a nie gwarancja naprawy:
raport nowego przebiegu trzeba sprawdzić osobno.

SVG pokazuje teraz nad każdą planszą wyraźne
\`NIEROZWIAZANE: 4a, 4b\` w przypadku problemów po symulacji
oraz status bez wykrytych problemów, jeśli celowe wydzielenia są
poprawne wg walidatora. Ulepszono również kontrast liter i opisów.
**Nadal nie zapisujemy MAP**.

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --sprawdz-warianty --json "byslaw_4abc_kolejnosc_v3.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_kolejnosc_v3.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_kolejnosc_v3.svg"
\`\`\`


## Etap 6C — wybór realnych blokerów i lokalne siatki konturów

Po teście \`byslaw_4abc_kolejnosc_v3.json\` nadal zmieniły się
tylko 2 napisy (L2/L3 \`4b\`); dla \`4a\` i \`4c\` pozostały konflikty.
W całej mapie liczba problemów spadła z 280 do 271, ale skan był
celowany i nie jest to miara ukończenia całej mapy.

Generator od tego etapu:
- przeszukuje każdy pierścień także w lokalnej siatce 7×7; jedna
  siatka na obrys całego wielokonturowego wydzielenia pomijała wąskie
  składniki oddalone od środka ogólnego bbox;
- rezerwuje w limicie 24 planów reprezentację różnych kierunków
  wyprowadzenia zewnętrznych napisów, nie tylko rodzaje strategii;
- zamiast dołączać jedynie najbliższe poligony, dla każdego planu
  identyfikuje faktycznie blokujące napisy i wysięgniki, a następnie
  próbuje w pierwszej kolejności wspólnie przesunąć **ich grupy**
  (w limicie \`--maks-grupa\`). Odległość sąsiadów pozostaje awaryjna.
  Nie zakłada, że bloker ma bliski geometrycznie poligon.

\`--sprawdz-warianty\` umieszcza dodatkowo w JSON:
\`minimalna_liczba_blokujacych_grup\`,
\`najczestsze_blokady\` (UUID + A1 + liczba zablokowanych planów),
\`przykladowe_minimalne_zestawy_blokad\`. Statystyki dotyczą
ograniczonego zbioru planów w otoczeniu wejściowym, nie wszystkich
teoretycznych położeń. Brak sukcesu nadal nie dowodzi braku miejsca.
Dodano regresje na wąski drugi kontur i odległy poligon, którego
przesunięty napis blokuje plan sąsiada. Źródłowy MAP nie jest zapisywany.

Próba na prawdziwym BYSŁAW:

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --sprawdz-warianty --json "byslaw_4abc_blokady_v4.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_blokady_v4.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_blokady_v4.svg"
\`\`\`


## Etap 6D — dokładne wspólne przeszukiwanie małego skupiska

Raport \`byslaw_4abc_blokady_v4.json\` wykazał 280 problemów przed
i 267 po przestawieniu czterech napisów: rozwiązał \`4b\`
i \`4c\`, ale \`4a\` pozostało nierozwiązane. Wszystkie 24
kandydaty \`4a\` były blokowane przez pierwotny układ \`4b\`,
a 17 również przez \`4c\`. To silna przesłanka, aby wybierać
pozycje trzech wydzieleń *równocześnie*, zamiast najpierw
zatwierdzać dwa łatwiejsze.

Dodano ogólną, deterministyczną próbę dokładną dla **2–3 jawnie
wybranych wydzieleń**, kiedy \`--maks-grupa\` i \`--limit-grup\`
zezwalają na objęcie ich wszystkich. Jej etapy:
- pobierz kandydatów wszystkich wskazanych wydzieleń, odrzuć
  te blokowane przez nieruchome napisy poza skupiskiem;
- przeszukaj wspólnie pozostałe konfiguracje z użyciem
  warunków geometrii, konfliktów prostokątów, wysięgników
  oraz dolnego ograniczenia kosztu;
- wybierz układ o najniższym koszcie spośród poprawnych
  **w ramach aktualnego zbioru kandydatów**;
- jeżeli brak kompletnej kombinacji, pozostaw układ bez
  zmian i uruchom dotychczasową optymalizację stopniową.

Ważne: dokładność dotyczy kombinacji **w obrębie 24
wygenerowanych planów na wydzielenie**, nie nieskończonej
przestrzeni pozycji. Nie ma gwarancji, że wszystkie trzy uda się
automatycznie rozmieścić. Wynik trafia do
\`raport_silnika.wspolna_proba\` wraz z liczbą planów po
odsianiu przeszkód i statusem \`sukces\`.

Tryb nie uruchamia się automatycznie na wszystkich 268
wydzieleniach i nie zmienia zachowania samodzielnej diagnostyki
\`3h\`. Żaden MAP nie jest zapisywany.

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --sprawdz-warianty --json "byslaw_4abc_wspolnie_v5.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_wspolnie_v5.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_wspolnie_v5.svg"
\`\`\`

Po wykonaniu porównaj \`wspolna_proba.sukces\` oraz statusy
\`NIEROZWIAZANE\` w SVG; same liczby problemów na całej mapie
nie są wystarczającym potwierdzeniem.


## Etap 6E — osobne obszary zewnętrzne i adaptacyjne poszukiwanie planów

Raport \`byslaw_4abc_wspolnie_v5.json\` wykazał
\`raport_silnika.wspolna_proba.sukces=false\`:
**wszystkie trzy wydzielenia miały po 24 plany
niekolizyjne z NIERUCHOMYM otoczeniem**, ale z tych list
nie istniała wspólna bezkolizyjna trójka. Fallback poprawił
\`4b\` i \`4c\` (4 napisy); \`4a\` nadal pozostało
niepoprawione. 280 → 267 problemów całej mapy.
Brak konfiguracji w ograniczonej puli NIE dowodzi braku miejsca.

Dwie poprawki o ogólnym znaczeniu:
1. Kandydaci **zewnętrzni** powstają wokół osobnego bbox
   każdego rzeczywistego konturu, nie tylko bbox wszystkich
   konturów razem. Kolejki globalne i lokalne są przeplatane,
   a walidacja nadal sprawdza własny poligon, pozostałe granice
   i napisy. Dla jednokonturowych obiektów zachowujemy
   dotychczasowy sposób próbkowania.
2. Wyłącznie dla jawnie wybranego skupiska 2–3 wydzieleń
   dokładny solver próbuje kolejno **24, 72, 112 planów** na
   wydzielenie. Szersze zestawy próbek reprezentują różne
   kierunki i dalsze odległości *zarówno litery, jak i opisu*.
   Przerwij przy pierwszym pełnym sukcesie, nie uruchamiaj
   droższych prób bez potrzeby. Dla diagnozy całej mapy lub
   pojedynczego wydzielenia te dodatkowe próby nie są
   uruchamiane.

Raport \`raport_silnika.wspolna_proba.proby\` zawiera
\`limit_planow_na_wydzielenie\`, liczbę planów pozostałych
po odrzuceniu nieruchomych przeszkód, \`sukces\` i
\`zgodne_pary_planow\` dla każdej pary grup. Zliczanie
zgodnych par wskazuje, **czy istnieje wzajemne dopasowanie
co najmniej dwóch grup**, zanim ocenimy kompletne układy
trójki. Nadal nie jest to dowód optymalności nad ciągłą
przestrzenią geometrii. Proszę zweryfikować czytelność
wyniku na SVG i następnie w GEO-MAP.

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --sprawdz-warianty --json "byslaw_4abc_adaptacja_v6.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_adaptacja_v6.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_adaptacja_v6.svg"
\`\`\`


## Etap 7 — estetyka pary L2/L3 i czytelność podglądu

W rzeczywistym teście \`byslaw_4abc_adaptacja_v6.json\` uzyskano
\`wspolna_proba.sukces=true\` już przy 24 wariantach na wydzielenie.
Przesunięto 6 napisów: \`4a\`, \`4b\` i \`4c\`; pozostałe zgłoszenia na
całej mapie spadły z 280 do 265. W SVG dla wybranych wydzieleń
brak wykrytych kolizji **według dotychczasowego walidatora**.

Mimo tego \`4a\` wygląda zbyt rozciągnięte: litera poza poligonem
poniżej innych obiektów, opis znacznie bardziej na lewo. Rozdzielamy
dwie warstwy jakości:
- **warunki twarde**: pełen prostokąt w poligonie bez wysięgnika,
  albo wymagany wysięgnik; nieprzecinanie się napisów; wspólny
  cel dla dwóch zewnętrznych napisów; cel opisu na literze, jeżeli
  ta jest wewnątrz; niezmieniona bezpieczna obsługa konturów;
- **ranking miękki**: istniejące kary za przesunięcie i długość
  wysięgnika oraz nowa kara za odległość pomiędzy prostokątami
  własnej litery L2 i opisu L3. Kara jest unormowana średnią
  wysokością prostokątów, największa gdy oba napisy są na zewnątrz,
  mniejsza gdy żaden nie wymaga wysięgnika. Dla pojedynczej etykiety
  koszt pozostaje bez zmian.

Zmiana nie obiecuje konkretnego krótszego rozwiązania: może istnieć
tylko jedna kompletna bezkolizyjna konfiguracja w ograniczonej
puli kandydatów. Bez dodatkowej weryfikacji rzeczywistego wyniku V7
nie należy twierdzić, że \`4a\` zostało estetycznie poprawione.

**SVG:** zawartość A2 zapisana jako \`tekst|pole\` jest pokazywana
w osobnych wierszach \`<tspan>\`, a pełny oryginalny tekst pozostaje
w \`data-full-text\` dla diagnostyki. Wysokość fontu dostosowana
do liczby wierszy; SVG nadal używa prostokątów przybliżonych, a nie
rzeczywistych fontów GEO-MAP.

**Granice walidacji:** raport \`pelna_walidacja_topologii=false\`
nadal obowiązuje, a podgląd \`Bez wykrytych kolizji\` dotyczy
modelowanych etykiet/wysięgników. Nie wolno z tego wyciągać wniosku,
że linie nie przecinają dodatkowych granic, dróg czy obiektów
kartograficznych, których przecięcia nie są jeszcze w pełni
walidowane. Brak automatycznego eksportu oryginału MAP.

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --sprawdz-warianty --json "byslaw_4abc_estetyka_v7.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_estetyka_v7.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_estetyka_v7.svg"
\`\`\`


## Etap V8 — rozszerzenie estetyki po pierwszym sukcesie

W rzeczywistym V7 \`byslaw_4abc_estetyka_v7.json\` wszystkie
6 prostokątów i wszystkie wysięgniki mają **identyczne współrzędne
jak V6**. Liczba problemów całej mapy pozostaje 280 → 265,
a dokładne wspólne przeszukiwanie \`wspolna_proba.sukces=true\`
zakończyło się już przy 24 wariantach. To pokazało, że sama
zmiana \`_koszt\` nie może poprawić estetyki, jeśli algorytm
kończy pracę po pierwszej poprawnej konfiguracji.

Teraz dla **jawnie wskazanej** grupy 2–3 wydzieleń:
- po pierwszym poprawnym rozwiązaniu obliczana jest maksymalna
  odległość prostokątów L2/L3 z **dwoma wysięgnikami**
  w średnich wysokościach napisów;
- jeśli przekracza 0,75 takiej wysokości, szukamy także w
  pulach 72 i maksymalnie 112; tylko w tych większych pulach
  generujemy *dodatkowo* opis tuż obok zewnętrznej litery
  (lewo, prawo, góra, dół) i weryfikujemy te propozycje
  tak samo jak inne warianty;
- przy każdym kroku wybieramy rozwiązanie o **niższym
  całkowitym koszcie**, nie ostatnie napotkane; brak nowego
  dobrego układu nie kasuje poprzedniego sukcesu;
- przy zwartym układzie albo zwykłej diagnostyce pojedynczego
  wydzielenia czy całej mapy dodatkowa praca się nie uruchamia.

Raport JSON zawiera \`wybrany_limit_planow\`,
\`koszt_wybranego_ukladu\`, \`maks_odstep_wybranego_ukladu\`,
a w \`wspolna_proba.proby\` także
\`koszt_znalezionego_ukladu\` oraz \`poprawiono_najlepszy\`.

**Uwaga:** zero kolizji L2/L3 w obecnym walidatorze **nie
oznacza pełnej walidacji mapy**: wielokonturowe obiekty,
dodatkowe granice i przejścia wysięgników przez obiekty
kartograficzne wciąż wymagają porównania z GEO-MAP.
Zmiana jest rankingiem/geometrią symulacji i nie eksportuje MAP.

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --sprawdz-warianty --json "byslaw_4abc_zwarte_v8.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_zwarte_v8.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_zwarte_v8.svg"
\`\`\`


## Etap V8B — odczyt rzeczywistych przecięć wysięgników z obiektami MAP

Analiza wyniku \`byslaw_4abc_zwarte_v8.json\` wykazała:
- rozwiązanie \`4a/4b/4c\` bez problemów *modelowanych* przez
  \`geometria_ukladu\`, z 280 → 265 zgłoszeniami na całej mapie;
- wybrana próba 72 wariantów ma koszt 858,05 (wcześniejsza
  próba 24 wariantów: 861,56), więc nastąpiła poprawa **funkcji
  kosztu**, a nie automatycznie wszystkich aspektów geometrii;
- \`4a\` ma prostokąty oddalone już o 5 m, ale dwa wysięgniki
  mają odpowiednio ok. 61,3 m i 70,3 m (wcześniej 20,8 i 50,2 m).
  Zwartość nie zastępuje wymagania rozsądnej długości linii.

Bezpieczna diagnostyka jest rozszerzona o pola:
- \`przeciecia_wysiegnikow_obiekty_mapy\` — dla każdego
  analizowanego wysięgnika: punkty przecięcia z liniowymi
  fragmentami obiektów GEO-MAP, rozpoznane rodzaje obiektów,
  czy punkt należy do granicy **własnego** wydzielenia,
  liczba dodatkowych punktów oraz współliniowe nakładanie;
- \`liczba_dodatkowych_przeciec_wysiegnikow\` — suma dodatkowych
  punktów, z pominięciem granicy własnego wydzielenia.

Ta sama linia na kilku warstwach GEO-MAP jest agregowana
**według współrzędnych rzeczywistego przecięcia** (0,01 jednostki),
zamiast fałszywego liczenia wielu oddzielnych problemów.
Przecięcia z własnym poligonem są oczekiwane, gdy dwa napisy
znajdują się na zewnątrz. Dodatkowe przecięcia nie stanowią
na razie automatycznego błędu: nie każda linia mapy (podział
geometryczny, droga, granica, warstwa kopiowana) powinna być
sztywną przeszkodą dla wysięgnika. Jest to **raport ostrzegawczy**,
który pozwoli wybrać reguły GIS przed pierwszym eksportem MAP.

Nowy raport uruchamia ta sama komenda diagnostyczna,
z kolejną nazwą pliku:

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --sprawdz-warianty --json "byslaw_4abc_przeciecia_v9.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_przeciecia_v9.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_przeciecia_v9.svg"
\`\`\`

To nadal wynik tylko diagnostyczny; źródłowe MAP i INI nie
są zapisywane ani zmieniane. \`pelna_walidacja_topologii=false\`
pozostaje prawidłowym, ostrożnym oznaczeniem.


## Etap V10 — miękka preferencja omijania obcych linii GEO-MAP

Raport V9 \`byslaw_4abc_przeciecia_v9.json\` potwierdza
**dwa dodatkowe punkty przecięcia**: wysięgnik litery \`4a\`
współrzędne (630301.90, 432710.05), opis \`4a\`
(630296.52, 432695.16). W obu punktach występują typy
obiektów \`*5214\` i \`*5216\`. Inne wysięgniki
\`4b\` i \`4c\` przecinają wyłącznie granicę własnego
wydzielenia (przecięcie dozwolone).
Na źródłowym MAP: \`*5214\` ma m.in. \`:A2[01 Bysław]\`,
a \`*5216\` \`:A2[209]\`. Nie ma przesłanek, by
na tym etapie ustalać automatyczny bezwzględny zakaz
przecinania wszystkich takich obiektów.

Zastosowano osobny przestrzenny indeks odcinków
\`app/core/przeciecia_map.py\`, używany przez diagnostykę
i opcjonalny scorer. Punkt na wielu warstwach liczy
się tylko raz. **Własna granica \`*5310\` nie podlega
karze**, zaś przecięcie innych linii lub nakładanie się
odcinków ma koszt zależny od parametru.

Nowy opcjonalny parametr CLI:
\`--kara-przeciecia 25\` — zwiększa łączny koszt
każdego planu o **25 punktów za dodatkowy fizyczny punkt
przecięcia** (oraz za nakładający się odcinek). Domyślnie
parametr wynosi \`0\`, a więc wcześniejszy układ
V9 pozostaje niezmieniony. Kara jest wyłącznie miękka,
nie zmienia reguł \`geo.waliduj_uklad\`.

Gdy kara jest dodatnia, uwzględnia się ją już przy
**generowaniu i rankingu wariantów** \`opcje_wydzielenia\`,
wspólnym solverze \`_wspolny_plan_dokladny\`,
koszcie wybieranym pomiędzy przebiegami 24/72/112
oraz w wiązkowym fallbacku. Jeśli zwarty plan nadal
ma naliczoną karę, wolno przeszukać szerszą pulę
112 zamiast kończyć przedwcześnie na 72. W raporcie:
\`kara_za_przeciecie\`, \`koszt_kary_wybranego_ukladu\`,
\`liczba_dodatkowych_przeciec_wysiegnikow\` i
\`przeciecia_wysiegnikow_obiekty_mapy\`.

**Bezpieczeństwo:** twarde zasady wysięgników pozostają
bez zmian; geometria oryginalnego MAP nie jest modyfikowana.
Jeśli zbiór kandydatów nie zawiera rozwiązania bez
dodatkowych przecięć, solver może nadal wybrać
wariant z przecinającymi liniami (miękka preferencja),
zamiast ukrywać problem. Pełna topologia nadal nie jest
zweryfikowana i należy porównać rezultat w GEO-MAP.

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --kara-przeciecia 25 --sprawdz-warianty --json "byslaw_4abc_miekkie_przeciecia_v10.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_miekkie_przeciecia_v10.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_miekkie_przeciecia_v10.svg"
\`\`\`


## Etap V11 — ograniczenie wielokrotnego przekraczania własnej granicy

Rzeczywisty test V10 \`byslaw_4abc_miekkie_przeciecia_v10.json\`
dał \`liczba_dodatkowych_przeciec_wysiegnikow=0\`,
a wszystkie \`4a/4b/4c\` nadal nie mają modelowanych kolizji
napisów (globalnie 280→265 problemów).
Jednakże obydwa wysięgniki \`4a\` **trzykrotnie** przecinają
własną granicę \`*5310\`: linie wchodzą w wydzielenie,
wychodzą z niego i wchodzą ponownie. Każdy wysięgnik
ma więc **2 nadmiarowe przekroczenia**, łącznie **4**.
To istotne, szczególnie dla wydzieleń o rozłącznych konturach
lub wewnętrznych pierścieniach. Sam brak przecięć obcych
warstw nie oznacza jeszcze poprawnego przebiegu wysięgnika.
Co więcej, wysięgnik opisu \`4a\` ma w V10 ok. 75,4 m
(V9: ok. 70,3 m); długości nie poprawiły się jednolicie.

Indeks przecięć zapisuje teraz dla każdej linii:
\`liczba_przeciec_wlasnej_granicy\` oraz
\`liczba_nadmiarowych_przeciec_wlasnej_granicy\`.
Za nadmiar uznaje się liczbę przecięć własnego obrysu ponad
pierwsze — przejście przez własną granicę przy prowadzeniu
linii z zewnątrz do jej wnętrza pozostaje dozwolone.
Wynik zbiorczy to
\`liczba_nadmiarowych_przeciec_wlasnej_granicy\`.

Nowa **opcjonalna, niezależna** kara:
\`--kara-wielokrotnej-granicy 50\`.
Wpisuje dodatkowe 50 punktów za każde nadmiarowe przecięcie.
Dla V10 (4 nadmiarowe punkty) zwiększyłaby koszt o 200.
Parametr \`--kara-przeciecia 25\` nadal osobno karze za
obce linie. Obie wartości domyślnie są 0 — starsze
polecenia i porównania pozostają zgodne. Obie kary są
**miękkie**, a nie zakazujące każdej kombinacji:
jeśli nie da się uniknąć wszystkich dodatkowych przecięć
w ograniczonej puli, raport nie zataja pozostałych.
Skan zawężony do 2–3 wydzieleń może przejść przez
24, 72 i 112 wariantów, gdy najlepsza propozycja nadal
ma niezerową karę kartograficzną.

Sugerowany cel porównania V11: 3/3 bez kolizji napisów,
liczba obcych przecięć **i** nadmiarowych przekroczeń
własnej granicy możliwie blisko zera oraz niepogorszone
długości wysięgników. Nowe testy kontrolują przypadek
dwóch rozłącznych pierścieni tego samego wydzielenia,
przeciętych przez jeden odcinek trzy razy. Oryginalny
MAP nadal nigdy nie jest modyfikowany.

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --kara-przeciecia 25 --kara-wielokrotnej-granicy 50 --sprawdz-warianty --json "byslaw_4abc_granice_v11.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_granice_v11.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_granice_v11.svg"
\`\`\`


## Etap V12 — widoczne punkty celowe wysięgników zamiast najbliższych dziewięciu

Rzeczywisty wynik \`byslaw_4abc_granice_v11.json\` wykazał:
- nadal \`3/3\` wydzielenia \`4a/4b/4c\` bez kolizji napisów
  wg modelu (\`280→265\` zgłoszeń na mapie);
- **zero** nadmiarowych przecięć własnych granic
  (w V10 były **cztery**, po dwa na wysięgnik \`4a\`);
- **dwa** dodatkowe przecięcia z liniami \`*5214/*5216\`
  w \`4a\`, które występowały już w V9; kara
  \`koszt_kary_wybranego_ukladu=50\`.
  Zewnętrzna litera \`4a\` miała wysięgnik ~61,3 m,
  opis ~70,3 m. Był to kompromis punktacji, a nie
  kompletne rozwiązanie kartograficzne.

Problem leżał także w ograniczonym **zbiorze punktów docelowych**:
dla dwóch napisów poza poligonem silnik wypróbowywał
zwykle 9 punktów najbliższych ich prostokątom. Istotny
punkt wewnątrz właściwej, wąskiej części wydzielenia
mógł nawet nie powstać w globalnej siatce \`bbox\`.

W V12 \`_cele\` w trybie rozszerzonym (siatka \`n>=9\`)
dla wielokonturowych wydzieleń dodaje lokalną siatkę
5×5 **każdego pierścienia** oraz kilka kandydatów
położonych tuż za jego krawędziami. Każdy punkt
przechodzi tę samą walidację wnętrza wielopierścieniowego
poligonu z marginesem 1,2 jednostki. Nie wydłużamy
globalnego przeszukiwania pojedynczych prostych działek.

Funkcja \`_cele_ocenione\` rozważa zróżnicowaną
pulę najbliższych i bardziej oddalonych celów.
Przy aktywnych kosztach GEO-MAP kolejność zależy
od długości projektowanego wysięgnika **oraz**
rzeczywistej kary z indeksu przecięć obcych linii
i wielokrotnych przejść przez własną granicę.
Bez włączonej opcjonalnej kary zachowuje wcześniejszy
sposób wybierania najbliższych celów.

Mechanizm jest ogólny dla grupy etykiet pojedynczych
i par \`L2/L3\`, także gdy dwa napisy poza wydzieleniem
wymagają **wspólnego punktu docelowego**. Reguły
bezkolizyjności i prostoliniowości pozostają twarde.
Nie ma gwarancji, że ograniczony zbiór kandydatów
zawiera konfigurację z zerową liczbą obu rodzajów
przecięć; wynik trzeba zweryfikować na prawdziwym MAP.

Test kontrolny bez zapisywania oryginału:

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --kara-przeciecia 25 --kara-wielokrotnej-granicy 50 --sprawdz-warianty --json "byslaw_4abc_cele_v12.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_cele_v12.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_cele_v12.svg"
\`\`\`


## Etap V13 — ochrona wariantów bez dodatkowych przecięć

Rzeczywisty test \`byslaw_4abc_cele_v12.json\` potwierdził:
- pełna wspólna optymalizacja \`4a/4b/4c\` daje 6 przesuniętych
  napisów, bez modelowanych konfliktów wewnątrz tej grupy;
- globalna liczba zgłoszeń pozostaje \`280→265\`;
- 2 dodatkowe przecięcia obcych linii (\`*5214/*5216\`)
  i 0 nadmiarowych przecięć własnych granic;
- wysięgniki \`4a\` skróciły się do ~57,4 m (litera)
  oraz ~65,6 m (opis), ale **oba obce przecięcia pozostały**;
- przebieg 72 kandydatów wybrano spośród trzech prób
  (24, 72, 112). Trzecia próba nie obniżyła kosztu.
  \`pelna_walidacja_topologii=false\`.

Analiza kodu ujawniła, że w limicie 72/112 reprezentacja
kandydatów była zapewniana według strategii i kierunku
(litera/opis oraz lewo/prawo/góra/dół), ale **nie ze względu
na koszt przecinania geometrii źródłowej**. Rzadki plan
z zerową karą GIS mógł zostać odrzucony, zanim
dokładny solver uzyskał szansę połączenia go z \`4b\`
i \`4c\`. Brak takiego planu w raporcie nie był więc
dowodem, że wygenerowane pozycje nie dawały czystej trasy.

W V13 przy włączonym \`--kara-przeciecia\` albo
\`--kara-wielokrotnej-granicy\` każda rozszerzona
rodzina kandydatów jest dodatkowo podzielona na:
- \`bez_kary_map\` — brak obu rodzajów dodatkowych przecięć;
- \`z_kara_map\` — co najmniej jedno ostrzeżenie w ramach
  aktualnych wag kar.

W ograniczonej puli zabezpieczane są reprezentanci
**obu** podgrup, jeśli istnieją. Koszt w dalszym ciągu
decyduje o wyborze spośród zgodnych pełnych planów.
Nie gwarantuje to układu z zerem przecięć: grupy
mogą być wzajemnie niezgodne, nawet jeśli pojedyncze
plany są czyste. Wyniki trzeba sprawdzić na rzeczywistej
mapie i w GEO-MAP. Klasyfikację planów obliczamy
raz na plan, aby nie mnożyć kosztownych zapytań
do indeksu geometrii.

Bez aktywnych dodatkowych kar zachowujemy klasyczną
selekcję według kierunku. Źródłowe MAP, INI
i \`main\` pozostają niezmienione.

\`\`\`cmd
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --etykiety 4a 4b 4c --maks-grupa 3 --wiazka 16 --przebiegi 2 --kara-przeciecia 25 --kara-wielokrotnej-granicy 50 --sprawdz-warianty --json "byslaw_4abc_czyste_warianty_v13.json"
py -m app.core.podglad_ukladu "01_BYSŁAW_z_opisami.MAP" "byslaw_4abc_czyste_warianty_v13.json" --etykiety 4a 4b 4c --svg "byslaw_4abc_czyste_warianty_v13.svg"
\`\`\`


## Tryb całej mapy — od testów 4a/4b/4c do automatyzacji BYSŁAW

Wcześniejsze wywołania \`--etykiety 4a 4b 4c\` służyły
do testowania geometrii **tylko trzech wydzieleń**.
Pełna mapa testowa BYSŁAW ma 268 oznaczonych wydzieleń,
416 etykiet L2/L3 i 280 wyjściowych zgłoszeń walidatora.
280 zgłoszeń **nie oznacza 280 wadliwych napisów**:
jeden napis może występować w więcej niż jednym konflikcie.
Po testach V13 samodzielny przykład 4a/4b/4c wciąż miał
2 przecięcia dodatkowych linii, mimo braku kolizji napisów.
Z tego powodu dalszy etap celowo nie wymaga kolejnej
serii mikrotestów tych samych trzech etykiet.

Polecenie \`--cala-mapa\` uruchamia:
1. Pełen skan wszystkich konfliktowych grup bez domyślnego
   ograniczenia \`--limit-grup 8\`; domyślnie 2 przebiegi
   i wiązkowe przeszukiwanie sąsiedztwa.
2. Automatyczne próby łączenia najtrudniejszych grup
   w duety i trójki, z istniejącą dokładną, adaptacyjną
   analizą 24/72/112. \`--maks-trudnych\` ogranicza
   wyłącznie **dodatkowy etap**, nie pełen skan.
3. Każda lokalna poprawka jest przyjmowana tylko wtedy,
   gdy zbiór zgłoszonych błędów jest **ściśle mniejszy**
   i nie zawiera żadnego nowego konfliktu.
4. Oddzielny raport \`skutecznosc_calej_mapy\`:
   ile napisów/wydzieleń nie ma problemów przed i po,
   ile naprawiono, ile dopiero powstało, lista wciąż
   problematycznych wydzieleń z liczbą/typami zgłoszeń.
   Zgłoszenia mogą być nadliczbowe względem napisów.
5. Odrębny, **nienadpisywalny** plik testowy \`.MAP\`
   tworzony parametrem \`--map-kopia\` (opcjonalny).
   Eksporter zmienia tylko odpowiednie linie L2/L3,
   zachowuje teksty A1/A2 i obrysy P, przelicza
   nagłówek N/CHK, weryfikuje SHA-256 oryginału i
   **ponownie parsuje wszystkie etykiety** przed zapisem.
   Przy niezgodności odmawia zapisania kopii.
   Plik źródłowy nigdy nie jest otwierany do zapisu.

Pierwszy pełny przebieg na lokalnym komputerze użytkownika:

\`\`\`cmd
cd /d C:\Users\niepy\Desktop\ForestlyMapper-test
git pull --ff-only
py -m unittest discover -s tests -v

py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --cala-mapa --wiazka 16 --maks-grupa 3 --przebiegi 2 --maks-trudnych 24 --rundy-dodatkowe 2 --kara-przeciecia 25 --kara-wielokrotnej-granicy 50 --json "BYSLAW_CALA_MAPA_auto.json" --map-kopia "01_BYSŁAW_AUTOMAT_TEST.MAP"
\`\`\`

Jeżeli kopia \`01_BYSŁAW_AUTOMAT_TEST.MAP\` już istnieje,
polecenie celowo przerwie eksport — wybierz **nową nazwę**,
nie usuwaj oryginalnego \`01_BYSŁAW_z_opisami.MAP\`.
Wygenerowana kopia nie jest certyfikowaną mapą:
topologia poligonów o kilku konturach, rzeczywiste fonty
GEO-MAP oraz przebieg wszystkich wysięgników mogą nadal
wymagać kontroli. Otworzenie testowej kopii w GEO-MAP
jest koniecznym krokiem weryfikacji po eksporcie.

Podstawowy raport nie oznacza, że usunięto wszystkie
problemy: \`nierozwiazane_wydzielenia\` jawnie pokazuje
pozostałą pracę, a \`dopracowanie_niepelne\` odróżnia
wyczerpany budżet prób od braku nowych możliwych pozycji.
\`analiza_czesciowa=false\` znaczy, że wszystkie grupy
zostały **przeskanowane**; nie znaczy, że wszystkie
udało się naprawić. Osiągnięcie blisko 100% automatyzacji
jest celem, a nie potwierdzonym wynikiem tego etapu.


## Etap jakości kartograficznej — drugi przebieg bez powtarzania całej mapy

Pierwszy wynik pełnej mapy BYSŁAW (\`BYSLAW_CALA_MAPA_auto.json\`):
416 etykiet, 268 wydzieleń; 176→410 etykiet bez modelowanych
problemów, 95→264 wydzieleń bez problemów, 280→7 zgłoszeń.
259 etykiet zostało przesuniętych lub otrzymało wysięgnik.
Dalej niepoprawne grupy: \`6gx\` (3 zgłoszenia),
\`6s\` (2), \`3i\` (1), \`3s\` (1).
Raport wykazuje również 90 dodatkowych przekroczeń
różnych obiektów mapy przez wysięgniki. Te przekroczenia
są ostrzeżeniami, nie wszystkie są przeszkodami GIS.

Oględziny GEO-MAP wskazały na osobny problem: estetykę
**poprawnych** wg dotychczasowego modelu lokalizacji.
Przykłady:
- \`6s\` wciąż ma konflikt między L2/L3, obecna
  litera nie znajduje się tam, gdzie czytelnie pasuje do opisu;
- opis \`6k\` ma wysięgnik około 95 m, a \`6j\`
  około 152 m; sąsiednie wydzielenia mogłyby wspólnie
  przesunąć napisy i skrócić obie linie;
- \`3c\`, \`4r\`, \`4p\`, \`4t\` mają opis z wysięgnikiem,
  mimo widocznej przestrzeni wewnątrz poligonów.

Dotychczas \`optymalizuj\` pomijał już rozwiązane wydzielenia:
brak kolizji nie powodował dalszego skracania linii.
Nowy moduł \`app/core/estetyka_mapy.py\` po usunięciu kolizji:
1. Przegląda obciążone wysięgnikami lub wciąż konfliktowe
   wydzielenia; priorytety kierownika mapy można przekazać
   przez \`--priorytety-estetyka\`.
2. Rozważa rozszerzone do 18 poprawne pozycje wewnętrzne
   L2/L3, zamiast tylko najbliższych 9, oraz warianty
   zewnętrzne.
3. Ocenia **bezwzględnie** ilość i długość wysięgników
   (z dodatkową karą za bardzo długie), oraz odstępy
   L2/L3 **z tego samego wydzielenia**.
4. Dodatkowo próbuje przesuwać obok siebie dwa wydzielenia
   jednym wspólnym planem, kiedy pierwszy etap solo nie
   da wystarczającej poprawy.
5. Przyjmuje plan wyłącznie gdy nie tworzy nowych kolizji
   względem bieżącego wyniku i **nie zwiększa** naliczanej
   kary GIS za przecięcia. W przypadku gdy zostaje usunięty
   istniejący problem, priorytetem jest naprawa błędu;
   w przeciwnym razie musi się poprawić ocena estetyki.

Z uwagi na czas obliczeń opcje \`--maks-estetyka\` (domyślnie
36) i \`--maks-par-estetyka\` (domyślnie 12 prób) ograniczają
dodatkowy przebieg, nie liczbę już sprawdzonych wydzieleń
na mapie. \`--maks-estetyka 0\` wyłącza drugi etap.

**Wznawianie:** nie trzeba powtarzać ponad 200 iteracji
pierwszego etapu. Użyj \`--bazowy-json\` aby odtworzyć
wszystkie proponowane pozycje z poprzedniego pełnego
raportu na NIEZMIENIONYM oryginalnym MAP.
Weryfikowane są SHA-256 oryginalnego MAP,
skala, wysokość pisma, ID, pierwotne prostokąty
i liczba konfliktów odtworzonego wyniku.
Następnie nowy etap estetyki pracuje tylko na
zatwierdzonych już pozycjach i zapisuje
**nowy** raport oraz **nową** testową kopię MAP.

\`\`\`cmd
cd /d C:\Users\niepy\Desktop\ForestlyMapper-test
git pull --ff-only
py -m unittest discover -s tests -v

py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --cala-mapa --bazowy-json "BYSLAW_CALA_MAPA_auto.json" --maks-estetyka 48 --maks-par-estetyka 12 --priorytety-estetyka 6s 6k 6j 3c 4r 4p 4t --kara-przeciecia 25 --kara-wielokrotnej-granicy 50 --json "BYSLAW_ESTETYKA_auto.json" --map-kopia "01_BYSŁAW_ESTETYKA_TEST.MAP"
\`\`\`

Otwórz nową kopię w GEO-MAP i sprawdź m.in. 6s, 6k/6j,
3c, 4r, 4p i 4t. Testy syntetyczne i odczyt testowej kopii
nie potwierdzają jeszcze poprawności wyglądu realnej mapy.
Klasyczny raport ilościowy 410/416 nie dowodzi idealnej
jakości drukarskiej: kolejne kryteria będą wymagały
weryfikacji praktycznej przez kartografa.


## Estetyka — wybór połączonych pozycji wewnętrznych i krótkich wysięgników

Ostatni wynik rzeczywisty \`BYSLAW_ESTETYKA_auto.json\` (przed
niniejszymi poprawkami): 40 zaakceptowanych zmian estetyki;
154→147 wysięgników, 8386,88→7220,88 m ich łącznej długości,
ale nadal 7 zgłoszeń błędów i 410/416 napisów bez problemów.
Wynik zawiera **83** dodatkowe przecięcia wysięgników
z elementami mapy (90 było w poprzednim raporcie).

Konkretne defekty z oględzin w GEO-MAP:
\`6s\` — litera nakłada się na opis (nadal brak poprawnego
przestawienia); \`3k\` — wysięgnik opisu 151,5 m;
\`6t\` — 119,2 m; \`4g\` — 98,1 m; \`6o\` — 91,8 m;
\`1j\` — 88,4 m; \`6j\` — 150,6 m. Na dodatek właściciel
mapy zauważył nieużywane wnętrza \`1h,1d,1l,1n,3c,4r,4p,4t\`
oraz zewnętrzne litery \`2n,6d\`.

W analizie kodu wykryto trzy ograniczenia:
1. Plan \`L2/L3\` wewnątrz był tworzony jako iloczyn
   **niezależnych list pozycji** każdej etykiety, a te listy
   kończyły się po kilku położeniach najbliższych oryginałowi.
   Nowa \`_pary_wewnatrz\` rozkłada **zwartą parę**
   poziomo lub pionowo na siatce wielu części konturu
   i weryfikuje obie pełne obwiednie. Warianty
   zachowują różnorodność po całym obszarze mapy.
2. Przesuwanie litery w kierunku opisu na zewnątrz mogło
   zostać pominięte, bo tylko 18 pozycji wybierano
   według odległości od **starej** litery. Rozszerzone
   \`_pozycje_wewnatrz(...,roznorodne=True)\` wybiera
   kandydatów zarówno blisko poprzedniej etykiety, jak
   i przy drugim napisie, a resztę metodą maksymalnego
   rozrzutu (farthest-point sampling).
3. Przy wspólnym przestawianiu sąsiadów dokładny solver
   nadal minimalizował **przesunięcie od obecnych pozycji**,
   nie bezwzględną jakość kartograficzną. Nowy opcjonalny
   \`ocena_planu\` umożliwia priorytet mniejszej liczby
   i długości wysięgników; obecny dobry układ sąsiada
   pozostaje zawsze kandydatem. Dobór sąsiadów uwzględnia
   obiekty blokujące konkretne, korzystniejsze plany
   napisów (a nie tylko bliskość geometryczną poligonów).

Niezmienne ograniczenia: brak nowych kolizji napisów,
brak wzrostu kar GIS, brak modyfikacji pierwotnego MAP,
a testowe pliki są odrębnymi nienadpisywalnymi kopiami.
Szacowane wymiary fontu GEO-MAP i niezbadana semantyka
dziur w poligonach pozostają ograniczeniami.

Weryfikacja realnego wyniku na nowym przebiegu estetyki,
**bez** ponownego rozwiązywania 189 grup:

\`\`\`cmd
cd /d C:\Users\niepy\Desktop\ForestlyMapper-test
git pull --ff-only
py -m unittest discover -s tests -v
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --cala-mapa --bazowy-json "BYSLAW_ESTETYKA_auto.json" --maks-estetyka 64 --maks-par-estetyka 20 --priorytety-estetyka 6s 4g 4j 3k 2n 6d 6t 6o 1j 1h 1d 1l 1n 3c 4r 4p 4t 6j 6k --kara-przeciecia 25 --kara-wielokrotnej-granicy 50 --json "BYSLAW_ESTETYKA_V2_auto.json" --map-kopia "01_BYSŁAW_ESTETYKA_V2_TEST.MAP"
\`\`\`

Liczbę zaakceptowanych zmian, długości i kolizje porównaj
z poprzednim JSON. Nowy moduł poprawia **zestaw dostępnych
propozycji i ranking**, nie gwarantuje, że wszystkie
kandydatury są możliwe na rzeczywistej mapie.


## Zatwierdzone wydzielenia i poprawa 6s z V2

Wynik \`BYSLAW_ESTETYKA_V2_auto.json\`:
- 416 etykiet, 410 poprawnych według przybliżonego modelu;
- 7 nierozwiązanych problemów w dokładnie czterech wydzieleniach:
  \`6s\` (2), \`6gx\` (3), \`3i\` (1), \`3s\` (1);
- 143 wysięgniki, 6392,26 m długości łącznej
  (w pierwszej automatyzacji było 154 i 8386,88 m);
- 81 dodatkowych punktów przecięć wysięgników z obiektami MAP;
- położenie \`6s\`, \`6gx\`, \`3i\`, \`3s\` nie zmieniło się względem
  raportu bazowego.

Użytkownik sprawdził w GEO-MAP i zaakceptował estetykę wszystkich
11 wielokonturowych wydzieleń: \`4c 4a 7b 7a 7d 8j 5g 5h 10r 10o 07h\`.

Dodałem \`--chron-estetyka\` do etapu estetyki:
- wyklucza zaakceptowane wydzielenia z grup do przestawienia;
- wyklucza je także jako drugie wydzielenie we wspólnej
  optymalizacji sąsiadów;
- przyjęcie wariantu z choćby jednym chronionym UUID jest
  dodatkowo zabronione;
- raport estetyki zwraca \`chronione_wydzielenia\`.
  Parametr dotyczy **etapu estetyki**, dlatego do bezpiecznego
  zachowania zatwierdzonych miejsc w bieżącej mapie użyj
  **wznowienia z V2**.

Dodatkowo naprawiono błąd pomijania nierozwiązanych wydzieleń
bez wysięgników na etapie wspólnego przestawiania.
Poprzednio \`6s\` było całkowicie pomijane w tej fazie,
bo obie etykiety nie miały wysięgnika, mimo iż nachodzą na
siebie. Teraz każde wydzielenie z choć jednym aktualnym
problemem geometrycznym jest uprawnione do próby z sąsiadami.
Nie gwarantuje to znalezienia rozwiązania przy ograniczonej
puli wariantów i bez potwierdzonego fontu GEO-MAP.

Zachowaj poprawny poprzedni wynik, koncentrując następny
przebieg na czterech nierozwiązanych grupach:

\`\`\`cmd
cd /d C:\Users\niepy\Desktop\ForestlyMapper-test
git pull --ff-only
py -m unittest discover -s tests -v
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --cala-mapa --bazowy-json "BYSLAW_ESTETYKA_V2_auto.json" --maks-estetyka 24 --maks-par-estetyka 24 --priorytety-estetyka 6s 6gx 3i 3s 6t --chron-estetyka 4c 4a 7b 7a 7d 8j 5g 5h 10r 10o 07h --kara-przeciecia 25 --kara-wielokrotnej-granicy 50 --json "BYSLAW_ZATWIERDZONE_I_NAPRAWY.json" --map-kopia "01_BYSŁAW_ZATWIERDZONE_NAPRAWY_TEST.MAP"
\`\`\`

Nie nadpisuj starego raportu ani poprzedniej kopii MAP.
Nowy test jest celowo krótki: drugi etap estetyki i naprawy,
nie pełny restart skanowania.


## Ocena \`BYSLAW_ZATWIERDZONE_I_NAPRAWY.json\` i proporcjonalny budżet napraw

Raport kolejnego przebiegu: **411/416** napisów bez zgłoszeń,
**265/268** wydzieleń bez problemów, **6** problemów
(\`6gx\`: 3, \`6s\`: 2, \`3s\`: 1). \`3i\` zostało naprawione.
280 etykiet ma modyfikację względem oryginału.
Równocześnie 143→144 wysięgników, 6392,26→6407,37 m,
81 dodatkowych przecięć bez zmiany. Zbiór zmian dla
zatwierdzonych \`4c 4a 7b 7a 7d 8j 5g 5h 10r 10o 07h\`
w całości zgodny z raportem V2.

Z analizy rzeczywistych obrysów poligonów (z oryginalnego MAP)
oraz aktualnego szacunkowego modelu fontu wynika, że
\`6s\`, \`6gx\` i \`3s\` są trudne: w próbie
siatkowej nie znaleziono **całego opisu** mieszczącego się
z marginesem w odpowiednim poligonie. Nie jest to
matematyczny dowód braku miejsca, ale prawdopodobnie
potrzebny będzie przynajmniej jeden wysięgnik.
Nie traktować tych miejsc jako zadania polegającego na
samym przesuwaniu dwóch tekstów wewnątrz.

Przyczyną dodatkowych niepowodzeń był wspólny budżet
\`--maks-par-estetyka\`, konsumowany w kolejności
dotychczasowych wybranych grup — \`6s\` mogło w ogóle
nie dostać szansy. Od teraz:
- aktualne, nadal błędne wydzielenia idą **przed**
  poprawnymi wizualnie, od największej liczby zgłoszeń;
- na każde trudne wydzielenie przypada osobna kwota
  (do ośmiu) prób sąsiedzkich;
- raport \`dopracowanie_estetyki.proby_par_na_wydzielenie\`
  pokazuje rzeczywisty rozkład prób;
- \`diagnostyka_nierozwiazanych\` pokazuje liczbę
  wygenerowanych planów, ile blokują napisy sąsiadów,
  ile przechodzi aktualną granicę kar GIS i które
  wydzielenia najczęściej blokują alternatywy.
  Raport wykorzystuje ograniczony zestaw 24 planów
  i **nie dowodzi** braku dobrego rozwiązania poza nimi.

Sprawdź tylko pozostałe trzy trudne grupy, nie
rozmieszczaj ponownie całej mapy:

\`\`\`cmd
cd /d C:\Users\niepy\Desktop\ForestlyMapper-test
git pull --ff-only
py -m unittest discover -s tests -v
py -m app.core.diag_silnik_grupowy "01_BYSŁAW_z_opisami.MAP" --skala 4000 --cala-mapa --bazowy-json "BYSLAW_ZATWIERDZONE_I_NAPRAWY.json" --maks-estetyka 3 --maks-par-estetyka 24 --priorytety-estetyka 6gx 6s 3s --chron-estetyka 4c 4a 7b 7a 7d 8j 5g 5h 10r 10o 07h --kara-przeciecia 25 --kara-wielokrotnej-granicy 50 --json "BYSLAW_TRUDNE_WYDZIELENIA.json" --map-kopia "01_BYSŁAW_TRUDNE_TEST.MAP"
\`\`\`

Jeżeli 6s/6gx/3s pozostaną niepoprawne,
\`diagnostyka_nierozwiazanych\` pozwala
rozróżnić brak kandydatów, blokady sąsiadów
od niespełnienia rygoru kar za przecinanie
geometrii — bez kolejnej ślepej zwiększanej
puli prób.
