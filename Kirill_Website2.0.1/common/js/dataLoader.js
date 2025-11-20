console.log("dataLoader.js geladen ✅");

// ----------------------------
// Geräte definieren (anstatt Abteilungen)
const devices = [
  { name: "01_Torben" },
  { name: "02_Michael" },
  { name: "03_Sarah" }
];

// Aktueller Zeitraum & Gerät
let currentTimeRange = "now"; // Standard: "Jetzt"
let currentDeviceIndex = 0;   // Standard: erstes Gerät

// Hilfsfunktionen
function padZero(n) { return n < 10 ? "0" + n : n; }
function getFilePathForDate(deviceName, year, month, day) {
  return `common/data/${deviceName}/${year}/${month}/${day}/totals.json`;
}

// Update Charts und HTML
function updateChartAndHTML(good, meh, bad, lineLabels = null, lineDataArray = null) {
  if (typeof barChart === "undefined" || typeof lineChart === "undefined") {
    console.warn("⏳ Charts noch nicht initialisiert.");
    return;
  }

  // Säulendiagramm
  barChart.data.datasets[0].data = [good, meh, bad];
  barChart.update();

  // Liniendiagramm
  if (lineLabels && lineDataArray) {
    lineChart.data.labels = lineLabels;
    lineChart.data.datasets[0].data = lineDataArray;
    lineChart.update();
  }

  // HTML-Werte
  document.getElementById("total-good").textContent = good;
  document.getElementById("total-moderate").textContent = meh;
  document.getElementById("total-bad").textContent = bad;
  document.getElementById("total-votes").textContent = good + meh + bad;
}

// Labels für Liniendiagramm
function getLineLabelsForRange(range) {
  const today = new Date();
  let labels = [];

  switch (range) {
    case "day":
    case "now":
      for (let h = 0; h < 24; h++) labels.push(h + ":00");
      break;
    case "week":
      labels = ["Mo","Di","Mi","Do","Fr","Sa","So"];
      break;
    case "month":
      const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
      for (let d = 1; d <= daysInMonth; d++) labels.push(d.toString());
      break;
    case "year":
      labels = ["Jan","Feb","Mär","Apr","Mai","Jun","Jul","Aug","Sep","Okt","Nov","Dez"];
      break;
  }
  return labels;
}

// Ladefunktionen nach Zeitraum
async function loadDayData() {
  showLoader();
  const today = new Date();
  const year = today.getFullYear();
  const month = padZero(today.getMonth() + 1);
  const day = padZero(today.getDate());

  const path = getFilePathForDate(devices[currentDeviceIndex].name, year, month, day);

  try {
    const resp = await fetch(path);
    const data = await resp.json();
    const lineLabels = getLineLabelsForRange("day");
    const lineDataArray = Array(24).fill(data.avg_sensor_day ? data.avg_sensor_day.temp : 0);
    updateChartAndHTML(data.good, data.meh, data.bad, lineLabels, lineDataArray);
  } catch {
    console.warn("❌ Datei nicht gefunden:", path);
    updateChartAndHTML(0, 0, 0); // falls keine Datei existiert
  } finally {
    hideLoader();
  }
}

async function loadWeekData() {
  showLoader();
  const today = new Date();
  const dayOfWeek = today.getDay();
  const monday = new Date(today);
  monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7));

  let totalGood = 0, totalMeh = 0, totalBad = 0;
  const lineLabels = getLineLabelsForRange("week");
  const lineDataArray = [];

  for (let d = new Date(monday); d <= today; d.setDate(d.getDate() + 1)) {
    const y = d.getFullYear(), m = padZero(d.getMonth() + 1), day = padZero(d.getDate());
    const path = getFilePathForDate(devices[currentDeviceIndex].name, y, m, day);

    try {
      const resp = await fetch(path);
      const json = await resp.json();
      totalGood += json.good;
      totalMeh += json.meh;
      totalBad += json.bad;
      lineDataArray.push(json.avg_sensor_day ? json.avg_sensor_day.temp : 0);
    } catch {
      lineDataArray.push(0);
    }
  }

  updateChartAndHTML(totalGood, totalMeh, totalBad, lineLabels, lineDataArray);
  hideLoader();
}

async function loadMonthData() {
  showLoader();
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth() + 1;
  const daysInMonth = new Date(year, month, 0).getDate();

  let totalGood = 0, totalMeh = 0, totalBad = 0;
  const lineLabels = getLineLabelsForRange("month");
  const lineDataArray = [];

  for (let d = 1; d <= daysInMonth; d++) {
    const path = getFilePathForDate(devices[currentDeviceIndex].name, year, padZero(month), padZero(d));
    try {
      const resp = await fetch(path);
      const data = await resp.json();
      totalGood += data.good;
      totalMeh += data.meh;
      totalBad += data.bad;
      lineDataArray.push(data.avg_sensor_day ? data.avg_sensor_day.temp : 0);
    } catch {
      lineDataArray.push(0);
    }
  }

  updateChartAndHTML(totalGood, totalMeh, totalBad, lineLabels, lineDataArray);
  hideLoader();
}

async function loadYearData() {
  showLoader();
  const today = new Date();
  const year = today.getFullYear();

  let totalGood = 0, totalMeh = 0, totalBad = 0;
  const lineLabels = getLineLabelsForRange("year");
  const lineDataArray = [];

  for (let m = 1; m <= 12; m++) {
    const daysInMonth = new Date(year, m, 0).getDate();
    let monthTemp = 0;

    for (let d = 1; d <= daysInMonth; d++) {
      const path = getFilePathForDate(devices[currentDeviceIndex].name, year, padZero(m), padZero(d));
      try {
        const resp = await fetch(path);
        const data = await resp.json();
        totalGood += data.good;
        totalMeh += data.meh;
        totalBad += data.bad;
        monthTemp += data.avg_sensor_day ? data.avg_sensor_day.temp : 0;
      } catch {}
    }

    lineDataArray.push(Math.round(monthTemp / daysInMonth));
  }

  updateChartAndHTML(totalGood, totalMeh, totalBad, lineLabels, lineDataArray);
  hideLoader();
}

// Zeitraum laden
function loadDataForCurrentRange() {
  if (currentTimeRange === "now" || currentTimeRange === "day") loadDayData();
  else if (currentTimeRange === "week") loadWeekData();
  else if (currentTimeRange === "month") loadMonthData();
  else if (currentTimeRange === "year") loadYearData();
}

// ----------------------------
// Event-Listener für Zeitbereich
document.querySelectorAll(".zeitraum td").forEach((td, index) => {
  td.addEventListener("click", () => {
    document.querySelectorAll(".zeitraum td").forEach(t => t.classList.remove("active"));
    td.classList.add("active");

    const ranges = ["now", "day", "week", "month", "year"];
    currentTimeRange = ranges[index];
    loadDataForCurrentRange();
  });
});

// Event-Listener für Geräte
document.querySelectorAll(".links tr").forEach((row, index) => {
  if (index === 0) return; // Überschrift überspringen
  row.addEventListener("click", () => {
    document.querySelectorAll(".links tr").forEach(r => r.classList.remove("active"));
    row.classList.add("active");

    currentDeviceIndex = index - 1;
    loadDataForCurrentRange();
  });
});

// Initialisierung
document.addEventListener("DOMContentLoaded", () => {
  document.querySelector(".zeitraum td").classList.add("active");
  document.querySelector(".links tr:nth-child(2)").classList.add("active");
  loadDataForCurrentRange();
});
