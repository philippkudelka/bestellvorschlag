"""Kuer: Zuordnungsvorschlag fuer eine echte B.I.T.-64-Exportdatei.

Liest eine unbekannte CSV, raet Zeichensatz, Trennzeichen und Kopfzeilen,
und schlaegt anhand von Spaltennamen UND Spalteninhalten eine Zuordnung zu
den Pflichtfeldern vor — als fertiger YAML-Ausschnitt fuer
konfiguration/einstellungen.yaml. Damit dauert der erste Kontakt mit den
echten Daten eine halbe Stunde und nicht zwei Tage.

Aufruf:  python skripte/bit_zuordnung.py pfad/zur/datei.csv
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Namens-Hinweise je Zielfeld (kleingeschrieben, Teilstring-Treffer)
NAMENSMUSTER = {
    "filiale": ["fil", "laden", "verkaufsstelle", "vst"],
    "artikel": ["art", "artnr", "nummer"],
    "bezeichnung": ["bez", "name", "text"],
    "datum": ["datum", "tag", "date"],
    "liefermenge": ["vk. men", "liefer", "menge", "geliefert", "bestellt"],
    "verkauf": ["verkauft", "verkauf", "umsatz", "abverkauf"],
    "retoure": ["retour", "rueck", "rück"],
    "erster_verkauf": ["erst", "erster"],
    "letzter_verkauf": ["letz", "letzter"],
}

MUSTER_UHRZEIT = re.compile(r"^\d{1,2}:\d{2}$")
MUSTER_DATUM_DE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
MUSTER_ZAHL_DE = re.compile(r"^-?\d{1,6}(,\d+)?$")
MUSTER_NUMMER_MIT_NULLEN = re.compile(r"^0\d+$")


def rate_zeichensatz(pfad: Path) -> str:
    roh = pfad.read_bytes()[:20000]
    try:
        roh.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def rate_trennzeichen(zeilen: list[str]) -> str:
    kandidaten = [";", "\t", ",", "|"]
    beste, bester_wert = ";", 0
    for k in kandidaten:
        wert = sum(z.count(k) for z in zeilen[:20])
        if wert > bester_wert:
            beste, bester_wert = k, wert
    return beste


def rate_kopfzeilen(zeilen: list[str], trenner: str) -> int:
    """Erste Zeile, die wie eine Spaltenueberschrift aussieht (mehrere
    Felder, keine reinen Zahlen)."""
    for i, z in enumerate(zeilen[:20]):
        teile = [t.strip() for t in z.split(trenner)]
        if len(teile) >= 4 and not any(MUSTER_ZAHL_DE.match(t) for t in teile if t):
            if i + 1 < len(zeilen) and len(zeilen[i + 1].split(trenner)) >= len(teile) - 1:
                return i
    return 0


def inhaltshinweise(werte: list[str]) -> set[str]:
    """Welche Zielfelder passen zum INHALT einer Spalte?"""
    werte = [w.strip() for w in werte if w.strip()][:200]
    if not werte:
        return set()
    hinweise = set()
    anteil = lambda muster: sum(bool(muster.match(w)) for w in werte) / len(werte)  # noqa: E731
    if anteil(MUSTER_UHRZEIT) > 0.7:
        hinweise |= {"erster_verkauf", "letzter_verkauf"}
    if anteil(MUSTER_DATUM_DE) > 0.7:
        hinweise.add("datum")
    if anteil(MUSTER_NUMMER_MIT_NULLEN) > 0.5:
        hinweise.add("artikel")
    if anteil(MUSTER_ZAHL_DE) > 0.8:
        eindeutig = {w for w in werte}
        if all(len(w) <= 3 and "," not in w for w in werte) and len(eindeutig) <= 30:
            hinweise.add("filiale")
        hinweise |= {"liefermenge", "verkauf", "retoure"}
    return hinweise


def schlage_zuordnung_vor(pfad: Path) -> dict:
    zeichensatz = rate_zeichensatz(pfad)
    with open(pfad, encoding=zeichensatz) as f:
        zeilen = f.read().splitlines()
    trenner = rate_trennzeichen(zeilen)
    kopf = rate_kopfzeilen(zeilen, trenner)
    spaltennamen = [s.strip() for s in zeilen[kopf].split(trenner)]
    datenzeilen = [z.split(trenner) for z in zeilen[kopf + 1:] if z.strip()]

    zuordnung: dict[str, str | None] = {feld: None for feld in NAMENSMUSTER}
    vergeben: set[str] = set()
    for feld, muster in NAMENSMUSTER.items():
        for i, name in enumerate(spaltennamen):
            if name in vergeben or not name:
                continue
            klein = name.lower()
            werte = [z[i] if i < len(z) else "" for z in datenzeilen]
            passt_name = any(m in klein for m in muster)
            passt_inhalt = feld in inhaltshinweise(werte)
            if passt_name and (passt_inhalt or feld == "bezeichnung"):
                zuordnung[feld] = name
                vergeben.add(name)
                break
        else:
            # zweiter Durchgang: nur der Inhalt
            for i, name in enumerate(spaltennamen):
                if name in vergeben or not name:
                    continue
                werte = [z[i] if i < len(z) else "" for z in datenzeilen]
                if feld in inhaltshinweise(werte):
                    zuordnung[feld] = name
                    vergeben.add(name)
                    break
    return {
        "zeichensatz": zeichensatz, "trennzeichen": trenner,
        "kopfzeilen": kopf + 1, "spalten": zuordnung,
        "spaltennamen": spaltennamen,
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Zuordnungsvorschlag fuer B.I.T.-Export")
    p.add_argument("datei")
    args = p.parse_args()
    pfad = Path(args.datei)
    ergebnis = schlage_zuordnung_vor(pfad)

    print(f"Datei: {pfad}")
    print(f"Gefundene Spalten: {ergebnis['spaltennamen']}")
    offen = [f for f, s in ergebnis["spalten"].items() if s is None]
    if offen:
        print(f"NICHT zuordenbar (bitte von Hand pruefen): {', '.join(offen)}")
    print("\nVorschlag fuer konfiguration/einstellungen.yaml:\n")
    print("bit_csv:")
    print(f"  verzeichnis: {pfad.parent}")
    print(f"  trennzeichen: \"{ergebnis['trennzeichen']}\"")
    print(f"  zeichensatz: \"{ergebnis['zeichensatz']}\"")
    print(f"  kopfzeilen: {ergebnis['kopfzeilen']}")
    print("  spalten:")
    for feld, spalte in ergebnis["spalten"].items():
        wert = f'"{spalte}"' if spalte else "null"
        print(f"    {feld}: {wert}")


if __name__ == "__main__":
    main()
