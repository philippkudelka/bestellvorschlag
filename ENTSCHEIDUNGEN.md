# Entscheidungen

Jede Zeile: getroffene Annahme oder Verkürzung, mit einem Satz Begründung.

## Umgebung

- **Python 3.12 über `uv`** statt Systempython: das System hat nur 3.9, der
  Auftrag verlangt 3.11+, und `uv` installiert reproduzierbar ohne Adminrechte.

## M0

- **Verzeichnisse `daten/`, `modelle/`, `protokoll/` sind nicht versioniert**:
  erzeugte Artefakte, jederzeit aus `demo_daten.py` bzw. dem Nachtlauf
  reproduzierbar; Berichte (`berichte/*.md`) bleiben im Repo, CSVs nicht.
