"""Schreibt Stammdaten aus der Konfiguration in die Ablage:
Filialen, Oeffnungszeiten (mit saisonalen Segmenten), Artikel,
Servicegrad-Einstellungen und Schliess-Ereignisse (Umbau, Neueroeffnung)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from bv.ablage import Ablage
from bv.konfiguration import Konfiguration

_WT = ["mo", "di", "mi", "do", "fr", "sa", "so"]
_ANFANG = "2023-01-01"
_ENDE = "2027-12-31"


def schreibe_stammdaten(ablage: Ablage, konfig: Konfiguration) -> None:
    ablage.schreibe("filiale", pd.DataFrame(
        [{"nummer": f["nummer"], "name": f["name"], "ort": f["ort"],
          "strasse": f.get("strasse"), "plz": f.get("plz"),
          "telefon": f.get("telefon")}
         for f in konfig.filialen]))

    ablage.schreibe("oeffnungszeit", pd.DataFrame(_oeffnungszeiten(konfig.filialen)))

    ablage.schreibe("artikel", pd.DataFrame([{
        "nummer": a["nummer"], "bezeichnung": a["bezeichnung"],
        "warengruppe": a["warengruppe"], "im_umfang": int(a["im_umfang"]),
        "mehrtagesartikel": int(a["mehrtagesartikel"]),
        "preis": a["preis"], "herstellkosten": a["herstellkosten"],
    } for a in konfig.artikel]))

    # Vorgabe-Servicegrad je Artikel gilt zunaechst fuer alle Filialen;
    # Uebersteuerung je Filiale kommt spaeter ueber die Oberflaeche.
    einstellungen = [
        {"filiale": f["nummer"], "artikel": a["nummer"],
         "servicegrad": a["servicegrad"], "zielretoure_prozent": None,
         "aktiv_ab": _ANFANG}
        for f in konfig.filialen for a in konfig.artikel
    ]
    ablage.schreibe("einstellung", pd.DataFrame(einstellungen))

    # Umbau und Zeit vor der Eroeffnung als Schliess-Ereignisse
    zu = []
    for f in konfig.filialen:
        if f.get("eroeffnet_am"):
            vortag = (date.fromisoformat(f["eroeffnet_am"]).toordinal() - 1)
            zu.append({
                "datum_von": _ANFANG,
                "datum_bis": date.fromordinal(vortag).isoformat(),
                "filialen": str(f["nummer"]),
                "bezeichnung": "noch nicht eroeffnet",
                "art": "geschlossen", "wirkung": 0.0,
            })
        if f.get("umbau"):
            zu.append({
                "datum_von": f["umbau"]["von"], "datum_bis": f["umbau"]["bis"],
                "filialen": str(f["nummer"]), "bezeichnung": "Umbau",
                "art": "geschlossen", "wirkung": 0.0,
            })
    if zu:
        ablage.schreibe("ereignis", pd.DataFrame(zu))


def _oeffnungszeiten(filialen: list[dict]) -> list[dict]:
    """Wochenplan in Gueltigkeitssegmente uebersetzen. Filialen mit
    Augustschliessung bekommen je Jahr eigene August-Segmente."""
    zeilen: list[dict] = []
    for f in filialen:
        plan = f["oeffnungszeiten"]
        august_zu = bool(f.get("august_nachmittag_zu"))
        segmente = [(_ANFANG, _ENDE, False)]
        if august_zu:
            segmente = []
            for jahr in range(2023, 2028):
                segmente.append((f"{jahr}-01-01", f"{jahr}-07-31", False))
                segmente.append((f"{jahr}-08-01", f"{jahr}-08-31", True))
                segmente.append((f"{jahr}-09-01", f"{jahr}-12-31", False))
        for von_g, bis_g, gekuerzt in segmente:
            for wt, schluessel in enumerate(_WT):
                zeiten = plan.get(schluessel)
                if not zeiten:
                    continue
                for von, bis in zeiten:
                    if gekuerzt and wt < 6:
                        bis = min(bis, "12:30")
                        if bis <= von:
                            continue
                    zeilen.append({
                        "filiale": f["nummer"], "gueltig_ab": von_g,
                        "gueltig_bis": bis_g, "wochentag": wt,
                        "von": von, "bis": bis,
                    })
    return zeilen
