"""Erzeugt drei Jahre synthetische Exportdateien unter daten/synthetisch/.

Aufruf:  python skripte/demo_daten.py [--von 2023-08-28] [--bis 2026-08-22]
"""

import argparse
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bv.konfiguration import PROJEKTWURZEL, lade_konfiguration  # noqa: E402
from bv.simulation.export import schreibe_exporte  # noqa: E402
from bv.simulation.welt import erzeuge_welt  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Synthetische Daten erzeugen")
    p.add_argument("--von", default="2023-08-28")
    p.add_argument("--bis", default="2026-08-22")
    p.add_argument("--seed", type=int, default=20260823)
    args = p.parse_args()

    konfig = lade_konfiguration()
    verzeichnis = PROJEKTWURZEL / konfig.einstellungen["synthetisch"]["verzeichnis"]

    start = time.time()
    print(f"Simuliere Welt {args.von} bis {args.bis} ...")
    welt = erzeuge_welt(konfig, date.fromisoformat(args.von), date.fromisoformat(args.bis),
                        seed=args.seed)
    print(f"  {len(welt.tage):,} Tageszeilen in {time.time() - start:.0f}s")

    print(f"Schreibe B.I.T.-aehnliche Exporte nach {verzeichnis} ...")
    protokoll = schreibe_exporte(welt, verzeichnis)
    print(f"  fehlende Tage (absichtlich): {protokoll['fehlende_tage']}")
    print(f"  doppelte Zeilen: {protokoll['doppelte_zeilen']}, "
          f"leere Zeilen: {protokoll['leere_zeilen']}")
    print(f"  Nummernwechsel: {protokoll['nummernwechsel']}")
    print(f"Fertig in {time.time() - start:.0f}s.")


if __name__ == "__main__":
    main()
