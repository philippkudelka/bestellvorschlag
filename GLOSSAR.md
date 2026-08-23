# Glossar

Fachbegriffe des Systems. In Bezeichnern werden sie deutsch und ohne Umlaute
geschrieben (`filiale`, `retoure`, `zielretoure` …); technisches Gerüst
(Repository, Adapter, Protocol) darf englisch heißen.

| Begriff | Bezeichner | Bedeutung |
|---|---|---|
| Filiale | `filiale` | Verkaufsstelle; zehn Stück im Landkreis Rosenheim. |
| Artikel | `artikel` | Ein Produkt aus der Produktion (Brot, Semmel, Breze …). |
| Liefermenge | `liefermenge` | Stückzahl, die morgens aus der Produktion an die Filiale geht. |
| Verkauf | `verkauf` | Tatsächlich an der Kasse verkaufte Stückzahl. **Nicht** die Nachfrage. |
| Retoure | `retoure` | Unverkaufte Ware, die zurückgeht. `retoure = liefermenge − verkauf`. |
| Nachfrage | `nachfrage` | Was verkauft worden **wäre**, hätte die Ware gereicht. Steht in keinem System; wird per Zensierungskorrektur geschätzt. |
| Zensierung | `zensierung` | Der Verkauf ist bei Ausverkauf nach oben abgeschnitten (zensiert): ab der Ausverkaufsminute geht Nachfrage verloren, ohne Spur in den Daten. |
| Ausverkauf | `ausverkauf` | Tag, an dem die Ware vor Ladenschluss ausging. Erkannt nur, wenn Retoure ≈ 0 **und** letzter Verkauf ≥ 10 Min. vor Ladenschluss **und** Verkauf ≈ Liefermenge. |
| Tagesverlaufskurve | `tageskurve` | Typische kumulierte Verteilung des Verkaufs über die Öffnungszeit; Grundlage der Hochrechnung bei Ausverkauf. |
| Servicegrad | `servicegrad` | Klasse A/B/C je Filiale und Artikel: wie sicher der Artikel verfügbar sein soll. A = nie ausgehen (Quantil 0.95), B = spätnachmittags weg (0.80), C = mittags weg (0.60). |
| Quantil | `quantil` | Punkt der Nachfrageverteilung, den das Modell vorhersagt; der Servicegrad wählt das Quantil. |
| Zielretoure | `zielretoure` | Optionale Vorgabe je Filiale/Artikel, welche Retourenquote gewollt ist. |
| Vorschlag | `vorschlag` | Vom System errechnete Bestellmenge je Liefertag, Filiale, Artikel — mit Begründung. Ein Mensch bestätigt; es wird nie automatisch bestellt. |
| Bestellung | `bestellung` | Was der Mensch tatsächlich bestellt hat (für den Vergleich Vorschlag ↔ Wirklichkeit). |
| Liefertag | `liefertag` | Der Tag, für den bestellt wird (Folgetag; freitags der Montag). |
| Öffnungszeit | `oeffnungszeit` | Pflichtdaten je Filiale, Datum und Wochentag; ohne sie ist die Ausverkaufserkennung wertlos. Mehrere Zeiträume je Tag möglich (Mittagspause). |
| Ereignis | `ereignis` | Dorffest, Straßensperrung, Aktion — bekannter äußerer Einfluss auf die Nachfrage. |
| Mehrtagesartikel | `mehrtagesartikel` | Artikel mit zwei Verkaufstagen (Kuchen); Retoure fällt zeitversetzt an. Im Datenmodell vorgesehen, rechnerisch außen vor. |
| Warengruppe | `warengruppe` | Gruppierung der Artikel (Brot, Semmeln, Brezen, Gebäck …); Modelle werden je Warengruppe trainiert. |
| Wächter | `waechter` | Prüfschritt nach dem Nachtlauf: Vollständigkeit, Ausreißer, Modellalter; schreibt WARNUNG.md. |
| Rückfallwert | `rueckfallwert` | Notbehelf, wenn das Modell versagt: Liefermenge der Vorwoche, offen als Notbehelf gekennzeichnet. |
| Rückrechnung | `rueckrechnung` | Backtest mit rollierendem Ursprung: trainieren bis T, vorhersagen für T+1. |
| WAPE | `wape` | Gewichteter absoluter Fehler in Prozent (Summe |Fehler| / Summe Ist); robust bei kleinen Stückzahlen, anders als MAPE. |
| Nachtlauf | `nachtlauf` | Der tägliche Lauf nach 23:00: Import → Zensierung → ggf. Training → Vorschlag → Wächter. Muss bis 06:30 fertig sein. |
| B.I.T. 64 | `bit_csv` | Warenwirtschaft von Ulmer Kemo. Exportformat unbekannt; Adapter ist Platzhalter mit dokumentierter Erwartung. |
| Newsvendor-Quantil | — | Betriebswirtschaftlich optimales Quantil q = (Preis − Herstellkosten) / Preis; nur als Vergleichsspalte. |
