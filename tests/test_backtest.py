"""M7: Kennzahlenrechnung der Rueckrechnung (schnelle Einheitstests).

Der volle Lauf (skripte/backtest_cli.py) dauert Minuten und wird nicht im
Testlauf wiederholt; Ergebnis vom 2026-08-23: 152s fuer 6 Monate, Bericht
unter berichte/rueckrechnung.md.
"""

import pandas as pd
import pytest

from bv.backtest import VERFAHREN, _inhaber_mittel3, kennzahlen


def test_kennzahlen_rechnen_richtig():
    df = pd.DataFrame({
        "datum": ["2026-01-01"] * 4,
        "filiale": [1, 1, 1, 1],
        "artikel": ["a", "b", "c", "d"],
        "wahrheit": [100.0, 100.0, 100.0, 100.0],
        "verkauf": [90.0, 100.0, 100.0, 100.0],
        "servicegrad": ["A", "A", "A", "A"],
    })
    for spalte in VERFAHREN:
        df[spalte] = [110.0, 90.0, 100.0, 120.0]
    kz = kennzahlen(df)
    zeile = kz[kz["verfahren"] == "modell"].iloc[0]
    # MAE: (10+10+0+20)/4 = 10; WAPE: 40/400 = 10 %
    assert zeile["mae_stueck"] == pytest.approx(10.0)
    assert zeile["wape_prozent"] == pytest.approx(10.0)
    # Verzerrung: (10-10+0+20)/4 = 5
    assert zeile["verzerrung_stueck"] == pytest.approx(5.0)
    # Servicegrad erreicht: 3 von 4 Tagen keine Unterdeckung
    assert zeile["erreichter_servicegrad"] == pytest.approx(0.75)
    # Retourenquote: Ueberschuss (10+0+0+20) / Vorschlagssumme 420
    assert zeile["retourenquote_prozent"] == pytest.approx(100 * 30 / 420)


def test_inhaber_mittel3_nutzt_nur_gleiche_wochentage():
    verkauf = pd.DataFrame({
        "datum": ["2026-05-02", "2026-05-09", "2026-05-16", "2026-05-23"],
        "filiale": [1] * 4,
        "artikel": ["a"] * 4,
        "menge": [90.0, 100.0, 110.0, 999.0],
    })
    m = _inhaber_mittel3(verkauf)
    zeile = m[m["datum"] == "2026-05-23"]
    # Mittel der drei Samstage davor: (90+100+110)/3 — der 23. selbst zaehlt nicht
    assert zeile["inhaber_mittel3"].iloc[0] == pytest.approx(100.0)
