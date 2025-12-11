// devices.js - small client for /manage UI
async function apiGetDevices() {
  const res = await fetch('/devices');
  if (!res.ok) throw new Error('Failed to fetch devices');
  return await res.json();
}

async function apiSetDeviceName(device_id, name) {
  const res = await fetch('/set_device_name', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ device_id, name })
  });
  return res.json();
}

function showStatus(msg, timeout=3000) {
  const el = document.getElementById('status');
  el.textContent = msg;
  if (timeout) setTimeout(()=> { if (el.textContent === msg) el.textContent = ''; }, timeout);
}

function renderDevices(devices) {
  const tbody = document.querySelector('#devicesTable tbody');
  tbody.innerHTML = '';
  const ids = Object.keys(devices).sort();
  for (const id of ids) {
    const meta = devices[id] || {};
    const tr = document.createElement('tr');

    const tdId = document.createElement('td');
    tdId.textContent = id;
    tr.appendChild(tdId);

    const tdName = document.createElement('td');
    const input = document.createElement('input');
    input.className = 'nameField';
    input.value = meta.name || '';
    input.placeholder = 'Set display name';
    tdName.appendChild(input);
    tr.appendChild(tdName);

    const tdCreated = document.createElement('td');
    tdCreated.textContent = meta.created || '-';
    tr.appendChild(tdCreated);

    const tdLast = document.createElement('td');
    tdLast.textContent = meta.last_upload || '-';
    tr.appendChild(tdLast);

    const tdActions = document.createElement('td');
    const btn = document.createElement('button');
    btn.textContent = 'Set';
    btn.className = 'saveBtn';
    btn.onclick = async () => {
      try {
        const name = input.value.trim();
        if (!name) { showStatus('Please enter a name'); return; }
        const r = await apiSetDeviceName(id, name);
        if (r && r.status === 'ok') {
          showStatus('Saved');
          loadDevices();
        } else {
          showStatus('Save failed');
        }
      } catch (e) {
        showStatus('Error: ' + e.message);
      }
    };
    tdActions.appendChild(btn);
    tr.appendChild(tdActions);

    tbody.appendChild(tr);
  }
}

async function loadDevices() {
  try {
    showStatus('Loading...');
    const d = await apiGetDevices();
    renderDevices(d);
    showStatus('Loaded', 1200);
  } catch (e) {
    showStatus('Failed to load devices: ' + e.message, 6000);
  }
}

document.addEventListener('DOMContentLoaded', ()=> {
  document.getElementById('btnRefresh').addEventListener('click', ()=> loadDevices());
  document.getElementById('btnAdd').addEventListener('click', async ()=>{
    const id = document.getElementById('newDeviceId').value.trim();
    const name = document.getElementById('newDeviceName').value.trim();
    if (!id || !name) { showStatus('Please enter both id and name'); return; }
    try {
      const r = await apiSetDeviceName(id, name);
      if (r && r.status === 'ok') {
        showStatus('Device added/updated');
        document.getElementById('newDeviceId').value = '';
        document.getElementById('newDeviceName').value = '';
        loadDevices();
      } else {
        showStatus('Add failed');
      }
    } catch (e) {
      showStatus('Error: ' + e.message);
    }
  });

  loadDevices();
});