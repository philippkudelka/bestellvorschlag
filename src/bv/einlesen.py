"""Import-Orchestrierung: holt Daten aus einer Quelle in die Ablage.

Jeder Dateiimport wird in import_lauf protokolliert. Bereits importierte
Dateien werden uebersprungen (und ein zweiter Import derselben Daten wuerde
wegen der eindeutigen Schluessel ohnehin nichts verdoppeln).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bv.ablage import Ablage
from bv.konfiguration import PROJEKTWURZEL, Konfiguration
from bv.quellen.synthetisch import lese_umsatzdatei
from bv.stammdaten import schreibe_stammdaten


def importiere_synthetisch(
    ablage: Ablage, konfig: Konfiguration, von: str = "0000", bis: str = "9999"
) -> dict:
    """Vollimport aus dem synthetischen Exportverzeichnis. Gibt eine kleine
    Statistik zurueck."""
    verzeichnis = PROJEKTWURZEL / konfig.einstellungen["synthetisch"]["verzeichnis"]
    schreibe_stammdaten(ablage, konfig)

    schon = set(
        ablage.lese("SELECT dateiname FROM import_lauf WHERE quelle = 'synthetisch'")
        ["dateiname"].tolist()
    )
    dateien = sorted(Path(verzeichnis).glob("umsatz_*.csv"))
    neu = 0
    for pfad in dateien:
        roh = pfad.stem.split("_")[1]
        iso = f"{roh[:4]}-{roh[4:6]}-{roh[6:]}"
        if pfad.name in schon or not (von <= iso <= bis):
            continue
        datum, df, stat = lese_umsatzdatei(pfad)
        uebernommen = 0
        if not df.empty:
            uebernommen += ablage.schreibe("verkauf", df.rename(
                columns={"verkauf": "menge"})[
                ["datum", "filiale", "artikel", "menge",
                 "erster_verkauf", "letzter_verkauf"]])
            ablage.schreibe("lieferung", df.rename(columns={"liefermenge": "menge"})[
                ["datum", "filiale", "artikel", "menge"]])
            ret = df.rename(columns={"retoure": "menge"})[
                ["datum", "filiale", "artikel", "menge"]].copy()
            ret["erfasst_am"] = ret["datum"]
            ablage.schreibe("retoure", ret)
            _ergaenze_unbekannte_artikel(ablage, df)
        ablage.protokolliere_import(
            "synthetisch", pfad.name, stat["gelesen"], uebernommen, stat["verworfen"])
        neu += 1

    neu += _importiere_stunden(ablage, verzeichnis, schon)
    _importiere_begleitdateien(ablage, verzeichnis)
    return {"dateien_neu": neu, "dateien_gesamt": len(dateien)}


def _importiere_stunden(ablage: Ablage, verzeichnis: Path, schon: set[str]) -> int:
    """Stundenumsatz-Dateien (soweit vorhanden) in verkauf_stunde laden."""
    neu = 0
    for pfad in sorted(Path(verzeichnis).glob("stunden_*.csv")):
        if pfad.name in schon:
            continue
        roh = pfad.stem.split("_")[1]
        datum = f"{roh[:4]}-{roh[4:6]}-{roh[6:]}"
        zeilen = []
        gelesen = 0
        verworfen = 0
        with open(pfad, encoding="cp1252") as f:
            inhalt = f.read().splitlines()
        for zeile in inhalt:
            if not zeile.strip() or not zeile[0].isdigit():
                continue
            gelesen += 1
            teile = zeile.split(";")
            if len(teile) < 4:
                verworfen += 1
                continue
            zeilen.append({"datum": datum, "filiale": int(teile[0]), "artikel": teile[1],
                           "stunde": int(teile[2]), "menge": float(teile[3])})
        n = ablage.schreibe("verkauf_stunde", pd.DataFrame(zeilen)) if zeilen else 0
        ablage.protokolliere_import("synthetisch", pfad.name, gelesen, n, verworfen)
        neu += 1
    return neu


def _ergaenze_unbekannte_artikel(ablage: Ablage, df: pd.DataFrame) -> None:
    """Artikelnummern, die nicht in den Stammdaten stehen (z. B. nach einem
    Nummernwechsel im Fremdsystem), werden mit der Bezeichnung aus der Datei
    angelegt — Warengruppe 'unbekannt', ausserhalb des Umfangs, bis jemand
    sie zuordnet. Der Datenqualitaetsbericht weist darauf hin."""
    bekannte = set(ablage.lese("SELECT nummer FROM artikel")["nummer"])
    fremd = df[~df["artikel"].isin(bekannte)][["artikel", "bezeichnung"]].drop_duplicates()
    if fremd.empty:
        return
    ablage.schreibe("artikel", pd.DataFrame([{
        "nummer": z.artikel, "bezeichnung": z.bezeichnung,
        "warengruppe": "unbekannt", "im_umfang": 0, "mehrtagesartikel": 0,
        "preis": None, "herstellkosten": None,
    } for z in fremd.itertuples(index=False)]))


def _importiere_begleitdateien(ablage: Ablage, verzeichnis: Path) -> None:
    """Wetter, Ereignisse und — nur Simulation — die Wahrheit."""
    wetter = verzeichnis / "wetter.csv"
    if wetter.exists():
        df = pd.read_csv(wetter)
        n = ablage.schreibe("wetter", df)
        ablage.protokolliere_import("synthetisch", "wetter.csv", len(df), n, 0)
    ereignisse = verzeichnis / "ereignisse.csv"
    if ereignisse.exists():
        df = pd.read_csv(ereignisse)
        n = ablage.schreibe("ereignis", df)
        ablage.protokolliere_import("synthetisch", "ereignisse.csv", len(df), n, 0)
    wahrheit = verzeichnis / "wahrheit.csv"
    if wahrheit.exists():
        df = pd.read_csv(wahrheit, dtype={"artikel": str})
        n = ablage.schreibe("wahrheit", df)
        ablage.protokolliere_import(
            "synthetisch", "wahrheit.csv", len(df), n, 0,
            "NUR Simulation — dient ausschliesslich der Bewertung")
