"""Dokładne testy geometrii układu opisów GEO-MAP.

Bez zależności zewnętrznych i bez zapisu do plików .MAP. Współrzędne są
w jednostkach mapy; prostokąty są osiowo wyrównane (xmin, ymin, xmax, ymax).
To fundament walidatora, a nie nowy algorytm rozmieszczania.
"""

from collections import defaultdict
import math

EPS = 1e-7


def _krzyz(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _roznica(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _blisko(a, b, eps=EPS):
    return math.dist(a, b) <= eps


def punkt_na_odcinku(p, a, b, eps=EPS):
    ab = _roznica(b, a)
    ap = _roznica(p, a)
    dlugosc = math.hypot(*ab)
    if dlugosc <= eps:
        return _blisko(p, a, eps)
    return (abs(_krzyz(ab, ap)) <= eps * dlugosc
            and min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
            and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps)


def punkt_w_poligonie(p, pts, *, granica=True, eps=EPS):
    """Promień poziomy; na granicy zwracaj granica (domyślnie True)."""
    if len(pts) < 3:
        return False
    x, y = p
    w_srodku = False
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        if punkt_na_odcinku(p, a, b, eps):
            return granica
        if (a[1] > y) != (b[1] > y):
            przeciecie_x = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < przeciecie_x:
                w_srodku = not w_srodku
    return w_srodku


def _odcinek_przecina_prostokat(a, b, r):
    """Liang–Barsky: przecięcie z domkniętym prostokątem."""
    x0, y0, x1, y1 = r
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]),
                 (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-15:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def odcinek_przecina_prostokat(a, b, r, *, wnetrze=False, eps=EPS):
    """Czy odcinek dotyka prostokąta; wnetrze=True wyklucza sam brzeg."""
    x0, y0, x1, y1 = r
    if x0 >= x1 or y0 >= y1:
        return False
    if wnetrze:
        x0, y0, x1, y1 = x0 + eps, y0 + eps, x1 - eps, y1 - eps
        if x0 >= x1 or y0 >= y1:
            return False
    return _odcinek_przecina_prostokat(a, b, (x0, y0, x1, y1))


def prostokat_w_poligonie(r, pts, eps=EPS):
    """Pełna zawartość prostokąta w prostym poligonie (również wklęsłym).

    Same narożniki nie wystarczą: wklęsła granica może wchodzić do środka
    prostokąta. Dopuszczamy styk z granicą, nie dopuszczamy jej przecięcia
    z otwartym wnętrzem prostokąta.
    """
    x0, y0, x1, y1 = r
    if len(pts) < 3 or x0 >= x1 or y0 >= y1:
        return False
    pole2 = sum(a[0] * b[1] - b[0] * a[1]
                for a, b in zip(pts, pts[1:] + pts[:1]))
    if abs(pole2) <= eps:
        return False
    rogi = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    if not all(punkt_w_poligonie(p, pts, eps=eps) for p in rogi):
        return False
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        if odcinek_przecina_prostokat(a, b, r, wnetrze=True, eps=eps):
            return False
    return True


def przeciecie_odcinkow(a, b, c, d, eps=EPS):
    """Zwróć ('brak'|'punkt'|'nakladanie', punkt lub None).

    Rozróżnia przecięcie w środku od dozwolonego wspólnego punktu końcowego.
    Nakładanie fragmentów współliniowych to zawsze kolizja.
    """
    r, s = _roznica(b, a), _roznica(d, c)
    rr, ss = r[0] ** 2 + r[1] ** 2, s[0] ** 2 + s[1] ** 2
    if rr <= eps ** 2 or ss <= eps ** 2:
        if rr <= eps ** 2 and ss <= eps ** 2:
            return ('punkt', a) if _blisko(a, c, eps) else ('brak', None)
        p = a if rr <= eps ** 2 else c
        u, v = (c, d) if rr <= eps ** 2 else (a, b)
        return ('punkt', p) if punkt_na_odcinku(p, u, v, eps) else ('brak', None)
    denom = _krzyz(r, s)
    ca = _roznica(c, a)
    if abs(denom) <= eps * math.sqrt(rr * ss):
        if abs(_krzyz(ca, r)) > eps * math.sqrt(rr):
            return 'brak', None
        # Współliniowość: projekcja na oś odcinka AB.
        t0 = (ca[0] * r[0] + ca[1] * r[1]) / rr
        db = _roznica(d, a)
        t1 = (db[0] * r[0] + db[1] * r[1]) / rr
        lo, hi = max(0.0, min(t0, t1)), min(1.0, max(t0, t1))
        tol_t = eps / math.sqrt(rr)
        if hi < lo - tol_t:
            return 'brak', None
        if hi <= lo + tol_t:
            return 'punkt', (a[0] + r[0] * max(0.0, lo), a[1] + r[1] * max(0.0, lo))
        return 'nakladanie', None
    t = _krzyz(ca, s) / denom
    u = _krzyz(ca, r) / denom
    if -eps <= t <= 1 + eps and -eps <= u <= 1 + eps:
        return 'punkt', (a[0] + t * r[0], a[1] + t * r[1])
    return 'brak', None


def wysiegniki_koliduja(w1, w2, *, to_samo_wydzielenie=False, eps=EPS):
    """Dopuszczamy tylko wspólny KONIEC dwóch linii tego samego wydzielenia."""
    typ, punkt = przeciecie_odcinkow(w1[0], w1[1], w2[0], w2[1], eps)
    if typ == 'brak':
        return False
    return not (typ == 'punkt' and to_samo_wydzielenie
                and _blisko(w1[1], w2[1], eps)
                and _blisko(punkt, w1[1], eps))


def prostokaty_koliduja(r1, r2, eps=EPS):
    """Dodatnie pole wspólne oznacza konflikt; sam styk krawędzi nie."""
    return min(r1[2], r2[2]) > max(r1[0], r2[0]) + eps and min(r1[3], r2[3]) > max(r1[1], r2[1]) + eps


def waliduj_uklad(elementy):
    """Walidacja bez modyfikowania mapy; lista problemów z ID elementów.

    element: {'id', 'wydzielenie', 'rodzaj', 'prostokat', 'poligon',
              'wysiegnik': ((x_start,y_start),(x_cel,y_cel)) lub None}.
    'prostokat' i 'poligon' są potrzebne także dla liter. Współrzędne celu
    są absolutne; wejście powinno być już przeliczone z zapisów GEO-MAP.
    """
    elementy = list(elementy)
    bledy = []

    def blad(typ, *ids):
        bledy.append({'typ': typ, 'elementy': list(ids)})

    grupy = defaultdict(list)
    for e in elementy:
        ident = e['id']
        grupy[e['wydzielenie']].append(e)
        w = e.get('wysiegnik')
        w_srodku = prostokat_w_poligonie(e['prostokat'], e['poligon'])
        if not w_srodku and not w:
            blad('poza_bez_wysiegnika', ident)
        if w_srodku and w:
            blad('zbedny_wysiegnik', ident)
        if w:
            if not punkt_w_poligonie(w[1], e['poligon'], granica=False):
                blad('cel_poza_poligonem', ident)
            prost = e['prostokat']
            rogi = ((prost[0], prost[1]), (prost[2], prost[1]),
                    (prost[2], prost[3]), (prost[0], prost[3]))
            if not any(punkt_na_odcinku(w[0], rogi[i], rogi[(i+1) % 4])
                       for i in range(4)):
                blad('start_poza_napisem', ident)
            if odcinek_przecina_prostokat(*w, prost, wnetrze=True):
                blad('wysiegnik_przecina_wlasny_napis', ident)

    for grupa in grupy.values():
        poza = [e for e in grupa if not prostokat_w_poligonie(e['prostokat'], e['poligon'])]
        z_w = [e for e in poza if e.get('wysiegnik')]
        if len(z_w) > 1 and any(not _blisko(z_w[0]['wysiegnik'][1],
                                             e['wysiegnik'][1]) for e in z_w[1:]):
            blad('rozne_cele_jednego_wydzielenia', *(e['id'] for e in z_w))

    for i, e1 in enumerate(elementy):
        for e2 in elementy[i+1:]:
            if prostokaty_koliduja(e1['prostokat'], e2['prostokat']):
                blad('napis_napis', e1['id'], e2['id'])
            for zrodlo, cel in ((e1, e2), (e2, e1)):
                w = zrodlo.get('wysiegnik')
                if w and odcinek_przecina_prostokat(*w, cel['prostokat']):
                    blad('wysiegnik_napis', zrodlo['id'], cel['id'])
            w1, w2 = e1.get('wysiegnik'), e2.get('wysiegnik')
            if w1 and w2 and wysiegniki_koliduja(
                    w1, w2, to_samo_wydzielenie=e1['wydzielenie'] == e2['wydzielenie']):
                blad('wysiegnik_wysiegnik', e1['id'], e2['id'])

    return bledy
