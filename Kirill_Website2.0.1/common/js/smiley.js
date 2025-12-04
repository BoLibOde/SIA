console.log("smiley.js wurde geladen ✅");
// Beispielwert für Luftqualität (AQI)
let luftQualitaet = 8; // Ändere diesen Wert für Test: z.B. 40, 85, 150

// DOM-Elemente
const good = document.getElementById("good");
const moderate = document.getElementById("moderate");
const bad = document.getElementById("bad");
const statusText = document.getElementById("status-text");

// Funktion, die die Smileys nach AQI aktualisiert
function updateLuftQualitaet(aqi) {
  // Zuerst alle Smileys deaktivieren
  [good, moderate, bad].forEach(el => el.classList.remove("active"));

  // AQI-Bereiche
  if (aqi <= 50) {
    good.classList.add("active");
    statusText.textContent = "Gute Luftqualität 🌿";
  } else if (aqi <= 100) {
    moderate.classList.add("active");
    statusText.textContent = "Mittlere Luftqualität 😐";
  } else {
    bad.classList.add("active");
    statusText.textContent = "Schlechte Luftqualität 😷";
  }
}

// Initial aufrufen
updateLuftQualitaet(luftQualitaet);

// Optional: Wert dynamisch ändern (z. B. jede Minute aktualisieren)
// setInterval(() => {
//   luftQualitaet = Math.floor(Math.random() * 200); // Zufallswert zum Testen
//   updateLuftQualitaet(luftQualitaet);
// }, 60000);
