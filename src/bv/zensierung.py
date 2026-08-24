"""Zensierungskorrektur — der Kern des ganzen Systems.

Verkauf ist nicht Nachfrage: wer vor Ladenschluss ausverkauft ist, haette
mehr verkauft, und diese Menge steht in keinem System. Hier wird sie
geschaetzt. Alles Weitere (Merkmale, Modell, Rueckrechnung) lernt und misst
auf der Tabelle `nachfrage`, nie auf `verkauf`.

Teil 1: Tagesverlaufskurve je Artikel und Filiale aus den nicht zensierten
Tagen des Stundenumsatzes schaetzen; auf den Anteil der Oeffnungsdauer
normalisiert. Zu wenige Beobachtungen -> Warengruppe -> Standardverlauf.

Teil 2: Ausverkauf erkennen (Retoure ~ 0, letzter Verkauf deutlich vor
Ladenschluss, Verkauf ~ Liefermenge) und den Verkauf ueber den Kurvenanteil
zur Nachfrage hochrechnen.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from bv.ablage import Ablage
from bv.konfiguration import Konfiguration

_RASTER = np.linspace(0.0, 1.0, 101)


def _dichte_zu_kurve(dichte: np.ndarray) -> np.ndarray:
    kum = np.cumsum(dichte)
    kum = kum / kum[-1]
    kum[0] = 0.0
    return kum


# Standardverlaeufe je Warengruppe — bewusst grobe Vorgaben, die nur greifen,
# wenn keine Stundendaten vorliegen. Nicht identisch mit den Simulatorkurven.
_STANDARD_FORMEN: dict[str, np.ndarray] = {
    "frueh": _dichte_zu_kurve(np.exp(-((_RASTER - 0.15) ** 2) / 0.06) + 0.2),
    "flach": _dichte_zu_kurve(np.ones_like(_RASTER)),
    "mittag": _dichte_zu_kurve(np.exp(-((_RASTER - 0.5) ** 2) / 0.05) + 0.3),
    "nachmittag": _dichte_zu_kurve(
        np.exp(-((_RASTER - 0.25) ** 2) / 0.05)
        + 0.8 * np.exp(-((_RASTER - 0.7) ** 2) / 0.04) + 0.25),
}
STANDARD_JE_WARENGRUPPE = {
    "Semmeln": "frueh", "Laugenbaeckerei": "frueh", "Brot": "flach",
    "Gebaeck": "nachmittag", "Imbiss": "mittag",
}
_MIN_TAGE_EIGENE_KURVE = 12
_MIN_TAGE_WARENGRUPPE = 30


class Tageskurven:
    """Nachschlagewerk: kumulierte Verkaufskurve je (filiale, artikel)."""

    def __init__(self, eigene: dict, je_warengruppe: dict, warengruppe_je_artikel: dict):
        self._eigene = eigene
        self._je_warengruppe = je_warengruppe
        self._wg = warengruppe_je_artikel

    def kurve(self, filiale: int, artikel: str) -> tuple[np.ndarray, str]:
        """Gibt (Kurve, Herkunft) zurueck."""
        if (filiale, artikel) in self._eigene:
            return self._eigene[(filiale, artikel)], "eigene Stundendaten"
        wg = self._wg.get(artikel)
        if wg in self._je_warengruppe:
            return self._je_warengruppe[wg], f"Warengruppe {wg}"
        form = STANDARD_JE_WARENGRUPPE.get(wg, "flach")
        return _STANDARD_FORMEN[form], "Standardverlauf"

    def anteil(self, filiale: int, artikel: str, position: float) -> float:
        kurve, _ = self.kurve(filiale, artikel)
        return float(np.interp(position, _RASTER, kurve))


def _oeffnungskarte(ablage: Ablage, paare: pd.DataFrame) -> dict:
    """(filiale, datum) -> (intervalle in Minuten, gesamtminuten, schluss)."""
    karte = {}
    for z in paare.drop_duplicates().itertuples(index=False):
        zeiten = ablage.oeffnung(int(z.filiale), z.datum)
        intervalle = [(_min(v), _min(b)) for v, b in zeiten]
        gesamt = sum(b - v for v, b in intervalle)
        schluss = max((b for _, b in intervalle), default=None)
        karte[(int(z.filiale), z.datum)] = (intervalle, gesamt, schluss)
    return karte


def _min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _position(minute: int, intervalle: list[tuple[int, int]], gesamt: int) -> float:
    if gesamt <= 0:
        return 1.0
    vergangen = sum(max(0, min(minute, b) - v) for v, b in intervalle)
    return min(1.0, vergangen / gesamt)


def schaetze_tageskurven(ablage: Ablage) -> Tageskurven:
    """Teil 1: Kurven aus dem Stundenumsatz nicht zensierter Tage schaetzen."""
    artikel = ablage.lese("SELECT nummer, warengruppe FROM artikel")
    wg_je_artikel = dict(zip(artikel["nummer"], artikel["warengruppe"]))

    stunden = ablage.lese("SELECT datum, filiale, artikel, stunde, menge FROM verkauf_stunde")
    if stunden.empty:
        return Tageskurven({}, {}, wg_je_artikel)

    # nicht zensierte Tage: es gab Retoure, also war bis Schluss Ware da
    retouren = ablage.lese(
        "SELECT datum, filiale, artikel, SUM(menge) AS retoure FROM retoure"
        " GROUP BY datum, filiale, artikel")
    stunden = stunden.merge(retouren, on=["datum", "filiale", "artikel"], how="left")
    stunden = stunden[stunden["retoure"].fillna(0) > 0]
    if stunden.empty:
        return Tageskurven({}, {}, wg_je_artikel)

    karte = _oeffnungskarte(ablage, stunden[["filiale", "datum"]])

    eigene: dict = {}
    sammel_wg: dict[str, list[np.ndarray]] = {}
    for (fil, art), gruppe in stunden.groupby(["filiale", "artikel"]):
        tageskurven = []
        for datum, tag in gruppe.groupby("datum"):
            intervalle, gesamt, _ = karte.get((int(fil), datum), ([], 0, None))
            if gesamt <= 0:
                continue
            tag = tag.sort_values("stunde")
            positionen = [_position((int(h) + 1) * 60, intervalle, gesamt)
                          for h in tag["stunde"]]
            kum = np.cumsum(tag["menge"].to_numpy())
            if kum[-1] <= 0:
                continue
            kum = kum / kum[-1]
            tageskurven.append(np.interp(_RASTER, [0.0] + positionen, np.concatenate([[0.0], kum])))
        if not tageskurven:
            continue
        mittel = np.maximum.accumulate(np.mean(tageskurven, axis=0))
        mittel[0] = 0.0
        mittel[-1] = 1.0
        wg = wg_je_artikel.get(art, "unbekannt")
        sammel_wg.setdefault(wg, []).extend(tageskurven)
        if len(tageskurven) >= _MIN_TAGE_EIGENE_KURVE:
            eigene[(int(fil), art)] = mittel

    je_wg = {}
    for wg, kurven in sammel_wg.items():
        if len(kurven) >= _MIN_TAGE_WARENGRUPPE:
            k = np.maximum.accumulate(np.mean(kurven, axis=0))
            k[0] = 0.0
            k[-1] = 1.0
            je_wg[wg] = k
    return Tageskurven(eigene, je_wg, wg_je_artikel)


def korrigiere_zensierung(
    ablage: Ablage, konfig: Konfiguration,
    von: str | None = None, bis: str | None = None,
    kurven: Tageskurven | None = None,
) -> dict:
    """Teil 2: schreibt die Tabelle `nachfrage` fuer alle Verkaufstage im
    Zeitraum. Bereits vorhandene Tage werden neu berechnet (Kurven koennen
    sich verbessert haben) — die Tabelle ist abgeleitet, nie Rohdaten."""
    p = konfig.zensierung
    umbenennung = {
        str(alt): str(neu)
        for alt, neu in (konfig.einstellungen.get("artikel_umbenennungen") or {}).items()
    }
    kurven = kurven or schaetze_tageskurven(ablage)

    bedingung = ""
    params: list[str] = []
    if von:
        bedingung += " AND v.datum >= ?"
        params.append(von)
    if bis:
        bedingung += " AND v.datum <= ?"
        params.append(bis)
    df = ablage.lese(f"""
        SELECT v.datum, v.filiale, v.artikel, v.menge AS verkauf,
               v.letzter_verkauf, l.menge AS liefermenge,
               COALESCE(r.retoure, 0) AS retoure
        FROM verkauf v
        LEFT JOIN lieferung l
          ON l.datum = v.datum AND l.filiale = v.filiale AND l.artikel = v.artikel
        LEFT JOIN (SELECT datum, filiale, artikel, SUM(menge) AS retoure
                   FROM retoure GROUP BY datum, filiale, artikel) r
          ON r.datum = v.datum AND r.filiale = v.filiale AND r.artikel = v.artikel
        WHERE 1=1 {bedingung}""", params)
    if df.empty:
        return {"tage": 0, "geschaetzt": 0, "unsicher": 0}

    # Nummernwechsel im Fremdsystem auf die kanonische Nummer zurueckfuehren
    if umbenennung:
        df["artikel"] = df["artikel"].map(lambda a: umbenennung.get(a, a))

    karte = _oeffnungskarte(ablage, df[["filiale", "datum"]])

    # Vorpruefung vektorisiert; die teure Kurvenrechnung nur fuer Kandidaten
    df["liefermenge"] = df["liefermenge"].fillna(0)
    kandidat = (
        (df["retoure"] <= p["schwelle_retoure"])
        & (df["liefermenge"] > 0)
        & (df["verkauf"] >= df["liefermenge"] * p["anteil_liefermenge"])
        & df["letzter_verkauf"].notna()
    )

    zeilen = []
    n_geschaetzt = 0
    n_unsicher = 0
    for z, ist_kandidat in zip(df.itertuples(index=False), kandidat.to_numpy()):
        menge = float(z.verkauf)
        ist_geschaetzt = 0
        unsicher = 0
        begruendung = None
        if ist_kandidat:
            intervalle, gesamt, schluss = karte.get((int(z.filiale), z.datum), ([], 0, None))
            if schluss is not None:
                lv = _min(z.letzter_verkauf)
                abstand = schluss - lv
                if abstand >= p["mindestabstand_minuten"]:
                    anteil = kurven.anteil(
                        int(z.filiale), z.artikel, _position(lv, intervalle, gesamt))
                    ist_geschaetzt = 1
                    n_geschaetzt += 1
                    if anteil < p["untergrenze_kurvenanteil"]:
                        anteil = p["untergrenze_kurvenanteil"]
                        unsicher = 1
                        n_unsicher += 1
                    menge = round(float(z.verkauf) / anteil)
                    begruendung = (
                        f"Ausverkauf {z.letzter_verkauf}, {abstand:.0f} Min. vor Schluss"
                        f" — Verkauf {z.verkauf:.0f} mit Kurvenanteil {anteil:.2f}"
                        f" auf {menge:.0f} hochgerechnet"
                        + (" (gedeckelt, unsicher)" if unsicher else ""))
        zeilen.append({
            "datum": z.datum, "filiale": int(z.filiale), "artikel": z.artikel,
            "menge": menge, "ist_geschaetzt": ist_geschaetzt,
            "unsicher": unsicher, "begruendung": begruendung,
        })

    ergebnis = pd.DataFrame(zeilen)
    # abgeleitete Tabelle: betroffene Tage ersetzen, dann neu schreiben
    tage = sorted(ergebnis["datum"].unique())
    ablage.verbindung.execute(
        "DELETE FROM nachfrage WHERE datum BETWEEN ? AND ?", (tage[0], tage[-1]))
    ablage.verbindung.commit()
    ablage.schreibe("nachfrage", ergebnis)
    return {"tage": len(ergebnis), "geschaetzt": n_geschaetzt, "unsicher": n_unsicher}
