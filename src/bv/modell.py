"""Quantilmodelle: je Warengruppe und Quantil ein Modell.

LightGBM mit objective='quantile'; Rueckfallebene (per Konfiguration):
sklearn HistGradientBoostingRegressor mit loss='quantile' — hinter
derselben Schnittstelle. Modellstaende werden versioniert unter
modelle/JJJJ-MM-TT-HHMM/ gespeichert, mit metadaten.json.
"""

from __future__ import annotations

import json
import pickle
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from bv.ablage import Ablage, jetzt
from bv.konfiguration import PROJEKTWURZEL, Konfiguration
from bv.merkmale import MERKMALSLISTE, baue_merkmale

MODELL_VERZEICHNIS = PROJEKTWURZEL / "modelle"


def _neues_modell(backend: str, quantil: float, einstellungen: dict):
    n_baeume = int(einstellungen.get("n_estimators", 120))
    lernrate = float(einstellungen.get("learning_rate", 0.08))
    if backend == "lightgbm":
        import lightgbm as lgb

        return lgb.LGBMRegressor(
            objective="quantile", alpha=quantil,
            n_estimators=n_baeume, learning_rate=lernrate,
            num_leaves=63, min_child_samples=30, verbose=-1,
        )
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(
        loss="quantile", quantile=quantil,
        max_iter=n_baeume, learning_rate=lernrate,
    )


@dataclass
class ModellStand:
    """Ein geladener, versionierter Satz von Modellen."""

    name: str
    modelle: dict = field(default_factory=dict)   # (warengruppe, quantil) -> Modell
    metadaten: dict = field(default_factory=dict)

    def vorhersage(self, merkmale: pd.DataFrame, quantil: float) -> np.ndarray:
        """Sagt fuer jede Zeile das gewuenschte Quantil vorher. Zeilen einer
        Warengruppe ohne Modell bekommen NaN (Rueckfall regelt der Aufrufer)."""
        ergebnis = np.full(len(merkmale), np.nan)
        x = merkmale[MERKMALSLISTE]
        for wg, maske in merkmale.groupby("warengruppe", observed=True).groups.items():
            modell = self.modelle.get((wg, quantil))
            if modell is None:
                continue
            werte = modell.predict(x.loc[maske])
            ergebnis[merkmale.index.get_indexer(maske)] = np.maximum(werte, 0.0)
        return ergebnis


def trainiere(ablage: Ablage, konfig: Konfiguration, stichtag: date) -> str:
    """Trainiert alle Modelle auf Nachfrage bis einschliesslich stichtag
    und speichert einen neuen Modellstand. Gibt den Standnamen zurueck."""
    fenster = int(konfig.einstellungen.get("modell", {}).get("trainingsfenster_tage", 400))
    von = (pd.Timestamp(stichtag) - pd.Timedelta(days=fenster)).date().isoformat()
    bis = stichtag.isoformat()

    tage = ablage.lese(
        "SELECT DISTINCT datum FROM nachfrage WHERE datum >= ? AND datum <= ?"
        " ORDER BY datum", (von, bis))["datum"].tolist()
    if not tage:
        raise ValueError(f"Keine Nachfragedaten zwischen {von} und {bis}")
    daten = baue_merkmale(ablage, konfig, tage, mit_ziel=True)
    daten = daten.dropna(subset=["ziel"])

    backend = konfig.modell_backend
    einstellungen = konfig.einstellungen.get("modell", {})
    quantile = konfig.quantile
    modelle: dict = {}
    kennzahlen: dict = {}
    for wg, gruppe in daten.groupby("warengruppe", observed=True):
        x = gruppe[MERKMALSLISTE]
        y = gruppe["ziel"]
        for q in quantile:
            modell = _neues_modell(backend, q, einstellungen)
            modell.fit(x, y)
            modelle[(wg, q)] = modell
            rest = y - np.maximum(modell.predict(x), 0)
            kennzahlen[f"{wg}_q{q}"] = {
                "zeilen": int(len(y)),
                "pinball": float(np.mean(np.maximum(q * rest, (q - 1) * rest))),
            }

    name = jetzt().strftime("%Y-%m-%d-%H%M")
    verz = MODELL_VERZEICHNIS / name
    verz.mkdir(parents=True, exist_ok=True)
    with open(verz / "modelle.pickle", "wb") as f:
        pickle.dump(modelle, f)
    metadaten = {
        "trainingszeitraum": [von, bis],
        "zeilen": int(len(daten)),
        "backend": backend,
        "quantile": quantile,
        "merkmale": MERKMALSLISTE,
        "kennzahlen": kennzahlen,
        "paketversionen": _paketversionen(backend),
        "erstellt": jetzt().isoformat(timespec="seconds"),
    }
    with open(verz / "metadaten.json", "w", encoding="utf-8") as f:
        json.dump(metadaten, f, indent=2, ensure_ascii=False)
    return name


def _paketversionen(backend: str) -> dict:
    import sklearn

    versionen = {"pandas": pd.__version__, "numpy": np.__version__,
                 "scikit-learn": sklearn.__version__}
    if backend == "lightgbm":
        import lightgbm

        versionen["lightgbm"] = lightgbm.__version__
    return versionen


def lade_neuesten_stand(verzeichnis: Path | None = None) -> ModellStand | None:
    verz = verzeichnis or MODELL_VERZEICHNIS
    if not verz.exists():
        return None
    staende = sorted(p for p in verz.iterdir()
                     if p.is_dir() and (p / "modelle.pickle").exists())
    if not staende:
        return None
    neuester = staende[-1]
    with open(neuester / "modelle.pickle", "rb") as f:
        modelle = pickle.load(f)
    with open(neuester / "metadaten.json", encoding="utf-8") as f:
        metadaten = json.load(f)
    return ModellStand(name=neuester.name, modelle=modelle, metadaten=metadaten)


def trainiere_falls_faellig(
    ablage: Ablage, konfig: Konfiguration, heute: date, erzwingen: bool = False
) -> str | None:
    """Woechentliches Training (Wochentag aus der Konfiguration); sofort,
    wenn noch gar kein Stand existiert oder erzwingen gesetzt ist."""
    faelliger_wochentag = int(
        konfig.einstellungen.get("nachtlauf", {}).get("training_wochentag", 0))
    vorhanden = lade_neuesten_stand()
    if not erzwingen and vorhanden is not None and heute.weekday() != faelliger_wochentag:
        return None
    return trainiere(ablage, konfig, heute)
