// 1. Daten definieren
const data = {
  labels: ['Januar', 'Februar', 'März', 'April', 'Mai'], // Beschriftung der X-Achse
  datasets: [{
    label: 'Umsatz in €',                // Name des Datensatzes für die Legende
    data: [1200, 1500, 1000, 1700, 1400], // Werte für jede Säule
    backgroundColor: 'rgba(75, 192, 192, 0.5)', // Füllfarbe der Balken (halbtransparent)
    borderColor: 'rgba(75, 192, 192, 1)',       // Randfarbe der Balken
    borderWidth: 1                               // Dicke des Balkenrands
  }]
};

// 2. Konfiguration des Diagramms
const config = {
  type: 'bar',  // Diagrammtyp: 'bar' = Säulendiagramm
  data: data,   // Verknüpft die Daten
  options: {
    responsive: false,           // Diagramm reagiert NICHT auf Bildschirmgröße
    maintainAspectRatio: false, // Diagramm passt sich automatisch an Bildschirmgröße an
    plugins: {
      legend: { display: true }, // Zeigt die Legende an
      title: { display: true, text: 'Monatlicher Umsatz' } // Titel des Diagramms
    },
    scales: {
      y: { beginAtZero: true } // Y-Achse startet bei 0, damit Säulen richtig dargestellt werden
    }
  }
};

// 3. Diagramm erzeugen
new Chart(
  document.getElementById('myChart'), // Ziel-Canvas auswählen
  config                              // Konfiguration anwenden
);
