// common/js/public.js
// Erzeugt Charts und stellt globale Datensätze zur Verfügung

// ---------------- Daten definieren ----------------
window.barDatasets = [
  { data: [] },   // Allgemein (wird später befüllt)
  { data: [30, 4, 2] },     // Werk (Platzhalter)
  { data: [5, 50, 100] }    // Büro (Platzhalter)
];

window.lineDatasets = [
  { data: [5, 7, 3] },      // Allgemein (Platzhalter)
  { data: [2, 9, 6] },      // Werk (Platzhalter)
  { data: [5, 50, 100] }    // Büro (Platzhalter)
];

// gewünschte Canvas-Höhe in Pixel (anpassen nach Geschmack)
const CANVAS_HEIGHT_PX = 340;

window.barChart = null;
window.lineChart = null;

// ---------------- Hilfs: sichere Chart-Erzeugung ----------------
(function initCharts() {
  // Wenn Charts bereits existieren, nichts tun (Schutz gegen mehrfache Initialisierung)
  if (window.barChart || window.lineChart) return;

  // Säulendiagramm Config (responsive:false -> feste Größe benutzen)
  const barData = {
    labels: ['Gut', 'Meh', 'Schlecht'],
    datasets: [{
      label: 'Anzahl der Leute',
      data: window.barDatasets[0].data,
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

  const barConfig = {
    type: 'bar',
    data: barData,
    options: {
      responsive: false, // wichtig: Chart.js passt Höhe nicht automatisch an
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

  const myChartEl = document.getElementById('myChart');
  if (myChartEl) {
    // Explizit Canvas-Größe setzen (CSS-änderungen vermeiden)
    myChartEl.style.height = CANVAS_HEIGHT_PX + 'px';
    myChartEl.height = CANVAS_HEIGHT_PX;
    // Breite übernimmt Chart.js vom Parent; du kannst style.width setzen falls nötig
    window.barChart = new Chart(myChartEl, barConfig);
  }

  // ---------------- Liniendiagramm ----------------
  const lineData = {
    labels: ['Gut', 'Meh', 'Schlecht'],
    datasets: [{
      label: '°C',
      data: window.lineDatasets[0].data,
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
      responsive: false, // ebenfalls deaktiviert
      maintainAspectRatio: false,
      plugins: {
        legend: { display: true },
        title: { display: true, text: 'Temperatur bei ebmpapst' }
      },
      scales: {
        y: { beginAtZero: true }
      }
    }
  };

  const lineChartEl = document.getElementById('lineChart');
  if (lineChartEl) {
    lineChartEl.style.height = CANVAS_HEIGHT_PX + 'px';
    lineChartEl.height = CANVAS_HEIGHT_PX;
    window.lineChart = new Chart(lineChartEl, lineConfig);
  }
})();


// ---------------- Update-Funktion ----------------
function updateCharts(index) {
  if (!Array.isArray(window.barDatasets) || !window.barDatasets[index]) {
    console.warn("updateCharts: ungültiger Index", index);
    return;
  }

  // Säulendiagramm aktualisieren
  if (window.barChart) {
    window.barChart.data.datasets[0].data = window.barDatasets[index].data;
    window.barChart.update();
  }

  // Liniendiagramm aktualisieren
  if (window.lineChart && window.lineDatasets[index]) {
    window.lineChart.data.datasets[0].data = window.lineDatasets[index].data;
    window.lineChart.update();
  }

  const elGood = document.getElementById('total-good');
  const elMeh = document.getElementById('total-moderate');
  const elBad = document.getElementById('total-bad');
  const elVotes = document.getElementById('total-votes');

  if (elGood) elGood.textContent = window.barDatasets[index].data[0] || 0;
  if (elMeh) elMeh.textContent = window.barDatasets[index].data[1] || 0;
  if (elBad) elBad.textContent = window.barDatasets[index].data[2] || 0;

  if (elVotes) {
    const sum = (window.barDatasets[index].data[0] || 0) + (window.barDatasets[index].data[1] || 0) + (window.barDatasets[index].data[2] || 0);
    elVotes.textContent = sum;
  }
}

// expose global so inline onclick handlers still work
window.updateCharts = updateCharts;

console.log("public.js wurde geladen ✅ (Charts initialisiert, feste Höhe gesetzt)");