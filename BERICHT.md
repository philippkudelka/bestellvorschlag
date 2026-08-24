# Abschlussbericht — Bestellvorschlag, erste lauffähige Fassung

Stand: 2026-08-23; am 2026-08-24 auf die Bäckerei Anders (Bruckmühl)
umgestellt: neun echte Filialen mit Adressen und Öffnungszeiten, echtes
Brotsortiment, Markenfarben — die Verkaufszahlen bleiben simuliert
(Details: ENTSCHEIDUNGEN.md, Abschnitt „Umstellung auf Bäckerei Anders"). Es ist ein System auf **simulierten** Daten. Es beweist,
dass das Verfahren rechnet — nicht, dass es in einer echten Bäckerei
funktioniert.

## Was fertig ist

Alle Meilensteine M0–M9, jeweils mit grünen Tests (37 Tests, `pytest` und
`ruff` sauber):

- **M1** Kanonisches Datenmodell in SQLite; Doppelimport erzeugt keine Dubletten.
- **M2** Simulator: drei Jahre, zehn Filialen, 69 Artikel, mit bekannter
  Wahrheit, Zensierung über Tagesverlaufskurven und absichtlich unsauberem
  B.I.T.-ähnlichem Export (cp1252, Dezimalkomma, Kopfzeilen, Dubletten,
  Nummernwechsel, fehlende Tage).
- **M3** Import inklusive Datenqualitätsbericht — er findet alle absichtlich
  eingebauten Fehler (fehlende Tage, Nummernwechsel Krapfen, Umbau-/
  Eröffnungslücken).
- **M4** Zensierungskorrektur: an zensierten Tagen sinkt der Fehler gegen die
  Wahrheit um **56.6 %** (4.32 → 1.87 Stück, Erkennungsquote 99 %); die
  Untergrenze 45 % steht als Test.
- **M5** Merkmale strikt bis T−2 (eigener Einschleusungstest), Wetter als
  damalige Vorhersage, LightGBM-Quantilmodelle je Warengruppe mit
  sklearn-Rückfallebene, versionierte Modellstände.
- **M6** Servicegrad → Quantil mit Übersteuerung, Vorschläge mit Begründung
  in normaler Sprache und Auffälligkeitsmerker.
- **M7** Rückrechnung: 6 Monate, rollierend, wöchentliches Neutraining, in
  **152 s** (Vorgabe: unter 10 Minuten).
- **M8** Nachtlauf mit Schaltern, Protokoll, Wächter, WARNUNG.md; bei
  abgeschaltetem Modell bekommen alle Filialen einen als Notbehelf
  gekennzeichneten Rückfallwert (Test vorhanden).
- **M9** Tablet-Oberfläche (vier Ansichten, Querformat, ohne Bauschritt),
  im Browser geprüft; Servicegrad-Änderung wirkt sofort sichtbar auf die Menge.
- **Kür:** Mehrtagesartikel (Bestandsrechenweg mit Übertrag),
  Newsvendor-Vergleichsspalte, Ausreißerdämpfung beim Lernen,
  Zuordnungsskript für echte B.I.T.-Dateien.

## Was nicht fertig ist

- **Anbindung des echten B.I.T.-64-Exports** — bewusst: es liegen keine
  echten Daten vor. Der Adapter ist ein Platzhalter mit dokumentierter
  Erwartung (README.md) und `skripte/bit_zuordnung.py` für den ersten Kontakt.
- **Aktionen/Angebote artikelgenau**: nur die pauschale Ereignis-Wirkung je
  Filiale fließt ein; ein Merkmal „Artikel im Angebot" mit gelerntem Hebel fehlt.
- **Mehrtagesartikel** rechnen ohne Modell (Heuristik mit Übertrag); echte
  Bestandsführung braucht rückdatierbare Retouren, die das Fremdsystem laut
  Auftrag heute nicht liefert.
- Kein Betriebsthema gelöst: kein Benutzerkonzept, keine Rechte, kein
  Backup, kein systemd/launchd-Eintrag für den Nachtlauf.

## Annahmen — vollständig

Die Liste, an der es mit echten Daten zuerst scheitern könnte
(Details in ENTSCHEIDUNGEN.md):

1. **`Vk. Men` = Liefermenge** im Export; `Verkauft` und `Retour` getrennt
   vorhanden. Reine Interpretation einer mehrdeutigen Abkürzung.
2. **Das Datum steht in der Kopfzeile** der Tagesdatei, nicht als Spalte.
3. **`letz. Ver` (Uhrzeit des letzten Verkaufs) ist im Export enthalten** —
   ohne dieses Feld gibt es keine Ausverkaufserkennung, der Kern entfällt.
4. **Retouren werden am Verkaufstag erfasst** (keine Rückdatierung); bei
   Mehrtagesartikeln ist das falsch, das Datenmodell hält beide Daten offen.
5. **Stundenumsatz ist für ein kurzes Fenster abrufbar** (hier: 56 Tage);
   fehlt er ganz, laufen nur Standard-Tagesverlaufskurven je Warengruppe —
   die Hochrechnung wird entsprechend gröber.
6. **Öffnungszeiten werden von Hand gepflegt** (konfiguration/filialen.yaml)
   und stimmen mit der Wirklichkeit überein — sie sind Pflichtdaten; jede
   Abweichung verfälscht die Ausverkaufserkennung direkt.
7. **An Feiertagen gilt der Sonntagsplan** (Filialen ohne Sonntagsöffnung
   geschlossen). Vermutung, keine Auskunft des Betriebs.
8. **Bayerische Schulferien sind fest hinterlegt** und nur bis 2026 gepflegt.
9. **Ein Wetterort für alle Filialen**; Monatsnormale fest im Code.
10. **Wochentags-, Saison-, Wetter- und Ereigniswirkungen der Simulation**
    sind plausible Setzungen, keine gemessenen Größen. Alle Kennzahlen unten
    gelten für diese simulierte Welt.
11. **Servicegrade starten je Artikel identisch für alle Filialen** (aus
    artikel.yaml) und werden über die Oberfläche je Filiale verfeinert.
12. **Nummernwechsel** werden über `artikel_umbenennungen` in
    einstellungen.yaml von Hand zugeordnet (der Qualitätsbericht findet sie).

## Kennzahlen der Rückrechnung (2026-01-01 bis 2026-06-30, gegen die wahre Nachfrage)

Neu gerechnet am 2026-08-24 auf der Anders-Welt (9 Filialen, Anders-Sortiment, 140 s):

| Verfahren | erreichter Servicegrad A / B / C | WAPE A / B / C | Retourenquote A / B / C |
|---|---|---|---|
| Modell (mit Korrektur) | **0.91 / 0.80 / 0.65** | 27.0 / 23.5 / 22.8 % | 20.7 / 17.2 / 13.5 % |
| Modell ohne Zensierungskorrektur | 0.79 / 0.70 / 0.60 | 19.7 / 20.5 / 22.5 % | 14.9 / 13.6 / 12.0 % |
| Inhaber-Verfahren (Mittel 3 Wochentage) | 0.45 / 0.46 / 0.47 | 17.0 / 21.8 / 25.7 % | 6.8 / 8.4 / 10.0 % |
| simulierter Mensch | 0.77 / 0.74 / 0.74 | 20.4 / 24.7 / 28.9 % | 15.3 / 17.4 / 19.5 % |
| Vorwoche | 0.74 / 0.72 / 0.72 | 22.8 / 26.7 / 30.5 % | 16.4 / 18.2 / 20.1 % |

Einordnung in einem Satz: Das Modell ist das einzige Verfahren, das die
eingestellten Servicegrade tatsächlich trifft (Ziel 0.95/0.80/0.60, erreicht
0.91/0.80/0.65) — es kauft das mit höherer Retoure, genau wie es die Klassen
verlangen, während das reine Wochentagsmittel zwar wenig Retoure hat, aber
an jedem zweiten Tag ausverkauft wäre; und ohne Zensierungskorrektur fällt
Klasse A von 0.91 auf 0.79, weil das Modell die Ausverkäufe der
Vergangenheit fortschreibt. Vollständige Tabellen: berichte/rueckrechnung.md.

Wichtig: WAPE/Retourenquote des Modells sind KEIN Qualitätsmangel gegenüber
dem Inhaber-Verfahren, sondern Folge des bewusst höheren Quantils. Das
eigentliche Versprechen des Systems ist ohnehin Zeitersparnis (heute ~1,5 h
täglich), nicht Retourensenkung — die 10–12 % des Betriebs sind gewollt.

## Was zuerst zu tun ist, sobald echte Daten da sind

1. `python skripte/bit_zuordnung.py <datei>` laufen lassen, Vorschlag prüfen,
   Zuordnung in `konfiguration/einstellungen.yaml` unter `bit_csv:` eintragen.
2. Annahmen 1–4 an der Datei verifizieren (insbesondere: gibt es `letz. Ver`?).
3. Öffnungszeiten aller neun Filialen gegen die Wirklichkeit prüfen (von der Website übernommen, Stand 2026-08-24) — Pflicht, ohne sie ist
   die Zensierungskorrektur wertlos.
4. `nachtlauf.py --nur-import` + Datenqualitätsbericht lesen; besonders den
   Abschnitt „Retoure = 0 bei hoher Liefermenge" (Verdacht fehlender Erfassung).
5. Simulationsreste trennen: Tabelle `wahrheit` bleibt leer, Kennzahlen der
   Rückrechnung dann nur noch gegen den beobachteten Verkauf (die Spalte
   `mae_gegen_verkauf` existiert bereits).
6. Erst danach: Modell trainieren, zwei Wochen Schattenbetrieb (Vorschlag
   neben der echten Bestellung des Inhabers, Vergleich über die Tabelle
   `bestellung`).

## Stellen, die beim Kontakt mit echten Daten sicher brechen

- [src/bv/quellen/bit_csv.py:36](src/bv/quellen/bit_csv.py:36) — bricht
  gewollt (`NotImplementedError`), bis die Spaltenzuordnung eingetragen ist.
- [src/bv/quellen/synthetisch.py:27](src/bv/quellen/synthetisch.py:27) — der
  Datumsfänger erwartet exakt `Datum: TT.MM.JJJJ` in der Kopfzeile; jede
  andere Kopfform des echten Exports bricht den Import der Tagesdateien.
- [src/bv/einlesen.py:50](src/bv/einlesen.py:50) — `erfasst_am = datum` ist
  für Mehrtagesartikel falsch, sobald das Fremdsystem doch rückdatieren kann.
- [src/bv/einlesen.py:76](src/bv/einlesen.py:76) — der Stundenzeilen-Parser
  erkennt Datenzeilen an einer führenden Ziffer; ein anderes echtes
  Stundenformat fällt lautlos durch (0 Zeilen).
- [src/bv/quellen/kalender.py:16](src/bv/quellen/kalender.py:16) — Schulferien
  enden 2026; ab 2027 rechnet das System stillschweigend „keine Ferien".
- [src/bv/stammdaten.py:75](src/bv/stammdaten.py:75) — Öffnungszeit-Segmente
  sind fest für 2023–2027 erzeugt; ab 2028 gilt keine Öffnungszeit mehr, und
  der Wächter meldet „keine Filiale geöffnet".
- [src/bv/ablage.py:120](src/bv/ablage.py:120) — Feiertagsregel
  „Sonntagsplan an Feiertagen" ist geraten; weicht der Betrieb ab, werden
  Feiertagsverkäufe als „außerhalb der Öffnungszeit" gemeldet und die
  Ausverkaufserkennung an Feiertagen verfälscht.
- [src/bv/merkmale.py:23](src/bv/merkmale.py:23) — Monatsnormal-Temperaturen
  fest im Code; für einen anderen Standort schlicht falsch.
- [src/bv/simulation/export.py:115](src/bv/simulation/export.py:115) — alles
  unter `simulation/` ist Testgeschirr und darf nie gegen echte Daten laufen.

## Git-Verlauf

```
85d18aa Kuer: Mehrtagesartikel, Newsvendor-Spalte, Ausreisserdaempfung, B.I.T.-Zuordnung
b5162cc M9: Tablet-Oberflaeche — vier Ansichten, FastAPI, ohne Bauschritt
c3d6f29 M7: Rueckrechnung fertig — 6 Monate in 152s, Kennzahlentests
12aa6f7 M7-Teil/M8: Rueckrechnung, Nachtlauf komplett, Waechter mit WARNUNG.md
7ec02cf M6: Servicegrad und Vorschlag mit Begruendung
c2f1673 M5: Merkmale und Quantilmodelle
7fb3419 M4: Zensierungskorrektur — Tagesverlaufskurven und Ausverkaufs-Hochrechnung
4d246e1 M3: Import, Quellen-Protokoll und Datenqualitaetsbericht
309e58f M2: Simulator — Welt mit bekannter Wahrheit und B.I.T.-aehnlicher Export
3b61136 M1: Kanonisches Datenmodell und SQLite-Ablage
061fa34 M0: Geruest — pyproject, venv, ruff, pytest, README, Fortschritt, Glossar
```

(Zwischencommits für Fixes ausgelassen; vollständig via `git log --oneline`.)
