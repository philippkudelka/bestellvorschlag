/* Oberflaeche im Redesign (apple.com-Stil, Design-Handoff 08/2026).
   Reines JavaScript ohne Bauschritt; API-Aufrufe unveraendert zum Bestand. */

"use strict";

const zustand = {
  ansicht: "uebersicht",
  liefertag: null,
  filiale: null,
  filialen: [],
  warengruppe: "alle",
  nurAuffaellige: false,
  mengen: {},            // filiale -> { artikel -> geaenderte Menge }
  info: null,            // /api/zustand (Modellstand, letzter Import, Warnung)
};

const RETOURE_WARNSCHWELLE = 20; // Prozent

async function api(pfad, optionen) {
  const antwort = await fetch(pfad, optionen);
  if (!antwort.ok) throw new Error(`${pfad}: ${antwort.status}`);
  return antwort.json();
}

function el(id) { return document.getElementById(id); }

function zahl(wert, stellen = 0) {
  if (wert === null || wert === undefined || Number.isNaN(wert)) return "–";
  return Number(wert).toLocaleString("de-DE",
    { minimumFractionDigits: stellen, maximumFractionDigits: stellen });
}

function datumDe(iso) {
  const [j, m, t] = iso.split("-");
  return `${t}.${m}.${j}`;
}

function zeitspanne(text) {
  return (text || "–").replaceAll("-", "–");
}

/* ---------- Navigation ---------------------------------------------- */

document.querySelectorAll("nav button").forEach((knopf) => {
  knopf.addEventListener("click", () => zeigeAnsicht(knopf.dataset.ansicht));
});

function zeigeAnsicht(name) {
  zustand.ansicht = name;
  document.querySelectorAll("nav button").forEach((k) =>
    k.classList.toggle("aktiv", k.dataset.ansicht === name));
  document.querySelectorAll(".ansicht").forEach((a) =>
    a.hidden = a.id !== `ansicht-${name}`);
  window.scrollTo(0, 0);
  lade();
}

el("liefertag").addEventListener("change", (e) => {
  zustand.liefertag = e.target.value;
  lade();
});

function lade() {
  if (zustand.ansicht === "uebersicht") ladeUebersicht();
  if (zustand.ansicht === "bestellung") ladeBestellung();
  if (zustand.ansicht === "servicegrade") ladeServicegrade();
  if (zustand.ansicht === "ereignisse") ladeEreignisse();
}

/* ---------- Fusszeile und Zustand ------------------------------------ */

async function ladeInfo() {
  try {
    zustand.info = await api("/api/zustand");
  } catch {
    zustand.info = null;
  }
  const teile = ["Bäckerei Anders", "Bestellvorschlag"];
  if (zustand.info?.modellstand) teile.push(`Modellstand ${zustand.info.modellstand}`);
  if (zustand.info?.letzter_import?.zeitpunkt) {
    teile.push(`letzter Import ${zustand.info.letzter_import.zeitpunkt.slice(11, 16)} Uhr`);
  }
  el("fusszeile").textContent = teile.join(" · ");
}

function warnungstext(roh) {
  /* Markdown-Kopf, Bullets und Warn-Symbole entfernen — nur der Klartext. */
  return roh
    .split("\n")
    .filter((z) => !z.startsWith("#"))
    .map((z) => z.replace(/^[-*]\s*/, "").replace(/[⚠️]/g, "").trim())
    .filter(Boolean)
    .join("\n");
}

/* ---------- Tagesuebersicht ----------------------------------------- */

const ZUSTAND_DARSTELLUNG = {
  "fertig": ["gruen", "Vorschläge liegen vor und warten auf Übernahme"],
  "bestellt": ["blau", "Bestellung wurde für diesen Liefertag bestätigt"],
  "kein Vorschlag": ["orange", "Für diesen Tag liegen keine Vorschläge vor — Nachtlauf prüfen"],
  "geschlossen": ["leise", "Die Filiale hat an diesem Tag geschlossen"],
};

async function ladeUebersicht() {
  const q = zustand.liefertag ? `?liefertag=${zustand.liefertag}` : "";
  const daten = await api(`/api/tagesuebersicht${q}`);
  zustand.liefertag = daten.liefertag;
  el("liefertag").value = daten.liefertag;
  await ladeInfo();

  const offene = daten.filialen.filter((f) => f.zustand !== "geschlossen");
  const fertige = offene.filter((f) => f.anzahl_vorschlaege > 0);
  const auffaelligSumme = offene.reduce((s, f) => s + f.auffaellig, 0);
  const quoten = offene.map((f) => f.retourenquote_vorwoche).filter((v) => v !== null);
  const mittlereQuote = quoten.length
    ? quoten.reduce((s, v) => s + v, 0) / quoten.length : null;
  const positionenJeFiliale = fertige.length
    ? Math.round(fertige.reduce((s, f) => s + f.anzahl_vorschlaege, 0) / fertige.length)
    : 0;

  const importZeit = zustand.info?.letzter_import?.zeitpunkt
    ? `${zustand.info.letzter_import.zeitpunkt.slice(11, 16)} Uhr` : "–";
  el("uebersicht-subline").textContent =
    `Liefertag ${datumDe(daten.liefertag)} · ${daten.filialen.length} Filialen` +
    ` · letzter Import ${importZeit}`;

  el("statreihe").innerHTML = `
    <div class="stat"><div class="wert">${zahl(positionenJeFiliale)}</div>
      <div class="label">Positionen je Filiale</div>
      <div class="sub">Vorschläge liegen vor</div></div>
    <div class="stat"><div class="wert orange">${zahl(auffaelligSumme)}</div>
      <div class="label">Auffällige Positionen</div>
      <div class="sub">hier zuerst hinschauen</div></div>
    <div class="stat"><div class="wert">${mittlereQuote === null ? "–"
      : zahl(mittlereQuote, 1) + " %"}</div>
      <div class="label">Ø Retourenquote</div>
      <div class="sub">letzte 7 Tage</div></div>
    <div class="stat"><div class="wert">${zahl(daten.filialen.length)}</div>
      <div class="label">Filialen</div>
      <div class="sub">${fertige.length === offene.length
        ? "alle mit fertigem Vorschlag"
        : fertige.length + " von " + offene.length + " mit Vorschlag"}</div></div>`;

  const kasten = el("warnung-kasten");
  if (zustand.info?.warnung) {
    kasten.hidden = false;
    el("warnung-text").textContent = warnungstext(zustand.info.warnung);
  } else {
    kasten.hidden = true;
  }

  const rumpf = el("uebersicht-tabelle").querySelector("tbody");
  rumpf.innerHTML = "";
  for (const f of daten.filialen) {
    const [farbe, erklaerung] = ZUSTAND_DARSTELLUNG[f.zustand] || ["leise", ""];
    const quote = f.retourenquote_vorwoche;
    const zeile = document.createElement("tr");
    zeile.innerHTML = `
      <td><span class="artikelname">${f.name}</span>
        <span class="unterzeile">${f.anschrift}</span></td>
      <td><span class="leise">${zeitspanne(f.oeffnung)}</span></td>
      <td><span class="zustandstext ${farbe}" title="${erklaerung}">${f.zustand}</span></td>
      <td class="zahl">${f.auffaellig > 0
        ? `<span class="warnzahl">${zahl(f.auffaellig)}</span>` : "0"}</td>
      <td class="zahl">${quote === null ? "–"
        : `<span class="${quote > RETOURE_WARNSCHWELLE ? "rotzahl" : "leise"}">${zahl(quote, 1)} %</span>`}</td>
      <td class="zahl">${f.zustand === "geschlossen" ? ""
        : `<a href="#" data-filiale="${f.filiale}">Zur Bestellung ›</a>`}</td>`;
    rumpf.appendChild(zeile);
  }
  rumpf.querySelectorAll("a[data-filiale]").forEach((a) =>
    a.addEventListener("click", (ereignis) => {
      ereignis.preventDefault();
      zustand.filiale = Number(a.dataset.filiale);
      zeigeAnsicht("bestellung");
    }));
}

/* ---------- Filial-Chips --------------------------------------------- */

async function filialchips(zielId, beimWechsel) {
  if (!zustand.filialen.length) zustand.filialen = await api("/api/filialen");
  if (!zustand.filiale) zustand.filiale = zustand.filialen[0].nummer;
  const ziel = el(zielId);
  ziel.innerHTML = "";
  for (const f of zustand.filialen) {
    const chip = document.createElement("button");
    chip.className = "chip" + (f.nummer === zustand.filiale ? " aktiv" : "");
    chip.textContent = `${f.nummer} · ${f.name}`;
    chip.addEventListener("click", () => { zustand.filiale = f.nummer; beimWechsel(); });
    ziel.appendChild(chip);
  }
}

/* ---------- Bestellvorschlag ---------------------------------------- */

let bestellDaten = null;

async function ladeBestellung() {
  await filialchips("bestellung-filialwahl", ladeBestellung);
  const q = zustand.liefertag ? `&liefertag=${zustand.liefertag}` : "";
  bestellDaten = await api(`/api/vorschlag?filiale=${zustand.filiale}${q}`);
  zustand.liefertag = bestellDaten.liefertag;
  el("liefertag").value = bestellDaten.liefertag;

  el("bestellung-titel").textContent = `${bestellDaten.filiale.name}.`;
  el("bestellung-subline").textContent =
    `${bestellDaten.filiale.anschrift} · Liefertag ${datumDe(bestellDaten.liefertag)}` +
    ` · geöffnet ${zeitspanne(bestellDaten.oeffnung)}`;

  zeichneBestellung();
}

function bestellmengeVon(p) {
  const lokal = zustand.mengen[zustand.filiale]?.[p.artikel];
  if (lokal !== undefined) return lokal;
  return p.bestellt ?? p.vorschlag;
}

function zeichneBestellung() {
  const positionen = bestellDaten.positionen;
  const gruppen = [...new Set(positionen.map((p) => p.warengruppe))];
  const auffaellige = positionen.filter((p) => p.auffaellig || p.notbehelf).length;
  const summe = positionen.reduce((s, p) => s + (Number(bestellmengeVon(p)) || 0), 0);

  const filter = el("bestellung-filter");
  filter.innerHTML = "";
  const alleChip = document.createElement("button");
  alleChip.className = "chip" + (zustand.warengruppe === "alle" ? " aktiv" : "");
  alleChip.textContent = "Alle";
  alleChip.addEventListener("click", () => { zustand.warengruppe = "alle"; zeichneBestellung(); });
  filter.appendChild(alleChip);
  for (const g of gruppen) {
    const chip = document.createElement("button");
    chip.className = "chip" + (zustand.warengruppe === g ? " aktiv" : "");
    chip.textContent = g;
    chip.addEventListener("click", () => { zustand.warengruppe = g; zeichneBestellung(); });
    filter.appendChild(chip);
  }
  const rechts = document.createElement("div");
  rechts.className = "rechts";
  const auffChip = document.createElement("button");
  auffChip.className = "chip" + (zustand.nurAuffaellige ? " aktiv-warn" : "");
  auffChip.textContent = `Nur auffällige (${auffaellige})`;
  auffChip.addEventListener("click", () => {
    zustand.nurAuffaellige = !zustand.nurAuffaellige;
    zeichneBestellung();
  });
  rechts.appendChild(auffChip);
  const summeEl = document.createElement("span");
  summeEl.innerHTML = `Summe Bestellmenge <strong>${zahl(summe)}</strong>`;
  rechts.appendChild(summeEl);
  filter.appendChild(rechts);

  const sichtbar = positionen.filter((p) =>
    (zustand.warengruppe === "alle" || p.warengruppe === zustand.warengruppe)
    && (!zustand.nurAuffaellige || p.auffaellig || p.notbehelf));

  const rumpf = el("bestellung-tabelle").querySelector("tbody");
  rumpf.innerHTML = "";
  if (!sichtbar.length) {
    rumpf.innerHTML = `<tr><td colspan="6" class="leer">Keine Positionen
      für diese Auswahl${positionen.length ? "" : " — Nachtlauf prüfen"}.</td></tr>`;
  }
  for (const p of sichtbar) {
    const warn = p.auffaellig || p.notbehelf;
    const untertext = warn ? p.begruendung : p.warengruppe;
    const retoureQuote = p.vorwoche_geliefert
      ? 100 * (p.vorwoche_retoure || 0) / p.vorwoche_geliefert : 0;
    const wert = bestellmengeVon(p);
    const zeile = document.createElement("tr");
    zeile.innerHTML = `
      <td><span class="artikelname">${p.bezeichnung}</span>
        <span class="artikelnummer">${p.artikel}</span>
        <span class="begruendung${warn ? " warn" : ""}"
          title="${(p.begruendung || "").replaceAll('"', "'")}">${untertext || ""}</span></td>
      <td class="zahl"><span class="vorschlagszahl"
        title="${(p.begruendung || "").replaceAll('"', "'")}">${zahl(p.vorschlag)}</span></td>
      <td class="zahl"><span class="leise">${zahl(p.menge_wirtschaftlich)}</span></td>
      <td class="zahl"><span class="leise">${zahl(p.vorwoche_geliefert)}</span></td>
      <td class="zahl"><span class="${retoureQuote > RETOURE_WARNSCHWELLE ? "rotzahl" : "leise"}">${zahl(p.vorwoche_retoure)}</span></td>
      <td class="zahl"><input class="menge${Number(wert) !== Number(p.vorschlag)
        ? " geaendert" : ""}" type="number" min="0" step="1"
        data-artikel="${p.artikel}" data-vorschlag="${p.vorschlag}" value="${wert}"></td>`;
    rumpf.appendChild(zeile);
  }

  rumpf.querySelectorAll("input.menge").forEach((feld) =>
    feld.addEventListener("input", () => {
      feld.classList.toggle("geaendert",
        Number(feld.value) !== Number(feld.dataset.vorschlag));
      const lokal = zustand.mengen[zustand.filiale] ?? {};
      lokal[feld.dataset.artikel] = Number(feld.value) || 0;
      zustand.mengen[zustand.filiale] = lokal;
      const neueSumme = bestellDaten.positionen.reduce(
        (s, p) => s + (Number(bestellmengeVon(p)) || 0), 0);
      summeEl.innerHTML = `Summe Bestellmenge <strong>${zahl(neueSumme)}</strong>`;
    }));

  const knopf = el("bestellung-uebernehmen");
  knopf.disabled = !positionen.length;
  knopf.onclick = async () => {
    const alle = bestellDaten.positionen.map((p) => ({
      artikel: p.artikel, menge: Number(bestellmengeVon(p)) || 0,
    }));
    await api("/api/bestellung", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        liefertag: bestellDaten.liefertag, filiale: zustand.filiale,
        positionen: alle,
      }),
    });
    el("bestellung-hinweis").innerHTML =
      `<span class="gruen">Übernommen ✓</span> — für diese Filiale ist die
      Bestellung festgehalten. Es wird nie automatisch bestellt.`;
  };
}

/* ---------- Servicegrade -------------------------------------------- */

const SG_ERKLAERUNG = {
  A: "Darf auf keinen Fall ausgehen — 95 % Sicherheit, mehr Retoure",
  B: "Darf am späten Nachmittag ausgehen — 80 %",
  C: "Darf mittags weg sein — 60 %, wenig Retoure",
};

async function ladeServicegrade() {
  await filialchips("servicegrade-filialwahl", ladeServicegrade);
  const q = zustand.liefertag ? `&liefertag=${zustand.liefertag}` : "";
  const daten = await api(`/api/einstellungen?filiale=${zustand.filiale}${q}`);

  const rumpf = el("servicegrade-tabelle").querySelector("tbody");
  rumpf.innerHTML = "";
  for (const a of daten.artikel) {
    const menge = a.menge_je_klasse[a.servicegrad];
    const zeile = document.createElement("tr");
    zeile.innerHTML = `
      <td><span class="artikelname">${a.bezeichnung}</span>
        <span class="artikelnummer">${a.artikel}</span>
        <span class="unterzeile">${a.warengruppe}</span></td>
      <td><span class="sg-wahl">
        ${["A", "B", "C"].map((k) => `<button data-klasse="${k}"
          title="${SG_ERKLAERUNG[k]}"
          class="${k === a.servicegrad ? "aktiv" : ""}">${k}</button>`).join("")}
      </span></td>
      <td class="zahl"><span class="vorschlagszahl" data-menge>${menge == null
        ? "–" : zahl(menge)}</span></td>`;
    zeile.querySelectorAll("button[data-klasse]").forEach((k) =>
      k.addEventListener("click", async () => {
        await api("/api/einstellungen", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filiale: zustand.filiale, artikel: a.artikel,
            servicegrad: k.dataset.klasse,
          }),
        });
        zeile.querySelectorAll("button[data-klasse]").forEach((b) =>
          b.classList.toggle("aktiv", b === k));
        const neu = a.menge_je_klasse[k.dataset.klasse];
        zeile.querySelector("[data-menge]").textContent = neu == null ? "–" : zahl(neu);
      }));
    rumpf.appendChild(zeile);
  }
}

/* ---------- Ereignisse ---------------------------------------------- */

function ereigniszeile(e) {
  const prozent = Math.round((e.wirkung - 1) * 100);
  const zeile = document.createElement("tr");
  zeile.innerHTML = `
    <td><span class="leise">${datumDe(e.datum_von)}</span></td>
    <td><span class="leise">${datumDe(e.datum_bis)}</span></td>
    <td>${e.filialen}</td>
    <td><span class="artikelname">${e.bezeichnung}</span></td>
    <td><span class="leise">${e.art || "sonstiges"}</span></td>
    <td class="zahl"><span class="${prozent >= 0 ? "gruen" : "rot"}">${prozent >= 0
      ? "+" : ""}${prozent} %</span></td>`;
  return zeile;
}

async function ladeEreignisse() {
  const daten = await api("/api/ereignisse");
  const rumpf = el("ereignis-tabelle").querySelector("tbody");
  rumpf.innerHTML = "";
  if (!daten.length) {
    rumpf.innerHTML = `<tr><td colspan="6" class="leer">Noch keine Einträge.</td></tr>`;
  }
  for (const e of daten) rumpf.appendChild(ereigniszeile(e));
}

el("ereignis-formular").addEventListener("submit", async (ereignis) => {
  ereignis.preventDefault();
  const formular = new FormData(ereignis.target);
  const neu = {
    datum_von: formular.get("datum_von"),
    datum_bis: formular.get("datum_bis"),
    filialen: formular.get("filialen") || "alle",
    bezeichnung: formular.get("bezeichnung"),
    art: "sonstiges",
    wirkung: Number(formular.get("wirkung")),
  };
  await api("/api/ereignisse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(neu),
  });
  ereignis.target.reset();
  const rumpf = el("ereignis-tabelle").querySelector("tbody");
  rumpf.querySelector(".leer")?.closest("tr")?.remove();
  rumpf.prepend(ereigniszeile(neu));
});

/* ---------- Start ---------------------------------------------------- */

ladeUebersicht();
