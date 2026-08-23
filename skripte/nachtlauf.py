"""Nachtlauf: Import -> Zensierung -> (woechentlich) Training -> Vorschlag
-> Waechter -> Protokoll.

Laeuft jede Nacht nach 23:00, muss bis 06:30 fertig sein. Jeder Schritt ist
einzeln aufrufbar. Bei Modellversagen gibt es immer einen Rueckfallwert.

Beispiele:
  python skripte/nachtlauf.py --liefertag 2026-08-23
  python skripte/nachtlauf.py --nur-import
  python skripte/nachtlauf.py --liefertag 2026-08-23 --kein-training
"""

import argparse
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bv.ablage import Ablage, jetzt  # noqa: E402
from bv.konfiguration import PROJEKTWURZEL, lade_konfiguration  # noqa: E402

PROTOKOLL_VERZEICHNIS = PROJEKTWURZEL / "protokoll"


class Protokoll:
    """Schreibt strukturiert und lesbar nach protokoll/JJJJ-MM-TT.log."""

    def __init__(self):
        PROTOKOLL_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
        self.pfad = PROTOKOLL_VERZEICHNIS / f"{jetzt().date().isoformat()}.log"
        self.datei = open(self.pfad, "a", encoding="utf-8")

    def schreibe(self, schritt: str, text: str) -> None:
        zeile = f"{jetzt().isoformat(timespec='seconds')}  [{schritt:<12}] {text}"
        print(zeile)
        self.datei.write(zeile + "\n")
        self.datei.flush()


def main() -> int:
    p = argparse.ArgumentParser(description="Naechtlicher Lauf")
    p.add_argument("--liefertag", help="ISO-Datum des Liefertags (Vorgabe: morgen)")
    p.add_argument("--nur-import", action="store_true")
    p.add_argument("--nur-zensierung", action="store_true")
    p.add_argument("--nur-training", action="store_true")
    p.add_argument("--nur-vorschlag", action="store_true")
    p.add_argument("--nur-waechter", action="store_true")
    p.add_argument("--kein-training", action="store_true")
    p.add_argument("--training-erzwingen", action="store_true")
    p.add_argument("--modell-abschalten", action="store_true",
                   help="Nur fuer Tests: erzwingt den Rueckfallweg")
    args = p.parse_args()

    nur_schalter = [args.nur_import, args.nur_zensierung, args.nur_training,
                    args.nur_vorschlag, args.nur_waechter]
    alles = not any(nur_schalter)

    konfig = lade_konfiguration()
    liefertag = args.liefertag or (jetzt().date() + timedelta(days=1)).isoformat()
    log = Protokoll()
    log.schreibe("start", f"Nachtlauf, Liefertag {liefertag}")
    fehler = 0

    with Ablage(konfig.datenbank_pfad) as ablage:
        if alles or args.nur_import:
            try:
                from bv.einlesen import importiere_synthetisch
                stat = importiere_synthetisch(ablage, konfig)
                log.schreibe("import", f"{stat['dateien_neu']} neue von "
                             f"{stat['dateien_gesamt']} Dateien importiert")
                from bv.qualitaet import erzeuge_bericht
                pfad = erzeuge_bericht(ablage)
                log.schreibe("qualitaet", f"Bericht: {pfad}")
            except Exception:
                fehler += 1
                log.schreibe("import", "FEHLER:\n" + traceback.format_exc())

        if alles or args.nur_zensierung:
            try:
                from bv.zensierung import korrigiere_zensierung
                stat = korrigiere_zensierung(ablage, konfig)
                log.schreibe("zensierung", f"{stat['tage']} Tageszeilen, davon "
                             f"{stat['geschaetzt']} hochgerechnet, "
                             f"{stat['unsicher']} unsicher")
            except Exception:
                fehler += 1
                log.schreibe("zensierung", "FEHLER:\n" + traceback.format_exc())

        if (alles and not args.kein_training) or args.nur_training:
            try:
                from bv.modell import trainiere_falls_faellig
                heute = date.fromisoformat(liefertag) - timedelta(days=1)
                stand = trainiere_falls_faellig(
                    ablage, konfig, heute, erzwingen=args.training_erzwingen
                    or args.nur_training)
                log.schreibe("training", stand or "uebersprungen (nicht faellig)")
            except Exception:
                fehler += 1
                log.schreibe("training", "FEHLER:\n" + traceback.format_exc())

        if alles or args.nur_vorschlag:
            try:
                from bv.vorschlag import erzeuge_vorschlaege
                stat = erzeuge_vorschlaege(
                    ablage, konfig, liefertag,
                    modell_abschalten=args.modell_abschalten)
                log.schreibe("vorschlag", f"{stat['anzahl']} Vorschlaege fuer "
                             f"{stat['filialen']} Filialen, Modellstand {stat['modellstand']}"
                             + (f", {stat['rueckfall']} Rueckfallwerte"
                                if stat.get("rueckfall") else ""))
            except Exception:
                fehler += 1
                log.schreibe("vorschlag", "FEHLER:\n" + traceback.format_exc())

        if alles or args.nur_waechter:
            try:
                from bv.waechter import pruefe
                meldungen = pruefe(ablage, konfig, liefertag)
                if meldungen:
                    for m in meldungen:
                        log.schreibe("waechter", "WARNUNG: " + m)
                else:
                    log.schreibe("waechter", "alle Pruefungen bestanden")
            except Exception:
                fehler += 1
                log.schreibe("waechter", "FEHLER:\n" + traceback.format_exc())

    log.schreibe("ende", f"fertig, {fehler} Fehler")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
