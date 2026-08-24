/* Demo-Umleiter fuer GitHub Pages: kein Server, keine Datenbank.
   GET /api/... -> eingefrorene JSON-Dateien; POST/PUT -> vorgetaeuscht. */
(() => {
  const echt = window.fetch.bind(window);
  window.fetch = (pfad, optionen) => {
    if (typeof pfad !== "string" || !pfad.startsWith("/api/")) {
      return echt(pfad, optionen);
    }
    const methode = (optionen && optionen.method) || "GET";
    if (methode !== "GET") {
      return Promise.resolve(new Response('{"demo": true}',
        { status: 200, headers: { "Content-Type": "application/json" } }));
    }
    const url = new URL(pfad, "http://demo");
    const name = url.pathname.replace("/api/", "");
    const filiale = url.searchParams.get("filiale");
    const datei = filiale ? `api/${name}_${filiale}.json` : `api/${name}.json`;
    return echt(datei);
  };
})();
