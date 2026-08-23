"""M4: Zensierungskorrektur gegen die Simulationswahrheit.

Der Beweis, dass die Korrektur funktioniert: an zensierten Tagen liegt die
geschaetzte Nachfrage DEUTLICH naeher an der Wahrheit als der rohe Verkauf.
Die gemessene Verbesserung steht als Untergrenze im Test, damit sie nicht
unbemerkt kaputtgeht.
"""

from datetime import date

import numpy as np
import pytest

from bv.ablage import Ablage
from bv.einlesen import importiere_synthetisch
from bv.konfiguration import lade_konfiguration
from bv.simulation.export import schreibe_exporte
from bv.simulation.welt import erzeuge_welt
from bv.zensierung import korrigiere_zensierung, schaetze_tageskurven


@pytest.fixture(scope="module")
def welt_mit_datenbank(tmp_path_factory):
    verz = tmp_path_factory.mktemp("synthetisch")
    konfig = lade_konfiguration()
    konfig.einstellungen = dict(konfig.einstellungen)
    konfig.einstellungen["synthetisch"] = {"verzeichnis": str(verz)}
    welt = erzeuge_welt(konfig, date(2026, 1, 1), date(2026, 5, 31), seed=42)
    schreibe_exporte(welt, verz)
    ablage = Ablage(tmp_path_factory.mktemp("db") / "test.sqlite")
    importiere_synthetisch(ablage, konfig)
    korrigiere_zensierung(ablage, konfig)
    yield konfig, welt, ablage
    ablage.schliessen()


def test_kurven_werden_aus_stundendaten_geschaetzt(welt_mit_datenbank):
    _, _, ablage = welt_mit_datenbank
    kurven = schaetze_tageskurven(ablage)
    # fuer gaengige Artikel gibt es eigene Kurven aus Stundendaten
    kurve, herkunft = kurven.kurve(1, "00101")
    assert herkunft == "eigene Stundendaten"
    # die Semmelkurve ist frueh und steil: zur Tagesmitte ist das meiste weg
    assert kurven.anteil(1, "00101", 0.5) > 0.75
    # monoton steigend von 0 auf 1
    assert kurve[0] == 0.0 and kurve[-1] == 1.0
    assert (np.diff(kurve) >= 0).all()


def test_geschaetzte_nachfrage_naeher_an_der_wahrheit(welt_mit_datenbank):
    """Kernnachweis des Systems (M4)."""
    _, welt, ablage = welt_mit_datenbank
    wahr = welt.tage[welt.tage["ausverkauft"] == 1][
        ["datum", "filiale", "artikel", "nachfrage", "verkauf"]]
    geschaetzt = ablage.lese(
        "SELECT datum, filiale, artikel, menge, ist_geschaetzt FROM nachfrage")
    beide = wahr.merge(geschaetzt, on=["datum", "filiale", "artikel"])
    assert len(beide) > 200

    fehler_roh = np.abs(beide["verkauf"] - beide["nachfrage"])
    fehler_korrigiert = np.abs(beide["menge"] - beide["nachfrage"])
    mae_roh = fehler_roh.mean()
    mae_korrigiert = fehler_korrigiert.mean()
    verbesserung = 1 - mae_korrigiert / mae_roh

    # Ein grosser Teil der zensierten Tage wird auch erkannt
    assert beide["ist_geschaetzt"].mean() > 0.6
    # UNTERGRENZE: gemessene Verbesserung darf nicht unbemerkt kaputtgehen.
    # Gemessen bei Einfuehrung (2026-08-23, seed 42, n=22119): Erkennung 99 %,
    # MAE roh 4.32 Stueck, korrigiert 1.87 Stueck -> Verbesserung 56.6 %.
    assert verbesserung > 0.45, (
        f"Zensierungskorrektur zu schwach: MAE roh {mae_roh:.2f}, "
        f"korrigiert {mae_korrigiert:.2f}, Verbesserung {verbesserung:.0%}")


def test_unzensierte_tage_bleiben_unangetastet(welt_mit_datenbank):
    _, welt, ablage = welt_mit_datenbank
    normal = welt.tage[(welt.tage["ausverkauft"] == 0) & (welt.tage["retoure"] > 0)][
        ["datum", "filiale", "artikel", "verkauf"]]
    geschaetzt = ablage.lese("SELECT datum, filiale, artikel, menge, ist_geschaetzt"
                             " FROM nachfrage")
    beide = normal.merge(geschaetzt, on=["datum", "filiale", "artikel"])
    # Tage mit Retoure koennen kein Ausverkauf sein -> Nachfrage = Verkauf
    assert (beide["ist_geschaetzt"] == 0).all()
    assert (beide["menge"] == beide["verkauf"]).all()
