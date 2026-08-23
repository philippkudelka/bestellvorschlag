# Entscheidungen

Jede Zeile: getroffene Annahme oder Verkürzung, mit einem Satz Begründung.

## Umgebung

- **Python 3.12 über `uv`** statt Systempython: das System hat nur 3.9, der
  Auftrag verlangt 3.11+, und `uv` installiert reproduzierbar ohne Adminrechte.

## M4

- **Stundenumsatz als zusätzliche Exportdatei (letzte 56 Tage)**: aus reinen
  Tagessummen lässt sich keine Tagesverlaufskurve schätzen; echte
  Warenwirtschaften bieten Stundenstatistiken meist nur für kurze Zeiträume,
  genau das bildet der Simulator ab. Fehlen Stundendaten, fällt die Schätzung
  auf Warengruppen- und Standardverläufe zurück — der echte B.I.T.-Anschluss
  funktioniert also auch ohne.
- **Kurvenschätzung nur aus Tagen mit Retoure > 0**: wer Retoure hatte, war
  bis Ladenschluss lieferfähig — der Tagesverlauf ist dann unzensiert.
- **`nachfrage` ist eine abgeleitete Tabelle** und wird bei jedem Lauf für
  den Zeitraum neu berechnet (Kurven verbessern sich mit mehr Daten);
  Rohdaten bleiben unangetastet.
- **Gemessener Nachweis** (Simulationswahrheit, 5 Monate, seed 42): Erkennung
  99 % der zensierten Tage, mittlerer Fehler 4.32 → 1.87 Stück, Verbesserung
  56.6 %. Untergrenze 45 % steht im Test.

## M2

- **Tagesdateien statt Monatsdateien** für den Export: die Spaltenliste des
  Auftrags enthält kein Datum, also steht das Datum wie bei vielen
  Warenwirtschafts-Tagesberichten nur in der Kopfzeile — je Tag eine Datei.
- **`Vk. Men` = Liefermenge**: die Abkürzung ist mehrdeutig; interpretiert als
  "verkaufsfähige Menge" (geliefert), da `Verkauft` separat existiert.
  Beim ersten echten Export prüfen!
- **Ein Wetterort für den ganzen Landkreis** ("Rosenheim"): die Filialen liegen
  nah beieinander, getrenntes Ortswetter brächte der Simulation nichts.
- **Ereigniswirkung gilt je Filiale für alle Artikel**: einfachstes Modell,
  das für Dorffest/Sperrung/Aktion ausreicht.
- **Simulierte Retourenquote ~17 %, Ausverkaufsquote ~24 %** statt der echten
  10–12 %: nach mehreren Kalibrierungsrunden belassen, weil der Simulator
  bewusst reichlich zensierte Tage liefern soll, an denen die Korrektur
  beweisbar wird; die Feinabstimmung auf echte Quoten lohnt erst mit echten
  Daten.
- **Schulferientermine sind Näherungen** der amtlichen bayerischen
  Ferienordnung, fest in `kalender.py` hinterlegt (offline-fähig).
- **An Feiertagen öffnen nur Filialen mit Sonntagsöffnung** (wie sonntags);
  alle anderen bleiben zu — einfachste vertretbare Regel.
- **Der simulierte Mensch** bestellt Mittel der letzten vier gleichen
  Wochentage × 1,14 + 1 Stück, legt nach einem Ausverkauf 15 % drauf und
  kennt den Kalender teilweise — genug Realismus für den Vergleich in M7.

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
