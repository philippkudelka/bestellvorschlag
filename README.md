# Bestellvorschlag für eine Handwerksbäckerei

Erzeugt jeden Morgen einen Bestellvorschlag je Filiale und Artikel für eine
Bäckerei mit zehn Filialen. Das System schlägt vor, ein Mensch bestätigt —
es wird nie automatisch bestellt.

## Voraussetzungen

- Python 3.11 oder neuer (hier eingerichtet mit `uv` und Python 3.12)
- Kein Internetzugang zur Laufzeit nötig. Wetter und Kalender kommen aus
  lokalen Dateien bzw. eingebauten Tabellen.

## Einrichtung

```bash
cd bestellvorschlag
uv venv --python 3.12 .venv
uv pip install -p .venv/bin/python -e '.[dev]'
```

Alle folgenden Befehle mit dem Python der virtuellen Umgebung ausführen
(`.venv/bin/python`), oder vorher `source .venv/bin/activate`.

## Ablauf von null auf lauffähig

```bash
# 1. Drei Jahre synthetische Daten erzeugen (Simulator, ~1 Minute)
.venv/bin/python skripte/demo_daten.py

# 2. Nachtlauf: Import, Zensierungskorrektur, Training, Vorschlag, Wächter
.venv/bin/python skripte/nachtlauf.py --liefertag 2026-08-23

# 3. Rückrechnung (Backtest)
.venv/bin/python skripte/backtest_cli.py --von 2026-01-01 --bis 2026-06-30

# 4. Oberfläche starten (Tablet, Querformat)
.venv/bin/uvicorn bv.api:app --host 0.0.0.0 --port 8000
# dann im Browser: http://localhost:8000/
```

## Tests und Linting

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests skripte
```

## Erwartete Struktur des echten B.I.T.-64-Exports

Die Warenwirtschaft ist B.I.T. 64 von Ulmer Kemo. **Es liegen noch keine
echten Exportdateien vor.** Der Adapter `src/bv/quellen/bit_csv.py` ist ein
Platzhalter mit derselben Schnittstelle wie der synthetische Adapter. Sobald
die erste echte Datei da ist, muss nur die Spaltenzuordnung in
`konfiguration/einstellungen.yaml` unter `bit_csv:` ausgefüllt werden.

Gebraucht werden je Verkaufstag, Filiale und Artikel:

| Feld | Bedeutung | Pflicht |
|---|---|---|
| Filialnummer | eindeutige Nummer der Filiale | ja |
| Artikelnummer | eindeutige Nummer des Artikels (führende Nullen erhalten!) | ja |
| Datum | Verkaufstag | ja |
| Liefermenge | an die Filiale gelieferte Stückzahl | ja |
| verkaufte Menge | verkaufte Stückzahl | ja |
| Retoure | zurückgegebene Stückzahl | ja |
| Uhrzeit letzter Verkauf | letzter Kassenbon mit diesem Artikel | ja — ohne sie keine Ausverkaufserkennung |
| Uhrzeit erster Verkauf | erster Kassenbon | wünschenswert |
| Bezeichnung, Warengruppe, Preis | Stammdaten | wünschenswert |

Erwartetes Format (aus Erfahrung mit deutschen Warenwirtschaften, **unbestätigt**):
Trennzeichen `;`, Zeichensatz `cp1252`, Dezimalkomma, Datum `TT.MM.JJJJ`,
Uhrzeit `HH:MM`, ggf. Kopfzeilen vor der Tabelle. Der synthetische Export
(`src/bv/simulation/export.py`) imitiert genau diese Eigenheiten, damit der
Import sie schon heute beherrscht.

**Pflichtdaten außerhalb des Exports:** Öffnungszeiten je Filiale und Datum
(`konfiguration/filialen.yaml`). Ohne sie ist die Ausverkaufserkennung
wertlos — siehe GLOSSAR.md, Stichwort Zensierung.

## Weitere Dokumente

- `ENTSCHEIDUNGEN.md` — getroffene Annahmen und Verkürzungen, je ein Satz Begründung
- `FORTSCHRITT.md` — Meilensteinliste mit Häkchen
- `GLOSSAR.md` — Fachbegriffe
- `BERICHT.md` — Abschlussbericht: was fertig ist, was nicht, Kennzahlen, Bruchstellen
