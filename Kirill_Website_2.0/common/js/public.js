console.log("public.js geladen ✅");

// ---------------- Daten ----------------
const barDatasets = [
  { data: [0, 0, 0] },   // Allgemein (JSON lädt echte Werte)
  { data: [30, 4, 2] },  // Werk
  { data: [5, 50, 100] } // Büro
];

const lineDatasets = [
  { data: [5, 7, 3] },
  { data: [2, 9, 6] },
  { data: [5, 50, 100] }
];

// ---------------- Säulendiagramm ----------------
const barData = {
  labels: ['Gut', 'Meh', 'Schlecht'],
  datasets: [{
    label: 'Anzahl der Leute',
    data: barDatasets[0].data,
    backgroundColor: ['#22c55e', '#eab308', '#ef4444'],
    borderColor: ['#16a34a', '#ca8a04', '#dc2626'],
    borderWidth: 1
  }]
};

const barChart = new Chart(document.getElementById('myChart'), {
  type: 'bar',
  data: barData,
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 1000, easing: 'easeOutQuart' },
    plugins: {
      legend: { display: true },
      title: { display: true, text: 'Zufriedenheit der Angestellten', font: { size: 18 } }
    },
    scales: { y: { beginAtZero: true, ticks: { stepSize: 10 } } }
  }
});

// ---------------- Liniendiagramm ----------------
const lineData = {
  labels: ['Gut', 'Meh', 'Schlecht'],
  datasets: [{
    label: 'Temperatur °C',
    data: lineDatasets[0].data,
    borderColor: '#007cbc',
    backgroundColor: 'rgba(0,124,188,0.1)',
    fill: true,
    tension: 0.4,
    pointRadius: 6,
    pointBackgroundColor: '#007cbc'
  }]
};

const lineChart = new Chart(document.getElementById('lineChart'), {
  type: 'line',
  data: lineData,
  options: {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 1200, easing: 'easeOutQuart' },
    plugins: {
      legend: { display: true },
      title: { display: true, text: 'Temperatur bei ebmpapst', font: { size: 18 } }
    },
    scales: { y: { beginAtZero: true, ticks: { stepSize: 10 } } }
  }
});

// ---------------- JSON für Allgemein laden ----------------
fetch('common/json/summary.json')
  .then(r => r.json())
  .then(json => {
    barDatasets[0].data = [json.good, json.meh, json.bad];
    barChart.data.datasets[0].data = barDatasets[0].data;
    barChart.update();
    document.getElementById('total-good').textContent = json.good;
    document.getElementById('total-moderate').textContent = json.meh;
    document.getElementById('total-bad').textContent = json.bad;
  })
  .catch(e => console.error('Fehler beim Laden der JSON:', e));

// ---------------- Update-Funktion für Sidebar ----------------
function updateCharts(index) {
  // Sanftes Update mit Animation
  const newBarData = barDatasets[index].data;
  const newLineData = lineDatasets[index].data;

  barChart.data.datasets[0].data = newBarData;
  barChart.update({ duration: 800, easing: 'easeOutQuart' });

  lineChart.data.datasets[0].data = newLineData;
  lineChart.update({ duration: 800, easing: 'easeOutQuart' });

  // Totals animiert ändern
  animateNumber('total-good', newBarData[0]);
  animateNumber('total-moderate', newBarData[1]);
  animateNumber('total-bad', newBarData[2]);
}

// ---------------- Hilfsfunktion: animierte Zahlen ----------------
function animateNumber(id, target) {
  const el = document.getElementById(id);
  const start = parseInt(el.textContent) || 0;
  const duration = 500;
  const stepTime = 30;
  let current = start;
  const step = (target - start) / (duration / stepTime);

  const timer = setInterval(() => {
    current += step;
    if ((step > 0 && current >= target) || (step < 0 && current <= target)) {
      current = target;
      clearInterval(timer);
    }
    el.textContent = Math.round(current);
  }, stepTime);
}

console.log("Modernes Chart-Update ✅");
