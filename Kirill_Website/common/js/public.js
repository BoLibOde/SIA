// ---------------- Daten definieren ----------------
const barDatasets = [
  { data: [50, 15, 10] },   // Allgemein
  { data: [30, 4, 2] },     // Werk
  { data: [5, 50, 100] }    // Büro
];

const lineDatasets = [
  { data: [5, 7, 3] },      // Allgemein
  { data: [2, 9, 6] },      // Werk
  { data: [5, 50, 100] }    // Büro
];

// ---------------- Säulendiagramm ----------------
const barData = {
  labels: ['Gut', 'Meh', 'Schlecht'],
  datasets: [{
    label: 'Anzahl der Leute',
    data: barDatasets[0].data,
    backgroundColor: 'rgba(75, 192, 192, 0.5)',
    borderColor: 'rgba(75, 192, 192, 1)',
    borderWidth: 1
  }]
};

const barConfig = {
  type: 'bar',
  data: barData,
  options: {
    responsive: false,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: true },
      title: { display: true, text: 'Zufriedenheit der Angestellten' }
    },
    scales: {
      y: { beginAtZero: true }
    }
  }
};

const barChart = new Chart(document.getElementById('myChart'), barConfig);

// ---------------- Liniendiagramm ----------------
const lineData = {
  labels: ['Gut', 'Meh', 'Schlecht'],
  datasets: [{
    label: 'Messwerte',
    data: lineDatasets[0].data,
    borderColor: 'blue',
    backgroundColor: 'rgba(0,0,255,0.1)',
    fill: true,
    tension: 0.3
  }]
};

const lineConfig = {
  type: 'line',
  data: lineData,
  options: {
    responsive: false,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: true },
      title: { display: true, text: 'Liniendiagramm der Werte' }
    },
    scales: {
      y: { beginAtZero: true }
    }
  }
};

const lineChart = new Chart(document.getElementById('lineChart'), lineConfig);

// ---------------- Update-Funktion ----------------
function updateCharts(index) {
  // Säulendiagramm aktualisieren
  barChart.data.datasets[0].data = barDatasets[index].data;
  barChart.update();

  // Liniendiagramm aktualisieren
  lineChart.data.datasets[0].data = lineDatasets[index].data;
  lineChart.update();
}
