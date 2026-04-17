'use strict';

// ── Estado global ─────────────────────────────────────────────────────────────
let clienteActual = '';
let moduloActual  = 'golpes';   // tab activo
let charts = {};
let lastData = { golpes: null, util: null, bat: null };  // cache para rankings
const COLORS = ['#e8650a','#a0a0a0','#ff9a4d','#6b6b6b','#ffb87a','#4a4a4a','#ffd4a8','#888888'];

Chart.defaults.color = '#888';
Chart.defaults.borderColor = '#2a2a2a';
Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
Chart.defaults.font.size = 11;

// ── Inicialización ────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', async () => {
  await cargarListaClientes();
  const path = window.location.pathname.split('/');
  const id = path[path.length - 1];
  if (id && id !== '' && id !== 'index.html') {
    clienteActual = id;
    document.getElementById('clienteSelect').value = id;
  }
  if (clienteActual) cargarModulo();

  // Auto-refresh cada 5 minutos — recarga solo el módulo visible
  setInterval(cargarModulo, 5 * 60 * 1000);
});

async function cargarListaClientes() {
  const res = await fetch('/api/clientes');
  const lista = await res.json();
  const sel = document.getElementById('clienteSelect');
  lista.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c.id;
    opt.textContent = c.label;
    sel.appendChild(opt);
  });
  if (!clienteActual && lista.length) {
    clienteActual = lista[0].id;
    sel.value = clienteActual;
  }
}

function cambiarCliente(id) {
  clienteActual = id;
  lastData = { golpes: null, util: null, bat: null };
  window.history.pushState({}, '', `/dashboard/${id}`);
  limpiarFiltros(false);
  cargarModulo();
}

function limpiarFiltros(reload = true) {
  document.getElementById('fDesde').value = '';
  document.getElementById('fHasta').value = '';
  document.getElementById('fFamilia').value = '';
  document.getElementById('fSite').value = '';
  document.getElementById('fConductor').value = '';
  if (reload) cargarModulo();
}

function aplicarFiltros() { cargarModulo(); }

function _params(modulo) {
  const p = new URLSearchParams();
  // rankings necesita todos los módulos — no pasar parámetro modulo
  if (modulo !== 'rankings') p.set('modulo', modulo);
  const v = (id) => document.getElementById(id).value;
  if (v('fDesde'))     p.set('desde',     v('fDesde'));
  if (v('fHasta'))     p.set('hasta',     v('fHasta'));
  if (v('fFamilia'))   p.set('familia',   v('fFamilia'));
  if (v('fSite'))      p.set('site',      v('fSite'));
  if (v('fConductor')) p.set('conductor', v('fConductor'));
  return '?' + p.toString();
}

// Carga solo el módulo activo
async function cargarModulo() {
  if (!clienteActual) return;
  setLoading(true);
  try {
    const res = await fetch(`/api/dashboard/${clienteActual}${_params(moduloActual)}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    setLoading(false);
    document.title = `I_Site — ${data.cliente}`;
    // Fusionar en lastData para que rankings tenga todos los módulos
    if (data.golpes) lastData.golpes = data.golpes;
    if (data.util)   lastData.util   = data.util;
    if (data.bat)    lastData.bat    = data.bat;
    if (data.golpes) { renderGolpes(data.golpes); actualizarFiltros(data.golpes); }
    if (data.util)   { renderUtil(data.util);     actualizarFiltros(data.util);   }
    if (data.bat)    { renderBat(data.bat); }
    if (moduloActual === 'rankings') renderRankings(lastData);
    if (!data.golpes && !data.util && !data.bat) {
      document.getElementById('noData').classList.remove('hidden');
    }
    document.getElementById('lastUpdate').textContent = 'Actualizado: ' + new Date().toLocaleTimeString();
  } catch (e) {
    setLoading(false);
    document.getElementById('noData').classList.remove('hidden');
    console.error(e);
  }
}

// Alias para el botón Actualizar del header
function cargarDashboard() { cargarModulo(); }

function setLoading(on) {
  document.getElementById('loading').classList.toggle('hidden', !on);
  document.getElementById('noData').classList.add('hidden');
}

function actualizarFiltros(src) {
  if (!src) return;
  llenarSelect('fFamilia',   src.familias    || []);
  llenarSelect('fSite',      src.sites       || []);
  llenarSelect('fConductor', src.conductores || []);
}

function llenarSelect(id, opciones) {
  const sel = document.getElementById(id);
  const val = sel.value;
  sel.innerHTML = '<option value="">Todos</option>';
  opciones.forEach(o => {
    const opt = document.createElement('option');
    opt.value = o; opt.textContent = o;
    sel.appendChild(opt);
  });
  sel.value = val;
}

// ── Golpes ───────────────────────────────────────────────────────────────────
function renderGolpes(g) {
  const k = g.kpis || {};
  setText('g-conductores', fmt(k.total_conductores));
  setText('g-altos',       fmt(k.total_golpes_altos));
  setText('g-medios',      fmt(k.total_golpes_medios));
  setText('g-maquinas',    fmt(k.total_maquinas));
  setText('g-batdesc',     fmt(k.apagado_bat_desc));

  // Donut familia
  donut('g-donut', g.por_familia, 'familia', 'total');

  // Línea por mes
  linea('g-linea-mes', g.por_mes, 'mes', 'total', 'Golpes Altos');

  // Barras 30 días
  barras('g-barras-30', g.ultimos_30dias, 'dia', 'total', 'Golpes Altos');

  // Ranking
  ranking('g-ranking',
    [{ key: 'conductor', label: 'Conductor' }, { key: 'golpes_altos', label: 'Golpes Altos' }],
    g.ranking || []);
}

// ── Utilización ───────────────────────────────────────────────────────────────
function renderUtil(u) {
  const k = u.kpis || {};
  setText('u-hrsfunc',    fmt(k.hrs_funcionamiento));
  setText('u-hrsllave',   fmt(k.hrs_llave));
  setText('u-eficiencia', (k.pct_eficiencia || 0) + ' %');
  setText('u-batdesc',    fmt(k.apagado_bat_desc));

  donut('u-donut', u.hrs_familia, 'familia', 'horas');
  barrasHoriz('u-claves', u.claves_conductor || [], 'conductor', 'claves', 'Claves Compartidas');
  linea('u-linea-mes', u.hrs_mes, 'mes', 'horas', 'Hrs Funcionamiento');
  barras('u-barras-dia', u.hrs_dia, 'dia', 'horas', 'Hrs Func');
  ranking('u-ranking',
    [{ key: 'conductor', label: 'Conductor' }, { key: 'hrs_func', label: 'Hrs Func' }, { key: 'eficiencia', label: '% Efic.' }],
    u.ranking || []);
}

// ── Baterías ─────────────────────────────────────────────────────────────────
function renderBat(b) {
  barrasApagado('b-maquina',    b.apagado_maquina    || [], 'maquina');
  barrasApagado('b-conductor',  b.apagado_conductor  || [], 'conductor');
  barras('b-mes',   b.por_mes   || [], 'mes',  'total', 'Recuento');
  linea('b-hora',   b.por_hora  || [], 'hora', 'total', 'Incidentes');
  barras('b-20pct', b.incidentes_20pct || [], 'mes', 'total', 'Incidentes <20%');
  ranking('b-ranking',
    [{ key: 'conductor', label: 'Conductor' }, { key: 'pct_bat', label: '% Bat. Desc.' }],
    b.ranking || []);
}

// ── Chart helpers ─────────────────────────────────────────────────────────────
function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function donut(id, data, labelKey, valKey) {
  destroyChart(id);
  if (!data || !data.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'doughnut',
    data: {
      labels: data.map(d => d[labelKey]),
      datasets: [{ data: data.map(d => d[valKey]), backgroundColor: COLORS, borderWidth: 1 }]
    },
    options: {
      plugins: { legend: { position: 'right', labels: { boxWidth: 12, padding: 8 } } },
      cutout: '65%',
    }
  });
}

function linea(id, data, xKey, yKey, label) {
  destroyChart(id);
  if (!data || !data.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'line',
    data: {
      labels: data.map(d => d[xKey]),
      datasets: [{
        label, data: data.map(d => d[yKey]),
        borderColor: COLORS[0], backgroundColor: COLORS[0] + '22',
        tension: 0.3, fill: true, pointRadius: 3,
      }]
    },
    options: {
      scales: { x: { grid: { color: '#1e1e1e' } }, y: { grid: { color: '#1e1e1e' } } },
      plugins: { legend: { display: false } },
    }
  });
}

function barras(id, data, xKey, yKey, label) {
  destroyChart(id);
  if (!data || !data.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'bar',
    data: {
      labels: data.map(d => d[xKey]),
      datasets: [{ label, data: data.map(d => d[yKey]), backgroundColor: COLORS[0], borderRadius: 2 }]
    },
    options: {
      scales: { x: { grid: { color: '#1a1a1a' } }, y: { grid: { color: '#1e1e1e' } } },
      plugins: { legend: { display: false } },
    }
  });
}

function barrasHoriz(id, data, labelKey, valKey, label) {
  destroyChart(id);
  if (!data || !data.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'bar',
    data: {
      labels: data.map(d => d[labelKey]),
      datasets: [{ label, data: data.map(d => d[valKey]), backgroundColor: COLORS[0], borderRadius: 2 }]
    },
    options: {
      indexAxis: 'y',
      scales: { x: { grid: { color: '#1e1e1e' } }, y: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    }
  });
}

function barrasApagado(id, data, labelKey) {
  destroyChart(id);
  if (!data || !data.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'bar',
    data: {
      labels: data.map(d => d[labelKey]),
      datasets: [
        { label: 'Normal',            data: data.map(d => d.normal   || 0), backgroundColor: COLORS[0], borderRadius: 2 },
        { label: 'Bat. Desconectada', data: data.map(d => d.bat_desc || 0), backgroundColor: COLORS[1], borderRadius: 2 },
      ]
    },
    options: {
      indexAxis: 'y',
      scales: { x: { stacked: true, grid: { color: '#1e1e1e' } }, y: { stacked: true, grid: { display: false } } },
      plugins: { legend: { position: 'top' } },
    }
  });
}

function ranking(id, cols, rows) {
  const el = document.getElementById(id);
  if (!rows || !rows.length) { el.innerHTML = '<p style="color:#555;font-size:11px">Sin datos</p>'; return; }
  const gridTpl = `repeat(${cols.length}, 1fr)`;
  let html = `<div class="r-header" style="grid-template-columns:${gridTpl}">`;
  cols.forEach(c => html += `<span>${c.label}</span>`);
  html += '</div>';
  rows.forEach(r => {
    html += `<div class="r-row" style="grid-template-columns:${gridTpl}">`;
    cols.forEach(c => html += `<span>${r[c.key] ?? '—'}</span>`);
    html += '</div>';
  });
  el.innerHTML = html;
}

// ── Rankings ──────────────────────────────────────────────────────────────────
function renderRankings(d) {
  const g = d.golpes || {};
  const u = d.util   || {};
  const b = d.bat    || {};

  ranking('rnk-golpes',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' }, { key: 'golpes_altos', label: 'Golpes Altos' }],
    (g.ranking || []).map((r, i) => ({ ...r, '#': i + 1 })));

  ranking('rnk-bat-desc',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' }, { key: 'bat_desc', label: 'Bat. Desconectadas' }],
    (b.ranking_bat_desc || []).map((r, i) => ({ ...r, '#': i + 1 })));

  ranking('rnk-claves',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' }, { key: 'claves', label: 'Claves Compartidas' }],
    (u.claves_conductor || []).map((r, i) => ({ ...r, '#': i + 1 })));

  ranking('rnk-hrs',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' }, { key: 'hrs_func', label: 'Hrs Utilización' }],
    (u.ranking_hrs || []).map((r, i) => ({ ...r, '#': i + 1 })));
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function showTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.remove('hidden');
  btn.classList.add('active');

  if (name === 'rankings') {
    // Rankings necesita todos los módulos
    const tieneAll = lastData.golpes && lastData.util;
    if (moduloActual !== 'rankings') {
      moduloActual = 'rankings';
      if (tieneAll) {
        renderRankings(lastData);
      } else {
        cargarModulo();
      }
    }
    return;
  }

  // Carga lazy: solo pide datos si cambió el módulo
  const nuevoModulo = name;
  if (nuevoModulo !== moduloActual) {
    moduloActual = nuevoModulo;
    cargarModulo();
  }
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function fmt(n) {
  if (n == null || n === undefined) return '—';
  return Number(n).toLocaleString('es-CL');
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
