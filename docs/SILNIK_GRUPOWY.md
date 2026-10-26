# Silnik grupowy — etap 1

Nowy moduł `app/core/silnik_grupowy.py` jest niezależny od interfejsu oraz zapisu MAP.
Przyjmuje elementy w formacie `diagnostyka_map.elementy_z_mapy` i zwraca
`(nowe_elementy, raport)` bez zmiany wejścia. Opcjonalny argument
`wszystkie_poligony` powinien obejmować **wszystkie** granice mapy,
również obiekty bez etykiet.

## Jak sprawdzić

```cmd
py -m unittest discover -s tests -v
```

Na tym etapie **nie podłączamy silnika do zapisu MAP ani produkcyjnego GUI**.
Algorytm używa ograniczonej siatki pozycji i beam search, grupuje sąsiadów
oraz preferuje etykiety wewnętrzne. Gdy brakuje bezpiecznej konfiguracji,
zwraca `nierozwiazane` i nie twierdzi, że mapa jest poprawna.
Wymiary tekstu są szacowane, a nie mierzone w GEO-MAP.

Kolejny etap: zweryfikować wydzielenia 3h, 3g i 3r na kopii BYSŁAW;
następnie dodać atomowy eksporter L2/L3 z walidacją i testami round-trip.
