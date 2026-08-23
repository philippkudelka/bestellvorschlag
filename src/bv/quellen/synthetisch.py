"""Liest die vom Simulator erzeugten B.I.T.-aehnlichen Exportdateien.

Der Parser behandelt bewusst dieselben Unsauberkeiten, die auch von einem
echten Warenwirtschaftsexport zu erwarten sind: Kopfzeilen vor der Tabelle,
cp1252, Dezimalkomma, leere und doppelte Zeilen, Artikelnummern als Text.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SPALTEN = ["Fil.", "Art.Nr", "Bez.", "Vk. Men", "Verkauft", "Retour",
           "letz. Ver", "erst. Ver"]


def _zahl(text: str) -> float:
    """Deutsche Dezimalzahl ('228,00') nach float."""
    return float(str(text).replace(".", "").replace(",", "."))


def _datum_aus_kopf(zeilen: list[str]) -> str:
    """Findet 'Datum: TT.MM.JJJJ' in den Kopfzeilen, gibt ISO zurueck."""
    for z in zeilen:
        m = re.search(r"Datum:\s*(\d{2})\.(\d{2})\.(\d{4})", z)
        if m:
            t, mo, j = m.groups()
            return f"{j}-{mo}-{t}"
    raise ValueError("Keine Datumszeile im Dateikopf gefunden")


def lese_umsatzdatei(pfad: Path) -> tuple[str, pd.DataFrame, dict]:
    """Liest eine Tagesdatei. Gibt (datum, DataFrame, statistik) zurueck.

    Statistik: gelesen, uebernommen, verworfen (leere/doppelte Zeilen).
    """
    with open(pfad, encoding="cp1252") as f:
        alle = f.read().splitlines()
    kopf: list[str] = []
    kopfende = 0
    for i, zeile in enumerate(alle):
        if zeile.startswith("Fil.;"):
            kopfende = i
            break
        kopf.append(zeile)
    datum = _datum_aus_kopf(kopf)

    gelesen = 0
    verworfen = 0
    zeilen = []
    gesehen: set[str] = set()
    for roh in alle[kopfende + 1:]:
        if not roh.strip():
            verworfen += 1
            continue
        gelesen += 1
        if roh in gesehen:          # doppelte Zeile
            verworfen += 1
            continue
        gesehen.add(roh)
        teile = roh.split(";")
        if len(teile) < 7:
            verworfen += 1
            continue
        zeilen.append({
            "datum": datum,
            "filiale": int(teile[0]),
            "artikel": teile[1],            # Text — fuehrende Nullen erhalten
            "bezeichnung": teile[2],
            "liefermenge": _zahl(teile[3]),
            "verkauf": _zahl(teile[4]),
            "retoure": _zahl(teile[5]),
            "letzter_verkauf": teile[6] or None,
            "erster_verkauf": teile[7] if len(teile) > 7 and teile[7] else None,
        })
    df = pd.DataFrame(zeilen)
    return datum, df, {"gelesen": gelesen, "uebernommen": len(df), "verworfen": verworfen}


class SynthetischeQuelle:
    """DatenQuelle-Umsetzung fuer das Exportverzeichnis des Simulators."""

    def __init__(self, verzeichnis: str | Path):
        self.verzeichnis = Path(verzeichnis)

    def _dateien(self, von: str, bis: str) -> list[Path]:
        ergebnis = []
        for p in sorted(self.verzeichnis.glob("umsatz_*.csv")):
            roh = p.stem.split("_")[1]
            iso = f"{roh[:4]}-{roh[4:6]}-{roh[6:]}"
            if von <= iso <= bis:
                ergebnis.append(p)
        return ergebnis

    def _alles(self, von: str, bis: str) -> pd.DataFrame:
        teile = [lese_umsatzdatei(p)[1] for p in self._dateien(von, bis)]
        teile = [t for t in teile if not t.empty]
        if not teile:
            return pd.DataFrame()
        return pd.concat(teile, ignore_index=True)

    def lade_verkaeufe(self, von: str, bis: str) -> pd.DataFrame:
        df = self._alles(von, bis)
        if df.empty:
            return df
        return df.rename(columns={"verkauf": "menge"})[
            ["datum", "filiale", "artikel", "menge", "erster_verkauf", "letzter_verkauf"]]

    def lade_retouren(self, von: str, bis: str) -> pd.DataFrame:
        df = self._alles(von, bis)
        if df.empty:
            return df
        df = df.rename(columns={"retoure": "menge"})
        # Das Fremdsystem kann nicht rueckdatieren: erfasst am Verkaufstag.
        df["erfasst_am"] = df["datum"]
        return df[["datum", "filiale", "artikel", "menge", "erfasst_am"]]

    def lade_lieferungen(self, von: str, bis: str) -> pd.DataFrame:
        df = self._alles(von, bis)
        if df.empty:
            return df
        return df.rename(columns={"liefermenge": "menge"})[
            ["datum", "filiale", "artikel", "menge"]]

    def lade_stammdaten(self) -> pd.DataFrame:
        """Artikelnummern und Bezeichnungen, wie sie in den Dateien vorkommen."""
        df = self._alles("0000-01-01", "9999-12-31")
        if df.empty:
            return df
        return df[["artikel", "bezeichnung"]].drop_duplicates().rename(
            columns={"artikel": "nummer"})
