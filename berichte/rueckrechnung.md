# Rückrechnung (Backtest)

Zeitraum: 2026-01-01 bis 2026-06-30 — rollierender Ursprung, wöchentliches Neutraining, Laufzeit 140s.

Alle Fehler gegen die **wahre Nachfrage** der Simulation (nur dort messbar); `mae_gegen_verkauf` zum Vergleich gegen den beobachteten Verkauf. `erreichter_servicegrad` = Anteil der Tage ohne Ausverkauf. WAPE statt MAPE, weil MAPE bei kleinen Mengen bricht.

## Servicegradklasse A

| verfahren             |   tage |   mae_stueck |   wape_prozent |   verzerrung_stueck |   erreichter_servicegrad |   retourenquote_prozent |   mae_gegen_verkauf |
|:----------------------|-------:|-------------:|---------------:|--------------------:|-------------------------:|------------------------:|--------------------:|
| inhaber_mittel3       |  13338 |        11.14 |          16.96 |               -2.6  |                     0.45 |                    6.77 |                9.35 |
| modell                |  13338 |        17.73 |          27    |               16.06 |                     0.91 |                   20.67 |               18.36 |
| modell_ohne_korrektur |  13338 |        12.92 |          19.68 |                9.36 |                     0.79 |                   14.85 |               12.24 |
| simulierter_mensch    |  13338 |        13.37 |          20.35 |                9.74 |                     0.77 |                   15.32 |               11.55 |
| vorwoche              |  13338 |        14.98 |          22.8  |                9.71 |                     0.74 |                   16.37 |               14.3  |

## Servicegradklasse B

| verfahren             |   tage |   mae_stueck |   wape_prozent |   verzerrung_stueck |   erreichter_servicegrad |   retourenquote_prozent |   mae_gegen_verkauf |
|:----------------------|-------:|-------------:|---------------:|--------------------:|-------------------------:|------------------------:|--------------------:|
| inhaber_mittel3       |  37050 |         5.76 |          21.78 |               -1.57 |                     0.46 |                    8.43 |                4.52 |
| modell                |  37050 |         6.23 |          23.54 |                4.41 |                     0.8  |                   17.22 |                6.1  |
| modell_ohne_korrektur |  37050 |         5.43 |          20.51 |                2.39 |                     0.7  |                   13.55 |                4.48 |
| simulierter_mensch    |  37050 |         6.55 |          24.74 |                4.04 |                     0.74 |                   17.35 |                5.29 |
| vorwoche              |  37050 |         7.07 |          26.7  |                3.99 |                     0.72 |                   18.15 |                6.47 |

## Servicegradklasse C

| verfahren             |   tage |   mae_stueck |   wape_prozent |   verzerrung_stueck |   erreichter_servicegrad |   retourenquote_prozent |   mae_gegen_verkauf |
|:----------------------|-------:|-------------:|---------------:|--------------------:|-------------------------:|------------------------:|--------------------:|
| inhaber_mittel3       |  32604 |         3.97 |          25.67 |               -1.11 |                     0.47 |                    9.95 |                3.03 |
| modell                |  32604 |         3.52 |          22.76 |                0.88 |                     0.65 |                   13.47 |                2.89 |
| modell_ohne_korrektur |  32604 |         3.48 |          22.51 |                0.32 |                     0.6  |                   12.04 |                2.6  |
| simulierter_mensch    |  32604 |         4.46 |          28.85 |                2.56 |                     0.74 |                   19.49 |                3.51 |
| vorwoche              |  32604 |         4.72 |          30.53 |                2.52 |                     0.72 |                   20.13 |                4.22 |

## Wirkung der Zensierungskorrektur

| Klasse | erreichter Servicegrad mit | ohne | WAPE mit | ohne |
|---|---|---|---|---|
| A | 0.915 | 0.794 | 27.0 % | 19.7 % |
| B | 0.796 | 0.697 | 23.5 % | 20.5 % |
| C | 0.651 | 0.603 | 22.8 % | 22.5 % |

Ohne Korrektur lernt das Modell die zensierten Verkäufe nach und schreibt Ausverkäufe fort — der erreichte Servicegrad fällt.