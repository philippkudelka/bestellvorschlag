# Rückrechnung (Backtest)

Zeitraum: 2026-01-01 bis 2026-06-30 — rollierender Ursprung, wöchentliches Neutraining, Laufzeit 152s.

Alle Fehler gegen die **wahre Nachfrage** der Simulation (nur dort messbar); `mae_gegen_verkauf` zum Vergleich gegen den beobachteten Verkauf. `erreichter_servicegrad` = Anteil der Tage ohne Ausverkauf. WAPE statt MAPE, weil MAPE bei kleinen Mengen bricht.

## Servicegradklasse A

| verfahren             |   tage |   mae_stueck |   wape_prozent |   verzerrung_stueck |   erreichter_servicegrad |   retourenquote_prozent |   mae_gegen_verkauf |
|:----------------------|-------:|-------------:|---------------:|--------------------:|-------------------------:|------------------------:|--------------------:|
| inhaber_mittel3       |  12256 |        10.74 |          16.9  |               -2.58 |                     0.45 |                    6.69 |                8.97 |
| modell                |  12256 |        16.87 |          26.55 |               15.35 |                     0.92 |                   20.42 |               17.58 |
| modell_ohne_korrektur |  12256 |        12.45 |          19.6  |                9.05 |                     0.8  |                   14.81 |               11.86 |
| simulierter_mensch    |  12256 |        12.94 |          20.37 |                9.33 |                     0.76 |                   15.28 |               11.14 |
| vorwoche              |  12256 |        14.25 |          22.43 |                9.22 |                     0.74 |                   16.13 |               13.58 |

## Servicegradklasse B

| verfahren             |   tage |   mae_stueck |   wape_prozent |   verzerrung_stueck |   erreichter_servicegrad |   retourenquote_prozent |   mae_gegen_verkauf |
|:----------------------|-------:|-------------:|---------------:|--------------------:|-------------------------:|------------------------:|--------------------:|
| inhaber_mittel3       |  35236 |         5.72 |          21.3  |               -1.5  |                     0.46 |                    8.32 |                4.53 |
| modell                |  35236 |         6.25 |          23.28 |                4.45 |                     0.8  |                   17.1  |                6.14 |
| modell_ohne_korrektur |  35236 |         5.45 |          20.29 |                2.48 |                     0.7  |                   13.52 |                4.57 |
| simulierter_mensch    |  35236 |         6.6  |          24.57 |                4.17 |                     0.75 |                   17.36 |                5.39 |
| vorwoche              |  35236 |         7.11 |          26.5  |                4.11 |                     0.73 |                   18.13 |                6.55 |

## Servicegradklasse C

| verfahren             |   tage |   mae_stueck |   wape_prozent |   verzerrung_stueck |   erreichter_servicegrad |   retourenquote_prozent |   mae_gegen_verkauf |
|:----------------------|-------:|-------------:|---------------:|--------------------:|-------------------------:|------------------------:|--------------------:|
| inhaber_mittel3       |  30640 |         3.86 |          25.92 |               -1.1  |                     0.47 |                   10.01 |                2.92 |
| modell                |  30640 |         3.44 |          23.16 |                0.85 |                     0.65 |                   13.66 |                2.84 |
| modell_ohne_korrektur |  30640 |         3.37 |          22.67 |                0.25 |                     0.6  |                   11.98 |                2.52 |
| simulierter_mensch    |  30640 |         4.34 |          29.21 |                2.46 |                     0.74 |                   19.63 |                3.4  |
| vorwoche              |  30640 |         4.56 |          30.65 |                2.41 |                     0.73 |                   20.16 |                4.06 |

## Wirkung der Zensierungskorrektur

| Klasse | erreichter Servicegrad mit | ohne | WAPE mit | ohne |
|---|---|---|---|---|
| A | 0.918 | 0.797 | 26.5 % | 19.6 % |
| B | 0.799 | 0.700 | 23.3 % | 20.3 % |
| C | 0.654 | 0.603 | 23.2 % | 22.7 % |

Ohne Korrektur lernt das Modell die zensierten Verkäufe nach und schreibt Ausverkäufe fort — der erreichte Servicegrad fällt.