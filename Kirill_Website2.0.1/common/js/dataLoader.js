// common/js/dataLoader.js
// Lädt totals.json aus den Geräte-Ordnern und aktualisiert Charts/HTML.

// -------------------- Lade-Overlay Steuerung --------------------
function showLoader() {
  const loader = document.getElementById("loader-overlay");
  if (loader) loader.style.display = "flex";
}

function hideLoader() {
  const loader = document.getElementById("loader-overlay");
  if (loader) loader.style.display = "none";
}

// ----------------------------
// Aktueller Zeitraum & Gerät (Ordnername)
let currentTimeRange = "now";        // Standard: "Jetzt"
let currentDepartment = "";          // wird beim Sidebar-Build gesetzt

// ----------------------------
// Hilfs: padZero/getBasePath (nutze appDataPaths wenn vorhanden)
function padZero(number) {
  if (window.appDataPaths && typeof window.appDataPaths.padZero === "function") {
    return window.appDataPaths.padZero(number);
  }
  return number < 10 ? "0" + number : String(number);
}

function getBasePathForDepartment(department) {
  // department kann entweder ein logischer key (z. B. 'allgemein') oder ein Ordnername ('01_Torben') sein.
  if (window.appDataPaths) {
    const base = window.appDataPaths.baseDataDir || 'common/data';
    const map = window.appDataPaths.departmentMap || {};

    // Wenn department exakt einem Map-Wert entspricht (Ordnername), dann verwenden:
    if (Object.values(map).includes(department)) {
      return `${base}/${department}`;
    }

    // Wenn department ein logischer Key ist (z. B. 'allgemein'), nutze die vorhandene Funktion:
    if (typeof window.appDataPaths.getBasePathForDepartment === "function") {
      return window.appDataPaths.getBasePathForDepartment(department);
    }

    // Fallback: treat department as foldername
    return `${base}/${department}`;
  }

  // Alte Fallbacks (falls appDataPaths fehlt)
  switch (department) {
    case "werk": return "common/data";
    case "buero": return "common/data_buero";
    default: return "common/data/01_Torben";
  }
}

function getFilePathForDate(department, year, month, day) {
  const basePath = getBasePathForDepartment(department);
  return `${basePath}/${year}/${month}/${day}/totals.json`;
}

// ----------------------------
// Helper: sicher fetch + json
async function safeFetchJson(path) {
  try {
    const resp = await fetch(path);
    if (!resp.ok) {
      // z.B. 404/500
      // console.warn(`❌ HTTP ${resp.status} beim Laden: ${path}`);
      return null;
    }
    return await resp.json();
  } catch (err) {
    // console.warn("❌ Fehler beim Fetch:", path, err);
    return null;
  }
}

// ----------------------------
// Chart-Update Funktion (defensiv)
function updateChartAndHTML(good, meh, bad, lineLabels = null, lineDataArray = null) {
  if (typeof window.barChart === "undefined" || typeof window.lineChart === "undefined") {
    console.warn("⏳ Charts noch nicht initialisiert.");
  } else {
    if (Array.isArray(window.barDatasets) && window.barDatasets[0]) {
      window.barDatasets[0].data = [good, meh, bad];
      if (window.barChart) {
        window.barChart.data.datasets[0].data = window.barDatasets[0].data;
        window.barChart.update();
      }
    }
    if (lineLabels && lineDataArray && window.lineChart) {
      window.lineChart.data.labels = lineLabels;
      window.lineChart.data.datasets[0].data = lineDataArray;
      window.lineChart.update();
    }
  }

  const elGood = document.getElementById("total-good");
  const elMeh = document.getElementById("total-moderate");
  const elBad = document.getElementById("total-bad");
  const elVotes = document.getElementById("total-votes");

  if (elGood) elGood.textContent = good || 0;
  if (elMeh) elMeh.textContent = meh || 0;
  if (elBad) elBad.textContent = bad || 0;
  if (elVotes) elVotes.textContent = (Number(good) || 0) + (Number(meh) || 0) + (Number(bad) || 0);
}

// ----------------------------
// Labels für Liniendiagramm
function getLineLabelsForRange(range) {
  const today = new Date();
  let labels = [];

  switch (range) {
    case "day":
      for (let h = 0; h < 24; h++) labels.push(h + ":00");
      break;
    case "week":
      labels = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
      break;
    case "month":
      const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
      for (let d = 1; d <= daysInMonth; d++) labels.push(d.toString());
      break;
    case "year":
      labels = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
      break;
  }
  return labels;
}

// ----------------------------
// Fallback helper: versuche basePath/totals.json wenn datierter Pfad fehlt
async function tryFallbackTotals(basePath) {
  const fallbackPath = `${basePath}/totals.json`;
  const data = await safeFetchJson(fallbackPath);
  return data; // null wenn nicht vorhanden
}

// ----------------------------
// Hauptladefunktionen (mit Fallbacks)
async function loadDayData() {
  showLoader();
  try {
    const today = new Date();
    const year = today.getFullYear();
    const month = padZero(today.getMonth() + 1);
    const day = padZero(today.getDate());
    const filePath = getFilePathForDate(currentDepartment, year, month, day);

    let data = await safeFetchJson(filePath);
    if (!data) {
      // fallback: base totals.json im Geräte-Ordner
      const basePath = getBasePathForDepartment(currentDepartment);
      data = await tryFallbackTotals(basePath);
      if (!data) {
        updateChartAndHTML(0, 0, 0, getLineLabelsForRange("day"), Array(24).fill(0));
        return;
      }
    }

    const lineLabels = getLineLabelsForRange("day");
    const lineDataArray = Array(24).fill(data.avg_sensor_day ? data.avg_sensor_day.temp : 0);

    updateChartAndHTML(data.good || 0, data.meh || 0, data.bad || 0, lineLabels, lineDataArray);
  } finally {
    hideLoader();
  }
}

async function loadWeekData() {
  showLoader();
  try {
    const today = new Date();
    const dayOfWeek = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7));

    let totalGood = 0, totalMeh = 0, totalBad = 0;
    const lineLabels = getLineLabelsForRange("week");
    const lineDataArray = [];

    for (let d = new Date(monday); d <= today; d.setDate(d.getDate() + 1)) {
      const y = d.getFullYear(), m = padZero(d.getMonth() + 1), day = padZero(d.getDate());
      const filePath = getFilePathForDate(currentDepartment, y, m, day);

      const json = await safeFetchJson(filePath);
      if (json) {
        totalGood += json.good || 0;
        totalMeh += json.meh || 0;
        totalBad += json.bad || 0;
        lineDataArray.push(json.avg_sensor_day ? json.avg_sensor_day.temp : 0);
      } else {
        // optional: Fallback pro Tag nicht sinnvoll -> push 0
        lineDataArray.push(0);
      }
    }

    // Wenn alle Tage 0 und evtl. base totals.json vorhanden, nutze diese als Fallback (einfacher Ansatz)
    const allZeros = lineDataArray.every(v => v === 0);
    if (allZeros) {
      const base = await tryFallbackTotals(getBasePathForDepartment(currentDepartment));
      if (base) {
        updateChartAndHTML(base.good || 0, base.meh || 0, base.bad || 0, lineLabels, Array(lineLabels.length).fill(base.avg_sensor_day ? base.avg_sensor_day.temp : 0));
        return;
      }
    }

    updateChartAndHTML(totalGood, totalMeh, totalBad, lineLabels, lineDataArray);
  } finally {
    hideLoader();
  }
}

async function loadMonthData() {
  showLoader();
  try {
    const today = new Date();
    const year = today.getFullYear();
    const month = today.getMonth() + 1;
    const daysInMonth = new Date(year, month, 0).getDate();

    let totalGood = 0, totalMeh = 0, totalBad = 0;
    const lineLabels = getLineLabelsForRange("month");
    const lineDataArray = [];

    for (let d = 1; d <= daysInMonth; d++) {
      const filePath = getFilePathForDate(currentDepartment, year, padZero(month), padZero(d));
      const data = await safeFetchJson(filePath);
      if (data) {
        totalGood += data.good || 0;
        totalMeh += data.meh || 0;
        totalBad += data.bad || 0;
        lineDataArray.push(data.avg_sensor_day ? data.avg_sensor_day.temp : 0);
      } else {
        lineDataArray.push(0);
      }
    }

    const allZeros = lineDataArray.every(v => v === 0);
    if (allZeros) {
      const base = await tryFallbackTotals(getBasePathForDepartment(currentDepartment));
      if (base) {
        updateChartAndHTML(base.good || 0, base.meh || 0, base.bad || 0, lineLabels, Array(lineLabels.length).fill(base.avg_sensor_day ? base.avg_sensor_day.temp : 0));
        return;
      }
    }

    updateChartAndHTML(totalGood, totalMeh, totalBad, lineLabels, lineDataArray);
  } finally {
    hideLoader();
  }
}

async function loadYearData() {
  showLoader();
  try {
    const today = new Date();
    const year = today.getFullYear();

    let totalGood = 0, totalMeh = 0, totalBad = 0;
    const lineLabels = getLineLabelsForRange("year");
    const lineDataArray = [];

    for (let month = 1; month <= 12; month++) {
      const daysInMonth = new Date(year, month, 0).getDate();
      let monthGood = 0, monthMeh = 0, monthBad = 0;
      let monthTempSum = 0;
      let monthTempCount = 0;

      for (let d = 1; d <= daysInMonth; d++) {
        const filePath = getFilePathForDate(currentDepartment, year, padZero(month), padZero(d));
        const data = await safeFetchJson(filePath);
        if (data) {
          monthGood += data.good || 0;
          monthMeh += data.meh || 0;
          monthBad += data.bad || 0;
          if (data.avg_sensor_day && typeof data.avg_sensor_day.temp === "number") {
            monthTempSum += data.avg_sensor_day.temp;
            monthTempCount++;
          }
        }
      }

      totalGood += monthGood;
      totalMeh += monthMeh;
      totalBad += monthBad;
      lineDataArray.push(monthTempCount > 0 ? Math.round(monthTempSum / monthTempCount) : 0);
    }

    const allZeros = lineDataArray.every(v => v === 0);
    if (allZeros) {
      const base = await tryFallbackTotals(getBasePathForDepartment(currentDepartment));
      if (base) {
        updateChartAndHTML(base.good || 0, base.meh || 0, base.bad || 0, lineLabels, Array(lineLabels.length).fill(base.avg_sensor_day ? base.avg_sensor_day.temp : 0));
        return;
      }
    }

    updateChartAndHTML(totalGood, totalMeh, totalBad, lineLabels, lineDataArray);
  } finally {
    hideLoader();
  }
}

// ----------------------------
// Zeitraumwechsel
function loadDataForCurrentRange() {
  if (!currentDepartment) {
    console.warn("Kein Gerät ausgewählt.");
    return;
  }

  if (currentTimeRange === "now" || currentTimeRange === "day") loadDayData();
  else if (currentTimeRange === "week") loadWeekData();
  else if (currentTimeRange === "month") loadMonthData();
  else if (currentTimeRange === "year") loadYearData();
}

// ----------------------------
// Sidebar dynamisch aufbauen (Geräte aus appDataPaths.departmentMap)
function buildDeviceList() {
  const table = document.querySelector(".links table");
  if (!table) return;

  // Header bezeichnen als Geräte
  const th = table.querySelector("th");
  if (th) th.textContent = "Geräte";

  // Entferne alle bisherigen Zeilen außer Header
  const rows = Array.from(table.querySelectorAll("tr")).slice(1);
  rows.forEach(r => r.remove());

  // Bestimme Devices (verwende departmentMap values)
  const map = (window.appDataPaths && window.appDataPaths.departmentMap) ? window.appDataPaths.departmentMap : null;
  let devices = [];

  if (map) {
    // Zeige die Ordnernamen (values) als Liste
    devices = Object.values(map);
  } else {
    // Fallback: falls keine Map, zeige Default '01_Torben'
    devices = ["01_Torben"];
  }

  // Erstelle Zeilen
  const tbody = table;
  devices.forEach((folderName, idx) => {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.textContent = folderName;
    tr.appendChild(td);
    tr.dataset.folder = folderName;
    tbody.appendChild(tr);

    // Click handler: setze currentDepartment und lade Daten
    tr.addEventListener("click", () => {
      // active class toggle
      document.querySelectorAll(".links tr").forEach(r => r.classList.remove("active"));
      tr.classList.add("active");

      currentDepartment = folderName;
      // Lade die Daten für den aktuell gesetzten Zeitraum
      loadDataForCurrentRange();
    });

    // Wenn noch kein currentDepartment gesetzt, wähle die erste automatisch
    if (!currentDepartment && idx === 0) {
      currentDepartment = folderName;
      // Markiere als aktiv
      tr.classList.add("active");
    }
  });
}

// ----------------------------
// Event-Listener (UI Interaktion)
document.addEventListener("DOMContentLoaded", () => {
  // Zeitraum-Buttons
  document.querySelectorAll(".zeitraum td").forEach((td, index) => {
    td.addEventListener("click", () => {
      document.querySelectorAll(".zeitraum td").forEach(t => t.classList.remove("active"));
      td.classList.add("active");

      const ranges = ["now", "day", "week", "month", "year"];
      currentTimeRange = ranges[index];
      loadDataForCurrentRange();
    });
  });

  // Dynamischen Geräte-List aufbauen (setzt currentDepartment auf erstes Gerät)
  buildDeviceList();

  // Initiale Auswahl und Laden
  const firstZeit = document.querySelector(".zeitraum td");
  if (firstZeit) firstZeit.classList.add("active");

  // Lade direkt für das initial gesetzte Gerät
  loadDataForCurrentRange();
});