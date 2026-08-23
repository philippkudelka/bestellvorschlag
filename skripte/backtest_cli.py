"""Rueckrechnung von der Kommandozeile.

Aufruf:  python skripte/backtest_cli.py --von 2026-01-01 --bis 2026-06-30
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bv.ablage import Ablage  # noqa: E402
from bv.backtest import rueckrechnung, schreibe_bericht  # noqa: E402
from bv.konfiguration import lade_konfiguration  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Rueckrechnung (Backtest)")
    p.add_argument("--von", required=True)
    p.add_argument("--bis", required=True)
    args = p.parse_args()

    konfig = lade_konfiguration()
    start = time.time()
    with Ablage(konfig.datenbank_pfad) as ablage:
        print(f"Rueckrechnung {args.von} bis {args.bis} ...")
        df = rueckrechnung(ablage, konfig, args.von, args.bis)
        dauer = time.time() - start
        md, csv, kz = schreibe_bericht(df, args.von, args.bis, dauer)
    print(f"Fertig in {dauer:.0f}s — Bericht: {md}, Rohdaten: {csv}")
    modell = kz[kz["verfahren"] == "modell"]
    inhaber = kz[kz["verfahren"] == "inhaber_mittel3"]
    if not modell.empty and not inhaber.empty:
        print(f"WAPE Modell:  {modell['wape_prozent'].mean():.1f} %  |  "
              f"WAPE Inhaber-Verfahren: {inhaber['wape_prozent'].mean():.1f} %")


if __name__ == "__main__":
    main()
