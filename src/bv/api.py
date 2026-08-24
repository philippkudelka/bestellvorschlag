"""FastAPI-Schnittstelle: JSON fuer die Tablet-Oberflaeche plus statische
Dateien. Es gibt keinen Schreibzugriff auf die Warenwirtschaft — die
Oberflaeche zeigt Vorschlaege, ein Mensch tippt sie ab und bestaetigt.

Start:  uvicorn bv.api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bv import waechter as waechter_modul
from bv.ablage import Ablage, jetzt
from bv.konfiguration import lade_konfiguration
from bv.merkmale import baue_merkmale
from bv.modell import lade_neuesten_stand

app = FastAPI(title="Bestellvorschlag", docs_url=None, redoc_url=None)

WEB_VERZEICHNIS = Path(__file__).parent / "web"

# Ein Cache je Liefertag: Merkmale + Modellstand, damit die Wirkung einer
# Servicegrad-Aenderung sofort sichtbar ist, ohne je Klick neu zu rechnen.
_zwischenspeicher: dict = {}


def _ablage() -> Ablage:
    konfig = lade_konfiguration()
    return Ablage(konfig.datenbank_pfad)


def _konfig():
    return lade_konfiguration()


def _standard_liefertag(ablage: Ablage) -> str:
    letzter = ablage.wert("SELECT MAX(liefertag) FROM vorschlag")
    return letzter or (jetzt().date() + timedelta(days=1)).isoformat()


def _vorhersagen_fuer(ablage: Ablage, liefertag: str) -> dict | None:
    """Merkmale und Vorhersagen aller Quantile fuer den Liefertag (gecacht)."""
    if liefertag in _zwischenspeicher:
        return _zwischenspeicher[liefertag]
    konfig = _konfig()
    stand = lade_neuesten_stand()
    if stand is None:
        _zwischenspeicher[liefertag] = None
        return None
    merkmale = baue_merkmale(ablage, konfig, [liefertag], mit_ziel=False)
    if merkmale.empty:
        _zwischenspeicher[liefertag] = None
        return None
    je_quantil = {q: stand.vorhersage(merkmale, q) for q in konfig.quantile}
    eintrag = {"merkmale": merkmale, "je_quantil": je_quantil}
    _zwischenspeicher[liefertag] = eintrag
    return eintrag


# ---------------------------------------------------------------------------


@app.get("/api/filialen")
def filialen():
    with _ablage() as ab:
        df = ab.lese("SELECT nummer, name, ort, strasse, plz, telefon"
                     " FROM filiale ORDER BY nummer")
        return df.to_dict(orient="records")


@app.get("/api/tagesuebersicht")
def tagesuebersicht(liefertag: str | None = None):
    with _ablage() as ab:
        liefertag = liefertag or _standard_liefertag(ab)
        filialen = ab.lese("SELECT nummer, name, ort, strasse, plz FROM filiale"
                           " ORDER BY nummer")
        vorschlaege = ab.lese(
            """SELECT filiale, COUNT(*) AS anzahl, SUM(auffaellig) AS auffaellig
               FROM vorschlag WHERE liefertag = ? AND erstellt_am =
                 (SELECT MAX(erstellt_am) FROM vorschlag WHERE liefertag = ?)
               GROUP BY filiale""", (liefertag, liefertag))
        vorschlag_je_filiale = vorschlaege.set_index("filiale")

        von = (date.fromisoformat(liefertag) - timedelta(days=8)).isoformat()
        bis = (date.fromisoformat(liefertag) - timedelta(days=1)).isoformat()
        retouren = ab.lese(
            """SELECT l.filiale, SUM(COALESCE(r.menge, 0)) AS retoure,
                      SUM(l.menge) AS geliefert
               FROM lieferung l LEFT JOIN
                 (SELECT datum, filiale, artikel, SUM(menge) AS menge
                  FROM retoure GROUP BY datum, filiale, artikel) r
                 ON r.datum = l.datum AND r.filiale = l.filiale AND r.artikel = l.artikel
               WHERE l.datum BETWEEN ? AND ? GROUP BY l.filiale""", (von, bis))
        retoure_je_filiale = retouren.set_index("filiale")

        bestellt = set(ab.lese(
            "SELECT DISTINCT filiale FROM bestellung WHERE liefertag = ?",
            (liefertag,))["filiale"])

        zeilen = []
        for f in filialen.itertuples(index=False):
            offen = ab.oeffnung(int(f.nummer), liefertag)
            v = (vorschlag_je_filiale.loc[f.nummer]
                 if f.nummer in vorschlag_je_filiale.index else None)
            r = (retoure_je_filiale.loc[f.nummer]
                 if f.nummer in retoure_je_filiale.index else None)
            zustand = "geschlossen" if not offen else (
                "bestellt" if f.nummer in bestellt else (
                    "fertig" if v is not None else "kein Vorschlag"))
            zeilen.append({
                "filiale": int(f.nummer), "name": f.name, "ort": f.ort,
                "anschrift": (f"{f.strasse}, {f.plz} {f.ort}"
                              if f.strasse else f.ort),
                "zustand": zustand,
                "oeffnung": " und ".join(f"{v_}-{b_}" for v_, b_ in offen) or "—",
                "anzahl_vorschlaege": int(v["anzahl"]) if v is not None else 0,
                "auffaellig": int(v["auffaellig"]) if v is not None else 0,
                "retourenquote_vorwoche": (
                    round(100 * float(r["retoure"]) / float(r["geliefert"]), 1)
                    if r is not None and r["geliefert"] else None),
            })
        return {"liefertag": liefertag, "filialen": zeilen}


@app.get("/api/vorschlag")
def vorschlag(filiale: int, liefertag: str | None = None):
    with _ablage() as ab:
        liefertag = liefertag or _standard_liefertag(ab)
        df = ab.lese(
            """SELECT v.artikel, a.bezeichnung, a.warengruppe, v.menge, v.quantil,
                      v.begruendung, v.auffaellig, v.modellstand, v.menge_wirtschaftlich
               FROM vorschlag v JOIN artikel a ON a.nummer = v.artikel
               WHERE v.liefertag = ? AND v.filiale = ? AND v.erstellt_am =
                 (SELECT MAX(erstellt_am) FROM vorschlag WHERE liefertag = ?)
               ORDER BY a.warengruppe, v.artikel""", (liefertag, filiale, liefertag))
        vorwoche = (date.fromisoformat(liefertag) - timedelta(days=7)).isoformat()
        vw = ab.lese(
            """SELECT l.artikel, l.menge AS geliefert, COALESCE(r.menge, 0) AS retoure
               FROM lieferung l LEFT JOIN
                 (SELECT datum, filiale, artikel, SUM(menge) AS menge
                  FROM retoure GROUP BY datum, filiale, artikel) r
                 ON r.datum = l.datum AND r.filiale = l.filiale AND r.artikel = l.artikel
               WHERE l.datum = ? AND l.filiale = ?""", (vorwoche, filiale))
        vw_je_artikel = vw.set_index("artikel")
        bestellung = ab.lese(
            "SELECT artikel, menge FROM bestellung WHERE liefertag = ? AND filiale = ?",
            (liefertag, filiale)).set_index("artikel")

        info = ab.lese("SELECT nummer, name, ort, strasse, plz FROM filiale"
                       " WHERE nummer = ?", (filiale,))
        if info.empty:
            raise HTTPException(404, "Unbekannte Filiale")
        offen = ab.oeffnung(filiale, liefertag)

        einstellungen = ab.lese(
            """SELECT artikel, servicegrad FROM einstellung
               WHERE filiale = ? AND aktiv_ab <= ?
               ORDER BY aktiv_ab""", (filiale, liefertag))
        sg = dict(zip(einstellungen["artikel"], einstellungen["servicegrad"]))

        zeilen = []
        for z in df.itertuples(index=False):
            v = (vw_je_artikel.loc[z.artikel]
                 if z.artikel in vw_je_artikel.index else None)
            zeilen.append({
                "artikel": z.artikel, "bezeichnung": z.bezeichnung,
                "warengruppe": z.warengruppe,
                "vorschlag": z.menge, "quantil": z.quantil,
                "menge_wirtschaftlich": (None if pd.isna(z.menge_wirtschaftlich)
                                         else float(z.menge_wirtschaftlich)),
                "servicegrad": sg.get(z.artikel),
                "begruendung": z.begruendung, "auffaellig": int(z.auffaellig),
                "notbehelf": z.modellstand == "rueckfall",
                "vorwoche_geliefert": float(v["geliefert"]) if v is not None else None,
                "vorwoche_retoure": float(v["retoure"]) if v is not None else None,
                "bestellt": (float(bestellung.loc[z.artikel, "menge"])
                             if z.artikel in bestellung.index else None),
            })
        return {
            "liefertag": liefertag,
            "filiale": {"nummer": int(info.loc[0, "nummer"]),
                        "name": info.loc[0, "name"], "ort": info.loc[0, "ort"],
                        "anschrift": (f"{info.loc[0, 'strasse']}, "
                                      f"{info.loc[0, 'plz']} {info.loc[0, 'ort']}"
                                      if info.loc[0, "strasse"] else info.loc[0, "ort"])},
            "oeffnung": " und ".join(f"{v_}-{b_}" for v_, b_ in offen) or "geschlossen",
            "positionen": zeilen,
        }


class BestellPosition(BaseModel):
    artikel: str
    menge: float = Field(ge=0)


class Bestellung(BaseModel):
    liefertag: str
    filiale: int
    positionen: list[BestellPosition]


@app.post("/api/bestellung")
def bestellung_uebernehmen(bestellung: Bestellung):
    """Der Mensch bestaetigt, was er in die Warenwirtschaft abgetippt hat."""
    with _ablage() as ab:
        for p in bestellung.positionen:
            ab.verbindung.execute(
                "INSERT OR REPLACE INTO bestellung (liefertag, filiale, artikel, menge)"
                " VALUES (?, ?, ?, ?)",
                (bestellung.liefertag, bestellung.filiale, p.artikel, p.menge))
        ab.verbindung.commit()
        return {"uebernommen": len(bestellung.positionen)}


@app.get("/api/einstellungen")
def einstellungen(filiale: int, liefertag: str | None = None):
    """Servicegrad je Artikel — mit der Menge, die jede Klasse ergaebe,
    damit die Wirkung einer Aenderung sofort sichtbar ist."""
    konfig = _konfig()
    abbildung = konfig.quantil_je_servicegrad
    with _ablage() as ab:
        liefertag = liefertag or _standard_liefertag(ab)
        artikel = ab.lese(
            "SELECT nummer, bezeichnung, warengruppe FROM artikel"
            " WHERE im_umfang = 1 ORDER BY warengruppe, nummer")
        aktuelle = ab.lese(
            """SELECT artikel, servicegrad FROM einstellung
               WHERE filiale = ? AND aktiv_ab <= ? ORDER BY aktiv_ab""",
            (filiale, liefertag))
        sg = dict(zip(aktuelle["artikel"], aktuelle["servicegrad"]))

        cache = _vorhersagen_fuer(ab, liefertag)
        mengen: dict[str, dict[str, float]] = {}
        if cache is not None:
            m = cache["merkmale"]
            maske = m["filiale"].astype(int) == filiale
            for klasse, q in abbildung.items():
                if q not in cache["je_quantil"]:
                    continue
                werte = cache["je_quantil"][q][maske.to_numpy()]
                for art, wert in zip(m[maske]["artikel"], werte):
                    mengen.setdefault(art, {})[klasse] = (
                        round(float(wert)) if wert == wert else None)

        zeilen = []
        for a in artikel.itertuples(index=False):
            zeilen.append({
                "artikel": a.nummer, "bezeichnung": a.bezeichnung,
                "warengruppe": a.warengruppe,
                "servicegrad": sg.get(a.nummer, "B"),
                "menge_je_klasse": mengen.get(a.nummer, {}),
            })
        return {"filiale": filiale, "liefertag": liefertag,
                "quantile": abbildung, "artikel": zeilen}


class EinstellungAenderung(BaseModel):
    filiale: int
    artikel: str
    servicegrad: str = Field(pattern="^[ABC]$")


@app.put("/api/einstellungen")
def einstellung_aendern(aenderung: EinstellungAenderung):
    heute = jetzt().date().isoformat()
    with _ablage() as ab:
        ab.verbindung.execute(
            "INSERT OR REPLACE INTO einstellung"
            " (filiale, artikel, servicegrad, zielretoure_prozent, aktiv_ab)"
            " VALUES (?, ?, ?, NULL, ?)",
            (aenderung.filiale, aenderung.artikel, aenderung.servicegrad, heute))
        ab.verbindung.commit()
    return {"filiale": aenderung.filiale, "artikel": aenderung.artikel,
            "servicegrad": aenderung.servicegrad, "aktiv_ab": heute}


@app.get("/api/ereignisse")
def ereignisse():
    with _ablage() as ab:
        df = ab.lese(
            "SELECT id, datum_von, datum_bis, filialen, bezeichnung, art, wirkung"
            " FROM ereignis WHERE art != 'geschlossen'"
            " ORDER BY datum_von DESC LIMIT 200")
        return df.to_dict(orient="records")


class NeuesEreignis(BaseModel):
    datum_von: str
    datum_bis: str
    filialen: str = "alle"
    bezeichnung: str
    art: str = "sonstiges"
    wirkung: float = 1.2


@app.post("/api/ereignisse")
def ereignis_anlegen(e: NeuesEreignis):
    with _ablage() as ab:
        ab.schreibe("ereignis", pd.DataFrame([e.model_dump()]))
    return e.model_dump()


@app.get("/api/zustand")
def zustand():
    """Fuer den Waechter-Blick: Warnungen, letzter Import, Modellstand."""
    with _ablage() as ab:
        letzter_import = ab.lese(
            "SELECT zeitpunkt, dateiname FROM import_lauf ORDER BY id DESC LIMIT 1")
        letzter_verkauf = ab.wert("SELECT MAX(datum) FROM verkauf")
    warnung = None
    if waechter_modul.WARNUNGSDATEI.exists():
        warnung = waechter_modul.WARNUNGSDATEI.read_text(encoding="utf-8")
    stand = lade_neuesten_stand()
    return {
        "warnung": warnung,
        "letzter_import": (letzter_import.to_dict(orient="records")[0]
                           if not letzter_import.empty else None),
        "letzter_verkaufstag": letzter_verkauf,
        "modellstand": stand.name if stand else None,
    }


# ---------------------------------------------------------------------------


@app.get("/")
def startseite():
    return FileResponse(WEB_VERZEICHNIS / "index.html")


app.mount("/web", StaticFiles(directory=WEB_VERZEICHNIS), name="web")
