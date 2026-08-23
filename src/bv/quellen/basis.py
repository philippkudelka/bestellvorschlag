"""Protokoll fuer Datenquellen: jede Quelle (synthetisch, echter B.I.T.-Export)
liefert dieselben kanonischen DataFrames — der Rest des Systems sieht nie,
woher die Daten kommen."""

from __future__ import annotations

from typing import Protocol

import pandas as pd


class DatenQuelle(Protocol):
    """Eine Quelle fuer Bewegungs- und Stammdaten.

    Alle DataFrames verwenden die kanonischen Spaltennamen des Schemas
    (siehe bv.schema), Datum als ISO-Text, Artikelnummern als Text.
    """

    def lade_verkaeufe(self, von: str, bis: str) -> pd.DataFrame:
        """Spalten: datum, filiale, artikel, menge, erster_verkauf, letzter_verkauf."""
        ...

    def lade_retouren(self, von: str, bis: str) -> pd.DataFrame:
        """Spalten: datum, filiale, artikel, menge, erfasst_am."""
        ...

    def lade_lieferungen(self, von: str, bis: str) -> pd.DataFrame:
        """Spalten: datum, filiale, artikel, menge."""
        ...

    def lade_stammdaten(self) -> pd.DataFrame:
        """Spalten: nummer, bezeichnung, warengruppe (soweit die Quelle sie kennt)."""
        ...
