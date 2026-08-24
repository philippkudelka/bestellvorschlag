"""M8: Waechter und Rueckfallweg.

Kernszenario: das Modell wird absichtlich abgeschaltet — der Lauf liefert
trotzdem fuer alle offenen Filialen einen gekennzeichneten Rueckfallwert,
und der Waechter meldet den fehlenden Modellstand.
"""

from datetime import date

import pytest

from bv import modell as modell_modul
from bv import waechter as waechter_modul
from bv.ablage import Ablage
from bv.einlesen import importiere_synthetisch
from bv.konfiguration import lade_konfiguration
from bv.simulation.export import schreibe_exporte
from bv.simulation.welt import erzeuge_welt
from bv.vorschlag import erzeuge_vorschlaege
from bv.waechter import pruefe
from bv.zensierung import korrigiere_zensierung

LIEFERTAG = "2026-05-30"  # Samstag: alle Filialen offen


@pytest.fixture(scope="module")
def system(tmp_path_factory):
    verz = tmp_path_factory.mktemp("synthetisch")
    konfig = lade_konfiguration()
    konfig.einstellungen = dict(konfig.einstellungen)
    konfig.einstellungen["synthetisch"] = {"verzeichnis": str(verz)}
    welt = erzeuge_welt(konfig, date(2026, 3, 1), date(2026, 5, 31), seed=5)
    schreibe_exporte(welt, verz)
    ablage = Ablage(tmp_path_factory.mktemp("db") / "test.sqlite")
    importiere_synthetisch(ablage, konfig)
    korrigiere_zensierung(ablage, konfig)

    alt_modelle = modell_modul.MODELL_VERZEICHNIS
    alt_warnung = waechter_modul.WARNUNGSDATEI
    modell_modul.MODELL_VERZEICHNIS = tmp_path_factory.mktemp("modelle_leer")
    waechter_modul.WARNUNGSDATEI = tmp_path_factory.mktemp("warnung") / "WARNUNG.md"
    yield konfig, ablage
    modell_modul.MODELL_VERZEICHNIS = alt_modelle
    waechter_modul.WARNUNGSDATEI = alt_warnung
    ablage.schliessen()


def test_modell_abgeschaltet_rueckfall_fuer_alle_filialen(system):
    konfig, ablage = system
    stat = erzeuge_vorschlaege(ablage, konfig, LIEFERTAG, modell_abschalten=True)
    assert stat["filialen"] == 9, "auch ohne Modell: alle offenen Filialen versorgt"
    df = ablage.lese(
        "SELECT * FROM vorschlag WHERE liefertag = ? AND modellstand != 'bestandsrechnung'",
        (LIEFERTAG,))
    assert (df["modellstand"] == "rueckfall").all()
    assert df["begruendung"].str.contains("Notbehelf").all()
    assert (df["menge"] >= 0).all()

    # Der Waechter meldet den fehlenden Modellstand und schreibt WARNUNG.md
    meldungen = pruefe(ablage, konfig, LIEFERTAG)
    assert any("Modellstand" in m for m in meldungen)
    assert waechter_modul.WARNUNGSDATEI.exists()
    inhalt = waechter_modul.WARNUNGSDATEI.read_text(encoding="utf-8")
    assert "WARNUNG" in inhalt


def test_waechter_meldet_fehlende_vorschlaege(system):
    konfig, ablage = system
    meldungen = pruefe(ablage, konfig, "2026-06-06")  # dafuer gibt es keine Vorschlaege
    assert any("KEINE" in m for m in meldungen)


def test_waechter_meldet_datenluecke(system):
    konfig, ablage = system
    # Liefertag weit nach dem letzten Verkaufstag (2026-05-31)
    meldungen = pruefe(ablage, konfig, "2026-06-20")
    assert any("Luecke" in m for m in meldungen)
