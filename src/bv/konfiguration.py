"""Laden der Konfiguration aus konfiguration/*.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJEKTWURZEL = Path(__file__).resolve().parents[2]
KONFIG_VERZEICHNIS = PROJEKTWURZEL / "konfiguration"


@dataclass
class Konfiguration:
    """Gesamte Konfiguration: Filialen, Artikel, Einstellungen."""

    filialen: list[dict[str, Any]] = field(default_factory=list)
    artikel: list[dict[str, Any]] = field(default_factory=list)
    einstellungen: dict[str, Any] = field(default_factory=dict)

    # ---- bequeme Zugriffe ---------------------------------------------

    @property
    def quantil_je_servicegrad(self) -> dict[str, float]:
        return {
            k: float(v)
            for k, v in self.einstellungen.get(
                "servicegrade", {"A": 0.95, "B": 0.80, "C": 0.60}
            ).items()
        }

    @property
    def quantile(self) -> list[float]:
        return [float(q) for q in self.einstellungen.get("quantile", [0.5, 0.6, 0.8, 0.9, 0.95])]

    @property
    def zensierung(self) -> dict[str, float]:
        vorgabe = {
            "schwelle_retoure": 0.0,
            "mindestabstand_minuten": 10.0,
            "anteil_liefermenge": 0.98,
            "untergrenze_kurvenanteil": 0.35,
        }
        vorgabe.update(self.einstellungen.get("zensierung", {}))
        return {k: float(v) for k, v in vorgabe.items()}

    @property
    def datenbank_pfad(self) -> Path:
        return PROJEKTWURZEL / self.einstellungen.get("datenbank", "daten/bestellvorschlag.sqlite")

    @property
    def modell_backend(self) -> str:
        """'lightgbm' oder 'sklearn' (Rueckfallebene)."""
        return self.einstellungen.get("modell", {}).get("backend", "lightgbm")


def lade_konfiguration(verzeichnis: Path | None = None) -> Konfiguration:
    verz = verzeichnis or KONFIG_VERZEICHNIS
    return Konfiguration(
        filialen=_lade(verz / "filialen.yaml").get("filialen", []),
        artikel=_lade(verz / "artikel.yaml").get("artikel", []),
        einstellungen=_lade(verz / "einstellungen.yaml"),
    )


def _lade(pfad: Path) -> dict:
    if not pfad.exists():
        return {}
    with open(pfad, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
