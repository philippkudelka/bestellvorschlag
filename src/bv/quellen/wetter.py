"""Wetter-Schnittstelle mit lokaler Datei-Umsetzung.

Zur Laufzeit wird kein Netz gebraucht: die Umsetzung liest aus einer CSV
(vom Simulator erzeugt, spaeter z. B. ein taeglich abgelegter DWD-Auszug).
Gelernt und vorhergesagt wird immer mit der damaligen VORHERSAGE
(ist_vorhersage = 1), nie mit dem eingetretenen Wetter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pandas as pd


class WetterQuelle(Protocol):
    def lade(self, von: str, bis: str, ist_vorhersage: bool) -> pd.DataFrame:
        """Spalten: datum, ort, temperatur_max, niederschlag_mm,
        sonnenstunden, ist_vorhersage."""
        ...


class DateiWetterQuelle:
    """Liest Wetterdaten aus einer lokalen CSV-Datei."""

    def __init__(self, pfad: str | Path):
        self.pfad = Path(pfad)

    def lade(self, von: str, bis: str, ist_vorhersage: bool = True) -> pd.DataFrame:
        if not self.pfad.exists():
            return pd.DataFrame(columns=["datum", "ort", "temperatur_max",
                                         "niederschlag_mm", "sonnenstunden",
                                         "ist_vorhersage"])
        df = pd.read_csv(self.pfad)
        df = df[(df["datum"] >= von) & (df["datum"] <= bis)]
        return df[df["ist_vorhersage"] == int(ist_vorhersage)].reset_index(drop=True)
