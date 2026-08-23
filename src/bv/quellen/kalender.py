"""Feiertage und Schulferien Bayern — vollstaendig offline.

Feiertage kommen aus dem Paket `holidays` (rechnet lokal, kein Netz).
Schulferien sind fest hinterlegt; die Termine sind den amtlichen
Ferienordnungen nachempfunden und fuer die Simulation ausreichend genau.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache

import holidays as _holidays

# (von, bis, bezeichnung) — jeweils einschliesslich
SCHULFERIEN_BAYERN: list[tuple[str, str, str]] = [
    ("2023-07-31", "2023-09-11", "Sommerferien"),
    ("2023-10-30", "2023-11-03", "Herbstferien"),
    ("2023-12-23", "2024-01-05", "Weihnachtsferien"),
    ("2024-02-12", "2024-02-16", "Faschingsferien"),
    ("2024-03-25", "2024-04-06", "Osterferien"),
    ("2024-05-21", "2024-05-31", "Pfingstferien"),
    ("2024-07-29", "2024-09-09", "Sommerferien"),
    ("2024-10-28", "2024-10-31", "Herbstferien"),
    ("2024-12-23", "2025-01-03", "Weihnachtsferien"),
    ("2025-03-03", "2025-03-07", "Faschingsferien"),
    ("2025-04-14", "2025-04-25", "Osterferien"),
    ("2025-06-10", "2025-06-20", "Pfingstferien"),
    ("2025-08-01", "2025-09-15", "Sommerferien"),
    ("2025-11-03", "2025-11-07", "Herbstferien"),
    ("2025-12-22", "2026-01-05", "Weihnachtsferien"),
    ("2026-02-16", "2026-02-20", "Faschingsferien"),
    ("2026-03-30", "2026-04-10", "Osterferien"),
    ("2026-05-26", "2026-06-05", "Pfingstferien"),
    ("2026-08-03", "2026-09-14", "Sommerferien"),
]


@lru_cache(maxsize=8)
def _feiertage(jahre: tuple[int, ...]) -> dict:
    return _holidays.Germany(subdiv="BY", years=list(jahre))


def ist_feiertag(tag: date) -> bool:
    return tag in _feiertage(tuple(range(2022, 2028)))


def ist_tag_vor_feiertag(tag: date) -> bool:
    return ist_feiertag(tag + timedelta(days=1))


def ist_tag_nach_feiertag(tag: date) -> bool:
    return ist_feiertag(tag - timedelta(days=1))


def ist_brueckentag(tag: date) -> bool:
    """Freitag nach Feiertags-Donnerstag oder Montag vor Feiertags-Dienstag."""
    if ist_feiertag(tag):
        return False
    if tag.weekday() == 4 and ist_feiertag(tag - timedelta(days=1)):
        return True
    if tag.weekday() == 0 and ist_feiertag(tag + timedelta(days=1)):
        return True
    return False


@lru_cache(maxsize=1)
def _ferien_grenzen() -> list[tuple[date, date, str]]:
    return [(date.fromisoformat(v), date.fromisoformat(b), n)
            for v, b, n in SCHULFERIEN_BAYERN]


def ist_schulferien(tag: date) -> bool:
    return any(v <= tag <= b for v, b, _ in _ferien_grenzen())


def ist_erster_ferientag(tag: date) -> bool:
    return any(tag == v for v, _, _ in _ferien_grenzen())


def ist_letzter_ferientag(tag: date) -> bool:
    return any(tag == b for _, b, _ in _ferien_grenzen())
