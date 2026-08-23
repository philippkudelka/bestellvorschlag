"""Rueckrechnung mit rollierendem Ursprung.

Trainiert auf allem bis Tag T, sagt T+1 vorher, geht einen Tag weiter;
neu trainiert wird woechentlich. Verglichen werden vier Verfahren:

1. das Modell (auf der zensierungskorrigierten Nachfrage),
2. Mittel der letzten drei gleichen Wochentage des beobachteten Verkaufs
   — das ist, was der Inhaber heute tut,
3. Liefermenge der Vorwoche,
4. die Liefermenge, die der Simulator dem simulierten Menschen gegeben hat.

Zusaetzlich: das Modell OHNE Zensierungskorrektur (auf rohem Verkauf
gelernt), um die Wirkung der Korrektur zu messen.

Weil es eine Simulation ist, wird der Fehler gegen die WAHRE Nachfrage
gemessen, nicht nur gegen den beobachteten Verkauf.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from bv.ablage import Ablage
from bv.konfiguration import PROJEKTWURZEL, Konfiguration
from bv.merkmale import MERKMALSLISTE, baue_merkmale
from bv.modell import _neues_modell
from bv.servicegrad import einstellungen_je_filiale_artikel

VERFAHREN = ["modell", "modell_ohne_korrektur", "inhaber_mittel3",
             "vorwoche", "simulierter_mensch"]


def rueckrechnung(ablage: Ablage, konfig: Konfiguration, von: str, bis: str) -> pd.DataFrame:
    """Fuehrt die Rueckrechnung aus und gibt die Tageszeilen zurueck:
    je (datum, filiale, artikel) alle Verfahren, Wahrheit und Verkauf."""
    einstellungen = einstellungen_je_filiale_artikel(ablage, konfig, von)
    quantil_je_paar = einstellungen.set_index(["filiale", "artikel"])["quantil"]
    servicegrad_je_paar = einstellungen.set_index(["filiale", "artikel"])["servicegrad"]
    quantile = sorted(einstellungen["quantil"].unique())

    fenster = int(konfig.einstellungen.get("modell", {}).get("backtest_fenster_tage", 200))
    start_merkmale = (date.fromisoformat(von) - timedelta(days=fenster + 35)).isoformat()
    tage = ablage.lese(
        "SELECT DISTINCT datum FROM nachfrage WHERE datum >= ? AND datum <= ?"
        " ORDER BY datum", (start_merkmale, bis))["datum"].tolist()

    # Merkmale EINMAL fuer alles bauen — Rueckblicke haengen nicht vom
    # Trainingsstichtag ab (immer nur Daten bis T-2)
    daten = baue_merkmale(ablage, konfig, tage, mit_ziel=True)
    daten_roh = baue_merkmale(ablage, konfig, tage, mit_ziel=True, quelle="verkauf")

    vorhersagen = _passendes_quantil(
        _rollierende_vorhersage(daten, konfig, von, bis, quantile), quantil_je_paar)
    vorhersagen_roh = _passendes_quantil(
        _rollierende_vorhersage(daten_roh, konfig, von, bis, quantile), quantil_je_paar)

    # Vergleichsverfahren und Bewertungsgroessen
    verkauf = _lade_langtabelle(ablage, konfig, "verkauf")
    lieferung = _lade_langtabelle(ablage, konfig, "lieferung")
    wahrheit = _lade_langtabelle(ablage, konfig, "wahrheit", mengenspalte="nachfrage")

    schluessel = ["datum", "filiale", "artikel"]
    im_umfang = set(ablage.lese(
        "SELECT nummer FROM artikel WHERE im_umfang = 1")["nummer"])
    df = wahrheit.rename(columns={"menge": "wahrheit"})
    df = df[(df["datum"] >= von) & (df["datum"] <= bis)]
    df = df[df["artikel"].isin(im_umfang)]
    df = df.merge(verkauf.rename(columns={"menge": "verkauf"}), on=schluessel, how="left")
    df = df.merge(lieferung.rename(columns={"menge": "simulierter_mensch"}),
                  on=schluessel, how="left")

    vw = lieferung.copy()
    vw["datum"] = (pd.to_datetime(vw["datum"]) + pd.Timedelta(days=7)).dt.strftime("%Y-%m-%d")
    df = df.merge(vw.rename(columns={"menge": "vorwoche"}), on=schluessel, how="left")

    df = df.merge(_inhaber_mittel3(verkauf), on=schluessel, how="left")

    df = df.merge(vorhersagen.rename(columns={"vorhersage": "modell"}),
                  left_on=schluessel, right_on=["liefertag", "filiale", "artikel"],
                  how="left").drop(columns=["liefertag"])
    df = df.merge(vorhersagen_roh.rename(
        columns={"vorhersage": "modell_ohne_korrektur"}),
        left_on=schluessel, right_on=["liefertag", "filiale", "artikel"],
        how="left").drop(columns=["liefertag"])

    paare = pd.MultiIndex.from_frame(df[["filiale", "artikel"]])
    df["servicegrad"] = servicegrad_je_paar.reindex(paare).to_numpy()
    df["quantil"] = quantil_je_paar.reindex(paare).to_numpy()
    for spalte in VERFAHREN:
        df[spalte] = df[spalte].round()
    # fairer Vergleich: alle Verfahren auf DENSELBEN Zeilen bewerten
    df = df.dropna(subset=["servicegrad", *VERFAHREN])
    return df


def _rollierende_vorhersage(
    daten: pd.DataFrame, konfig: Konfiguration, von: str, bis: str,
    quantile: list[float],
) -> pd.DataFrame:
    """Woechentliches Neutraining, Vorhersage der Folgewoche."""
    backend = konfig.modell_backend
    einstellungen = dict(konfig.einstellungen.get("modell", {}))
    einstellungen["n_estimators"] = int(einstellungen.get("backtest_n_estimators", 60))
    einstellungen["num_leaves"] = int(einstellungen.get("backtest_num_leaves", 31))
    einstellungen["n_jobs"] = int(einstellungen.get("backtest_n_jobs", 4))
    fenster = int(einstellungen.get("backtest_fenster_tage", 200))

    ergebnisse = []
    stichtag = date.fromisoformat(von) - timedelta(days=1)
    ende = date.fromisoformat(bis)
    while stichtag < ende:
        prognose_bis = min(stichtag + timedelta(days=7), ende)
        train_von = (stichtag - timedelta(days=fenster)).isoformat()
        train = daten[(daten["liefertag"] >= train_von)
                      & (daten["liefertag"] <= stichtag.isoformat())].dropna(subset=["ziel"])
        blick = daten[(daten["liefertag"] > stichtag.isoformat())
                      & (daten["liefertag"] <= prognose_bis.isoformat())]
        if train.empty or blick.empty:
            stichtag = prognose_bis
            continue
        for wg, train_wg in train.groupby("warengruppe", observed=True):
            blick_wg = blick[blick["warengruppe"] == wg]
            if blick_wg.empty:
                continue
            x_train = train_wg[MERKMALSLISTE]
            y_train = train_wg["ziel"]
            x_blick = blick_wg[MERKMALSLISTE]
            for q in quantile:
                modell = _neues_modell(backend, q, einstellungen)
                modell.fit(x_train, y_train)
                werte = np.maximum(modell.predict(x_blick), 0.0)
                ergebnisse.append(pd.DataFrame({
                    "liefertag": blick_wg["liefertag"].to_numpy(),
                    "filiale": blick_wg["filiale"].to_numpy(),
                    "artikel": blick_wg["artikel"].to_numpy(),
                    "quantil": q,
                    "vorhersage": werte,
                }))
        stichtag = prognose_bis
    if not ergebnisse:
        return pd.DataFrame(columns=["liefertag", "filiale", "artikel", "vorhersage"])
    alle = pd.concat(ergebnisse, ignore_index=True)
    return alle


def _passendes_quantil(vorhersagen: pd.DataFrame, quantil_je_paar: pd.Series) -> pd.DataFrame:
    """Behaelt je (filiale, artikel) nur die Vorhersage des eingestellten Quantils."""
    if vorhersagen.empty:
        return vorhersagen
    paare = pd.MultiIndex.from_frame(vorhersagen[["filiale", "artikel"]])
    soll = quantil_je_paar.reindex(paare).to_numpy()
    passend = vorhersagen[vorhersagen["quantil"].to_numpy() == soll]
    return passend[["liefertag", "filiale", "artikel", "vorhersage"]]


def _inhaber_mittel3(verkauf: pd.DataFrame) -> pd.DataFrame:
    """Mittel der letzten drei gleichen Wochentage des beobachteten Verkaufs."""
    teile = []
    for versatz in (7, 14, 21):
        t = verkauf.copy()
        t["datum"] = (pd.to_datetime(t["datum"])
                      + pd.Timedelta(days=versatz)).dt.strftime("%Y-%m-%d")
        t = t.rename(columns={"menge": f"v{versatz}"})
        teile.append(t)
    zusammen = teile[0]
    for t in teile[1:]:
        zusammen = zusammen.merge(t, on=["datum", "filiale", "artikel"], how="outer")
    zusammen["inhaber_mittel3"] = zusammen[["v7", "v14", "v21"]].mean(axis=1)
    return zusammen[["datum", "filiale", "artikel", "inhaber_mittel3"]]


def _lade_langtabelle(ablage: Ablage, konfig: Konfiguration, tabelle: str,
                      mengenspalte: str = "menge") -> pd.DataFrame:
    df = ablage.lese(
        f"SELECT datum, filiale, artikel, {mengenspalte} AS menge FROM {tabelle}")
    umbenennung = {
        str(alt): str(neu)
        for alt, neu in (konfig.einstellungen.get("artikel_umbenennungen") or {}).items()
    }
    if umbenennung:
        df["artikel"] = df["artikel"].map(lambda a: umbenennung.get(a, a))
        df = df.groupby(["datum", "filiale", "artikel"], as_index=False)["menge"].sum()
    return df


def kennzahlen(df: pd.DataFrame) -> pd.DataFrame:
    """Kennzahlen je Verfahren und Servicegradklasse, gegen die Wahrheit."""
    zeilen = []
    for (verfahren, klasse), gruppe in _ausrollen(df).groupby(["verfahren", "servicegrad"]):
        g = gruppe.dropna(subset=["vorschlag"])
        if g.empty:
            continue
        fehler = g["vorschlag"] - g["wahrheit"]
        zeilen.append({
            "verfahren": verfahren,
            "servicegrad": klasse,
            "tage": len(g),
            "mae_stueck": float(np.abs(fehler).mean()),
            "wape_prozent": float(100 * np.abs(fehler).sum() / g["wahrheit"].sum()),
            "verzerrung_stueck": float(fehler.mean()),
            "erreichter_servicegrad": float((g["vorschlag"] >= g["wahrheit"]).mean()),
            "retourenquote_prozent": float(
                100 * np.maximum(fehler, 0).sum() / max(g["vorschlag"].sum(), 1)),
            "mae_gegen_verkauf": float(np.abs(g["vorschlag"] - g["verkauf"]).mean()),
        })
    return pd.DataFrame(zeilen)


def _ausrollen(df: pd.DataFrame) -> pd.DataFrame:
    laenge = df.melt(
        id_vars=["datum", "filiale", "artikel", "wahrheit", "verkauf", "servicegrad"],
        value_vars=VERFAHREN, var_name="verfahren", value_name="vorschlag")
    return laenge


def schreibe_bericht(df: pd.DataFrame, von: str, bis: str,
                     dauer_sekunden: float) -> tuple:
    kz = kennzahlen(df)
    verz = PROJEKTWURZEL / "berichte"
    verz.mkdir(parents=True, exist_ok=True)
    csv_pfad = verz / "rueckrechnung.csv"
    kz.round(3).to_csv(csv_pfad, index=False)

    teile = [
        "# Rückrechnung (Backtest)",
        f"\nZeitraum: {von} bis {bis} — rollierender Ursprung, wöchentliches "
        f"Neutraining, Laufzeit {dauer_sekunden:.0f}s.",
        "\nAlle Fehler gegen die **wahre Nachfrage** der Simulation "
        "(nur dort messbar); `mae_gegen_verkauf` zum Vergleich gegen den "
        "beobachteten Verkauf. `erreichter_servicegrad` = Anteil der Tage "
        "ohne Ausverkauf. WAPE statt MAPE, weil MAPE bei kleinen Mengen bricht.",
    ]
    for klasse in ["A", "B", "C"]:
        t = kz[kz["servicegrad"] == klasse].drop(columns=["servicegrad"])
        if t.empty:
            continue
        teile.append(f"\n## Servicegradklasse {klasse}\n")
        teile.append(t.round(2).to_markdown(index=False))

    # Wirkung der Zensierungskorrektur gesondert ausweisen
    mit = kz[kz["verfahren"] == "modell"]
    ohne = kz[kz["verfahren"] == "modell_ohne_korrektur"]
    if not mit.empty and not ohne.empty:
        teile.append("\n## Wirkung der Zensierungskorrektur\n")
        teile.append(
            "| Klasse | erreichter Servicegrad mit | ohne | WAPE mit | ohne |\n"
            "|---|---|---|---|---|")
        for klasse in ["A", "B", "C"]:
            m = mit[mit["servicegrad"] == klasse]
            o = ohne[ohne["servicegrad"] == klasse]
            if m.empty or o.empty:
                continue
            teile.append(
                f"| {klasse} | {m.iloc[0]['erreichter_servicegrad']:.3f} "
                f"| {o.iloc[0]['erreichter_servicegrad']:.3f} "
                f"| {m.iloc[0]['wape_prozent']:.1f} % "
                f"| {o.iloc[0]['wape_prozent']:.1f} % |")
        teile.append(
            "\nOhne Korrektur lernt das Modell die zensierten Verkäufe nach "
            "und schreibt Ausverkäufe fort — der erreichte Servicegrad fällt.")

    md_pfad = verz / "rueckrechnung.md"
    md_pfad.write_text("\n".join(teile), encoding="utf-8")
    return md_pfad, csv_pfad, kz
