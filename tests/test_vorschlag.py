"""M6: Servicegrad-Abbildung und Vorschlag mit Begruendung."""

from datetime import date

import pytest

from bv import modell as modell_modul
from bv.ablage import Ablage
from bv.einlesen import importiere_synthetisch
from bv.konfiguration import lade_konfiguration
from bv.modell import trainiere
from bv.servicegrad import newsvendor_quantil
from bv.simulation.export import schreibe_exporte
from bv.simulation.welt import erzeuge_welt
from bv.vorschlag import erzeuge_vorschlaege
from bv.zensierung import korrigiere_zensierung

LIEFERTAG = "2026-05-30"  # Samstag: alle Filialen offen


@pytest.fixture(scope="module")
def system(tmp_path_factory):
    verz = tmp_path_factory.mktemp("synthetisch")
    konfig = lade_konfiguration()
    konfig.einstellungen = dict(konfig.einstellungen)
    konfig.einstellungen["synthetisch"] = {"verzeichnis": str(verz)}
    konfig.einstellungen["modell"] = {"backend": "lightgbm", "n_estimators": 40,
                                      "learning_rate": 0.1,
                                      "trainingsfenster_tage": 400}
    welt = erzeuge_welt(konfig, date(2026, 1, 1), date(2026, 5, 31), seed=7)
    schreibe_exporte(welt, verz)
    ablage = Ablage(tmp_path_factory.mktemp("db") / "test.sqlite")
    importiere_synthetisch(ablage, konfig)
    korrigiere_zensierung(ablage, konfig)

    alt = modell_modul.MODELL_VERZEICHNIS
    modell_modul.MODELL_VERZEICHNIS = tmp_path_factory.mktemp("modelle")
    trainiere(ablage, konfig, date(2026, 5, 28))
    yield konfig, ablage
    modell_modul.MODELL_VERZEICHNIS = alt
    ablage.schliessen()


def test_vorschlaege_fuer_alle_offenen_filialen(system):
    konfig, ablage = system
    stat = erzeuge_vorschlaege(ablage, konfig, LIEFERTAG)
    assert stat["filialen"] == 10  # Samstag: alle offen
    assert stat["rueckfall"] == 0

    df = ablage.lese(
        "SELECT * FROM vorschlag WHERE liefertag = ?", (LIEFERTAG,))
    assert (df["begruendung"].str.len() > 5).all(), "jede Zeile braucht eine Begruendung"
    assert (df["menge"] >= 0).all()
    # Servicegrad A (Semmel 00101) bekommt das 0.95er-Quantil
    semmel = df[df["artikel"] == "00101"]
    assert (semmel["quantil"] == 0.95).all()
    # Sonntagsfiliale 3 schliesst frueh, hat aber Samstag Vorschlaege
    assert (df["filiale"] == 3).any()


def test_sonntag_nur_offene_filialen(system):
    konfig, ablage = system
    stat = erzeuge_vorschlaege(ablage, konfig, "2026-05-31")  # Sonntag
    assert stat["filialen"] == 4  # nur Filialen 1, 3, 6, 9 haben Sonntagsoeffnung


def test_rueckfall_ohne_modell(system):
    """Modell abgeschaltet: trotzdem Vorschlaege, ehrlich etikettiert."""
    konfig, ablage = system
    stat = erzeuge_vorschlaege(ablage, konfig, LIEFERTAG, modell_abschalten=True)
    assert stat["anzahl"] > 0
    assert stat["rueckfall"] > 0
    df = ablage.lese(
        "SELECT * FROM vorschlag WHERE liefertag = ? AND modellstand = 'rueckfall'",
        (LIEFERTAG,))
    # alle Modellzeilen sind Rueckfall; Mehrtagesartikel gehen den eigenen
    # Bestandsrechenweg (modellstand 'bestandsrechnung')
    assert len(df) == stat["rueckfall"]
    assert df["begruendung"].str.contains("Notbehelf").all()


def test_newsvendor_quantil():
    assert newsvendor_quantil(0.45, 0.12) == pytest.approx((0.45 - 0.12) / 0.45)
    assert newsvendor_quantil(None, 0.12) is None
    assert newsvendor_quantil(0.0, 0.0) is None
