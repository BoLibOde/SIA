// common/js/lautstaerke.js
console.log("lautstaerke.js wurde geladen ✅");

// -----------------------------
// Lautstärkeanzeige
// -----------------------------
const lautstaerkeLevels = [
  { icon: "icon-maus", name: "Maus", min: 0, max: 30 },
  { icon: "icon-sprechen", name: "Sprechen", min: 31, max: 50 },
  { icon: "icon-musik", name: "Musik", min: 51, max: 70 },
  { icon: "icon-auto", name: "Auto", min: 71, max: 90 },
  { icon: "icon-flugzeug", name: "Flugzeug", min: 91, max: 200 }
];

function resetIcons() {
  document.querySelectorAll(".laut-icon").forEach(i => i.classList.remove("active"));
}

function updateLautstaerkeAnzeige(dbValue) {
  resetIcons();

  const text = document.getElementById("lautstaerke-text");
  const level = lautstaerkeLevels.find(l => dbValue >= l.min && dbValue <= l.max);

  if (level) {
    const el = document.getElementById(level.icon);
    if (el) el.classList.add("active");
    if (text) text.textContent = `${dbValue} dB – ${level.name}`;
  } else {
    if (text) text.textContent = `${dbValue} dB`;
  }
}

// lokale Helfer (vermeiden globale Namenskonflikte)
const _padZero = (n) => {
  if (window.appDataPaths && typeof window.appDataPaths.padZero === "function") return window.appDataPaths.padZero(n);
  return n < 10 ? "0" + n : String(n);
};

const _getBasePathForDepartment = (dep) => {
  if (window.appDataPaths) {
    const base = window.appDataPaths.baseDataDir || 'common/data';
    const map = window.appDataPaths.departmentMap || {};

    // Wenn dep ist ein Ordnername (z. B. '01_Torben'), verwende ihn direkt
    if (Object.values(map).includes(dep)) {
      return `${base}/${dep}`;
    }

    // Falls dep ein logischer key ist (z. B. 'allgemein'), nutze getBasePathForDepartment wenn vorhanden
    if (typeof window.appDataPaths.getBasePathForDepartment === "function") {
      return window.appDataPaths.getBasePathForDepartment(dep);
    }

    // fallback: treat dep as foldername
    return `${base}/${dep}`;
  }

  // fallback default
  switch (dep) {
    case "werk": return "common/data";
    case "buero": return "common/data_buero";
    default: return "common/data/01_Torben";
  }
};

const _getFilePathForDate = (dep, y, m, d) => `${_getBasePathForDepartment(dep)}/${y}/${m}/${d}/totals.json`;

// -----------------------------
// Datenlader für Lautstärke
async function loadLautstaerke(retry = true) {
  // Prüfen, ob dataLoader.js Variablen schon da sind
  if (typeof currentTimeRange === "undefined" || typeof currentDepartment === "undefined" || !currentDepartment) {
    if (retry) {
      console.warn("⏳ Daten noch nicht bereit, versuche erneut...");
      setTimeout(() => loadLautstaerke(false), 500);
    } else {
      console.warn("⏳ Daten immer noch nicht bereit, Abbruch.");
    }
    return;
  }

  console.log(`🔊 Lade Lautstärke für ${currentTimeRange} / ${currentDepartment}`);

  const today = new Date();
  let totalDb = 0, count = 0;

  async function loadDbForDate(y, m, d) {
    const path = _getFilePathForDate(currentDepartment, y, m, d);
    try {
      const resp = await fetch(path);
      if (!resp.ok) {
        // versuche keinen console spam, nur warnen
        return;
      }
      const data = await resp.json();
      let val = NaN;
      if (data && typeof data.db === "number") val = data.db;
      else if (data && data.avg_sensor_day && typeof data.avg_sensor_day.db === "number")
        val = data.avg_sensor_day.db;

      if (!isNaN(val)) {
        totalDb += val;
        count++;
      }
    } catch (e) {
      // ignore
    }
  }

  // Zeitraumbezogenes Laden
  if (currentTimeRange === "now" || currentTimeRange === "day") {
    await loadDbForDate(today.getFullYear(), _padZero(today.getMonth() + 1), _padZero(today.getDate()));
  } else if (currentTimeRange === "week") {
    const dayOfWeek = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7));
    for (let d = new Date(monday); d <= today; d.setDate(d.getDate() + 1)) {
      await loadDbForDate(d.getFullYear(), _padZero(d.getMonth() + 1), _padZero(d.getDate()));
    }
  } else if (currentTimeRange === "month") {
    const y = today.getFullYear();
    const m = today.getMonth() + 1;
    const days = new Date(y, m, 0).getDate();
    for (let d = 1; d <= days; d++) {
      await loadDbForDate(y, _padZero(m), _padZero(d));
    }
  } else if (currentTimeRange === "year") {
    const y = today.getFullYear();
    for (let m = 1; m <= 12; m++) {
      const days = new Date(y, m, 0).getDate();
      for (let d = 1; d <= days; d++) {
        await loadDbForDate(y, _padZero(m), _padZero(d));
      }
    }
  }

  // fallback: falls count === 0 versuche base totals.json
  if (count === 0) {
    try {
      const basePath = _getBasePathForDepartment(currentDepartment);
      const fallbackResp = await fetch(`${basePath}/totals.json`);
      if (fallbackResp.ok) {
        const fallbackData = await fallbackResp.json();
        if (fallbackData) {
          const val = (fallbackData.avg_sensor_day && typeof fallbackData.avg_sensor_day.db === "number") ? fallbackData.avg_sensor_day.db : (typeof fallbackData.db === 'number' ? fallbackData.db : NaN);
          if (!isNaN(val)) {
            totalDb = val;
            count = 1;
          }
        }
      }
    } catch (e) {
      // ignore
    }
  }

  const avgDb = count > 0 ? Math.round(totalDb / count) : 0;
  console.log(`📈 Durchschnittliche Lautstärke: ${avgDb} dB (${count} Werte)`);
  updateLautstaerkeAnzeige(avgDb);
}

// -----------------------------
// Automatisch reagieren auf UI
document.addEventListener("DOMContentLoaded", () => {
  loadLautstaerke();
  // Reaktion auf Wechsel von Zeit oder Gerät in der Sidebar
  document.querySelectorAll(".zeitraum td").forEach(el => {
    el.addEventListener("click", () => setTimeout(loadLautstaerke, 600));
  });

  // Sidebar-Events für Geräte: die Sidebar-Zeilen werden dynamisch erzeugt in dataLoader.js,
  // daher hier eine Delegation: (falls Rows später existieren)
  document.addEventListener("click", (e) => {
    const tr = e.target.closest && e.target.closest(".links tr");
    if (tr && tr.dataset && tr.dataset.folder) {
      // war ein Geräte-Click -> lade Lautstärke mit leichtem Delay (UI hat evtl. animate)
      setTimeout(loadLautstaerke, 600);
    }
  });
});