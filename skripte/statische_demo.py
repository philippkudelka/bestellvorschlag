"""Baut eine statische Demo der Oberflaeche fuer GitHub Pages unter docs/.

GitHub Pages kann keinen Python-Server ausfuehren. Deshalb werden die
API-Antworten einmalig als JSON-Dateien eingefroren und ein kleiner
fetch-Umleiter (demo_shim.js) vor die unveraenderte app.js geschaltet:
GET-Aufrufe lesen die JSON-Dateien, POST/PUT werden nur vorgetaeuscht.
Die Demo ist damit klickbar, aber schreibt nichts — ein Banner sagt das.

Aufruf:  python skripte/statische_demo.py [--liefertag JJJJ-MM-TT]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from bv import api as api_modul  # noqa: E402
from bv.konfiguration import PROJEKTWURZEL  # noqa: E402

DOCS = PROJEKTWURZEL / "docs"
WEB = PROJEKTWURZEL / "src" / "bv" / "web"

DEMO_SHIM = """\
/* Demo-Umleiter fuer GitHub Pages: kein Server, keine Datenbank.
   GET /api/... -> eingefrorene JSON-Dateien; POST/PUT -> vorgetaeuscht. */
(() => {
  const echt = window.fetch.bind(window);
  window.fetch = (pfad, optionen) => {
    if (typeof pfad !== "string" || !pfad.startsWith("/api/")) {
      return echt(pfad, optionen);
    }
    const methode = (optionen && optionen.method) || "GET";
    if (methode !== "GET") {
      return Promise.resolve(new Response('{"demo": true}',
        { status: 200, headers: { "Content-Type": "application/json" } }));
    }
    const url = new URL(pfad, "http://demo");
    const name = url.pathname.replace("/api/", "");
    const filiale = url.searchParams.get("filiale");
    const datei = filiale ? `api/${name}_${filiale}.json` : `api/${name}.json`;
    return echt(datei);
  };
})();
"""

BANNER = """\
  <div style="background:#fdf3cc;border-bottom:1px solid #8a6a00;color:#8a6a00;
    padding:10px 24px;font-size:0.9rem;">
    Statische Demo mit <strong>simulierten Daten</strong> (Stand: Liefertag
    {liefertag}) — kein Angebot der B&auml;ckerei Anders. Eingaben werden
    nicht gespeichert; der Liefertag-Wechsel ist in der Demo ohne Wirkung.
  </div>
"""


def main() -> None:
    p = argparse.ArgumentParser(description="Statische Demo bauen")
    p.add_argument("--liefertag", default=None)
    args = p.parse_args()

    client = TestClient(api_modul.app)
    api_verz = DOCS / "api"
    if DOCS.exists():
        shutil.rmtree(DOCS)
    api_verz.mkdir(parents=True)

    def speichere(name: str, pfad: str) -> dict | list:
        antwort = client.get(pfad)
        antwort.raise_for_status()
        daten = antwort.json()
        (api_verz / f"{name}.json").write_text(
            json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        return daten

    uebersicht = speichere(
        "tagesuebersicht",
        "/api/tagesuebersicht" + (f"?liefertag={args.liefertag}" if args.liefertag else ""))
    liefertag = uebersicht["liefertag"]
    filialen = speichere("filialen", "/api/filialen")
    speichere("ereignisse", "/api/ereignisse")
    speichere("zustand", "/api/zustand")
    for f in filialen:
        nummer = f["nummer"]
        speichere(f"vorschlag_{nummer}",
                  f"/api/vorschlag?filiale={nummer}&liefertag={liefertag}")
        speichere(f"einstellungen_{nummer}",
                  f"/api/einstellungen?filiale={nummer}&liefertag={liefertag}")

    # Oberflaeche kopieren, Pfade relativ machen, Banner und Umleiter einbauen
    (DOCS / "demo_shim.js").write_text(DEMO_SHIM, encoding="utf-8")
    shutil.copy(WEB / "stil.css", DOCS / "stil.css")
    shutil.copy(WEB / "app.js", DOCS / "app.js")
    html = (WEB / "index.html").read_text(encoding="utf-8")
    html = html.replace('href="/web/stil.css"', 'href="stil.css"')
    html = html.replace('src="/web/app.js"',
                        'src="demo_shim.js"></script>\n  <script src="app.js"')
    html = html.replace("<body>", "<body>\n" + BANNER.format(liefertag=liefertag))
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Statische Demo unter {DOCS} gebaut (Liefertag {liefertag}, "
          f"{len(filialen)} Filialen).")


if __name__ == "__main__":
    main()
