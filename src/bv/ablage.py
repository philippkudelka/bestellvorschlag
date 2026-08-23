"""SQLite-Ablage: eine duenne Schicht ueber sqlite3, kein ORM.

Schreiben laeuft ueber INSERT OR IGNORE auf die eindeutigen Schluessel der
Tabellen — dadurch verdoppelt ein zweimaliger Import desselben Tages nichts,
und Rohdaten werden nie ueberschrieben.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from bv.schema import SCHEMA

ZEITZONE = ZoneInfo("Europe/Berlin")


def jetzt() -> datetime:
    """Aktuelle Zeit in Europe/Berlin."""
    return datetime.now(ZEITZONE)


class Ablage:
    """Zugriff auf die SQLite-Datenbank des Systems."""

    def __init__(self, pfad: str | Path):
        self.pfad = Path(pfad)
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        self.verbindung = sqlite3.connect(self.pfad)
        self.verbindung.execute("PRAGMA journal_mode=WAL")
        self.verbindung.executescript(SCHEMA)

    def schliessen(self) -> None:
        self.verbindung.close()

    def __enter__(self) -> "Ablage":
        return self

    def __exit__(self, *_exc) -> None:
        self.schliessen()

    # ---- Schreiben ----------------------------------------------------

    def schreibe(self, tabelle: str, zeilen: pd.DataFrame) -> int:
        """Schreibt einen DataFrame mit INSERT OR IGNORE. Gibt die Zahl der
        tatsaechlich uebernommenen Zeilen zurueck (Dubletten zaehlen nicht)."""
        if zeilen.empty:
            return 0
        spalten = list(zeilen.columns)
        platzhalter = ", ".join(["?"] * len(spalten))
        sql = f"INSERT OR IGNORE INTO {tabelle} ({', '.join(spalten)}) VALUES ({platzhalter})"
        cur = self.verbindung.cursor()
        vorher = self.verbindung.total_changes
        cur.executemany(sql, zeilen.itertuples(index=False, name=None))
        self.verbindung.commit()
        return self.verbindung.total_changes - vorher

    def leere_tabelle(self, tabelle: str) -> None:
        """Nur fuer abgeleitete Tabellen (nachfrage, vorschlag) gedacht —
        Rohdaten werden nie geloescht."""
        self.verbindung.execute(f"DELETE FROM {tabelle}")
        self.verbindung.commit()

    def protokolliere_import(
        self,
        quelle: str,
        dateiname: str,
        gelesen: int,
        uebernommen: int,
        verworfen: int,
        bemerkung: str = "",
    ) -> None:
        self.verbindung.execute(
            "INSERT INTO import_lauf (zeitpunkt, quelle, dateiname, zeilen_gelesen,"
            " zeilen_uebernommen, zeilen_verworfen, bemerkung) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (jetzt().isoformat(timespec="seconds"), quelle, dateiname, gelesen,
             uebernommen, verworfen, bemerkung),
        )
        self.verbindung.commit()

    # ---- Lesen --------------------------------------------------------

    def lese(self, sql: str, params: tuple | list = ()) -> pd.DataFrame:
        return pd.read_sql_query(sql, self.verbindung, params=list(params))

    def wert(self, sql: str, params: tuple | list = ()):
        zeile = self.verbindung.execute(sql, list(params)).fetchone()
        return zeile[0] if zeile else None

    # ---- Oeffnungszeiten ---------------------------------------------

    def oeffnung(self, filiale: int, datum: date | str) -> list[tuple[str, str]]:
        """Oeffnungszeitraeume (von, bis als HH:MM) einer Filiale an einem Datum.
        Leere Liste = geschlossen. Ein Ereignis der Art 'geschlossen'
        (Umbau, noch nicht eroeffnet) uebersteuert den Wochenplan."""
        if isinstance(datum, str):
            datum = date.fromisoformat(datum)
        iso = datum.isoformat()
        zu = self.verbindung.execute(
            "SELECT COUNT(*) FROM ereignis WHERE art = 'geschlossen'"
            " AND datum_von <= ? AND datum_bis >= ?"
            " AND (filialen = 'alle' OR ',' || filialen || ',' LIKE ?)",
            (iso, iso, f"%,{filiale},%"),
        ).fetchone()[0]
        if zu:
            return []
        # Feiertagsregel: an Feiertagen gilt der Sonntagsplan (Filialen ohne
        # Sonntagsoeffnung sind zu) — gleiche Regel wie im Simulator.
        from bv.quellen import kalender

        wochentag = 6 if kalender.ist_feiertag(datum) else datum.weekday()
        zeilen = self.verbindung.execute(
            "SELECT von, bis FROM oeffnungszeit WHERE filiale = ? AND wochentag = ?"
            " AND gueltig_ab <= ? AND gueltig_bis >= ? ORDER BY von",
            (filiale, wochentag, iso, iso),
        ).fetchall()
        return [(v, b) for v, b in zeilen]

    def ladenschluss(self, filiale: int, datum: date | str) -> str | None:
        """Letzte Schliessminute des Tages als HH:MM, None wenn geschlossen."""
        zeiten = self.oeffnung(filiale, datum)
        return max(b for _, b in zeiten) if zeiten else None

    def oeffnungsminuten(self, filiale: int, datum: date | str) -> int:
        """Gesamtdauer der Oeffnung in Minuten (Pausen abgezogen)."""
        return sum(_minuten(b) - _minuten(v) for v, b in self.oeffnung(filiale, datum))


def _minuten(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)
