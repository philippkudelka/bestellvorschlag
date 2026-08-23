"""Der Waechter: prueft nach dem Nachtlauf stur eine feste Liste.

Bei Verstoss: deutliche Meldung im Protokoll und in WARNUNG.md, die der
Betreiber sieht. Der Waechter repariert nichts — er meldet. Den Rueckfall-
wert stellt bereits der Vorschlagsschritt sicher (um 06:30 muss etwas
dastehen, notfalls etwas Dummes mit ehrlichem Etikett).
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from bv import modell as _modell
from bv.ablage import Ablage, jetzt
from bv.konfiguration import PROJEKTWURZEL, Konfiguration

WARNUNGSDATEI = PROJEKTWURZEL / "WARNUNG.md"


def pruefe(ablage: Ablage, konfig: Konfiguration, liefertag: str) -> list[str]:
    """Fuehrt alle Pruefungen aus. Gibt die Liste der Warnungen zurueck und
    schreibt WARNUNG.md (bzw. loescht sie, wenn alles in Ordnung ist)."""
    w = konfig.einstellungen.get("waechter", {})
    meldungen: list[str] = []

    meldungen += _vorschlaege_vorhanden(ablage, liefertag)
    meldungen += _daten_aktuell(ablage, liefertag,
                                int(w.get("max_fehlende_tage", 2)))
    meldungen += _abweichung_vorwoche(
        ablage, liefertag, float(w.get("max_abweichung_vorwoche_prozent", 40)))
    meldungen += _abweichung_vorjahr(
        ablage, liefertag, float(w.get("max_abweichung_vorjahr_prozent", 25)))
    meldungen += _modellalter(int(w.get("max_modellalter_tage", 14)))

    if meldungen:
        zeilen = [
            "# WARNUNG — Nachtlauf auffaellig",
            f"\nLiefertag {liefertag}, geprueft {jetzt().isoformat(timespec='seconds')}\n",
        ]
        zeilen += [f"- ⚠️ {m}" for m in meldungen]
        zeilen.append("\nVorschlaege ggf. besonders kritisch pruefen. "
                      "Rueckfallwerte sind in der Begruendung als Notbehelf markiert.")
        WARNUNGSDATEI.write_text("\n".join(zeilen), encoding="utf-8")
    elif WARNUNGSDATEI.exists():
        WARNUNGSDATEI.unlink()
    return meldungen


def _offene_filialen(ablage: Ablage, liefertag: str) -> list[int]:
    filialen = ablage.lese("SELECT nummer FROM filiale")["nummer"].tolist()
    return [f for f in filialen if ablage.oeffnung(f, liefertag)]


def _vorschlaege_vorhanden(ablage: Ablage, liefertag: str) -> list[str]:
    offene = _offene_filialen(ablage, liefertag)
    if not offene:
        return [f"Keine Filiale hat am {liefertag} geoeffnet — bitte Oeffnungszeiten pruefen."]
    mit_vorschlag = set(ablage.lese(
        "SELECT DISTINCT filiale FROM vorschlag WHERE liefertag = ? AND erstellt_am ="
        " (SELECT MAX(erstellt_am) FROM vorschlag WHERE liefertag = ?)",
        (liefertag, liefertag))["filiale"].tolist())
    fehlend = [f for f in offene if f not in mit_vorschlag]
    if fehlend:
        return [f"Fuer Filiale(n) {', '.join(map(str, fehlend))} liegen KEINE "
                f"Vorschlaege fuer {liefertag} vor."]
    return []


def _daten_aktuell(ablage: Ablage, liefertag: str, max_tage: int) -> list[str]:
    letzter = ablage.wert("SELECT MAX(datum) FROM verkauf")
    if letzter is None:
        return ["Es liegen ueberhaupt keine Verkaufsdaten vor."]
    luecke = (date.fromisoformat(liefertag) - date.fromisoformat(letzter)).days - 1
    if luecke > max_tage:
        return [f"Letzte Verkaufsdaten vom {letzter} — {luecke} Tage Luecke "
                f"(erlaubt: {max_tage}). Import pruefen."]
    return []


def _abweichung_vorwoche(ablage: Ablage, liefertag: str, schwelle_prozent: float) -> list[str]:
    vorwoche = (date.fromisoformat(liefertag) - timedelta(days=7)).isoformat()
    df = ablage.lese("""
        SELECT v.filiale, v.artikel, v.menge AS vorschlag, l.menge AS vorwoche
        FROM vorschlag v JOIN lieferung l
          ON l.datum = ? AND l.filiale = v.filiale AND l.artikel = v.artikel
        WHERE v.liefertag = ? AND l.menge >= 10
          AND v.erstellt_am = (SELECT MAX(erstellt_am) FROM vorschlag
                               WHERE liefertag = v.liefertag)""",
        (vorwoche, liefertag))
    if df.empty:
        return []
    abweichung = (df["vorschlag"] - df["vorwoche"]).abs() / df["vorwoche"] * 100
    auffaellig = df[abweichung > schwelle_prozent]
    if len(auffaellig):
        beispiele = ", ".join(
            f"Filiale {z.filiale}/Artikel {z.artikel} ({z.vorschlag:.0f} statt {z.vorwoche:.0f})"
            for z in auffaellig.head(3).itertuples(index=False))
        return [f"{len(auffaellig)} Vorschlaege weichen mehr als "
                f"{schwelle_prozent:.0f} % von der Vorwoche ab — z. B. {beispiele}."]
    return []


def _abweichung_vorjahr(ablage: Ablage, liefertag: str, schwelle_prozent: float) -> list[str]:
    summe = ablage.wert(
        "SELECT SUM(menge) FROM vorschlag WHERE liefertag = ? AND erstellt_am ="
        " (SELECT MAX(erstellt_am) FROM vorschlag WHERE liefertag = ?)",
        (liefertag, liefertag))
    if not summe:
        return []
    # Vorjahresvergleich: gleicher Wochentag vor 52 Wochen, Summe der Lieferungen
    vorjahr = (date.fromisoformat(liefertag) - timedelta(weeks=52)).isoformat()
    summe_vorjahr = ablage.wert(
        "SELECT SUM(menge) FROM lieferung WHERE datum = ?", (vorjahr,))
    if not summe_vorjahr:
        return []
    abweichung = (summe - summe_vorjahr) / summe_vorjahr * 100
    if abs(abweichung) > schwelle_prozent:
        return [f"Gesamtsumme ueber alle Filialen ist {abweichung:+.0f} % gegenueber "
                f"dem Vorjahrestag ({vorjahr}: {summe_vorjahr:.0f}, "
                f"jetzt {summe:.0f}) — erlaubt: ±{schwelle_prozent:.0f} %."]
    return []


def _modellalter(max_tage: int) -> list[str]:
    verz = _modell.MODELL_VERZEICHNIS
    staende = sorted(p for p in verz.iterdir()
                     if p.is_dir() and (p / "metadaten.json").exists()) \
        if verz.exists() else []
    if not staende:
        return ["Es existiert noch kein Modellstand — es werden nur "
                "Rueckfallwerte vorgeschlagen."]
    with open(staende[-1] / "metadaten.json", encoding="utf-8") as f:
        metadaten = json.load(f)
    erstellt = date.fromisoformat(metadaten["erstellt"][:10])
    alter = (jetzt().date() - erstellt).days
    if alter > max_tage:
        return [f"Der neueste Modellstand ({staende[-1].name}) ist {alter} Tage alt "
                f"(erlaubt: {max_tage}). Training pruefen."]
    return []
