(function () {
  // Konfig: Passe die Werte hier an, damit alle Skripte die gleichen Pfade verwenden.
  // Aktuell existiert bei dir nur '01_Torben' — das ist als "allgemein" voreingestellt.
  window.appDataPaths = {
    // Basisverzeichnis, das die Abteilungsordner enthält
    baseDataDir: 'common/data',

    // Map: logischer Abteilungsname -> Ordnername in common/data
    departmentMap: {
      allgemein: '01_Torben',
      werk: '02_Werk',   // Platzhalter: später vorhandenen Ordnernamen eintragen
      buero: '03_Buero'  // Platzhalter
    },

    // Liefert den Basispfad für eine Abteilung, z. B. 'common/data/01_Torben'
    getBasePathForDepartment(dep) {
      const map = this.departmentMap || {};
      if (map[dep]) return `${this.baseDataDir}/${map[dep]}`;
      // Fallback: versuche direct unter baseDataDir den Dep‑Namen zu verwenden
      return `${this.baseDataDir}/${dep}`;
    },

    // Hilfsfunktion zum Zero-Padding
    padZero(n) {
      return n < 10 ? '0' + n : String(n);
    }
  };
})();