'use strict';

// ── Estado global ─────────────────────────────────────────────────────────────
let moduloActual  = 'golpes';
let charts = {};
let lastData = { golpes: null, util: null, bat: null };

const C1 = '#e8650a';  // naranja
const C2 = '#a0a0a0';  // gris
const C3 = '#ff9a4d';  // naranja claro
const C4 = '#6b6b6b';  // gris oscuro
const COLORS = [C1, C2, C3, C4, '#ffb87a', '#4a4a4a', '#ffd4a8', '#888888'];

Chart.defaults.color = '#888';
Chart.defaults.borderColor = '#2a2a2a';
Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
Chart.defaults.font.size = 11;

// ── Inicialización ────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  cargarModulo();
  setInterval(cargarModulo, 5 * 60 * 1000);
});

function limpiarFiltros(reload = true) {
  ['fDesde','fHasta','fFamilia','fSite','fConductor'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  if (reload) cargarModulo();
}

function aplicarFiltros() { cargarModulo(); }

function _params(modulo) {
  const p = new URLSearchParams();
  if (modulo !== 'rankings') p.set('modulo', modulo);
  const v = id => document.getElementById(id)?.value || '';
  if (v('fDesde'))     p.set('desde',     v('fDesde'));
  if (v('fHasta'))     p.set('hasta',     v('fHasta'));
  if (v('fFamilia'))   p.set('familia',   v('fFamilia'));
  if (v('fSite'))      p.set('site',      v('fSite'));
  if (v('fConductor')) p.set('conductor', v('fConductor'));
  return '?' + p.toString();
}

async function cargarModulo() {
  setLoading(true);
  try {
    const res = await fetch(`/api/dashboard${_params(moduloActual)}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    setLoading(false);

    if (data.golpes) { lastData.golpes = data.golpes; renderGolpes(data.golpes); actualizarFiltros(data.golpes); }
    if (data.util)   { lastData.util   = data.util;   renderUtil(data.util);     actualizarFiltros(data.util);   }
    if (data.bat)    { lastData.bat    = data.bat;     renderBat(data.bat); }
    if (moduloActual === 'rankings') renderRankings(lastData);

    if (!data.golpes && !data.util && !data.bat)
      document.getElementById('noData').classList.remove('hidden');

    document.getElementById('lastUpdate').textContent = 'Actualizado: ' + new Date().toLocaleTimeString();
  } catch (e) {
    setLoading(false);
    document.getElementById('noData').classList.remove('hidden');
    console.error(e);
  }
}

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
  if (!sel) return;
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
  setText('g-total',       fmt(k.total_golpes));
  setText('g-altos',       fmt(k.total_golpes_altos));
  setText('g-medios',      fmt(k.total_golpes_medios));
  setText('g-bajos',       fmt(k.total_golpes_bajos));
  setText('g-pct-altos',   (k.pct_altos || 0) + ' %');
  setText('g-conductores', fmt(k.total_conductores));
  setText('g-maquinas',    fmt(k.total_maquinas));
  setText('g-vel',         k.velocidad_promedio ? k.velocidad_promedio + ' km/h' : '—');

  donut('g-donut', g.por_familia || [], 'familia', 'total');

  // Línea por mes — altos + medios
  lineaDoble('g-linea-mes', g.por_mes || [], 'mes',
    { key: 'altos',  label: 'Altos',  color: C1 },
    { key: 'medios', label: 'Medios', color: C2 });

  // Barras 30 días — altos + medios
  barrasDoble('g-barras-30', g.ultimos_30dias || [], 'dia',
    { key: 'altos',  label: 'Altos',  color: C1 },
    { key: 'medios', label: 'Medios', color: C2 });

  barras('g-hora',      g.por_hora      || [], 'hora', 'total', 'Golpes Altos', C1);
  barras('g-diasemana', g.por_dia_semana|| [], 'dia',  'total', 'Golpes Altos', C1);
  barrasHoriz('g-maquinas-chart', g.por_maquina || [], 'maquina', 'total', 'Golpes Altos');
  barrasHoriz('g-site', g.por_site      || [], 'site', 'total',   'Golpes Altos');

  ranking('g-ranking',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' }, { key: 'golpes_altos', label: 'Golpes Altos' }],
    (g.ranking || []).map((r, i) => ({ ...r, '#': i + 1 })));
}

// ── Utilización ───────────────────────────────────────────────────────────────
function renderUtil(u) {
  const k = u.kpis || {};
  setText('u-hrsfunc',   fmt(k.hrs_funcionamiento));
  setText('u-hrsllave',  fmt(k.hrs_llave));
  setText('u-hrstrac',   fmt(k.hrs_traccion));
  setText('u-hrselev',   fmt(k.hrs_elevacion));
  setText('u-eficiencia',(k.pct_eficiencia || 0) + ' %');
  setText('u-sesiones',  fmt(k.n_sesiones));
  setText('u-avgsesion', k.avg_min_sesion ? k.avg_min_sesion + ' min' : '—');
  setText('u-batdesc',   fmt(k.apagado_bat_desc));
  setText('u-pctbat',    (k.pct_bat_apagado || 0) + ' %');

  donut('u-donut',  u.hrs_familia     || [], 'familia', 'horas');
  donut('u-metodo', u.metodo_apagado  || [], 'metodo',  'total');

  linea('u-linea-mes',  u.hrs_mes       || [], 'mes', 'horas', 'Hrs Func');
  barras('u-barras-dia',u.hrs_dia       || [], 'dia', 'horas', 'Hrs Func', C1);
  barras('u-diasemana', u.hrs_dia_semana|| [], 'dia', 'horas', 'Hrs Func', C2);

  barrasHoriz('u-maquinas', u.por_maquina      || [], 'maquina',   'horas',  'Hrs Func');
  barrasHoriz('u-claves',   u.claves_conductor || [], 'conductor', 'claves', 'Claves');

  ranking('u-ranking',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' },
     { key: 'hrs_func', label: 'Hrs Func' }],
    (u.ranking_hrs || []).map((r, i) => ({ ...r, '#': i + 1 })));
}

// ── Baterías ─────────────────────────────────────────────────────────────────
function renderBat(b) {
  const k = b.kpis || {};
  setText('b-total',   fmt(k.total_sesiones));
  setText('b-batdesc', fmt(k.bat_desconectadas));
  setText('b-pctbat',  (k.pct_bat_desc || 0) + ' %');
  setText('b-normal',  fmt(k.normal));
  setText('b-inactiv', fmt(k.inactividad));

  linea('b-bat-mes',   b.bat_desc_mes  || [], 'mes',  'total', 'Bat. Desc.', C1);
  barras('b-mes',      b.por_mes       || [], 'mes',  'total', 'Sesiones',  C2);
  barras('b-hora',     b.por_hora      || [], 'hora', 'total', 'Bat. Desc.', C1);
  barras('b-diasemana',b.por_dia_semana|| [], 'dia',  'total', 'Bat. Desc.', C1);

  barrasApagado('b-maquina',   b.apagado_maquina   || [], 'maquina');
  barrasApagado('b-conductor', b.apagado_conductor || [], 'conductor');

  ranking('b-ranking',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' },
     { key: 'bat_desc', label: 'Bat. Desc.' }, { key: 'pct_bat', label: '% Bat.' }],
    (b.ranking || []).map((r, i) => ({ ...r, '#': i + 1 })));
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
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' }, { key: 'bat_desc', label: 'Bat. Desc.' }],
    (b.ranking_bat_desc || []).map((r, i) => ({ ...r, '#': i + 1 })));

  ranking('rnk-claves',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' }, { key: 'claves', label: 'Claves' }],
    (u.claves_conductor || []).map((r, i) => ({ ...r, '#': i + 1 })));

  ranking('rnk-hrs',
    [{ key: '#', label: '#' }, { key: 'conductor', label: 'Conductor' }, { key: 'hrs_func', label: 'Hrs Util.' }],
    (u.ranking_hrs || []).map((r, i) => ({ ...r, '#': i + 1 })));
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function showTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.remove('hidden');
  btn.classList.add('active');

  if (name === 'rankings') {
    const tieneAll = lastData.golpes && lastData.util;
    if (moduloActual !== 'rankings') {
      moduloActual = 'rankings';
      if (tieneAll) renderRankings(lastData);
      else cargarModulo();
    }
    return;
  }

  const nuevoModulo = name;
  if (nuevoModulo !== moduloActual) {
    moduloActual = nuevoModulo;
    cargarModulo();
  }
}

// ── Chart helpers ─────────────────────────────────────────────────────────────
function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function donut(id, data, labelKey, valKey) {
  destroyChart(id);
  if (!data?.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'doughnut',
    data: {
      labels: data.map(d => d[labelKey]),
      datasets: [{ data: data.map(d => d[valKey]), backgroundColor: COLORS, borderWidth: 1 }]
    },
    options: {
      plugins: { legend: { position: 'right', labels: { boxWidth: 10, padding: 6 } } },
      cutout: '65%',
    }
  });
}

function linea(id, data, xKey, yKey, label, color = C1) {
  destroyChart(id);
  if (!data?.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'line',
    data: {
      labels: data.map(d => d[xKey]),
      datasets: [{ label, data: data.map(d => d[yKey]),
        borderColor: color, backgroundColor: color + '22',
        tension: 0.3, fill: true, pointRadius: 3 }]
    },
    options: {
      scales: { x: { grid: { color: '#1e1e1e' } }, y: { grid: { color: '#1e1e1e' }, beginAtZero: true } },
      plugins: { legend: { display: false } },
    }
  });
}

function lineaDoble(id, data, xKey, s1, s2) {
  destroyChart(id);
  if (!data?.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'line',
    data: {
      labels: data.map(d => d[xKey]),
      datasets: [
        { label: s1.label, data: data.map(d => d[s1.key] ?? 0),
          borderColor: s1.color, backgroundColor: s1.color + '22', tension: 0.3, fill: false, pointRadius: 3 },
        { label: s2.label, data: data.map(d => d[s2.key] ?? 0),
          borderColor: s2.color, backgroundColor: s2.color + '22', tension: 0.3, fill: false, pointRadius: 3 },
      ]
    },
    options: {
      scales: { x: { grid: { color: '#1e1e1e' } }, y: { grid: { color: '#1e1e1e' }, beginAtZero: true } },
      plugins: { legend: { position: 'top' } },
    }
  });
}

function barrasDoble(id, data, xKey, s1, s2) {
  destroyChart(id);
  if (!data?.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'bar',
    data: {
      labels: data.map(d => d[xKey]),
      datasets: [
        { label: s1.label, data: data.map(d => d[s1.key] ?? 0), backgroundColor: s1.color, borderRadius: 2 },
        { label: s2.label, data: data.map(d => d[s2.key] ?? 0), backgroundColor: s2.color, borderRadius: 2 },
      ]
    },
    options: {
      scales: { x: { grid: { color: '#1a1a1a' } }, y: { grid: { color: '#1e1e1e' }, beginAtZero: true } },
      plugins: { legend: { position: 'top' } },
    }
  });
}

function barras(id, data, xKey, yKey, label, color = C1) {
  destroyChart(id);
  if (!data?.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'bar',
    data: {
      labels: data.map(d => d[xKey]),
      datasets: [{ label, data: data.map(d => d[yKey]), backgroundColor: color, borderRadius: 2 }]
    },
    options: {
      scales: { x: { grid: { color: '#1a1a1a' } }, y: { grid: { color: '#1e1e1e' }, beginAtZero: true } },
      plugins: { legend: { display: false } },
    }
  });
}

function barrasHoriz(id, data, labelKey, valKey, label) {
  destroyChart(id);
  if (!data?.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'bar',
    data: {
      labels: data.map(d => d[labelKey]),
      datasets: [{ label, data: data.map(d => d[valKey]), backgroundColor: C1, borderRadius: 2 }]
    },
    options: {
      indexAxis: 'y',
      scales: { x: { grid: { color: '#1e1e1e' }, beginAtZero: true }, y: { grid: { display: false } } },
      plugins: { legend: { display: false } },
    }
  });
}

function barrasApagado(id, data, labelKey) {
  destroyChart(id);
  if (!data?.length) return;
  charts[id] = new Chart(document.getElementById(id), {
    type: 'bar',
    data: {
      labels: data.map(d => d[labelKey]),
      datasets: [
        { label: 'Bat. Desconectada', data: data.map(d => d.bat_desc   || 0), backgroundColor: C1, borderRadius: 2 },
        { label: 'Inactividad',       data: data.map(d => d.inactividad|| 0), backgroundColor: C3, borderRadius: 2 },
        { label: 'Normal',            data: data.map(d => d.normal     || 0), backgroundColor: C2, borderRadius: 2 },
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
  if (!el) return;
  if (!rows?.length) { el.innerHTML = '<p style="color:#555;font-size:11px;padding:8px">Sin datos</p>'; return; }
  const gridTpl = cols.map(c => c.key === '#' ? '32px' : c.key === 'conductor' ? '1fr' : '100px').join(' ');
  let html = `<div class="r-header" style="grid-template-columns:${gridTpl}">`;
  cols.forEach(c => html += `<span>${c.label}</span>`);
  html += '</div>';
  rows.forEach((r, i) => {
    const hi = i < 3 ? ` r-top${i+1}` : '';
    html += `<div class="r-row${hi}" style="grid-template-columns:${gridTpl}">`;
    cols.forEach(c => {
      const v = r[c.key] ?? '—';
      html += `<span>${typeof v === 'number' ? v.toLocaleString('es-CL') : v}</span>`;
    });
    html += '</div>';
  });
  el.innerHTML = html;
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function fmt(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('es-CL');
}
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
