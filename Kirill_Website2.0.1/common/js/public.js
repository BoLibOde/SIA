console.log("public.js wurde geladen ✅");

// ----------------------------
// Globale Variablen für Geräte
// ----------------------------
let devicesList = [];       // Liste der Geräte
let devicesData = {};       // { deviceName: { bar: [], line: [], lineLabels: [] } }
let currentDevice = "";     // aktuell ausgewähltes Gerät

// ----------------------------
// Chart-Initialisierung
// ----------------------------
const barData = {
  labels: ['Gut', 'Meh', 'Schlecht'],
  datasets: [{
    label: 'Anzahl der Leute',
    data: [0, 0, 0],
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
  data: barData,
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

const lineData = {
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
  data: lineData,
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
// Update-Funktion für Charts
// ----------------------------
function updateChartsForDevice(deviceName) {
  if (!devicesData[deviceName]) return;

  const barValues = devicesData[deviceName].bar;
  const lineValues = devicesData[deviceName].line;
  const lineLabels = devicesData[deviceName].lineLabels;

  barChart.data.datasets[0].data = barValues;
  barChart.update();

  lineChart.data.datasets[0].data = lineValues;
  lineChart.data.labels = lineLabels;
  lineChart.update();

  document.getElementById('total-good').textContent = barValues[0];
  document.getElementById('total-moderate').textContent = barValues[1];
  document.getElementById('total-bad').textContent = barValues[2];
  document.getElementById('total-votes').textContent = barValues.reduce((a,b)=>a+b,0);
}

// ----------------------------
// Event-Listener für Gerätewahl
// ----------------------------
function initDeviceSelection() {
  const table = document.querySelector(".links table");
  table.innerHTML = "<tr><th>Geräte</th></tr>";
  devicesList.forEach((dev) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${dev}</td>`;
    tr.addEventListener("click", () => {
      document.querySelectorAll(".links tr").forEach(r => r.classList.remove("active"));
      tr.classList.add("active");
      currentDevice = dev;
      updateChartsForDevice(dev);
      if (typeof loadDataForCurrentRange === "function") loadDataForCurrentRange();
    });
    table.appendChild(tr);
  });
}

// ----------------------------
// Initialisierung
// ----------------------------
document.addEventListener("DOMContentLoaded", () => {
  if (devicesList.length > 0) {
    currentDevice = devicesList[0];
    initDeviceSelection();
    updateChartsForDevice(currentDevice);
  }
});
