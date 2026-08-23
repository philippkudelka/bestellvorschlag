"""Schreibt aus der simulierten Welt Dateien, die einem deutschen
Warenwirtschaftsexport aehneln — absichtlich unsauber, damit der Import
etwas zu tun bekommt.

Je Verkaufstag eine Datei ``umsatz_TTMMJJJJ.csv``:
Trennzeichen ;, Zeichensatz cp1252, Dezimalkomma, Datum nur in der
Kopfzeile, Artikelnummern mit fuehrenden Nullen, abgekuerzte Spaltennamen.

Eingebaute Fehler (werden in fehler_protokoll.json festgehalten, damit der
Datenqualitaetsbericht in M3 dagegen geprueft werden kann):
- vereinzelt leere Zeilen und doppelte Zeilen,
- ein Artikel wechselt ab einem Stichtag die Nummer (gleiche Bezeichnung),
- ein paar Tage fehlen komplett.

Daneben saubere Begleitdateien (kein B.I.T.-Bestandteil):
wetter.csv, ereignisse.csv und wahrheit.csv (nur fuer die Bewertung!).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from bv.simulation.welt import Welt

# Artikel, der ab dem Stichtag unter neuer Nummer laeuft (gleiche Bezeichnung)
NUMMERNWECHSEL = {"alt": "00409", "neu": "00459", "ab": "2025-09-01"}


def _de(zahl: float) -> str:
    """Zahl mit Dezimalkomma, zwei Stellen — wie ein deutscher Export."""
    return f"{zahl:.2f}".replace(".", ",")


def _datum_de(iso: str) -> str:
    j, m, t = iso.split("-")
    return f"{t}.{m}.{j}"


def schreibe_exporte(welt: Welt, verzeichnis: str | Path, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    verz = Path(verzeichnis)
    verz.mkdir(parents=True, exist_ok=True)

    tage = welt.tage
    alle_daten = sorted(tage["datum"].unique())

    # ein paar fehlende Tage (nicht am Rand, damit der Rueckblick nicht leidet)
    fehlend = sorted(rng.choice(alle_daten[30:-30], size=3, replace=False).tolist())

    bezeichnung = {a["nummer"]: a["bezeichnung"] for a in welt.artikel}
    doppelte = 0
    leere = 0

    for iso, tag_df in tage.groupby("datum", sort=True):
        if iso in fehlend:
            continue
        zeilen_out: list[str] = []
        for z in tag_df.itertuples(index=False):
            nummer = z.artikel
            if nummer == NUMMERNWECHSEL["alt"] and iso >= NUMMERNWECHSEL["ab"]:
                nummer = NUMMERNWECHSEL["neu"]
            felder = [
                str(z.filiale),
                nummer,
                bezeichnung[z.artikel],
                _de(z.liefermenge),
                _de(z.verkauf),
                _de(z.retoure),
                z.letzter_verkauf if isinstance(z.letzter_verkauf, str) else "",
                z.erster_verkauf if isinstance(z.erster_verkauf, str) else "",
            ]
            zeilen_out.append(";".join(felder))
            if rng.random() < 0.0004:            # vereinzelt doppelte Zeile
                zeilen_out.append(";".join(felder))
                doppelte += 1
            if rng.random() < 0.0006:            # vereinzelt leere Zeile
                zeilen_out.append("")
                leere += 1

        datei = verz / f"umsatz_{iso.replace('-', '')}.csv"
        with open(datei, "w", encoding="cp1252", newline="\r\n") as f:
            f.write("B.I.T. 64 Tagesumsatz je Artikel und Filiale\n")
            f.write(f"Datum: {_datum_de(iso)};;;;;;;\n")
            f.write("\n")
            f.write("Fil.;Art.Nr;Bez.;Vk. Men;Verkauft;Retour;letz. Ver;erst. Ver\n")
            f.write("\n".join(zeilen_out))
            f.write("\n")

    # saubere Begleitdateien
    welt.wetter.to_csv(verz / "wetter.csv", index=False)
    welt.ereignisse.to_csv(verz / "ereignisse.csv", index=False)
    wahrheit = tage[["datum", "filiale", "artikel", "nachfrage"]]
    wahrheit.to_csv(verz / "wahrheit.csv", index=False)

    protokoll = {
        "fehlende_tage": fehlend,
        "doppelte_zeilen": doppelte,
        "leere_zeilen": leere,
        "nummernwechsel": NUMMERNWECHSEL,
        "zeitraum": [alle_daten[0], alle_daten[-1]],
    }
    with open(verz / "fehler_protokoll.json", "w", encoding="utf-8") as f:
        json.dump(protokoll, f, indent=2, ensure_ascii=False)
    return protokoll
