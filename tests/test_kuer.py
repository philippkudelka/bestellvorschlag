"""Kuer: Mehrtagesartikel, Ausreisserdaempfung, B.I.T.-Zuordnungsvorschlag."""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skripte"))

from bit_zuordnung import schlage_zuordnung_vor  # noqa: E402

from bv.ablage import Ablage  # noqa: E402
from bv.konfiguration import Konfiguration  # noqa: E402
from bv.simulation.export import schreibe_exporte  # noqa: E402
from bv.simulation.welt import erzeuge_welt  # noqa: E402
from bv.vorschlag import _mehrtages_vorschlaege  # noqa: E402


def test_mehrtagesartikel_beruecksichtigt_uebertrag(tmp_path):
    with Ablage(tmp_path / "t.sqlite") as ab:
        ab.schreibe("filiale", pd.DataFrame(
            [{"nummer": 1, "name": "Test", "ort": "Rosenheim"}]))
        ab.schreibe("oeffnungszeit", pd.DataFrame([
            {"filiale": 1, "gueltig_ab": "2023-01-01", "gueltig_bis": "2027-12-31",
             "wochentag": wt, "von": "06:00", "bis": "18:00"} for wt in range(7)]))
        ab.schreibe("artikel", pd.DataFrame([{
            "nummer": "00601", "bezeichnung": "Apfelkuchen", "warengruppe": "Kuchen",
            "im_umfang": 0, "mehrtagesartikel": 1, "preis": 2.4, "herstellkosten": 0.8}]))
        ab.schreibe("einstellung", pd.DataFrame([{
            "filiale": 1, "artikel": "00601", "servicegrad": "B",
            "zielretoure_prozent": None, "aktiv_ab": "2023-01-01"}]))
        # vier gleiche Wochentage mit Verkauf 20 -> Zielbestand 20 * 1.15 = 23
        verkaufstage = ["2026-08-15", "2026-08-08", "2026-08-01", "2026-07-25"]
        ab.schreibe("verkauf", pd.DataFrame([
            {"datum": t, "filiale": 1, "artikel": "00601", "menge": 20,
             "erster_verkauf": "07:00", "letzter_verkauf": "17:00"}
            for t in verkaufstage]))
        # Vortag: 18 geliefert, 13 verkauft -> Uebertrag 5
        ab.schreibe("lieferung", pd.DataFrame([
            {"datum": "2026-08-21", "filiale": 1, "artikel": "00601", "menge": 18}]))
        ab.schreibe("verkauf", pd.DataFrame([
            {"datum": "2026-08-21", "filiale": 1, "artikel": "00601", "menge": 13,
             "erster_verkauf": "07:00", "letzter_verkauf": "17:00"}]))

        konfig = Konfiguration(einstellungen={})
        zeilen = _mehrtages_vorschlaege(ab, konfig, "2026-08-22", "2026-08-21T22:00:00")
        assert len(zeilen) == 1
        z = zeilen[0]
        # Zielbestand 23, Uebertrag 5 -> 18
        assert z["menge"] == 18
        assert "Uebertrag" in z["begruendung"]
        assert z["modellstand"] == "bestandsrechnung"


def test_bit_zuordnung_findet_spalten(tmp_path):
    konfig_mini = Konfiguration(
        filialen=[{
            "nummer": 1, "name": "Test", "ort": "Rosenheim", "grundniveau": 1.0,
            "trend_prozent_pro_jahr": 0.0,
            "oeffnungszeiten": {t: [["06:00", "18:00"]] for t in
                                ["mo", "di", "mi", "do", "fr", "sa"]} | {"so": None},
        }],
        artikel=[{
            "nummer": "00101", "bezeichnung": "Semmel", "warengruppe": "Semmeln",
            "im_umfang": True, "mehrtagesartikel": False, "preis": 0.45,
            "herstellkosten": 0.12, "servicegrad": "A", "grundmenge": 150,
            "kurve": "frueh", "wetter": {"temperatur": 0.004, "regen": -0.1},
        }],
        einstellungen={},
    )
    welt = erzeuge_welt(konfig_mini, date(2026, 5, 1), date(2026, 5, 14), seed=2)
    schreibe_exporte(welt, tmp_path)
    datei = sorted(tmp_path.glob("umsatz_*.csv"))[5]
    ergebnis = schlage_zuordnung_vor(datei)
    s = ergebnis["spalten"]
    assert s["filiale"] == "Fil."
    assert s["artikel"] == "Art.Nr"
    assert s["liefermenge"] == "Vk. Men"
    assert s["verkauf"] == "Verkauft"
    assert s["retoure"] == "Retour"
    assert s["letzter_verkauf"] == "letz. Ver"
    assert ergebnis["trennzeichen"] == ";"
