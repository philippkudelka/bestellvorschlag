"""M3: Import der B.I.T.-aehnlichen Dateien und Datenqualitaetsbericht."""

from datetime import date
from pathlib import Path

import pytest

from bv.ablage import Ablage
from bv.konfiguration import lade_konfiguration
from bv.quellen.bit_csv import BitCsvQuelle
from bv.quellen.synthetisch import SynthetischeQuelle, lese_umsatzdatei
from bv.simulation.export import schreibe_exporte
from bv.simulation.welt import erzeuge_welt


@pytest.fixture(scope="module")
def kleine_welt(tmp_path_factory):
    """Drei Monate simulieren und exportieren — geteilt von allen Tests."""
    verz = tmp_path_factory.mktemp("synthetisch")
    konfig = lade_konfiguration()
    welt = erzeuge_welt(konfig, date(2026, 3, 1), date(2026, 5, 31), seed=11)
    protokoll = schreibe_exporte(welt, verz)
    return konfig, welt, verz, protokoll


def test_umsatzdatei_wird_sauber_gelesen(kleine_welt):
    _, welt, verz, protokoll = kleine_welt
    pfad = sorted(Path(verz).glob("umsatz_*.csv"))[10]
    datum, df, stat = lese_umsatzdatei(pfad)
    assert len(datum) == 10 and datum.count("-") == 2
    # Artikelnummern bleiben Text mit fuehrenden Nullen
    assert df["artikel"].str.startswith("0").all()
    # keine Dubletten trotz absichtlich doppelter Zeilen
    assert not df.duplicated(["filiale", "artikel"]).any()


def test_quelle_liefert_kanonische_daten(kleine_welt):
    _, welt, verz, _ = kleine_welt
    quelle = SynthetischeQuelle(verz)
    vk = quelle.lade_verkaeufe("2026-04-01", "2026-04-07")
    assert set(vk.columns) == {"datum", "filiale", "artikel", "menge",
                               "erster_verkauf", "letzter_verkauf"}
    assert vk["datum"].between("2026-04-01", "2026-04-07").all()
    ret = quelle.lade_retouren("2026-04-01", "2026-04-07")
    assert (ret["erfasst_am"] == ret["datum"]).all()


def test_import_ist_idempotent_und_findet_fehler(kleine_welt, tmp_path):
    konfig, welt, verz, protokoll = kleine_welt
    from bv import einlesen
    from bv.qualitaet import erzeuge_bericht

    # absoluter Pfad: PROJEKTWURZEL / absolut ergibt den absoluten Pfad
    konfig.einstellungen = dict(konfig.einstellungen)
    konfig.einstellungen["synthetisch"] = {"verzeichnis": str(verz)}

    with Ablage(tmp_path / "test.sqlite") as ablage:
        einlesen.importiere_synthetisch(ablage, konfig)
        n1 = ablage.wert("SELECT COUNT(*) FROM verkauf")
        stat2 = einlesen.importiere_synthetisch(ablage, konfig)
        n2 = ablage.wert("SELECT COUNT(*) FROM verkauf")
        assert n1 > 0
        assert n1 == n2, "Doppelter Import darf nichts verdoppeln"
        assert stat2["dateien_neu"] == 0

        # Wahrheit ist da, aber getrennt
        assert ablage.wert("SELECT COUNT(*) FROM wahrheit") > 0

        bericht = erzeuge_bericht(ablage, tmp_path / "bericht.md").read_text(encoding="utf-8")
        # findet die absichtlich fehlenden Tage
        for tag in protokoll["fehlende_tage"]:
            assert tag in bericht
        # findet den Nummernwechsel nur, wenn er im Zeitraum liegt
        if protokoll["zeitraum"][1] >= protokoll["nummernwechsel"]["ab"]:
            assert "Krapfen" in bericht


def test_bit_adapter_ist_ehrlicher_platzhalter():
    quelle = BitCsvQuelle({"bit_csv": {"spalten": {}}})
    with pytest.raises(NotImplementedError) as fehler:
        quelle.lade_verkaeufe("2026-01-01", "2026-01-31")
    assert "letzter_verkauf" in str(fehler.value)
