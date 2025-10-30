console.log("lautstaerke.js wurde geladen ✅");

// -----------------------------
// Lautstärkeanzeige
// -----------------------------

const lautstaerkeLevels = [
  { icon: "icon-maus", name: "Maus", min: 0, max: 30 },
  { icon: "icon-sprechen", name: "Sprechen", min: 31, max: 50 },
  { icon: "icon-musik", name: "Musik", min: 51, max: 70 },
  { icon: "icon-auto", name: "Auto", min: 71, max: 90 },
  { icon: "icon-flugzeug", name: "Flugzeug", min: 91, max: 200 }
];

function resetIcons() {
  document.querySelectorAll(".laut-icon").forEach(i => i.classList.remove("active"));
}

function updateLautstaerkeAnzeige(dbValue) {
  resetIcons();

  const text = document.getElementById("lautstaerke-text");
  const level = lautstaerkeLevels.find(l => dbValue >= l.min && dbValue <= l.max);

  if (level) {
    document.getElementById(level.icon).classList.add("active");
    text.textContent = `${dbValue} dB – ${level.name}`;
  } else {
    text.textContent = `${dbValue} dB`;
  }
}

function getBasePathForDepartment(dep) {
  switch (dep) {
    case "werk": return "common/data";
    case "buero": return "common/data_buero";
    default: return "common/data_allgemein";
  }
}
function padZero(n) { return n < 10 ? "0" + n : n; }
function getFilePathForDate(dep, y, m, d) {
  return `${getBasePathForDepartment(dep)}/${y}/${m}/${d}/totals.json`;
}

// -----------------------------
// Datenlader für Lautstärke
// -----------------------------
async function loadLautstaerke() {
  // Prüfen, ob dataLoader.js Variablen schon da sind
  if (typeof currentTimeRange === "undefined" || typeof currentDepartment === "undefined") {
    console.warn("⏳ Daten noch nicht bereit, versuche erneut...");
    setTimeout(loadLautstaerke, 500);
    return;
  }

  console.log(`🔊 Lade Lautstärke für ${currentTimeRange} / ${currentDepartment}`);

  const today = new Date();
  let totalDb = 0, count = 0;

  async function loadDbForDate(y, m, d) {
    const path = getFilePathForDate(currentDepartment, y, m, d);
    try {
      const resp = await fetch(path);
      const data = await resp.json();
      let val = 0;
      if (data.db !== undefined) val = data.db;
      else if (data.avg_sensor_day && data.avg_sensor_day.db !== undefined)
        val = data.avg_sensor_day.db;

      if (!isNaN(val)) {
        totalDb += val;
        count++;
      }
    } catch (e) {
      console.warn("❌ Datei nicht gefunden:", path);
    }
  }

  // Zeitraumbezogenes Laden
  if (currentTimeRange === "now" || currentTimeRange === "day") {
    await loadDbForDate(today.getFullYear(), padZero(today.getMonth() + 1), padZero(today.getDate()));
  } else if (currentTimeRange === "week") {
    const dayOfWeek = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - ((dayOfWeek + 6) % 7));
    for (let d = new Date(monday); d <= today; d.setDate(d.getDate() + 1)) {
      await loadDbForDate(d.getFullYear(), padZero(d.getMonth() + 1), padZero(d.getDate()));
    }
  } else if (currentTimeRange === "month") {
    const y = today.getFullYear();
    const m = today.getMonth() + 1;
    const days = new Date(y, m, 0).getDate();
    for (let d = 1; d <= days; d++) {
      await loadDbForDate(y, padZero(m), padZero(d));
    }
  } else if (currentTimeRange === "year") {
    const y = today.getFullYear();
    for (let m = 1; m <= 12; m++) {
      const days = new Date(y, m, 0).getDate();
      for (let d = 1; d <= days; d++) {
        await loadDbForDate(y, padZero(m), padZero(d));
      }
    }
  }

  // Durchschnitt berechnen
  const avgDb = count > 0 ? Math.round(totalDb / count) : 0;
  console.log(`📈 Durchschnittliche Lautstärke: ${avgDb} dB (${count} Werte)`);
  updateLautstaerkeAnzeige(avgDb);
}

// -----------------------------
// Automatisch reagieren
// -----------------------------
document.addEventListener("DOMContentLoaded", () => {
  loadLautstaerke();
  // Reaktion auf Wechsel von Zeit oder Abteilung
  document.querySelectorAll(".zeitraum td, .links tr").forEach(el => {
    el.addEventListener("click", () => setTimeout(loadLautstaerke, 600));
  });
});
