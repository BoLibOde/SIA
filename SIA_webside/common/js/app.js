let chart = null;

async function fetchSummary() {
  try {
    const res = await fetch('common/json/summary.json', { cache: "no-store" });
    if (!res.ok) throw new Error('Fetch fehlgeschlagen: ' + res.status);
    const data = await res.json();
    return normalize(data);
  } catch (err) {
    console.warn('Fehler beim Laden von summary.json:', err.message);
    throw err;
  }
}

function normalize(raw) {
  const good = Number(raw.good ?? raw.Good ?? 0) || 0;
  const meh  = Number(raw.meh ?? raw.Meh ?? 0) || 0;
  const bad  = Number(raw.bad ?? raw.Bad ?? 0) || 0;
  const last_update = raw.last_update ?? raw.lastUpdate ?? null;
  return { good, meh, bad, last_update };
}

function updateTable(obj) {
  document.getElementById('valGood').textContent = obj.good;
  document.getElementById('valMeh').textContent = obj.meh;
  document.getElementById('valBad').textContent = obj.bad;
  document.getElementById('valSum').textContent = (obj.good + obj.meh + obj.bad);
  document.getElementById('valTime').textContent = obj.last_update ?? '—';
}

function updateChart(obj) {
  const ctx = document.getElementById('chartCanvas').getContext('2d');
  const values = [obj.good, obj.meh, obj.bad];

  if (chart) {
    chart.data.datasets[0].data = values;
    chart.update();
    return;
  }

  chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Good', 'Meh', 'Bad'],
      datasets: [{
        label: 'Anzahl',
        data: values,
        backgroundColor: [
          'rgba(34,197,94,0.8)',   // grün
          'rgba(245,158,11,0.85)', // orange
          'rgba(239,68,68,0.85)'   // rot
        ],
        borderRadius: 6,
        barThickness: 36
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
    }
  });
}

function updateUI(data) {
  updateTable(data);
  updateChart(data);
}

async function loadAndShow() {
  try {
    const data = await fetchSummary();
    updateUI(data);
  } catch {
    console.warn('Ladeversuch fehlgeschlagen. Bitte Datei hochladen oder JSON einfügen.');
  }
}

// Event-Handler
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById('reloadBtn').addEventListener('click', loadAndShow);

  document.getElementById('uploadBtn').addEventListener('click', () =>
    document.getElementById('fileInput').click()
  );

  document.getElementById('fileInput').addEventListener('change', ev => {
    const file = ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target.result);
        updateUI(normalize(parsed));
      } catch (err) {
        alert('Ungültige JSON-Datei: ' + err.message);
      }
    };
    reader.readAsText(file, 'utf-8');
  });

  document.getElementById('pasteBtn').addEventListener('click', () => {
    document.getElementById('pasteArea').style.display = 'block';
    document.getElementById('jsonText').focus();
  });

  document.getElementById('cancelJson').addEventListener('click', () => {
    document.getElementById('pasteArea').style.display = 'none';
    document.getElementById('jsonText').value = '';
  });

  document.getElementById('applyJson').addEventListener('click', () => {
    const txt = document.getElementById('jsonText').value.trim();
    if (!txt) return alert('Bitte JSON eingeben.');
    try {
      const parsed = JSON.parse(txt);
      updateUI(normalize(parsed));
      document.getElementById('pasteArea').style.display = 'none';
      document.getElementById('jsonText').value = '';
    } catch (err) {
      alert('Ungültiges JSON: ' + err.message);
    }
  });

  loadAndShow();
});
