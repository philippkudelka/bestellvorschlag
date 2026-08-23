"""Adapter fuer den echten B.I.T.-64-Export von Ulmer Kemo — PLATZHALTER.

Es liegen noch keine echten Exportdateien vor. Wie der Export tatsaechlich
aussieht, weiss niemand. Dieser Adapter hat dieselbe Schnittstelle wie die
synthetische Quelle; sobald die erste echte Datei da ist, muss nur die
Spaltenzuordnung in konfiguration/einstellungen.yaml unter `bit_csv:`
ausgefuellt werden (Dokumentation der erwarteten Struktur: README.md).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PFLICHTFELDER = ["filiale", "artikel", "datum", "liefermenge", "verkauf",
                 "retoure", "letzter_verkauf"]

HINWEIS = (
    "Der echte B.I.T.-64-Export ist noch nicht angebunden. Es fehlen die "
    "Spaltenzuordnungen in konfiguration/einstellungen.yaml unter 'bit_csv:'. "
    f"Gebraucht werden mindestens: {', '.join(PFLICHTFELDER)} "
    "(je Verkaufstag, Filiale und Artikel; Artikelnummern als Text mit "
    "fuehrenden Nullen; 'letzter_verkauf' als Uhrzeit ist Pflicht fuer die "
    "Ausverkaufserkennung). Erwartete Dateiform siehe README.md."
)


class BitCsvQuelle:
    """DatenQuelle fuer echte B.I.T.-64-Dateien. Wirft NotImplementedError,
    solange die Spaltenzuordnung nicht konfiguriert ist."""

    def __init__(self, einstellungen: dict):
        self.konfig = einstellungen.get("bit_csv", {})

    def _pruefe_konfiguration(self) -> None:
        spalten = self.konfig.get("spalten") or {}
        fehlend = [f for f in PFLICHTFELDER if not spalten.get(f)]
        if fehlend or not self.konfig.get("verzeichnis"):
            raise NotImplementedError(HINWEIS + f" (offen: {', '.join(fehlend) or 'verzeichnis'})")

    def _lese(self) -> pd.DataFrame:  # pragma: no cover - erst mit echten Daten
        self._pruefe_konfiguration()
        spalten = self.konfig["spalten"]
        teile = []
        for pfad in sorted(Path(self.konfig["verzeichnis"]).glob("*.csv")):
            df = pd.read_csv(
                pfad,
                sep=self.konfig.get("trennzeichen", ";"),
                encoding=self.konfig.get("zeichensatz", "cp1252"),
                skiprows=self.konfig.get("kopfzeilen") or 0,
                decimal=",",
                dtype={spalten["artikel"]: str},
            )
            teile.append(df.rename(columns={v: k for k, v in spalten.items() if v}))
        return pd.concat(teile, ignore_index=True)

    def lade_verkaeufe(self, von: str, bis: str) -> pd.DataFrame:
        self._pruefe_konfiguration()
        raise NotImplementedError(HINWEIS)

    def lade_retouren(self, von: str, bis: str) -> pd.DataFrame:
        self._pruefe_konfiguration()
        raise NotImplementedError(HINWEIS)

    def lade_lieferungen(self, von: str, bis: str) -> pd.DataFrame:
        self._pruefe_konfiguration()
        raise NotImplementedError(HINWEIS)

    def lade_stammdaten(self) -> pd.DataFrame:
        self._pruefe_konfiguration()
        raise NotImplementedError(HINWEIS)
