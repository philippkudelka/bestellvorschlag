"""M5: Merkmalsbau (kein Blick in die Zukunft) und Quantilmodelle."""

from datetime import date

import numpy as np
import pytest

from bv import modell as modell_modul
from bv.ablage import Ablage
from bv.einlesen import importiere_synthetisch
from bv.konfiguration import lade_konfiguration
from bv.merkmale import MERKMALSLISTE, baue_merkmale
from bv.modell import lade_neuesten_stand, trainiere
from bv.simulation.export import schreibe_exporte
from bv.simulation.welt import erzeuge_welt
from bv.zensierung import korrigiere_zensierung

LIEFERTAG = "2026-05-30"


@pytest.fixture(scope="module")
def datenbank(tmp_path_factory):
    verz = tmp_path_factory.mktemp("synthetisch")
    konfig = lade_konfiguration()
    konfig.einstellungen = dict(konfig.einstellungen)
    konfig.einstellungen["synthetisch"] = {"verzeichnis": str(verz)}
    konfig.einstellungen["modell"] = {"backend": "lightgbm", "n_estimators": 40,
                                      "learning_rate": 0.1,
                                      "trainingsfenster_tage": 400}
    welt = erzeuge_welt(konfig, date(2026, 1, 1), date(2026, 5, 31), seed=7)
    schreibe_exporte(welt, verz)
    pfad = tmp_path_factory.mktemp("db") / "test.sqlite"
    ablage = Ablage(pfad)
    importiere_synthetisch(ablage, konfig)
    korrigiere_zensierung(ablage, konfig)
    yield konfig, ablage, pfad
    ablage.schliessen()


def test_kein_blick_in_die_zukunft(datenbank, tmp_path):
    """Bewusster Einschleusungsversuch: Nachfrage an T und T-1 wird massiv
    verfaelscht. Aendert sich irgendein Merkmal fuer Liefertag T, ist Zukunft
    eingeflossen — dann muss dieser Test fehlschlagen."""
    konfig, ablage, _ = datenbank
    vorher = baue_merkmale(ablage, konfig, [LIEFERTAG], mit_ziel=False)

    # Zukunft einschleusen: T und T-1 um Faktor 100 verfaelschen
    ablage.verbindung.execute(
        "UPDATE nachfrage SET menge = menge * 100 WHERE datum IN (?, ?)",
        (LIEFERTAG, "2026-05-29"))
    ablage.verbindung.commit()
    try:
        nachher = baue_merkmale(ablage, konfig, [LIEFERTAG], mit_ziel=False)
    finally:
        ablage.verbindung.execute(
            "UPDATE nachfrage SET menge = menge / 100 WHERE datum IN (?, ?)",
            (LIEFERTAG, "2026-05-29"))
        ablage.verbindung.commit()

    assert len(vorher) == len(nachher) > 0
    for spalte in MERKMALSLISTE:
        gleich = (vorher[spalte].fillna(-9e9).to_numpy()
                  == nachher[spalte].fillna(-9e9).to_numpy())
        assert gleich.all(), f"Merkmal '{spalte}' nutzt Daten nach T-2 — Zukunftsleck!"


def test_t_minus_2_fliesst_ein(datenbank):
    """Gegenprobe: Daten von T-2 DUERFEN einfliessen — sonst waere der
    Zukunftstest trivial erfuellbar."""
    konfig, ablage, _ = datenbank
    vorher = baue_merkmale(ablage, konfig, [LIEFERTAG], mit_ziel=False)
    ablage.verbindung.execute(
        "UPDATE nachfrage SET menge = menge * 100 WHERE datum = ?", ("2026-05-28",))
    ablage.verbindung.commit()
    try:
        nachher = baue_merkmale(ablage, konfig, [LIEFERTAG], mit_ziel=False)
    finally:
        ablage.verbindung.execute(
            "UPDATE nachfrage SET menge = menge / 100 WHERE datum = ?", ("2026-05-28",))
        ablage.verbindung.commit()
    assert not np.allclose(vorher["mittel_3"].to_numpy(), nachher["mittel_3"].to_numpy())


def test_training_speichern_laden_vorhersagen(datenbank, tmp_path, monkeypatch):
    konfig, ablage, _ = datenbank
    monkeypatch.setattr(modell_modul, "MODELL_VERZEICHNIS", tmp_path / "modelle")
    name = trainiere(ablage, konfig, date(2026, 5, 28))
    stand = lade_neuesten_stand(tmp_path / "modelle")
    assert stand is not None and stand.name == name
    assert stand.metadaten["merkmale"] == MERKMALSLISTE

    merkmale = baue_merkmale(ablage, konfig, [LIEFERTAG], mit_ziel=False)
    v80 = stand.vorhersage(merkmale, 0.8)
    v50 = stand.vorhersage(merkmale, 0.5)
    bekannt = ~np.isnan(v80)
    assert bekannt.mean() > 0.9
    assert (v80 >= 0)[bekannt].all()
    # das hoehere Quantil liegt im Schnitt ueber dem Median
    assert v80[bekannt].mean() > v50[bekannt].mean()
    # und die Vorhersagen sind plausibel nah an den Rueckblicken
    plausibel = merkmale["mittel_7"].to_numpy()[bekannt]
    assert np.corrcoef(v50[bekannt], plausibel)[0, 1] > 0.8
