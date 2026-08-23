# Entscheidungen

Jede Zeile: getroffene Annahme oder Verkürzung, mit einem Satz Begründung.

## Umgebung

- **Python 3.12 über `uv`** statt Systempython: das System hat nur 3.9, der
  Auftrag verlangt 3.11+, und `uv` installiert reproduzierbar ohne Adminrechte.

## M1

- **69 statt 80 Artikel**: die Stammdatenliste deckt alle geforderten Fälle ab
  (Warengruppen, Mehrtagesartikel, Teiglinge, Kleinstartikel außerhalb des
  Umfangs); mehr Artikel brächten nur Volumen, keine neue Logik.
- **Umbau und "noch nicht eröffnet" als Ereignis `art='geschlossen'`** statt
  Lücken im Öffnungszeitplan: der Wochenplan bleibt sauber, und die
  Übersteuerung ist an einer Stelle (`Ablage.oeffnung`) implementiert.
- **`INSERT OR IGNORE` auf eindeutige Schlüssel** als Dubletten-Schutz: einfach,
  transaktionssicher, und der Importlauf protokolliert übernommene vs.
  verworfene Zeilen trotzdem.
- **Artikelnummer als TEXT** in allen Tabellen: führende Nullen sind im
  Warenwirtschaftsexport bedeutungstragend und dürfen nie verloren gehen.

## M0

- **Verzeichnisse `daten/`, `modelle/`, `protokoll/` sind nicht versioniert**:
  erzeugte Artefakte, jederzeit aus `demo_daten.py` bzw. dem Nachtlauf
  reproduzierbar; Berichte (`berichte/*.md`) bleiben im Repo, CSVs nicht.
