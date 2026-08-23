"""Datenqualitaetsbericht: prueft die importierten Daten stur auf die
bekannten Schwaechen von Warenwirtschaftsexporten und schreibt einen
Markdown-Bericht unter berichte/."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from bv.ablage import Ablage, jetzt
from bv.konfiguration import PROJEKTWURZEL


def erzeuge_bericht(ablage: Ablage, ziel: Path | None = None) -> Path:
    teile: list[str] = [
        "# Datenqualitätsbericht",
        f"\nErzeugt: {jetzt().isoformat(timespec='seconds')}\n",
    ]

    grenzen = ablage.lese("SELECT MIN(datum) AS von, MAX(datum) AS bis FROM verkauf")
    von, bis = grenzen.loc[0, "von"], grenzen.loc[0, "bis"]
    teile.append(f"Datenzeitraum: {von} bis {bis}\n")

    teile.append(_fehlende_tage(ablage, von, bis))
    teile.append(_retoure_groesser_lieferung(ablage))
    teile.append(_verkauf_groesser_lieferung(ablage))
    teile.append(_verkauf_ausserhalb_oeffnung(ablage))
    teile.append(_nummernwechsel(ablage))
    teile.append(_retoure_null_verdacht(ablage))
    teile.append(_luecken_je_filiale(ablage, von, bis))

    ziel = ziel or (PROJEKTWURZEL / "berichte" / "datenqualitaet.md")
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text("\n".join(teile), encoding="utf-8")
    return ziel


def _fehlende_tage(ablage: Ablage, von: str, bis: str) -> str:
    """Tage, an denen eine Filiale laut Plan offen war, aber keinerlei
    Verkaufsdaten vorliegen — meist fehlt dann die Exportdatei."""
    vorhanden = ablage.lese("SELECT DISTINCT datum, filiale FROM verkauf")
    je_filiale = {f: set(g["datum"]) for f, g in vorhanden.groupby("filiale")}
    filialen = ablage.lese("SELECT nummer FROM filiale")["nummer"].tolist()
    fehlend: dict[int, list[str]] = {}
    tag = date.fromisoformat(von)
    ende = date.fromisoformat(bis)
    while tag <= ende:
        iso = tag.isoformat()
        for f in filialen:
            if ablage.oeffnung(f, tag) and iso not in je_filiale.get(f, set()):
                fehlend.setdefault(f, []).append(iso)
        tag += timedelta(days=1)

    zeilen = ["\n## Fehlende Tage je Filiale\n"]
    if not fehlend:
        zeilen.append("Keine. ✓")
    else:
        alle_tage = sorted({t for tt in fehlend.values() for t in tt})
        zeilen.append(f"Betroffene Kalendertage: {', '.join(alle_tage[:15])}"
                      + (" …" if len(alle_tage) > 15 else ""))
        zeilen.append("\n| Filiale | fehlende Tage |\n|---|---|")
        for f, tt in sorted(fehlend.items()):
            zeilen.append(f"| {f} | {len(tt)} |")
    return "\n".join(zeilen)


def _retoure_groesser_lieferung(ablage: Ablage) -> str:
    df = ablage.lese("""
        SELECT r.datum, r.filiale, r.artikel, SUM(r.menge) AS retoure, l.menge AS liefermenge
        FROM retoure r JOIN lieferung l
          ON l.datum = r.datum AND l.filiale = r.filiale AND l.artikel = r.artikel
        GROUP BY r.datum, r.filiale, r.artikel
        HAVING SUM(r.menge) > l.menge""")
    kopf = "\n## Retoure größer als Liefermenge\n"
    if df.empty:
        return kopf + "Keine Fälle. ✓"
    return kopf + f"**{len(df)} Fälle** — Beispiele:\n\n" + df.head(10).to_markdown(index=False)


def _verkauf_groesser_lieferung(ablage: Ablage) -> str:
    df = ablage.lese("""
        SELECT v.datum, v.filiale, v.artikel, v.menge AS verkauf, l.menge AS liefermenge
        FROM verkauf v JOIN lieferung l
          ON l.datum = v.datum AND l.filiale = v.filiale AND l.artikel = v.artikel
        WHERE v.menge > l.menge""")
    kopf = "\n## Verkauf größer als Liefermenge\n"
    if df.empty:
        return kopf + "Keine Fälle. ✓"
    return kopf + f"**{len(df)} Fälle** — Beispiele:\n\n" + df.head(10).to_markdown(index=False)


def _verkauf_ausserhalb_oeffnung(ablage: Ablage) -> str:
    df = ablage.lese("""
        SELECT datum, filiale, MIN(erster_verkauf) AS frueh, MAX(letzter_verkauf) AS spaet
        FROM verkauf WHERE letzter_verkauf IS NOT NULL GROUP BY datum, filiale""")
    faelle = []
    for z in df.itertuples(index=False):
        zeiten = ablage.oeffnung(int(z.filiale), z.datum)
        if not zeiten:
            faelle.append((z.datum, z.filiale, "Verkauf trotz geschlossener Filiale"))
            continue
        offen_ab = min(v for v, _ in zeiten)
        schluss = max(b for _, b in zeiten)
        if z.frueh is not None and z.frueh < offen_ab:
            faelle.append((z.datum, z.filiale, f"erster Verkauf {z.frueh} vor Öffnung {offen_ab}"))
        if z.spaet is not None and z.spaet > schluss:
            faelle.append(
                (z.datum, z.filiale, f"letzter Verkauf {z.spaet} nach Schluss {schluss}"))
    kopf = "\n## Verkäufe außerhalb der Öffnungszeit\n"
    if not faelle:
        return kopf + "Keine Fälle. ✓"
    zeilen = [kopf + f"**{len(faelle)} Fälle** — entweder stimmen die hinterlegten "
              "Öffnungszeiten nicht, oder die Kassendaten. Beispiele:\n"]
    zeilen += [f"- {d}, Filiale {f}: {txt}" for d, f, txt in faelle[:12]]
    return "\n".join(zeilen)


def _nummernwechsel(ablage: Ablage) -> str:
    df = ablage.lese("""
        SELECT bezeichnung, GROUP_CONCAT(nummer) AS nummern, COUNT(*) AS anzahl
        FROM artikel GROUP BY bezeichnung HAVING COUNT(*) > 1""")
    kopf = "\n## Artikel mit Nummernwechsel (gleiche Bezeichnung, mehrere Nummern)\n"
    if df.empty:
        return kopf + "Keine Fälle. ✓"
    zeilen = [kopf + "Vermutlich wurde der Artikel im Fremdsystem neu angelegt. "
              "Zuordnung in `konfiguration/einstellungen.yaml` unter "
              "`artikel_umbenennungen` eintragen, damit die Historie "
              "zusammenhängend gelernt wird.\n"]
    for z in df.itertuples(index=False):
        ab = ablage.lese(
            "SELECT artikel, MIN(datum) AS ab, MAX(datum) AS bis FROM verkauf"
            " WHERE artikel IN (SELECT nummer FROM artikel WHERE bezeichnung = ?)"
            " GROUP BY artikel ORDER BY ab", (z.bezeichnung,))
        zeitraeume = ", ".join(f"{r.artikel} ({r.ab} bis {r.bis})"
                               for r in ab.itertuples(index=False))
        zeilen.append(f"- **{z.bezeichnung}**: {zeitraeume}")
    return "\n".join(zeilen)


def _retoure_null_verdacht(ablage: Ablage) -> str:
    """Viele Tage mit Retoure exakt null bei hoher Liefermenge koennen auch
    heissen: Retouren werden nicht erfasst statt: sie fallen nicht an."""
    df = ablage.lese("""
        SELECT l.filiale, l.artikel,
               AVG(CASE WHEN COALESCE(r.menge, 0) = 0 THEN 1.0 ELSE 0 END) AS anteil_null,
               AVG(l.menge) AS mittlere_liefermenge, COUNT(*) AS tage
        FROM lieferung l LEFT JOIN retoure r
          ON r.datum = l.datum AND r.filiale = l.filiale AND r.artikel = l.artikel
        WHERE l.menge >= 20
        GROUP BY l.filiale, l.artikel
        HAVING COUNT(*) >= 30 AND anteil_null > 0.6""")
    kopf = "\n## Verdacht: Retoure nicht erfasst (Retoure = 0 bei hoher Liefermenge)\n"
    if df.empty:
        return kopf + "Keine Auffälligkeiten. ✓"
    df = df.sort_values("anteil_null", ascending=False)
    return (kopf + f"**{len(df)} Filiale/Artikel-Paare** mit über 60 % Null-Retoure-Tagen "
            "trotz Liefermenge ≥ 20. Kann echter Dauer-Ausverkauf sein — oder fehlende "
            "Erfassung. Beispiele:\n\n" + df.head(10).round(2).to_markdown(index=False))


def _luecken_je_filiale(ablage: Ablage, von: str, bis: str) -> str:
    geschlossen = ablage.lese(
        "SELECT filialen, bezeichnung, datum_von, datum_bis FROM ereignis"
        " WHERE art = 'geschlossen' ORDER BY datum_von")
    kopf = "\n## Filialen mit Lücken (Eröffnung, Umbau)\n"
    if geschlossen.empty:
        return kopf + "Keine bekannten Schließungen."
    zeilen = [kopf]
    for z in geschlossen.itertuples(index=False):
        zeilen.append(f"- Filiale {z.filialen}: {z.bezeichnung} ({z.datum_von} bis {z.datum_bis})")
    zeilen.append("\nDiese Zeiträume sind beim Lernen und im Rückblick ausgenommen.")
    return "\n".join(zeilen)
