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
// Aktueller Zeitraum & Abteilung
// ----------------------------
let currentTimeRange = "now";        // Standard: "Jetzt"
let currentDepartment = "allgemein"; // Standard: Allgemein

// ----------------------------
// Hilfsfunktionen
// ----------------------------
function padZero(number) {
  return number < 10 ? "0" + number : number;
}

function getBasePathForDepartment(department) {
  switch (department) {
    case "werk": return "common/data";
    case "buero": return "common/data_buero";
    default: return "common/data_allgemein";
  }
}

function getFilePathForDate(department, year, month, day) {
  const basePath = getBasePathForDepartment(department);
  return `${basePath}/${year}/${month}/${day}/totals.json`;
}

// ----------------------------
// Chart-Update Funktion
// ----------------------------
function updateChartAndHTML(good, meh, bad, lineLabels = null, lineDataArray = null) {
  if (typeof barChart === "undefined" || typeof lineChart === "undefined") {
    console.warn("⏳ Charts noch nicht initialisiert.");
    return;
  }

  // Säulendiagramm
  barDatasets[0].data = [good, meh, bad];
  barChart.data.datasets[0].data = barDatasets[0].data;
  barChart.update();

  // Liniendiagramm (optional)
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

// ----------------------------
// Labels für Liniendiagramm
// ----------------------------
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
// Hauptladefunktionen
// ----------------------------
async function loadDayData() {
  showLoader();
  const today = new Date();
  const year = today.getFullYear();
  const month = padZero(today.getMonth() + 1);
  const day = padZero(today.getDate());
  const filePath = getFilePathForDate(currentDepartment, year, month, day);

  try {
    const resp = await fetch(filePath);
    const data = await resp.json();

    const lineLabels = getLineLabelsForRange("day");
    const lineDataArray = Array(24).fill(data.avg_sensor_day ? data.avg_sensor_day.temp : 0);

    updateChartAndHTML(data.good, data.meh, data.bad, lineLabels, lineDataArray);
  } catch {
    console.warn("❌ Datei nicht gefunden:", filePath);
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
    const filePath = getFilePathForDate(currentDepartment, y, m, day);

    try {
      const resp = await fetch(filePath);
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
    const filePath = getFilePathForDate(currentDepartment, year, padZero(month), padZero(d));
    try {
      const resp = await fetch(filePath);
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

  for (let month = 1; month <= 12; month++) {
    const daysInMonth = new Date(year, month, 0).getDate();
    let monthGood = 0, monthMeh = 0, monthBad = 0;
    let monthTemp = 0;

    for (let d = 1; d <= daysInMonth; d++) {
      const filePath = getFilePathForDate(currentDepartment, year, padZero(month), padZero(d));
      try {
        const resp = await fetch(filePath);
        const data = await resp.json();
        monthGood += data.good;
        monthMeh += data.meh;
        monthBad += data.bad;
        monthTemp += data.avg_sensor_day ? data.avg_sensor_day.temp : 0;
      } catch { }
    }

    totalGood += monthGood;
    totalMeh += monthMeh;
    totalBad += monthBad;
    lineDataArray.push(Math.round(monthTemp / daysInMonth));
  }

  updateChartAndHTML(totalGood, totalMeh, totalBad, lineLabels, lineDataArray);
  hideLoader();
}

// ----------------------------
// Zeitraumwechsel
// ----------------------------
function loadDataForCurrentRange() {
  if (currentTimeRange === "now" || currentTimeRange === "day") loadDayData();
  else if (currentTimeRange === "week") loadWeekData();
  else if (currentTimeRange === "month") loadMonthData();
  else if (currentTimeRange === "year") loadYearData();
}

// ----------------------------
// Event-Listener
// ----------------------------
document.querySelectorAll(".zeitraum td").forEach((td, index) => {
  td.addEventListener("click", () => {
    document.querySelectorAll(".zeitraum td").forEach(t => t.classList.remove("active"));
    td.classList.add("active");

    const ranges = ["now", "day", "week", "month", "year"];
    currentTimeRange = ranges[index];
    loadDataForCurrentRange();
  });
});

document.querySelectorAll(".links tr").forEach((row, index) => {
  if (index === 0) return;
  row.addEventListener("click", () => {
    document.querySelectorAll(".links tr").forEach(r => r.classList.remove("active"));
    row.classList.add("active");

    const departments = ["allgemein", "werk", "buero"];
    currentDepartment = departments[index - 1];
    updateCharts(index - 1);
    loadDataForCurrentRange();
  });
});

// ----------------------------
// Initialisierung
// ----------------------------
document.addEventListener("DOMContentLoaded", () => {
  document.querySelector(".zeitraum td").classList.add("active");
  document.querySelector(".links tr:nth-child(2)").classList.add("active");
  loadDataForCurrentRange();
});
