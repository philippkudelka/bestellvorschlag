"""M2: Simulator — Ausverkaufslogik und Exportformat."""

from datetime import date

import numpy as np

from bv.konfiguration import Konfiguration
from bv.simulation.welt import (
    KURVEN,
    erzeuge_welt,
    kumulierter_anteil,
    minute_bei_kumuliertem_anteil,
    oeffnungsintervalle,
)


def test_ausverkaufsminute_bei_bekannter_nachfrage():
    """Bei bekannter Nachfrage und Liefermenge liegt letzter_verkauf an der
    erwarteten Minute: dort, wo die Kurve den Anteil L/(N+1) erreicht."""
    kurve = KURVEN["frueh"]
    intervalle = [(7 * 60, 11 * 60)]  # Sonntag 07:00-11:00
    nachfrage, liefermenge = 200, 100
    u = liefermenge / (nachfrage + 1.0)
    minute = minute_bei_kumuliertem_anteil(u, kurve, intervalle)
    # Halbe Nachfrage gedeckt, fruehe Kurve: deutlich vor der Tagesmitte
    assert 7 * 60 < minute < 9 * 60
    # Rueckrichtung: an dieser Minute ist der kumulierte Anteil wieder ~u
    position = (minute - intervalle[0][0]) / (intervalle[0][1] - intervalle[0][0])
    assert abs(kumulierter_anteil(kurve, position) - u) < 0.02


def test_ausverkaufsminute_mit_mittagspause():
    """Die Kurve laeuft ueber die Oeffnungsminuten — die Pause wird uebersprungen."""
    kurve = KURVEN["flach"]
    intervalle = [(6 * 60, 12 * 60), (14 * 60, 18 * 60)]
    minute_spaet = minute_bei_kumuliertem_anteil(0.95, kurve, intervalle)
    assert 14 * 60 <= minute_spaet <= 18 * 60  # nie in der Pause


def _mini_konfig() -> Konfiguration:
    return Konfiguration(
        filialen=[{
            "nummer": 1, "name": "Test", "ort": "Rosenheim", "grundniveau": 1.0,
            "trend_prozent_pro_jahr": 0.0,
            "oeffnungszeiten": {t: [["06:00", "18:00"]] for t in
                                ["mo", "di", "mi", "do", "fr"]} | {
                "sa": [["06:00", "13:00"]], "so": [["07:00", "11:00"]]},
        }],
        artikel=[{
            "nummer": "00101", "bezeichnung": "Semmel", "warengruppe": "Semmeln",
            "im_umfang": True, "mehrtagesartikel": False, "preis": 0.45,
            "herstellkosten": 0.12, "servicegrad": "A", "grundmenge": 150,
            "kurve": "frueh", "wetter": {"temperatur": 0.004, "regen": -0.1},
        }],
        einstellungen={},
    )


def test_welt_zensierung_stimmt():
    """verkauf = min(nachfrage, liefermenge); Retoure 0 genau bei Ausverkauf;
    letzter_verkauf liegt bei Ausverkauf frueher am Tag."""
    welt = erzeuge_welt(_mini_konfig(), date(2026, 5, 1), date(2026, 7, 31), seed=1)
    t = welt.tage
    assert (t["verkauf"] == np.minimum(t["nachfrage"], t["liefermenge"])).all()
    assert (t["retoure"] == t["liefermenge"] - t["verkauf"]).all()
    aus = t[t["ausverkauft"] == 1]
    voll = t[(t["ausverkauft"] == 0) & (t["verkauf"] > 5)]
    assert len(aus) > 3, "Simulation muss auch Ausverkaeufe erzeugen"
    # an Ausverkaufstagen endet der Verkauf im Schnitt frueher
    def minuten(s):
        return s.str.split(":").map(lambda x: int(x[0]) * 60 + int(x[1]))

    assert minuten(aus["letzter_verkauf"]).median() < minuten(voll["letzter_verkauf"]).median()


def test_besondere_oeffnungszeiten():
    fil = {
        "nummer": 5, "grundniveau": 1.0, "august_nachmittag_zu": True,
        "umbau": {"von": "2024-10-07", "bis": "2024-10-20"},
        "eroeffnet_am": "2024-01-15",
        "oeffnungszeiten": {"mo": [["06:00", "17:30"]], "so": None},
    }
    assert oeffnungsintervalle(fil, date(2024, 1, 8)) == []          # vor Eroeffnung
    assert oeffnungsintervalle(fil, date(2024, 10, 14)) == []        # Umbau (Montag)
    assert oeffnungsintervalle(fil, date(2024, 8, 5)) == [(360, 750)]   # August: bis 12:30
    assert oeffnungsintervalle(fil, date(2024, 7, 1)) == [(360, 1050)]  # sonst bis 17:30
    assert oeffnungsintervalle(fil, date(2024, 4, 1)) == []          # Ostermontag: Feiertag
