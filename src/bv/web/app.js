/* Tablet-Oberflaeche: vier Ansichten, reines JavaScript, kein Bauschritt. */

"use strict";

const zustand = {
  ansicht: "uebersicht",
  liefertag: null,
  filiale: null,
  filialen: [],
};

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

/* ---------- Tagesuebersicht ----------------------------------------- */

const ZUSTAND_ERKLAERUNG = {
  "fertig": "Vorschläge liegen vor und warten auf Übernahme",
  "bestellt": "Bestellung wurde für diesen Liefertag bestätigt",
  "kein Vorschlag": "Für diesen Tag liegen keine Vorschläge vor — Nachtlauf prüfen",
  "geschlossen": "Die Filiale hat an diesem Tag geschlossen",
};

async function ladeUebersicht() {
  const q = zustand.liefertag ? `?liefertag=${zustand.liefertag}` : "";
  const daten = await api(`/api/tagesuebersicht${q}`);
  zustand.liefertag = daten.liefertag;
  el("liefertag").value = daten.liefertag;

  const info = await api("/api/zustand");
  const kasten = el("warnung-kasten");
  if (info.warnung) {
    kasten.hidden = false;
    kasten.textContent = info.warnung.replace(/^#.*$/m, "").trim();
  } else {
    kasten.hidden = true;
  }

  const rumpf = el("uebersicht-tabelle").querySelector("tbody");
  rumpf.innerHTML = "";
  for (const f of daten.filialen) {
    const zeile = document.createElement("tr");
    const marke = f.zustand === "geschlossen" ? "leise"
      : f.zustand === "kein Vorschlag" ? "warn" : "ok";
    zeile.innerHTML = `
      <td><strong>${f.name}</strong><span class="begruendung">${f.anschrift}</span></td>
      <td>${f.oeffnung}</td>
      <td><span class="marke ${marke}"
        title="${ZUSTAND_ERKLAERUNG[f.zustand] || ""}">${f.zustand}</span></td>
      <td class="zahl" title="Artikel mit starker Abweichung zur Vorwoche, erkanntem Ausverkauf oder hoher Retoure">${f.auffaellig > 0
        ? `<span class="marke warn">${f.auffaellig}</span>` : "0"}</td>
      <td class="zahl">${f.retourenquote_vorwoche === null
        ? "–" : zahl(f.retourenquote_vorwoche, 1) + " %"}</td>
      <td>${f.zustand === "geschlossen" ? "" :
        `<button class="zeile" data-filiale="${f.filiale}">Zur Bestellung</button>`}</td>`;
    rumpf.appendChild(zeile);
  }
  rumpf.querySelectorAll("button[data-filiale]").forEach((k) =>
    k.addEventListener("click", () => {
      zustand.filiale = Number(k.dataset.filiale);
      zeigeAnsicht("bestellung");
    }));
}

/* ---------- Bestellvorschlag ---------------------------------------- */

async function filialknoepfe(zielId, beimWechsel) {
  if (!zustand.filialen.length) zustand.filialen = await api("/api/filialen");
  if (!zustand.filiale) zustand.filiale = zustand.filialen[0].nummer;
  const ziel = el(zielId);
  ziel.innerHTML = "";
  for (const f of zustand.filialen) {
    const k = document.createElement("button");
    k.textContent = `${f.nummer} · ${f.name}`;
    k.classList.toggle("aktiv", f.nummer === zustand.filiale);
    k.addEventListener("click", () => { zustand.filiale = f.nummer; beimWechsel(); });
    ziel.appendChild(k);
  }
}

async function ladeBestellung() {
  await filialknoepfe("bestellung-filialwahl", ladeBestellung);
  const q = zustand.liefertag ? `&liefertag=${zustand.liefertag}` : "";
  const daten = await api(`/api/vorschlag?filiale=${zustand.filiale}${q}`);
  zustand.liefertag = daten.liefertag;
  el("liefertag").value = daten.liefertag;

  el("bestellung-kopf").innerHTML = `
    <span class="gross">${daten.filiale.name}</span>
    <span class="leise">${daten.filiale.anschrift}</span>
    <span>Liefertag ${datumDe(daten.liefertag)}</span>
    <span class="leise">geöffnet ${daten.oeffnung}</span>`;

  const rumpf = el("bestellung-tabelle").querySelector("tbody");
  rumpf.innerHTML = "";
  if (!daten.positionen.length) {
    rumpf.innerHTML = `<tr><td colspan="7" class="leer">
      Für diesen Tag liegen keine Vorschläge vor — Nachtlauf prüfen.</td></tr>`;
  }
  for (const p of daten.positionen) {
    const zeile = document.createElement("tr");
    if (p.auffaellig) zeile.classList.add("auffaellig");
    const begruendung = (p.auffaellig || p.notbehelf)
      ? `<span class="begruendung">${p.begruendung}</span>` : "";
    zeile.innerHTML = `
      <td>${p.artikel}</td>
      <td><strong>${p.bezeichnung}</strong>${begruendung}</td>
      <td class="zahl vorschlagszahl" title="${(p.begruendung || "").replaceAll('"', "'")}">${zahl(p.vorschlag)}</td>
      <td class="zahl" title="Newsvendor-Vergleichswert — nur zur Orientierung">${zahl(p.menge_wirtschaftlich)}</td>
      <td class="zahl">${zahl(p.vorwoche_geliefert)}</td>
      <td class="zahl">${zahl(p.vorwoche_retoure)}</td>
      <td class="zahl"><input class="menge" type="number" min="0" step="1"
        title="Tatsächlich bestellte Menge — vorbelegt mit dem Vorschlag"
        data-artikel="${p.artikel}" data-vorschlag="${p.vorschlag}"
        value="${p.bestellt ?? p.vorschlag}"></td>`;
    rumpf.appendChild(zeile);
  }
  rumpf.querySelectorAll("input.menge").forEach((feld) =>
    feld.addEventListener("input", () => feld.classList.toggle(
      "geaendert", Number(feld.value) !== Number(feld.dataset.vorschlag))));

  const knopf = el("bestellung-uebernehmen");
  knopf.disabled = !daten.positionen.length;
  knopf.onclick = async () => {
    const positionen = [...rumpf.querySelectorAll("input.menge")].map((f) => ({
      artikel: f.dataset.artikel, menge: Number(f.value) || 0,
    }));
    await api("/api/bestellung", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        liefertag: daten.liefertag, filiale: zustand.filiale, positionen,
      }),
    });
    knopf.textContent = "Übernommen ✓";
    setTimeout(() => { knopf.textContent = "Bestellung übernommen"; }, 2500);
  };
}

/* ---------- Servicegrade -------------------------------------------- */

async function ladeServicegrade() {
  await filialknoepfe("servicegrade-filialwahl", ladeServicegrade);
  const q = zustand.liefertag ? `&liefertag=${zustand.liefertag}` : "";
  const daten = await api(`/api/einstellungen?filiale=${zustand.filiale}${q}`);

  const rumpf = el("servicegrade-tabelle").querySelector("tbody");
  rumpf.innerHTML = "";
  for (const a of daten.artikel) {
    const zeile = document.createElement("tr");
    const menge = a.menge_je_klasse[a.servicegrad];
    zeile.innerHTML = `
      <td>${a.artikel}</td>
      <td><strong>${a.bezeichnung}</strong>
        <span class="begruendung">${a.warengruppe}</span></td>
      <td><span class="sg-wahl">
        ${["A", "B", "C"].map((k) => `<button data-klasse="${k}"
          title="${{A: "Darf auf keinen Fall ausgehen — 95 % Sicherheit, mehr Retoure",
                    B: "Darf am späten Nachmittag ausgehen — 80 %",
                    C: "Darf mittags weg sein — 60 %, wenig Retoure"}[k]}"
          class="${k === a.servicegrad ? "aktiv" : ""}">${k}</button>`).join("")}
      </span></td>
      <td class="zahl vorschlagszahl" data-menge>${menge == null ? "–" : zahl(menge)}</td>`;
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
        // Wirkung sofort sichtbar: Menge der gewaehlten Klasse anzeigen
        const neu = a.menge_je_klasse[k.dataset.klasse];
        zeile.querySelector("[data-menge]").textContent =
          neu == null ? "–" : zahl(neu);
      }));
    rumpf.appendChild(zeile);
  }
}

/* ---------- Ereignisse ---------------------------------------------- */

async function ladeEreignisse() {
  const daten = await api("/api/ereignisse");
  const rumpf = el("ereignis-tabelle").querySelector("tbody");
  rumpf.innerHTML = "";
  if (!daten.length) {
    rumpf.innerHTML = `<tr><td colspan="5" class="leer">Noch keine Einträge.</td></tr>`;
  }
  for (const e of daten) {
    const zeile = document.createElement("tr");
    const prozent = Math.round((e.wirkung - 1) * 100);
    zeile.innerHTML = `
      <td>${datumDe(e.datum_von)}</td><td>${datumDe(e.datum_bis)}</td>
      <td>${e.filialen}</td><td><strong>${e.bezeichnung}</strong></td>
      <td class="zahl">${prozent >= 0 ? "+" : ""}${prozent} %</td>`;
    rumpf.appendChild(zeile);
  }
}

el("ereignis-formular").addEventListener("submit", async (ereignis) => {
  ereignis.preventDefault();
  const formular = new FormData(ereignis.target);
  await api("/api/ereignisse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      datum_von: formular.get("datum_von"),
      datum_bis: formular.get("datum_bis"),
      filialen: formular.get("filialen") || "alle",
      bezeichnung: formular.get("bezeichnung"),
      art: "sonstiges",
      wirkung: Number(formular.get("wirkung")),
    }),
  });
  ereignis.target.reset();
  ladeEreignisse();
});

/* ---------- Start ---------------------------------------------------- */

ladeUebersicht();
