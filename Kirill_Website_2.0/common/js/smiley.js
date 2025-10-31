console.log("smiley.js geladen ✅");

let luftQualitaet = 8;

const good = document.getElementById("good");
const moderate = document.getElementById("moderate");
const bad = document.getElementById("bad");
const statusText = document.getElementById("status-text");

function updateLuftQualitaet(aqi){
  [good,moderate,bad].forEach(el=>el.classList.remove("active"));
  if(aqi<=50){ good.classList.add("active"); statusText.textContent="Gute Luftqualität 🌿"; }
  else if(aqi<=100){ moderate.classList.add("active"); statusText.textContent="Mittlere Luftqualität 😐"; }
  else{ bad.classList.add("active"); statusText.textContent="Schlechte Luftqualität 😷"; }
}

updateLuftQualitaet(luftQualitaet);
