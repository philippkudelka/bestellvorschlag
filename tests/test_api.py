"""M9: Endpunkte der Tablet-Oberflaeche."""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from bv import api as api_modul
from bv import modell as modell_modul
from bv.ablage import Ablage
from bv.einlesen import importiere_synthetisch
from bv.konfiguration import lade_konfiguration
from bv.modell import trainiere
from bv.simulation.export import schreibe_exporte
from bv.simulation.welt import erzeuge_welt
from bv.vorschlag import erzeuge_vorschlaege
from bv.zensierung import korrigiere_zensierung

LIEFERTAG = "2026-05-30"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    verz = tmp_path_factory.mktemp("synthetisch")
    konfig = lade_konfiguration()
    konfig.einstellungen = dict(konfig.einstellungen)
    konfig.einstellungen["synthetisch"] = {"verzeichnis": str(verz)}
    konfig.einstellungen["modell"] = {"backend": "lightgbm", "n_estimators": 30,
                                      "learning_rate": 0.12,
                                      "trainingsfenster_tage": 400}
    db_pfad = tmp_path_factory.mktemp("db") / "test.sqlite"
    konfig.einstellungen["datenbank"] = str(db_pfad)

    welt = erzeuge_welt(konfig, date(2026, 2, 1), date(2026, 5, 31), seed=13)
    schreibe_exporte(welt, verz)
    with Ablage(db_pfad) as ablage:
        importiere_synthetisch(ablage, konfig)
        korrigiere_zensierung(ablage, konfig)
        alt = modell_modul.MODELL_VERZEICHNIS
        modell_modul.MODELL_VERZEICHNIS = tmp_path_factory.mktemp("modelle")
        trainiere(ablage, konfig, date(2026, 5, 28))
        erzeuge_vorschlaege(ablage, konfig, LIEFERTAG)

    # API auf die Testdatenbank umbiegen
    api_modul._konfig = lambda: konfig
    api_modul._ablage = lambda: Ablage(db_pfad)
    yield TestClient(api_modul.app)
    modell_modul.MODELL_VERZEICHNIS = alt


def test_filialen(client):
    antwort = client.get("/api/filialen")
    assert antwort.status_code == 200
    assert len(antwort.json()) == 10


def test_tagesuebersicht(client):
    daten = client.get(f"/api/tagesuebersicht?liefertag={LIEFERTAG}").json()
    assert daten["liefertag"] == LIEFERTAG
    assert len(daten["filialen"]) == 10
    fertige = [f for f in daten["filialen"] if f["zustand"] == "fertig"]
    assert len(fertige) == 10  # Samstag, alle offen, alle mit Vorschlag


def test_vorschlag_und_bestellung(client):
    daten = client.get(f"/api/vorschlag?filiale=1&liefertag={LIEFERTAG}").json()
    assert daten["filiale"]["nummer"] == 1
    assert daten["oeffnung"] != "geschlossen"
    assert len(daten["positionen"]) > 30
    erste = daten["positionen"][0]
    assert erste["vorschlag"] >= 0
    assert erste["begruendung"]

    antwort = client.post("/api/bestellung", json={
        "liefertag": LIEFERTAG, "filiale": 1,
        "positionen": [{"artikel": erste["artikel"], "menge": 99}],
    })
    assert antwort.status_code == 200
    daten2 = client.get(f"/api/vorschlag?filiale=1&liefertag={LIEFERTAG}").json()
    assert daten2["positionen"][0]["bestellt"] == 99


def test_einstellungen_aendern_wirkt_sofort(client):
    daten = client.get(f"/api/einstellungen?filiale=1&liefertag={LIEFERTAG}").json()
    artikel = daten["artikel"][0]
    # Mengenvorschau je Klasse vorhanden (Modell ist geladen)
    assert set(artikel["menge_je_klasse"]) == {"A", "B", "C"}
    assert artikel["menge_je_klasse"]["A"] >= artikel["menge_je_klasse"]["C"]

    neu = "A" if artikel["servicegrad"] != "A" else "C"
    antwort = client.put("/api/einstellungen", json={
        "filiale": 1, "artikel": artikel["artikel"], "servicegrad": neu})
    assert antwort.status_code == 200
    danach = client.get("/api/einstellungen?filiale=1&liefertag=2026-12-31").json()
    passend = [a for a in danach["artikel"] if a["artikel"] == artikel["artikel"]]
    assert passend[0]["servicegrad"] == neu


def test_ereignisse(client):
    antwort = client.post("/api/ereignisse", json={
        "datum_von": "2026-06-05", "datum_bis": "2026-06-06",
        "filialen": "3", "bezeichnung": "Testfest", "wirkung": 1.5})
    assert antwort.status_code == 200
    liste = client.get("/api/ereignisse").json()
    assert any(e["bezeichnung"] == "Testfest" for e in liste)


def test_zustand(client):
    daten = client.get("/api/zustand").json()
    assert daten["modellstand"] is not None
    assert daten["letzter_verkaufstag"] == "2026-05-31"


def test_startseite_liefert_html(client):
    antwort = client.get("/")
    assert antwort.status_code == 200
    assert "Tagesübersicht" in antwort.text
    for datei in ("stil.css", "app.js"):
        assert client.get(f"/web/{datei}").status_code == 200
