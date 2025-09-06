function $(id) { return document.getElementById(id); }
function val(id) { return $(id).value.trim(); }

function setStatus(el, msg) { if (el) el.textContent = msg || ''; }

function formatRateLimit(info, fallbackStr) {
  if (!info) return fallbackStr || '';
  const rem = (info.remaining ?? '?');
  const used = (info.used ?? '?');
  const total = (info.total ?? (typeof rem === 'number' && typeof used === 'number' ? rem + used : '?'));
  const pct = info.pct_str || '?%';
  return `Remaining: ${rem}/${total} (${pct})`;
}

function updateRateLimitDisplays(payload) {
  const info = payload?.ratelimit_info;
  const str = formatRateLimit(info, payload?.ratelimit);
  setStatus($('rateLimit'), `RateLimit: ${str}`);
  setStatus($('rlHeader'), str);
}

async function fetchJSON(url) {
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
  const data = await res.json();
  return { ok: res.ok, status: res.status, data };
}

function apiUrl(path, params = {}) {
  const base = val('apiBase') || 'http://127.0.0.1:8000';
  const q = new URLSearchParams(params);
  return `${base}${path}?${q.toString()}`;
}

function renderLineup(containerId, title, payload) {
  const c = $(containerId);
  const rows = payload.lineup || [];
  const target = payload.target || 'mid';
  const total = payload.total_points ?? 0;
  const ratelimit = payload.ratelimit || '';
  let headerCols = '';
  let rowHtml = [];
  if (target === 'mid') {
    headerCols = '<th>Slot</th><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th>';
    rowHtml = rows.map(r => `<tr><td>${r.slot}</td><td>${r.name}</td><td>${r.pos}</td><td>${Number(r.floor).toFixed(2)}</td><td>${Number(r.mid).toFixed(2)}</td><td>${Number(r.ceiling).toFixed(2)}</td></tr>`);
  } else {
    headerCols = '<th>Slot</th><th>Name</th><th>Pos</th><th>Floor</th><th>Ceiling</th>';
    rowHtml = rows.map(r => `<tr><td>${r.slot}</td><td>${r.name}</td><td>${r.pos}</td><td>${Number(r.floor).toFixed(2)}</td><td>${Number(r.ceiling).toFixed(2)}</td></tr>`);
  }

  const table = [
    `<h3>${title} — target: ${target} (total: ${total.toFixed(2)})</h3>`,
    `<table><thead><tr>${headerCols}</tr></thead><tbody>`,
    ...rowHtml,
    '</tbody></table>',
    `<div class="status">RateLimit: ${ratelimit}</div>`
  ].join('\n');
  c.innerHTML = table;
}

function renderDefenses(containerId, payload) {
  const c = $(containerId);
  const rows = payload.defenses || [];
  const table = [
    '<table><thead><tr><th>Defense</th><th>Opponent</th><th>Game Date</th><th>Opp Implied</th><th># Books</th><th>Source</th></tr></thead><tbody>',
    ...rows.map(r => `<tr><td>${r.defense}</td><td>${r.opponent}</td><td>${r.game_date}</td><td>${Number(r.implied_total_median).toFixed(2)}</td><td>${r.book_count}</td><td>${r.source}</td></tr>`),
    '</tbody></table>',
    `<div class="status">RateLimit: ${payload.ratelimit || ''}</div>`
  ].join('\n');
  c.innerHTML = table;
}

async function loadLineup(week, target) {
  const url = apiUrl('/lineup', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week,
    target
  });
  console.debug('GET', url);
  const { ok, data } = await fetchJSON(url);
  if (!ok) return alert('Failed to load lineup');
  const containerId = week === 'this' ? 'lineup-this' : 'lineup-next';
  const title = week === 'this' ? 'This Week Lineup' : 'Next Week Lineup';
  renderLineup(containerId, title, data);
  updateRateLimitDisplays(data);
}

async function loadDefenses(week) {
  const url = apiUrl('/defenses', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week,
    scope: 'both'
  });
  console.debug('GET', url);
  const { ok, data } = await fetchJSON(url);
  if (!ok) return alert('Failed to load defenses');
  const containerId = week === 'this' ? 'defenses-this' : 'defenses-next';
  renderDefenses(containerId, data);
  updateRateLimitDisplays(data);
}

async function pingApi() {
  const url = apiUrl('/health');
  const { ok, data } = await fetchJSON(url);
  setStatus($('pingStatus'), ok ? 'API OK' : 'API Error');
  updateRateLimitDisplays(data || {});
}

async function dbgProjections(week) {
  const url = apiUrl('/projections', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week
  });
  const { ok, data } = await fetchJSON(url);
  if (!ok) return alert('Failed to load projections');
  $('projectionsDebug').textContent = JSON.stringify(data, null, 2);
  updateRateLimitDisplays(data);
}

// Wire handlers
document.addEventListener('DOMContentLoaded', () => {
  $('btnPing').addEventListener('click', pingApi);
  document.querySelectorAll('.btn-lineup').forEach(btn => {
    btn.addEventListener('click', () => loadLineup(btn.dataset.week, btn.dataset.target));
  });
  document.querySelectorAll('.btn-defenses').forEach(btn => {
    btn.addEventListener('click', () => loadDefenses(btn.dataset.week));
  });
  $('btnProjThis').addEventListener('click', () => dbgProjections('this'));
  $('btnProjNext').addEventListener('click', () => dbgProjections('next'));
  // Periodic update of health for active rate-limit counter
  setInterval(pingApi, 10000);
});
