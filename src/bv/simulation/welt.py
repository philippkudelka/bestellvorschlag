"""Der Simulator: erzeugt eine Welt, deren Wahrheit bekannt ist.

Weil die wahre Nachfrage hier bekannt ist, laesst sich spaeter beweisen,
dass die Zensierungskorrektur funktioniert — mit echten Daten geht das nie.

Kernablauf je Tag, Filiale, Artikel:
1. wahre Tagesnachfrage aus Grundniveau x Wochentag x Saison x Trend x
   Feiertag x Ferien x Wetter x Ereignis, negativ-binomial verstreut,
2. Liefermenge, wie sie ein Mensch bestimmt haette (Mittel der letzten drei
   gleichen Wochentage des beobachteten Verkaufs, Aufschlag, Fehler),
3. Zensierung: die Nachfrage laeuft entlang der Tagesverlaufskurve; sobald
   sie die Liefermenge uebersteigt, ist ausverkauft — alles Weitere geht
   verloren und hinterlaesst keine Spur im Verkauf.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from bv.konfiguration import Konfiguration
from bv.quellen import kalender

# ---------------------------------------------------------------------------
# Tagesverlaufskurven: kumulierte Verteilung des Verkaufs ueber den
# normalisierten geoeffneten Tag (0 = Oeffnung, 1 = Ladenschluss).
# ---------------------------------------------------------------------------

_RASTER = np.linspace(0.0, 1.0, 101)


def _dichte_zu_kurve(dichte: np.ndarray) -> np.ndarray:
    kum = np.cumsum(dichte)
    kum = kum / kum[-1]
    kum[0] = 0.0
    return kum


def _kurven() -> dict[str, np.ndarray]:
    u = _RASTER
    return {
        # Semmeln/Brezen: frueh und steil
        "frueh": _dichte_zu_kurve(np.exp(-((u - 0.12) ** 2) / 0.045) + 0.15),
        # Brot: flach
        "flach": _dichte_zu_kurve(np.ones_like(u) + 0.3 * np.exp(-((u - 0.3) ** 2) / 0.1)),
        # Snacks: Mittagsspitze
        "mittag": _dichte_zu_kurve(np.exp(-((u - 0.5) ** 2) / 0.03) + 0.25),
        # Gebaeck: frueher Buckel und zweiter am Nachmittag
        "nachmittag": _dichte_zu_kurve(
            np.exp(-((u - 0.2) ** 2) / 0.03) + 0.9 * np.exp(-((u - 0.75) ** 2) / 0.025) + 0.2
        ),
    }


KURVEN = _kurven()


def kumulierter_anteil(kurve: np.ndarray, position: float | np.ndarray) -> float | np.ndarray:
    """F(u): Anteil des Tagesverkaufs bis zur normalisierten Position u."""
    return np.interp(position, _RASTER, kurve)


def position_bei_anteil(kurve: np.ndarray, anteil: float | np.ndarray) -> float | np.ndarray:
    """F^-1(q): normalisierte Position, an der der Anteil q erreicht ist."""
    return np.interp(anteil, kurve, _RASTER)


# ---------------------------------------------------------------------------
# Oeffnungszeiten aus der Konfiguration (der Simulator kennt keine Datenbank)
# ---------------------------------------------------------------------------

_WOCHENTAG_SCHLUESSEL = ["mo", "di", "mi", "do", "fr", "sa", "so"]


def _minuten(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _hhmm(minuten: int) -> str:
    return f"{minuten // 60:02d}:{minuten % 60:02d}"


def oeffnungsintervalle(filiale: dict, tag: date) -> list[tuple[int, int]]:
    """Oeffnungsintervalle in Tagesminuten fuer eine Filiale an einem Datum.
    Beruecksichtigt Neueroeffnung, Umbau, Augustschliessung und Feiertage
    (an Feiertagen oeffnen nur Filialen mit Sonntagsoeffnung, wie sonntags)."""
    er = filiale.get("eroeffnet_am")
    if er and tag < date.fromisoformat(er):
        return []
    umbau = filiale.get("umbau")
    if umbau and date.fromisoformat(umbau["von"]) <= tag <= date.fromisoformat(umbau["bis"]):
        return []
    plan = filiale["oeffnungszeiten"]
    if kalender.ist_feiertag(tag):
        zeiten = plan.get("so")
        if not zeiten:
            return []
    else:
        zeiten = plan.get(_WOCHENTAG_SCHLUESSEL[tag.weekday()])
    if not zeiten:
        return []
    intervalle = [(_minuten(v), _minuten(b)) for v, b in zeiten]
    if filiale.get("august_nachmittag_zu") and tag.month == 8 and tag.weekday() < 6:
        intervalle = [(v, min(b, _minuten("12:30"))) for v, b in intervalle]
        intervalle = [(v, b) for v, b in intervalle if b > v]
    return intervalle


def minute_bei_kumuliertem_anteil(
    anteil_verkauf: float, kurve: np.ndarray, intervalle: list[tuple[int, int]]
) -> int:
    """Tagesminute (Uhrzeit), zu der der gegebene Anteil des Tagesverkaufs
    erreicht ist. Die Kurve laeuft ueber die aneinandergehaengten
    Oeffnungsintervalle, eine Mittagspause wird also uebersprungen."""
    position = float(position_bei_anteil(kurve, anteil_verkauf))
    gesamt = sum(b - v for v, b in intervalle)
    ziel = position * gesamt
    for v, b in intervalle:
        dauer = b - v
        if ziel <= dauer or (v, b) == intervalle[-1]:
            return int(round(v + min(ziel, dauer)))
        ziel -= dauer
    return intervalle[-1][1]


# ---------------------------------------------------------------------------
# Wetter
# ---------------------------------------------------------------------------

MONATSNORMAL_TEMPERATUR = {1: 3, 2: 5, 3: 10, 4: 14, 5: 19, 6: 22,
                           7: 25, 8: 24, 9: 20, 10: 14, 11: 7, 12: 4}


def erzeuge_wetter(tage: list[date], rng: np.random.Generator) -> pd.DataFrame:
    """Tatsaechliches Wetter und die damalige Vorhersage (mit Fehler)."""
    n = len(tage)
    normal = np.array([MONATSNORMAL_TEMPERATUR[t.month] for t in tage], dtype=float)
    # AR(1)-Abweichung vom Monatsnormal
    abw = np.zeros(n)
    for i in range(1, n):
        abw[i] = 0.75 * abw[i - 1] + rng.normal(0, 2.2)
    temp = normal + abw
    regen_tag = rng.random(n) < 0.38
    regen = np.where(regen_tag, rng.gamma(1.6, 4.0, n), 0.0).round(1)
    sonne = np.clip(10 - regen * 0.6 + rng.normal(0, 1.5, n), 0, 14).round(1)

    ist = pd.DataFrame({
        "datum": [t.isoformat() for t in tage], "ort": "Rosenheim",
        "temperatur_max": temp.round(1), "niederschlag_mm": regen,
        "sonnenstunden": sonne, "ist_vorhersage": 0,
    })
    # Vorhersage: Temperatur +- 1.5 Grad, Regen manchmal falsch
    vh = ist.copy()
    vh["temperatur_max"] = (temp + rng.normal(0, 1.5, n)).round(1)
    regen_vh = np.where(rng.random(n) < 0.82, regen, np.where(regen_tag, 0.0, 2.0))
    vh["niederschlag_mm"] = (regen_vh * np.abs(rng.normal(1, 0.3, n))).round(1)
    vh["sonnenstunden"] = np.clip(sonne + rng.normal(0, 1.5, n), 0, 14).round(1)
    vh["ist_vorhersage"] = 1
    return pd.concat([ist, vh], ignore_index=True)


# ---------------------------------------------------------------------------
# Ereignisse
# ---------------------------------------------------------------------------

def erzeuge_ereignisse(
    filialen: list[dict], von: date, bis: date, rng: np.random.Generator
) -> pd.DataFrame:
    zeilen = []
    jahr = von.year
    while jahr <= bis.year:
        for f in filialen:
            # ein Dorffest je Filiale und Jahr, im Sommerhalbjahr
            start = date(jahr, int(rng.integers(5, 9)), int(rng.integers(1, 28)))
            if von <= start <= bis - timedelta(days=1):
                zeilen.append({
                    "datum_von": start.isoformat(),
                    "datum_bis": (start + timedelta(days=1)).isoformat(),
                    "filialen": str(f["nummer"]),
                    "bezeichnung": f"Dorffest {f['ort']}", "art": "dorffest",
                    "wirkung": round(float(rng.uniform(1.3, 1.6)), 2),
                })
        jahr += 1
    sperrung_von = date(2025, 4, 7)
    if von <= sperrung_von <= bis:
        zeilen.append({
            "datum_von": "2025-04-07", "datum_bis": "2025-04-25", "filialen": "7",
            "bezeichnung": "Strassensperrung Ortsdurchfahrt", "art": "sperrung",
            "wirkung": 0.55,
        })
    for aktion_von, fil in [(date(2024, 3, 4), "alle"), (date(2025, 10, 6), "alle")]:
        if von <= aktion_von <= bis:
            zeilen.append({
                "datum_von": aktion_von.isoformat(),
                "datum_bis": (aktion_von + timedelta(days=5)).isoformat(),
                "filialen": fil, "bezeichnung": "Aktionswoche", "art": "aktion",
                "wirkung": 1.2,
            })
    return pd.DataFrame(zeilen, columns=["datum_von", "datum_bis", "filialen",
                                         "bezeichnung", "art", "wirkung"])


# ---------------------------------------------------------------------------
# Die eigentliche Welt
# ---------------------------------------------------------------------------

@dataclass
class Welt:
    """Ergebnis der Simulation: Tagesgeschichte plus bekannte Wahrheit."""

    tage: pd.DataFrame          # datum, filiale, artikel, liefermenge, verkauf,
    #                             retoure, erster_verkauf, letzter_verkauf,
    #                             nachfrage (WAHRHEIT), ausverkauft (WAHRHEIT)
    wetter: pd.DataFrame
    ereignisse: pd.DataFrame
    filialen: list[dict] = field(default_factory=list)
    artikel: list[dict] = field(default_factory=list)


def erzeuge_welt(
    konfig: Konfiguration,
    von: date,
    bis: date,
    seed: int = 20260823,
    deterministisch: bool = False,
) -> Welt:
    """Erzeugt die komplette Tagesgeschichte. `deterministisch=True` ersetzt
    die Ordnungsstatistik-Streuung der Verkaufszeiten durch ihren Erwartungs-
    wert — dafuer gibt es einen Test, der die Ausverkaufsminute nachrechnet."""
    rng = np.random.default_rng(seed)
    filialen = konfig.filialen
    artikel = konfig.artikel
    alle_tage = [von + timedelta(days=i) for i in range((bis - von).days + 1)]

    wetter = erzeuge_wetter(alle_tage, rng)
    wetter_ist = wetter[wetter["ist_vorhersage"] == 0].set_index("datum")
    ereignisse = erzeuge_ereignisse(filialen, von, bis, rng)

    nf = len(filialen)
    na = len(artikel)
    grundniveau = np.array([f["grundniveau"] for f in filialen])
    trend = np.array([f.get("trend_prozent_pro_jahr", 0.0) for f in filialen]) / 100.0
    grundmenge = np.array([a["grundmenge"] for a in artikel], dtype=float)
    temp_sens = np.array([a["wetter"]["temperatur"] for a in artikel])
    regen_sens = np.array([a["wetter"]["regen"] for a in artikel])
    kurve_je_artikel = [KURVEN[a["kurve"]] for a in artikel]
    kurvenname = [a["kurve"] for a in artikel]

    # Wochentagsfaktoren, je Warengruppe leicht unterschiedlich
    wt_basis = np.array([0.95, 0.90, 0.95, 1.00, 1.15, 1.40, 1.55])
    wt_je_artikel = np.array([
        wt_basis * (1.10 if a["warengruppe"] in ("Semmeln", "Laugenbaeckerei", "Gebaeck") else 1.0)
        for a in artikel
    ])
    # Wochenendaufschlag nur auf Sa/So wirken lassen, Werktage normalisieren
    wt_je_artikel[:, :5] = wt_basis[:5]

    # Ereignisfaktor je (tag, filiale) vorberechnen
    ereignis_faktor = np.ones((len(alle_tage), nf))
    tag_index = {t: i for i, t in enumerate(alle_tage)}
    for _, e in ereignisse.iterrows():
        d0 = date.fromisoformat(e["datum_von"])
        d1 = date.fromisoformat(e["datum_bis"])
        betroffen = (range(nf) if e["filialen"] == "alle"
                     else [i for i, f in enumerate(filialen)
                           if str(f["nummer"]) in e["filialen"].split(",")])
        t = d0
        while t <= d1:
            if t in tag_index:
                for fi in betroffen:
                    ereignis_faktor[tag_index[t], fi] *= e["wirkung"]
            t += timedelta(days=1)

    # Verkaufshistorie fuer die menschliche Liefermenge:
    # je (filiale, artikel, wochentag) die letzten drei beobachteten Verkaeufe
    historie: list[list[deque]] = [
        [deque(maxlen=4) for _ in range(7)] for _ in range(nf * na)
    ]

    standard_minuten = np.zeros(nf)
    for fi, f in enumerate(filialen):
        werktag = f["oeffnungszeiten"].get("mi") or f["oeffnungszeiten"].get("mo")
        standard_minuten[fi] = sum(_minuten(b) - _minuten(v) for v, b in werktag)

    zeilen: list[dict] = []
    for ti, tag in enumerate(alle_tage):
        wt = tag.weekday()
        iso = tag.isoformat()
        jahresfortschritt = (tag.timetuple().tm_yday - 1) / 365.0
        saison = 1.0 + 0.10 * np.sin(2 * np.pi * (jahresfortschritt - 0.22))
        if tag.month == 12 and 18 <= tag.day <= 24:
            saison *= 1.45
        feiertag_morgen = kalender.ist_tag_vor_feiertag(tag)
        feiertag_gestern = kalender.ist_tag_nach_feiertag(tag)
        ferien = kalender.ist_schulferien(tag)
        kalfaktor = 1.0
        if feiertag_morgen:
            kalfaktor *= 1.35
        if feiertag_gestern:
            kalfaktor *= 0.75
        if ferien:
            kalfaktor *= 1.04

        w = wetter_ist.loc[iso]
        temp_abw = w["temperatur_max"] - MONATSNORMAL_TEMPERATUR[tag.month]
        wetterfaktor = (1.0 + temp_sens * temp_abw) * (
            1.0 + regen_sens * min(w["niederschlag_mm"], 10.0) / 10.0
        )
        wetterfaktor = np.clip(wetterfaktor, 0.5, 1.6)

        jahre_seit_start = (tag - alle_tage[0]).days / 365.25

        for fi, f in enumerate(filialen):
            intervalle = oeffnungsintervalle(f, tag)
            if not intervalle:
                continue
            offen_min = sum(b - v for v, b in intervalle)
            offen_faktor = 0.55 + 0.45 * min(offen_min / standard_minuten[fi], 1.0)
            tourismus = 1.12 if (ferien and f.get("tourismus")) else 1.0

            mu = (
                grundmenge
                * grundniveau[fi]
                * wt_je_artikel[:, wt]
                * saison
                * kalfaktor
                * tourismus
                * (1.0 + trend[fi]) ** jahre_seit_start
                * wetterfaktor
                * ereignis_faktor[ti, fi]
                * offen_faktor
            )
            mu = np.maximum(mu, 0.05)

            # negativ-binomial: Gamma-Poisson-Mischung, ueberstreut
            r = 150.0
            lam = rng.gamma(r, mu / r)
            nachfrage = rng.poisson(lam).astype(float)

            for ai in range(na):
                n_wahr = nachfrage[ai]
                h = historie[fi * na + ai][wt]
                if len(h) >= 2:
                    basis = float(np.mean([v for v, _ in h]))
                    # der Mensch reagiert: war zuletzt alles weg, legt er drauf
                    if h[-1][1]:
                        basis *= 1.15
                else:
                    basis = mu[ai] * 1.10
                # der Mensch kennt den Kalender: Feiertage plant er teilweise ein
                basis *= kalfaktor ** 0.8
                fehler = 0.0 if deterministisch else float(rng.normal(0, 0.03))
                liefermenge = max(0.0, round(basis * 1.14 * (1.0 + fehler) + 1.0))

                kurve = kurve_je_artikel[ai]
                if n_wahr <= 0:
                    verkauf, retoure = 0.0, liefermenge
                    ev, lv = None, None
                    ausverkauft = 0
                elif n_wahr > liefermenge:
                    verkauf = liefermenge
                    retoure = 0.0
                    ausverkauft = 1
                    ln, nn = int(liefermenge), int(n_wahr)
                    if liefermenge <= 0:
                        lv = None
                        ev = None
                    else:
                        # Ordnungsstatistik: Anteil des L-ten von N Kunden
                        u = (ln / (nn + 1.0)) if deterministisch else float(
                            rng.beta(ln, nn - ln + 1))
                        lv = _hhmm(minute_bei_kumuliertem_anteil(u, kurve, intervalle))
                        u0 = (1.0 / (nn + 1.0)) if deterministisch else float(rng.beta(1, nn))
                        ev = _hhmm(minute_bei_kumuliertem_anteil(u0, kurve, intervalle))
                else:
                    verkauf = n_wahr
                    retoure = liefermenge - n_wahr
                    ausverkauft = 0
                    nn = int(n_wahr)
                    u = (nn / (nn + 1.0)) if deterministisch else float(rng.beta(nn, 1))
                    lv = _hhmm(minute_bei_kumuliertem_anteil(u, kurve, intervalle))
                    u0 = (1.0 / (nn + 1.0)) if deterministisch else float(rng.beta(1, nn))
                    ev = _hhmm(minute_bei_kumuliertem_anteil(u0, kurve, intervalle))

                if liefermenge > 0 or verkauf > 0:
                    h.append((verkauf, bool(ausverkauft)))

                zeilen.append({
                    "datum": iso, "filiale": f["nummer"], "artikel": artikel[ai]["nummer"],
                    "liefermenge": liefermenge, "verkauf": verkauf, "retoure": retoure,
                    "erster_verkauf": ev, "letzter_verkauf": lv,
                    "nachfrage": n_wahr, "ausverkauft": ausverkauft,
                    "kurve": kurvenname[ai],
                })

    return Welt(
        tage=pd.DataFrame(zeilen), wetter=wetter, ereignisse=ereignisse,
        filialen=filialen, artikel=artikel,
    )
