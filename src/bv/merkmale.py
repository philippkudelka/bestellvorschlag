"""Merkmalsbau je (Liefertag, Filiale, Artikel).

Eiserne Regel — kein Blick in die Zukunft: bestellt wird am Abend von T-1,
die Kassendaten von T-1 kommen aber erst um 23:00. Jedes Rueckblickmerkmal
fuer den Liefertag T verwendet daher nur Nachfrage bis einschliesslich T-2.
Wetter ist die damalige VORHERSAGE, nie das eingetretene Wetter. Kalender
und Ereignisse duerfen aus der Zukunft kommen — sie sind vorab bekannt.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from bv.ablage import Ablage
from bv.konfiguration import Konfiguration
from bv.quellen import kalender

# Klimatologie (langjaehrige Monatsmittel der Tageshoechsttemperatur, grob);
# dient nur der Abweichungsbildung, kein Datenleck.
MONATSNORMAL = {1: 3, 2: 5, 3: 10, 4: 14, 5: 19, 6: 22,
                7: 25, 8: 24, 9: 20, 10: 14, 11: 7, 12: 4}

MERKMALSLISTE = [
    "wochentag", "tag_im_monat", "kalenderwoche", "monat",
    "jahr_sin", "jahr_cos",
    "feiertag", "tag_vor_feiertag", "tag_nach_feiertag", "brueckentag",
    "schulferien", "erster_ferientag", "letzter_ferientag",
    "oeffnungsminuten",
    "mittel_3", "mittel_7", "mittel_28", "median_7", "median_28",
    "vorwoche_1", "vorwoche_2", "vorwoche_3", "vorwoche_4",
    "temperatur", "niederschlag", "sonnenstunden", "temperatur_abweichung",
    "ereignis_wirkung", "ereignis_aktiv",
    "filiale", "artikel_code",
]
KATEGORISCH = ["wochentag", "monat", "filiale", "artikel_code"]


def baue_merkmale(
    ablage: Ablage,
    konfig: Konfiguration,
    liefertage: list[str],
    mit_ziel: bool = True,
    quelle: str = "nachfrage",
) -> pd.DataFrame:
    """Merkmalszeilen fuer die gegebenen Liefertage, nur Artikel im Umfang.

    Ergebnis: Schluessel (liefertag, filiale, artikel, warengruppe),
    Merkmale laut MERKMALSLISTE, und `ziel` (Nachfrage an T), falls bekannt.

    `quelle` ist normalerweise die zensierungskorrigierte Tabelle `nachfrage`;
    `verkauf` dient nur der Rueckrechnung, um die Wirkung der Korrektur zu
    messen (Modellvariante ohne Korrektur).
    """
    artikel = ablage.lese(
        "SELECT nummer, warengruppe FROM artikel WHERE im_umfang = 1")
    im_umfang = set(artikel["nummer"])
    wg = dict(zip(artikel["nummer"], artikel["warengruppe"]))

    nachfrage = ablage.lese(f"SELECT datum, filiale, artikel, menge FROM {quelle}")
    if quelle != "nachfrage":
        # Nummernwechsel wird sonst in der Zensierung angewandt
        umbenennung = {
            str(alt): str(neu)
            for alt, neu in (konfig.einstellungen.get("artikel_umbenennungen") or {}).items()
        }
        if umbenennung:
            nachfrage["artikel"] = nachfrage["artikel"].map(
                lambda a: umbenennung.get(a, a))
            nachfrage = nachfrage.groupby(
                ["datum", "filiale", "artikel"], as_index=False)["menge"].sum()
    nachfrage = nachfrage[nachfrage["artikel"].isin(im_umfang)]
    if nachfrage.empty:
        return pd.DataFrame()

    # Breite Tafel Tage x (filiale, artikel); Index laueckenlos taeglich,
    # damit shift() Kalendertage bedeutet
    nachfrage["datum"] = pd.to_datetime(nachfrage["datum"])
    tafel = nachfrage.pivot_table(index="datum", columns=["filiale", "artikel"],
                                  values="menge", aggfunc="sum")
    letzter_tag = max(pd.to_datetime(max(liefertage)), tafel.index.max())
    voll = pd.date_range(tafel.index.min(), letzter_tag, freq="D")
    tafel = tafel.reindex(voll)

    # Rueckblicke: nur Daten bis T-2 (shift um 2 Kalendertage)
    verfuegbar = tafel.shift(2)
    rueckblicke = {
        "mittel_3": verfuegbar.rolling(3, min_periods=1).mean(),
        "mittel_7": verfuegbar.rolling(7, min_periods=2).mean(),
        "mittel_28": verfuegbar.rolling(28, min_periods=7).mean(),
        "median_7": verfuegbar.rolling(7, min_periods=2).median(),
        "median_28": verfuegbar.rolling(28, min_periods=7).median(),
        "vorwoche_1": tafel.shift(7),
        "vorwoche_2": tafel.shift(14),
        "vorwoche_3": tafel.shift(21),
        "vorwoche_4": tafel.shift(28),
    }

    wetter = ablage.lese(
        "SELECT datum, temperatur_max, niederschlag_mm, sonnenstunden FROM wetter"
        " WHERE ist_vorhersage = 1")
    wetter_je_tag = wetter.set_index("datum")

    ereignisse = ablage.lese(
        "SELECT datum_von, datum_bis, filialen, wirkung FROM ereignis"
        " WHERE art != 'geschlossen'")

    bloecke = []
    for liefertag in liefertage:
        t = pd.Timestamp(liefertag)
        tag = t.date()
        if t not in tafel.index:
            continue
        kal = _kalendermerkmale(tag)
        w = (wetter_je_tag.loc[liefertag]
             if liefertag in wetter_je_tag.index else None)

        zeilen = {"liefertag": liefertag}
        block = pd.DataFrame({
            name: frame.loc[t] for name, frame in rueckblicke.items()
        })
        block.index.names = ["filiale", "artikel"]
        block = block.reset_index()
        if mit_ziel:
            block["ziel"] = tafel.loc[t].reset_index(drop=True)
        for k, v in {**zeilen, **kal}.items():
            block[k] = v
        if w is not None:
            block["temperatur"] = float(w["temperatur_max"])
            block["niederschlag"] = float(w["niederschlag_mm"])
            block["sonnenstunden"] = float(w["sonnenstunden"])
            block["temperatur_abweichung"] = (
                float(w["temperatur_max"]) - MONATSNORMAL[tag.month])
        else:
            block["temperatur"] = np.nan
            block["niederschlag"] = np.nan
            block["sonnenstunden"] = np.nan
            block["temperatur_abweichung"] = np.nan
        block = _ereignismerkmale(block, ereignisse, liefertag)
        minuten = {int(f): ablage.oeffnungsminuten(int(f), tag)
                   for f in block["filiale"].unique()}
        block["oeffnungsminuten"] = block["filiale"].astype(int).map(minuten)
        bloecke.append(block)

    if not bloecke:
        return pd.DataFrame()
    df = pd.concat(bloecke, ignore_index=True)
    df["warengruppe"] = df["artikel"].map(wg)
    # stabile Codes: Reihenfolge der Stammdaten, nicht des Datenausschnitts —
    # sonst passen Trainings- und Vorhersagecodes nicht zusammen
    codes = {nummer: i for i, nummer in enumerate(sorted(im_umfang))}
    df["artikel_code"] = df["artikel"].map(codes)
    # geschlossene Filialen (0 Minuten) brauchen keinen Vorschlag
    df = df[df["oeffnungsminuten"] > 0].reset_index(drop=True)
    return df


def _kalendermerkmale(tag: date) -> dict:
    fortschritt = (tag.timetuple().tm_yday - 1) / 365.0
    return {
        "wochentag": tag.weekday(),
        "tag_im_monat": tag.day,
        "kalenderwoche": tag.isocalendar()[1],
        "monat": tag.month,
        "jahr_sin": np.sin(2 * np.pi * fortschritt),
        "jahr_cos": np.cos(2 * np.pi * fortschritt),
        "feiertag": int(kalender.ist_feiertag(tag)),
        "tag_vor_feiertag": int(kalender.ist_tag_vor_feiertag(tag)),
        "tag_nach_feiertag": int(kalender.ist_tag_nach_feiertag(tag)),
        "brueckentag": int(kalender.ist_brueckentag(tag)),
        "schulferien": int(kalender.ist_schulferien(tag)),
        "erster_ferientag": int(kalender.ist_erster_ferientag(tag)),
        "letzter_ferientag": int(kalender.ist_letzter_ferientag(tag)),
    }


def _ereignismerkmale(block: pd.DataFrame, ereignisse: pd.DataFrame,
                      liefertag: str) -> pd.DataFrame:
    wirkung = np.ones(len(block))
    if not ereignisse.empty:
        aktiv = ereignisse[(ereignisse["datum_von"] <= liefertag)
                           & (ereignisse["datum_bis"] >= liefertag)]
        for e in aktiv.itertuples(index=False):
            if e.filialen == "alle":
                wirkung *= e.wirkung
            else:
                betroffen = {int(x) for x in str(e.filialen).split(",")}
                maske = block["filiale"].astype(int).isin(betroffen).to_numpy()
                wirkung[maske] *= e.wirkung
    block["ereignis_wirkung"] = wirkung
    block["ereignis_aktiv"] = (wirkung != 1.0).astype(int)
    return block
