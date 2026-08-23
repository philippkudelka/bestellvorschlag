"""Servicegrad: bildet die Klasse A/B/C je Filiale und Artikel auf ein
Quantil ab, mit Uebersteuerung aus der Tabelle `einstellung`.

Zusaetzlich das betriebswirtschaftliche Quantil nach dem Newsvendor-Ansatz:
q = (preis - herstellkosten) / preis — die Retoure einer Brezel kostet
weniger als die eines Stuecks Kuchen. Nur als Vergleichsspalte, nie als
Vorgabe.
"""

from __future__ import annotations

import pandas as pd

from bv.ablage import Ablage
from bv.konfiguration import Konfiguration


def einstellungen_je_filiale_artikel(
    ablage: Ablage, konfig: Konfiguration, stichtag: str
) -> pd.DataFrame:
    """Aktuelle Einstellung je (filiale, artikel) am Stichtag:
    servicegrad, quantil, zielretoure_prozent."""
    df = ablage.lese(
        """SELECT filiale, artikel, servicegrad, zielretoure_prozent, aktiv_ab
           FROM einstellung WHERE aktiv_ab <= ?""", (stichtag,))
    if df.empty:
        return df
    df = (df.sort_values("aktiv_ab")
            .groupby(["filiale", "artikel"], as_index=False).last())
    abbildung = konfig.quantil_je_servicegrad
    df["quantil"] = df["servicegrad"].map(abbildung)
    # Zielretoure uebersteuert die Klasse: wer 10 % Retoure will, bekommt
    # ungefaehr das 90-%-Quantil — gerundet auf das naechste trainierte.
    hat_ziel = df["zielretoure_prozent"].notna()
    if hat_ziel.any():
        trainierte = sorted(konfig.quantile)
        gewuenscht = 1.0 - df.loc[hat_ziel, "zielretoure_prozent"] / 100.0
        df.loc[hat_ziel, "quantil"] = gewuenscht.map(
            lambda q: min(trainierte, key=lambda t: abs(t - q)))
    return df


def newsvendor_quantil(preis: float | None, herstellkosten: float | None) -> float | None:
    """Betriebswirtschaftlich optimales Quantil, wenn Preis und Kosten bekannt."""
    if not preis or herstellkosten is None or preis <= 0:
        return None
    return max(0.0, min(1.0, (preis - herstellkosten) / preis))
