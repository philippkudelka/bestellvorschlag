"""Erzeugt je Liefertag, Filiale und Artikel den Bestellvorschlag.

Menge aus dem Quantilmodell des jeweiligen Servicegrads, kaufmaennisch
gerundet, mit einer Begruendung in normaler Sprache aus den staerksten
Einfluessen des Tages — die Begruendung ist der Grund, warum jemand dem
Vorschlag traut. Versagt das Modell, gibt es immer einen Rueckfallwert
(Menge der Vorwoche), offen als Notbehelf gekennzeichnet.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from bv.ablage import Ablage, jetzt
from bv.konfiguration import Konfiguration
from bv.merkmale import baue_merkmale
from bv.modell import lade_neuesten_stand
from bv.servicegrad import einstellungen_je_filiale_artikel

WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]


def erzeuge_vorschlaege(
    ablage: Ablage, konfig: Konfiguration, liefertag: str,
    modell_abschalten: bool = False,
) -> dict:
    merkmale = baue_merkmale(ablage, konfig, [liefertag], mit_ziel=False)
    if merkmale.empty:
        return {"anzahl": 0, "filialen": 0, "modellstand": "-", "rueckfall": 0}

    einstellungen = einstellungen_je_filiale_artikel(ablage, konfig, liefertag)
    merkmale = merkmale.merge(
        einstellungen[["filiale", "artikel", "servicegrad", "quantil"]],
        on=["filiale", "artikel"], how="left")
    vorgabe_quantil = konfig.quantil_je_servicegrad.get("B", 0.8)
    merkmale["quantil"] = merkmale["quantil"].fillna(vorgabe_quantil)

    stand = None if modell_abschalten else lade_neuesten_stand()
    vorhersagen: dict[float, np.ndarray] = {}
    if stand is not None:
        for q in sorted(merkmale["quantil"].unique()):
            vorhersagen[q] = stand.vorhersage(merkmale, q)

    kontext = _kontext_vorwoche(ablage, konfig, liefertag)
    schwelle = float(konfig.einstellungen.get("vorschlag", {})
                     .get("auffaellig_abweichung_prozent", 25)) / 100.0
    hohe_retoure = float(konfig.einstellungen.get("vorschlag", {})
                         .get("hohe_retoure_prozent", 30)) / 100.0

    zeitstempel = jetzt().isoformat(timespec="seconds")
    zeilen = []
    n_rueckfall = 0
    for i, z in enumerate(merkmale.itertuples(index=False)):
        schluessel = (int(z.filiale), z.artikel)
        vw = kontext.get(schluessel, {})
        menge = np.nan
        if stand is not None:
            menge = vorhersagen[z.quantil][i]
        if np.isnan(menge):
            # Rueckfallwert: Liefermenge der Vorwoche, ehrlich etikettiert
            n_rueckfall += 1
            menge = vw.get("liefermenge_vorwoche")
            if menge is None or np.isnan(menge):
                menge = z.mittel_7 if not np.isnan(z.mittel_7) else 0.0
            begruendung = ("Notbehelf: Menge der Vorwoche uebernommen — "
                           "kein Modell verfuegbar")
            modellstand = "rueckfall"
            auffaellig = 1
        else:
            begruendung = _begruendung(z, vw, menge)
            modellstand = stand.name
            auffaellig = _ist_auffaellig(menge, vw, schwelle, hohe_retoure)
        zeilen.append({
            "erstellt_am": zeitstempel, "liefertag": liefertag,
            "filiale": int(z.filiale), "artikel": z.artikel,
            "menge": float(round(menge)), "quantil": float(z.quantil),
            "begruendung": begruendung, "modellstand": modellstand,
            "auffaellig": int(auffaellig),
        })

    df = pd.DataFrame(zeilen)
    ablage.schreibe("vorschlag", df)
    return {"anzahl": len(df), "filialen": df["filiale"].nunique(),
            "modellstand": "rueckfall" if stand is None else stand.name,
            "rueckfall": n_rueckfall}


def _kontext_vorwoche(ablage: Ablage, konfig: Konfiguration, liefertag: str) -> dict:
    """Vorwochenwerte je (filiale, artikel): Liefermenge, Retoure, Ausverkauf."""
    vorwoche = (date.fromisoformat(liefertag) - timedelta(days=7)).isoformat()
    umbenennung = {
        str(alt): str(neu)
        for alt, neu in (konfig.einstellungen.get("artikel_umbenennungen") or {}).items()
    }
    df = ablage.lese("""
        SELECT l.filiale, l.artikel, l.menge AS liefermenge,
               COALESCE(r.menge, 0) AS retoure, n.ist_geschaetzt,
               n.begruendung AS ausverkauf_text, v.letzter_verkauf
        FROM lieferung l
        LEFT JOIN (SELECT datum, filiale, artikel, SUM(menge) AS menge
                   FROM retoure GROUP BY datum, filiale, artikel) r
          ON r.datum = l.datum AND r.filiale = l.filiale AND r.artikel = l.artikel
        LEFT JOIN verkauf v
          ON v.datum = l.datum AND v.filiale = l.filiale AND v.artikel = l.artikel
        LEFT JOIN nachfrage n
          ON n.datum = l.datum AND n.filiale = l.filiale AND n.artikel = l.artikel
        WHERE l.datum = ?""", (vorwoche,))
    kontext = {}
    for z in df.itertuples(index=False):
        artikel = umbenennung.get(z.artikel, z.artikel)
        kontext[(int(z.filiale), artikel)] = {
            "liefermenge_vorwoche": float(z.liefermenge),
            "retoure_vorwoche": float(z.retoure),
            "ausverkauf_vorwoche": bool(z.ist_geschaetzt),
            "letzter_verkauf_vorwoche": z.letzter_verkauf,
        }
    return kontext


def _ist_auffaellig(menge: float, vw: dict, schwelle: float, hohe_retoure: float) -> bool:
    liefer_vw = vw.get("liefermenge_vorwoche")
    if liefer_vw and liefer_vw > 0:
        if abs(menge - liefer_vw) / liefer_vw > schwelle:
            return True
        if vw.get("retoure_vorwoche", 0) / liefer_vw > hohe_retoure:
            return True
    if vw.get("ausverkauf_vorwoche"):
        return True
    return False


def _begruendung(z, vw: dict, menge: float) -> str:
    """Kleine Regelsammlung: nennt die zwei bis drei staerksten Einfluesse
    des Tages in normaler Sprache."""
    tag = date.fromisoformat(z.liefertag)
    teile: list[str] = [WOCHENTAGE[tag.weekday()]]

    # Wetter
    if not np.isnan(z.temperatur):
        wetter = f"{z.temperatur:.0f} Grad"
        if z.niederschlag >= 3:
            wetter += ", Regen angesagt"
        elif z.niederschlag < 0.5:
            wetter = "trocken, " + wetter
        teile.append(wetter)

    # Kalender
    if z.feiertag:
        teile.append("Feiertag")
    elif z.tag_vor_feiertag:
        teile.append("Tag vor Feiertag")
    elif z.tag_nach_feiertag:
        teile.append("Tag nach Feiertag")
    if z.letzter_ferientag:
        teile.append("Ferienende")
    elif z.erster_ferientag:
        teile.append("Ferienbeginn")

    if z.ereignis_aktiv:
        richtung = "Ereignis im Kalender" if z.ereignis_wirkung >= 1 else \
            "Ereignis daempft (z. B. Sperrung)"
        teile.append(richtung)

    satz = ", ".join(teile)

    # Vergleich mit dem Schnitt der letzten vier gleichen Wochentage
    vorwochen = [v for v in (z.vorwoche_1, z.vorwoche_2, z.vorwoche_3, z.vorwoche_4)
                 if v is not None and not np.isnan(v)]
    if vorwochen:
        schnitt = float(np.mean(vorwochen))
        if schnitt > 0:
            abweichung = (menge - schnitt) / schnitt
            if abs(abweichung) >= 0.05:
                richtung = "ueber" if abweichung > 0 else "unter"
                satz += (f" — {abs(abweichung):.0%} {richtung} dem Schnitt der letzten"
                         f" vier {WOCHENTAGE[tag.weekday()]}e")

    # Ausverkauf oder hohe Retoure in der Vorwoche schlagen alles
    if vw.get("ausverkauf_vorwoche") and vw.get("letzter_verkauf_vorwoche"):
        aufschlag = menge - vw.get("liefermenge_vorwoche", menge)
        satz = (f"Letzten {WOCHENTAGE[tag.weekday()]} um "
                f"{vw['letzter_verkauf_vorwoche']} ausverkauft"
                + (f" — deshalb {aufschlag:.0f} Stueck mehr" if aufschlag > 0 else "")
                + ". " + satz)
    elif vw.get("liefermenge_vorwoche", 0) > 0:
        quote = vw.get("retoure_vorwoche", 0) / vw["liefermenge_vorwoche"]
        if quote > 0.25:
            satz = (f"{vw['retoure_vorwoche']:.0f} von {vw['liefermenge_vorwoche']:.0f}"
                    f" zurueck letzte Woche — deshalb weniger. " + satz)
    return satz
