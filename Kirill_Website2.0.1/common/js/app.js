/* app.js — gesamte App in einer Datei
   Funktionalität:
   - Charts (Bar + Line)
   - Geräte-Auswahl (links)
   - Datenladen für day/week/month/year (aus common/data/<device>/<YYYY>/<MM>/<DD>/totals.json)
   - Lade-Overlay
   - Smiley (Luftqualität)
   - Lautstärkeanzeige (🐭 🗣️ 🎵 🚗 ✈️)
   - Scroll-Spinner
   - Einfacher in-memory Cache, um wiederholte fetches zu vermeiden
*/

// ----------------------------
// Konfiguration / Globals
// ----------------------------
console.log("app.js geladen ✅");

// Basis-Pfad zu den Daten (relativ zu public.html)
const BASE_DATA_PATH = "common/data"; // passt zu: Kirill_Website2.0.1/common/data/...

// Liste der Geräte (du kannst hier Geräte hinzufügen/ändern)
let devicesList = ["01_Torben"]; // später: ["01_Torben","02_Michael",...]

// Aktueller Zustand
let currentTimeRange = "now";      // now | day | week | month | year
let currentDevice = devicesList[0] || null;

// Einfacher in-memory cache: url -> parsed JSON
const fetchCache = {};

// ----------------------------
// Helper-Funktionen
// ----------------------------
function padZero(n) { return n < 10 ? "0" + n : String(n); }

function makeTotalsPath(deviceName, year, month, day) {
  return `${BASE_DATA_PATH}/${deviceName}/${year}/${month}/${day}/totals.json`;
}

function makeUploadXPath(deviceName, year, month, day) {
  return `${BASE_DATA_PATH}/${deviceName}/${year}/${month}/${day}/uplodeX.json`;
}

async function fetchJson(url) {
  // Cache prüfen
  if (fetchCache[url]) {
    // console.log("cache hit:", url);
    return fetchCache[url];
  }

  try {
    const resp = await fetch(url);
    if (!resp.ok) {
      console.warn(`fetch ${url} -> ${resp.status}`);
      return null;
    }
    const json = await resp.json();
    fetchCache[url] = json;
    return json;
  } catch (e) {
    console.warn("fetch error:", url, e);
    return null;
  }
}

// ----------------------------
// Loader Overlay
// ----------------------------
function showLoader() {
  const loader = document.getElementById("loader-overlay");
  if (loader) loader.style.display = "flex";
}
function hideLoader() {
  const loader = document.getElementById("loader-overlay");
  if (loader) loader.style.display = "none";
}

// ----------------------------
// Chart-Initialisierung (Chart.js)
// ----------------------------
const barDataObj = {
  labels: ['Gut', 'Meh', 'Schlecht'],
  datasets: [{
    label: 'Anzahl der Leute',
    data: [0,0,0],
    backgroundColor: [
      'rgba(34, 197, 94, 0.5)',
      'rgba(234, 179, 8, 0.5)',
      'rgba(239, 68, 68, 0.5)'
    ],
    borderColor: [
      'rgba(34, 197, 94, 1)',
      'rgba(234, 179, 8, 1)',
      'rgba(239, 68, 68, 1)'
    ],
    borderWidth: 1
  }]
};

const barChart = new Chart(document.getElementById('myChart'), {
  type: 'bar',
  data: barDataObj,
  options: {
    responsive: false,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: true },
      title: { display: true, text: 'Zufriedenheit' }
    },
    scales: { y: { beginAtZero: true } }
  }
});

const lineDataObj = {
  labels: [],
  datasets: [{
    label: '°C',
    data: [],
    borderColor: 'blue',
    backgroundColor: 'rgba(0,0,255,0.1)',
    fill: true,
    tension: 0.3
  }]
};

const lineChart = new Chart(document.getElementById('lineChart'), {
  type: 'line',
  data: lineDataObj,
  options: {
    responsive: false,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: true },
      title: { display: true, text: 'Temperatur' }
    },
    scales: { y: { beginAtZero: true } }
  }
});

// ----------------------------
// UI Update (Charts + Numbers)
// ----------------------------
function updateChartsAndUI(barArr, lineArr = null, lineLabels = null) {
  // Bar
  barChart.data.datasets[0].data = barArr;
  barChart.update();

  // Line optional
  if (lineArr && lineLabels) {
    lineChart.data.labels = lineLabels;
    lineChart.data.datasets[0].data = lineArr;
    lineChart.update();
  }

  // Zahlen
  document.getElementById('total-good').textContent = barArr[0] ?? 0;
  document.getElementById('total-moderate').textContent = barArr[1] ?? 0;
  document.getElementById('total-bad').textContent = barArr[2] ?? 0;
  document.getElementById('total-votes').textContent = (barArr[0] + barArr[1] + barArr[2]) || 0;
}

// ----------------------------
// Line-Labels Generator
// ----------------------------
function getLineLabelsForRange(range) {
  const today = new Date();
  if (range === "day" || range === "now") {
    return Array.from({length:24}, (_,i) => `${i}:00`);
  } else if (range === "week") {
    return ["Mo","Di","Mi","Do","Fr","Sa","So"];
  } else if (range === "month") {
    const daysInMonth = new Date(today.getFullYear(), today.getMonth()+1, 0).getDate();
    return Array.from({length: daysInMonth}, (_,i) => String(i+1));
  } else if (range === "year") {
    return ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"];
  }
  return [];
}

// ----------------------------
// Smiley (Luftqualität) Funktion
// ----------------------------
function updateLuftQualitaet(aqi) {
  const goodEl = document.getElementById("good");
  const moderateEl = document.getElementById("moderate");
  const badEl = document.getElementById("bad");
  const statusText = document.getElementById("status-text");
  [goodEl, moderateEl, badEl].forEach(e => e && e.classList.remove("active"));

  if (aqi <= 50) {
    goodEl && goodEl.classList.add("active");
    statusText && (statusText.textContent = "Gute Luftqualität 🌿");
  } else if (aqi <= 100) {
    moderateEl && moderateEl.classList.add("active");
    statusText && (statusText.textContent = "Mittlere Luftqualität 😐");
  } else {
    badEl && badEl.classList.add("active");
    statusText && (statusText.textContent = "Schlechte Luftqualität 😷");
  }
}

// ----------------------------
// Lautstärke-Icons (update)
// ----------------------------
const lautstaerkeLevels = [
  { iconId: "icon-maus", name: "Maus", min: 0, max: 30 },
  { iconId: "icon-sprechen", name: "Sprechen", min: 31, max: 50 },
  { iconId: "icon-musik", name: "Musik", min: 51, max: 70 },
  { iconId: "icon-auto", name: "Auto", min: 71, max: 90 },
  { iconId: "icon-flugzeug", name: "Flugzeug", min: 91, max: 200 }
];

function resetLautIcons() {
  document.querySelectorAll(".laut-icon").forEach(i => i.classList.remove("active"));
}

function updateLautstaerkeAnzeige(dbValue) {
  resetLautIcons();
  const text = document.getElementById("lautstaerke-text");
  const level = lautstaerkeLevels.find(l => dbValue >= l.min && dbValue <= l.max);
  if (level) {
    const el = document.getElementById(level.iconId);
    if (el) el.classList.add("active");
    if (text) text.textContent = `${dbValue} dB – ${level.name}`;
  } else {
    if (text) text.textContent = `${dbValue} dB`;
  }
}

// ----------------------------
// Daten-Ladefunktionen (Tag/Woche/Monat/Jahr)
// ----------------------------
async function loadDayRange(deviceName) {
  showLoader();
  try {
    const today = new Date();
    const y = today.getFullYear();
    const m = padZero(today.getMonth()+1);
    const d = padZero(today.getDate());
    const totals = await fetchJson(makeTotalsPath(deviceName, y, m, d));
    // Wenn totals fehlen: setze 0
    const good = totals?.good ?? 0;
    const meh  = totals?.meh  ?? 0;
    const bad  = totals?.bad  ?? 0;

    // line: 24 entries with avg temp (falls vorhanden)
    const avgTemp = totals?.avg_sensor_day?.temp ?? 0;
    const lineLabels = getLineLabelsForRange("day");
    const lineDataArr = Array(24).fill(avgTemp);

    // Luftqualität: wir benutzen avg_sensor_day.db falls vorhanden
    const avgDb = totals?.avg_sensor_day?.db ?? totals?.db ?? 0;
    updateLautstaerkeAnzeige(Math.round(avgDb));
    updateLuftQualitaet(totals?.avg_sensor_day?.voc ?? 0); // wenn voc als proxy, sonst ok

    updateChartsAndUI([good, meh, bad], lineDataArr, lineLabels);
  } finally {
    hideLoader();
  }
}

async function loadWeekRange(deviceName) {
  showLoader();
  try {
    const today = new Date();
    const dayOfWeek = today.getDay(); // 0=So
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7)); // Montag

    let totalGood=0, totalMeh=0, totalBad=0;
    const temps = [];
    let dbSum = 0, dbCount = 0;

    for (let d = new Date(monday); d <= today; d.setDate(d.getDate()+1)) {
      const y = d.getFullYear(), m = padZero(d.getMonth()+1), day = padZero(d.getDate());
      const totals = await fetchJson(makeTotalsPath(deviceName, y, m, day));
      if (totals) {
        totalGood += (totals.good ?? 0);
        totalMeh  += (totals.meh  ?? 0);
        totalBad  += (totals.bad  ?? 0);
        temps.push(totals.avg_sensor_day?.temp ?? 0);
        if (typeof totals.avg_sensor_day?.db === "number") {
          dbSum += totals.avg_sensor_day.db;
          dbCount++;
        } else if (typeof totals.db === "number") {
          dbSum += totals.db; dbCount++;
        }
      } else {
        temps.push(0);
      }
    }

    const avgDb = dbCount>0 ? Math.round(dbSum/dbCount) : 0;
    updateLautstaerkeAnzeige(avgDb);
    updateLuftQualitaet(0); // optional: compute voc average if wanted

    const labels = getLineLabelsForRange("week");
    // align temps length to labels length (week days)
    while (temps.length < labels.length) temps.push(0);

    updateChartsAndUI([totalGood, totalMeh, totalBad], temps, labels);
  } finally {
    hideLoader();
  }
}

async function loadMonthRange(deviceName) {
  showLoader();
  try {
    const today = new Date();
    const y = today.getFullYear();
    const m = today.getMonth() + 1;
    const daysInMonth = new Date(y, m, 0).getDate();

    let totalGood=0, totalMeh=0, totalBad=0;
    const temps = [];
    let dbSum=0, dbCount=0;

    for (let day=1; day<=daysInMonth; day++) {
      const totals = await fetchJson(makeTotalsPath(deviceName, y, padZero(m), padZero(day)));
      if (totals) {
        totalGood += totals.good ?? 0;
        totalMeh  += totals.meh  ?? 0;
        totalBad  += totals.bad  ?? 0;
        temps.push(totals.avg_sensor_day?.temp ?? 0);
        if (typeof totals.avg_sensor_day?.db === "number") { dbSum += totals.avg_sensor_day.db; dbCount++; }
        else if (typeof totals.db === "number") { dbSum += totals.db; dbCount++; }
      } else {
        temps.push(0);
      }
    }

    const avgDb = dbCount>0 ? Math.round(dbSum/dbCount) : 0;
    updateLautstaerkeAnzeige(avgDb);
    updateLuftQualitaet(0);

    const labels = getLineLabelsForRange("month");
    updateChartsAndUI([totalGood, totalMeh, totalBad], temps, labels);
  } finally {
    hideLoader();
  }
}

async function loadYearRange(deviceName) {
  showLoader();
  try {
    const today = new Date();
    const y = today.getFullYear();

    let totalGood=0, totalMeh=0, totalBad=0;
    const temps = [];
    let dbSum=0, dbCount=0;

    for (let month=1; month<=12; month++) {
      const daysInMonth = new Date(y, month, 0).getDate();
      let monthTempSum = 0, monthTempCount = 0;

      for (let day=1; day<=daysInMonth; day++) {
        const totals = await fetchJson(makeTotalsPath(deviceName, y, padZero(month), padZero(day)));
        if (totals) {
          totalGood += totals.good ?? 0;
          totalMeh  += totals.meh  ?? 0;
          totalBad  += totals.bad  ?? 0;
          if (typeof totals.avg_sensor_day?.temp === "number") { monthTempSum += totals.avg_sensor_day.temp; monthTempCount++; }
          if (typeof totals.avg_sensor_day?.db === "number") { dbSum += totals.avg_sensor_day.db; dbCount++; }
          else if (typeof totals.db === "number") { dbSum += totals.db; dbCount++; }
        }
      }

      const monthAvg = monthTempCount>0 ? Math.round(monthTempSum / monthTempCount) : 0;
      temps.push(monthAvg);
    }

    const avgDb = dbCount>0 ? Math.round(dbSum/dbCount) : 0;
    updateLautstaerkeAnzeige(avgDb);
    updateLuftQualitaet(0);

    const labels = getLineLabelsForRange("year");
    updateChartsAndUI([totalGood, totalMeh, totalBad], temps, labels);
  } finally {
    hideLoader();
  }
}

// ----------------------------
// Dispatcher: lade Daten je nach aktuellem Zeitraum
// ----------------------------
async function loadDataForCurrentRange() {
  if (!currentDevice) {
    console.warn("Kein Gerät ausgewählt.");
    return;
  }
  if (currentTimeRange === "now" || currentTimeRange === "day") {
    await loadDayRange(currentDevice);
  } else if (currentTimeRange === "week") {
    await loadWeekRange(currentDevice);
  } else if (currentTimeRange === "month") {
    await loadMonthRange(currentDevice);
  } else if (currentTimeRange === "year") {
    await loadYearRange(currentDevice);
  }
}

// ----------------------------
// UI: Geräte-Tabelle aufbauen
// ----------------------------
function buildDeviceTable() {
  const table = document.querySelector(".links table");
  if (!table) return;
  table.innerHTML = "<tr><th>Geräte</th></tr>";
  devicesList.forEach((dev, idx) => {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.textContent = dev;
    tr.appendChild(td);
    tr.addEventListener("click", () => {
      // mark active
      document.querySelectorAll(".links tr").forEach(r => r.classList.remove("active"));
      tr.classList.add("active");
      currentDevice = dev;
      // lade daten
      loadDataForCurrentRange();
    });
    table.appendChild(tr);
    // default aktiv beim ersten
    if (idx === 0) {
      tr.classList.add("active");
      currentDevice = dev;
    }
  });
}

// ----------------------------
// Event-Listener: Zeitleiste (Jetzt/Tag/Woche/Monat/Jahr)
// ----------------------------
function initTimeRangeButtons() {
  document.querySelectorAll(".zeitraum td").forEach((td, index) => {
    td.addEventListener("click", () => {
      document.querySelectorAll(".zeitraum td").forEach(t => t.classList.remove("active"));
      td.classList.add("active");
      const ranges = ["now","day","week","month","year"];
      currentTimeRange = ranges[index] || "now";
      loadDataForCurrentRange();
    });
  });
}

// ----------------------------
// Scroll-Spinner (drehend beim scrollen)
// ----------------------------
function initScrollSpinner() {
  const spinner = document.getElementById("scroll-spinner");
  if (!spinner) return;

  let lastScrollY = window.scrollY;
  let rotation = 0;
  function frame() {
    const currentY = window.scrollY;
    const delta = currentY - lastScrollY;
    rotation += delta * 0.5; // anpassen falls stärker/schwächer gewünscht
    spinner.style.transform = `rotate(${rotation}deg)`;
    lastScrollY = currentY;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

// ----------------------------
// Initialisierung beim Laden
// ----------------------------
document.addEventListener("DOMContentLoaded", () => {
  // Baue Geräteliste in der Sidebar
  buildDeviceTable();

  // init Zeit-Buttons
  initTimeRangeButtons();

  // init scroll spinner
  initScrollSpinner();

  // set default active zeit (erste td)
  const firstTd = document.querySelector(".zeitraum td");
  if (firstTd) firstTd.classList.add("active");

  // falls currentDevice gesetzt: load
  if (currentDevice) {
    loadDataForCurrentRange();
  }

  // Reagiere auf Klicks auch global (falls andere UI Elemente existieren)
  // (Optional) Falls du Lautstärke + andere Komponenten neu laden willst, kannst du hier Haken setzen.
});
