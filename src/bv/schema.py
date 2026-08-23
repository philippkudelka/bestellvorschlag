"""Kanonisches Datenmodell: SQL-Schema der SQLite-Ablage.

Die interne Wahrheit des Systems, unabhaengig davon, was ein Fremdsystem
liefert. Rohdaten werden nie ueberschrieben: alle Kern-Tabellen tragen
eindeutige Schluessel, Importe schreiben mit INSERT OR IGNORE und
protokollieren sich in import_lauf.
"""

SCHEMA = """
CREATE TABLE IF NOT EXISTS filiale (
    nummer      INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    ort         TEXT NOT NULL
);

-- Oeffnungszeiten sind Pflichtdaten. Mehrere Zeitraeume je Tag moeglich
-- (Mittagspause); saisonale Aenderung ueber gueltig_ab/gueltig_bis.
CREATE TABLE IF NOT EXISTS oeffnungszeit (
    filiale     INTEGER NOT NULL REFERENCES filiale(nummer),
    gueltig_ab  TEXT NOT NULL,      -- ISO-Datum
    gueltig_bis TEXT NOT NULL,      -- ISO-Datum, einschliesslich
    wochentag   INTEGER NOT NULL,   -- 0 = Montag ... 6 = Sonntag
    von         TEXT NOT NULL,      -- HH:MM
    bis         TEXT NOT NULL,      -- HH:MM
    UNIQUE (filiale, gueltig_ab, gueltig_bis, wochentag, von, bis)
);

CREATE TABLE IF NOT EXISTS artikel (
    nummer          TEXT PRIMARY KEY,   -- als Text: fuehrende Nullen erhalten
    bezeichnung     TEXT NOT NULL,
    warengruppe     TEXT NOT NULL,
    im_umfang       INTEGER NOT NULL DEFAULT 1,
    mehrtagesartikel INTEGER NOT NULL DEFAULT 0,
    preis           REAL,
    herstellkosten  REAL
);

CREATE TABLE IF NOT EXISTS einstellung (
    filiale             INTEGER NOT NULL,
    artikel             TEXT NOT NULL,
    servicegrad         TEXT NOT NULL CHECK (servicegrad IN ('A', 'B', 'C')),
    zielretoure_prozent REAL,
    aktiv_ab            TEXT NOT NULL,
    UNIQUE (filiale, artikel, aktiv_ab)
);

CREATE TABLE IF NOT EXISTS lieferung (
    datum   TEXT NOT NULL,
    filiale INTEGER NOT NULL,
    artikel TEXT NOT NULL,
    menge   REAL NOT NULL,
    UNIQUE (datum, filiale, artikel)
);

CREATE TABLE IF NOT EXISTS verkauf (
    datum          TEXT NOT NULL,
    filiale        INTEGER NOT NULL,
    artikel        TEXT NOT NULL,
    menge          REAL NOT NULL,
    erster_verkauf TEXT,             -- HH:MM, kann fehlen
    letzter_verkauf TEXT,            -- HH:MM, Pflicht fuer Ausverkaufserkennung
    UNIQUE (datum, filiale, artikel)
);

-- datum = Verkaufstag, erfasst_am = Eingabetag. Bei Mehrtagesartikeln fallen
-- die auseinander; das Fremdsystem kann heute nicht rueckdatieren.
CREATE TABLE IF NOT EXISTS retoure (
    datum      TEXT NOT NULL,
    filiale    INTEGER NOT NULL,
    artikel    TEXT NOT NULL,
    menge      REAL NOT NULL,
    erfasst_am TEXT NOT NULL,
    UNIQUE (datum, filiale, artikel, erfasst_am)
);

CREATE TABLE IF NOT EXISTS ereignis (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    datum_von   TEXT NOT NULL,
    datum_bis   TEXT NOT NULL,
    filialen    TEXT NOT NULL,       -- kommagetrennte Nummern oder 'alle'
    bezeichnung TEXT NOT NULL,
    art         TEXT NOT NULL,       -- dorffest, sperrung, aktion, geschlossen ...
    wirkung     REAL NOT NULL DEFAULT 1.0,  -- multiplikativer Faktor auf die Nachfrage
    UNIQUE (datum_von, datum_bis, filialen, bezeichnung)
);

CREATE TABLE IF NOT EXISTS wetter (
    datum          TEXT NOT NULL,
    ort            TEXT NOT NULL,
    temperatur_max REAL,
    niederschlag_mm REAL,
    sonnenstunden  REAL,
    ist_vorhersage INTEGER NOT NULL, -- 1 = damalige Vorhersage, 0 = eingetreten
    UNIQUE (datum, ort, ist_vorhersage)
);

CREATE TABLE IF NOT EXISTS vorschlag (
    erstellt_am TEXT NOT NULL,       -- ISO-Zeitstempel
    liefertag   TEXT NOT NULL,
    filiale     INTEGER NOT NULL,
    artikel     TEXT NOT NULL,
    menge       REAL NOT NULL,
    quantil     REAL NOT NULL,
    begruendung TEXT NOT NULL,
    modellstand TEXT NOT NULL,       -- Verzeichnisname des Modellstands oder 'rueckfall'
    auffaellig  INTEGER NOT NULL DEFAULT 0,
    UNIQUE (liefertag, filiale, artikel, erstellt_am)
);

-- Was tatsaechlich bestellt wurde — fuer den spaeteren Vergleich.
CREATE TABLE IF NOT EXISTS bestellung (
    liefertag TEXT NOT NULL,
    filiale   INTEGER NOT NULL,
    artikel   TEXT NOT NULL,
    menge     REAL NOT NULL,
    UNIQUE (liefertag, filiale, artikel)
);

-- Stundenumsatz, soweit das Fremdsystem ihn hergibt (oft nur fuer kurze
-- Zeitraeume abrufbar). Grundlage der geschaetzten Tagesverlaufskurve;
-- fehlt er, faellt die Schaetzung auf Standardverlaeufe je Warengruppe zurueck.
CREATE TABLE IF NOT EXISTS verkauf_stunde (
    datum   TEXT NOT NULL,
    filiale INTEGER NOT NULL,
    artikel TEXT NOT NULL,
    stunde  INTEGER NOT NULL,   -- 0-23
    menge   REAL NOT NULL,
    UNIQUE (datum, filiale, artikel, stunde)
);

CREATE TABLE IF NOT EXISTS import_lauf (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    zeitpunkt          TEXT NOT NULL,
    quelle             TEXT NOT NULL,
    dateiname          TEXT NOT NULL,
    zeilen_gelesen     INTEGER NOT NULL,
    zeilen_uebernommen INTEGER NOT NULL,
    zeilen_verworfen   INTEGER NOT NULL,
    bemerkung          TEXT
);

-- Ergebnis der Zensierungskorrektur: die geschaetzte echte Nachfrage.
-- Alles Weitere lernt und misst auf dieser Tabelle, nie auf verkauf.
CREATE TABLE IF NOT EXISTS nachfrage (
    datum        TEXT NOT NULL,
    filiale      INTEGER NOT NULL,
    artikel      TEXT NOT NULL,
    menge        REAL NOT NULL,
    ist_geschaetzt INTEGER NOT NULL DEFAULT 0,
    unsicher     INTEGER NOT NULL DEFAULT 0,
    begruendung  TEXT,
    UNIQUE (datum, filiale, artikel)
);

-- Nur der Simulator schreibt hier: die wahre Nachfrage. Ausschliesslich fuer
-- die Bewertung — das Modell darf diese Tabelle niemals sehen.
CREATE TABLE IF NOT EXISTS wahrheit (
    datum   TEXT NOT NULL,
    filiale INTEGER NOT NULL,
    artikel TEXT NOT NULL,
    nachfrage REAL NOT NULL,
    UNIQUE (datum, filiale, artikel)
);

CREATE INDEX IF NOT EXISTS ix_verkauf_datum ON verkauf(datum);
CREATE INDEX IF NOT EXISTS ix_lieferung_datum ON lieferung(datum);
CREATE INDEX IF NOT EXISTS ix_retoure_datum ON retoure(datum);
CREATE INDEX IF NOT EXISTS ix_nachfrage_datum ON nachfrage(datum);
CREATE INDEX IF NOT EXISTS ix_vorschlag_liefertag ON vorschlag(liefertag);
"""
