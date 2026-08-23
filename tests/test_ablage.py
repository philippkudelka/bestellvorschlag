"""M1: Ablage — anlegen, schreiben, lesen, keine Dubletten bei Doppelimport."""

import pandas as pd

from bv.ablage import Ablage


def _neue_ablage(tmp_path):
    return Ablage(tmp_path / "test.sqlite")


def test_anlegen_schreiben_lesen(tmp_path):
    with _neue_ablage(tmp_path) as ab:
        ab.schreibe("filiale", pd.DataFrame(
            [{"nummer": 1, "name": "Stammhaus", "ort": "Rosenheim"}]))
        df = ab.lese("SELECT * FROM filiale")
        assert len(df) == 1
        assert df.loc[0, "name"] == "Stammhaus"


def test_doppelimport_erzeugt_keine_dubletten(tmp_path):
    zeilen = pd.DataFrame([
        {"datum": "2026-08-20", "filiale": 1, "artikel": "00101", "menge": 140,
         "erster_verkauf": "06:02", "letzter_verkauf": "17:40"},
        {"datum": "2026-08-20", "filiale": 1, "artikel": "00102", "menge": 55,
         "erster_verkauf": "06:10", "letzter_verkauf": "17:55"},
    ])
    with _neue_ablage(tmp_path) as ab:
        n1 = ab.schreibe("verkauf", zeilen)
        n2 = ab.schreibe("verkauf", zeilen)  # derselbe Import noch einmal
        assert n1 == 2
        assert n2 == 0
        assert ab.wert("SELECT COUNT(*) FROM verkauf") == 2


def test_import_lauf_protokolliert(tmp_path):
    with _neue_ablage(tmp_path) as ab:
        ab.protokolliere_import("synthetisch", "verkauf_2026-08.csv", 100, 98, 2, "2 leere Zeilen")
        df = ab.lese("SELECT * FROM import_lauf")
        assert len(df) == 1
        assert df.loc[0, "zeilen_verworfen"] == 2


def test_oeffnungszeiten_mit_pause_und_schliessung(tmp_path):
    with _neue_ablage(tmp_path) as ab:
        ab.schreibe("filiale", pd.DataFrame(
            [{"nummer": 4, "name": "Marienplatz", "ort": "Bad Aibling"}]))
        # Montag mit Mittagspause
        ab.schreibe("oeffnungszeit", pd.DataFrame([
            {"filiale": 4, "gueltig_ab": "2023-01-01", "gueltig_bis": "2026-12-31",
             "wochentag": 0, "von": "06:00", "bis": "12:30"},
            {"filiale": 4, "gueltig_ab": "2023-01-01", "gueltig_bis": "2026-12-31",
             "wochentag": 0, "von": "14:00", "bis": "18:00"},
        ]))
        # 2026-08-17 ist ein Montag
        assert ab.oeffnung(4, "2026-08-17") == [("06:00", "12:30"), ("14:00", "18:00")]
        assert ab.ladenschluss(4, "2026-08-17") == "18:00"
        assert ab.oeffnungsminuten(4, "2026-08-17") == 390 + 240
        # Dienstag: kein Eintrag -> geschlossen
        assert ab.oeffnung(4, "2026-08-18") == []
        # Umbau uebersteuert den Wochenplan
        ab.schreibe("ereignis", pd.DataFrame([
            {"datum_von": "2026-08-17", "datum_bis": "2026-08-23", "filialen": "4",
             "bezeichnung": "Umbau", "art": "geschlossen", "wirkung": 0.0},
        ]))
        assert ab.oeffnung(4, "2026-08-17") == []
