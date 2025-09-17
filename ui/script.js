// Simple debug logger
const DEBUG = true; // toggle to enable/disable UI debug logs
function dbg(...args) { if (DEBUG && console && console.log) console.log('[ui]', ...args); }

function $(id) { return document.getElementById(id); }
function val(id) { return ($(id) ? $(id).value : '').trim(); }

// In-memory cache for preloaded data
const appCache = {
  lineups: { this: {}, next: {} },
  defenses: { this: null, next: null },
  projections: { this: null, next: null },
  lastRateLimit: null,
};
// Store raw players for local lineup building
appCache.lineupPlayers = { this: null, next: null };
const selectedTarget = { this: 'mid', next: 'mid' };

// Track network activity to drive header spinner
let _inflight = 0;
function _updateNetSpin() {
  const el = $('netSpin');
  if (!el) return;
  if (_inflight > 0) el.classList.remove('hidden'); else el.classList.add('hidden');
}
function _incNet() { _inflight++; _updateNetSpin(); }
function _decNet() { _inflight = Math.max(0, _inflight - 1); _updateNetSpin(); }

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

// Build lineup locally from projections
function computeLineupFromPlayers(players, target) {
  const buckets = { QB: [], RB: [], WR: [], TE: [] };
  for (const p of (players || [])) {
    if (buckets[p.pos]) buckets[p.pos].push(p);
  }
  const by = (t) => (a, b) => Number(b[t] || 0) - Number(a[t] || 0);
  Object.keys(buckets).forEach(pos => buckets[pos].sort(by(target)));
  const nameKey = (s) => String(s||'').toLowerCase().replace(/[\.'`-]/g,'').replace(/\s+/g,' ').trim();
  const used = new Set();
  const take = (pos, n) => {
    const out = [];
    for (const p of buckets[pos]) {
      const key = nameKey(p.name);
      if (!used.has(key)) { out.push(p); used.add(key); if (out.length === n) break; }
    }
    return out;
  };
  const starters = {
    QB: take('QB', 1),
    WR: take('WR', 2),
    RB: take('RB', 2),
    TE: take('TE', 1)
  };
  // FLEX best remaining WR/RB/TE
  const flexPool = [];
  for (const pos of ['WR','RB','TE']) {
    for (const p of buckets[pos]) { const key=nameKey(p.name); if (!used.has(key)) flexPool.push(p); }
  }
  flexPool.sort(by(target));
  const FLEX = flexPool.slice(0, 1);
  FLEX.forEach(p => used.add(nameKey(p.name)));

  // Compose rows in the required order: QB, WR, WR, RB, RB, TE, FLEX
  const rows = [];
  let total = 0;
  const add = (slot, p) => {
    const pts = Number(p[target] || 0);
    total += pts;
    rows.push({ slot, name: p.name, pos: p.pos, floor: Number(p.floor||0), mid: Number(p.mid||0), ceiling: Number(p.ceiling||0) });
  };
  starters.QB.forEach(p => add('QB', p));
  if (starters.WR[0]) add('WR', starters.WR[0]);
  if (starters.WR[1]) add('WR', starters.WR[1]);
  if (starters.RB[0]) add('RB', starters.RB[0]);
  if (starters.RB[1]) add('RB', starters.RB[1]);
  starters.TE.forEach(p => add('TE', p));
  FLEX.forEach(p => add('FLEX', p));

  // Bench: include everyone else, even zeros
  const bench = [];
  for (const pos of ['QB','WR','RB','TE']) {
    for (const p of buckets[pos]) { const key=nameKey(p.name); if (!used.has(key)) bench.push(p); }
  }
  bench.sort(by(target));
  bench.forEach(p => rows.push({ slot: 'BENCH', name: p.name, pos: p.pos, floor: Number(p.floor||0), mid: Number(p.mid||0), ceiling: Number(p.ceiling||0) }));
  return { target, lineup: rows, total_points: Number(total.toFixed(2)) };
}

function renderLineupFromPlayers(week) {
  const players = appCache.lineupPlayers[week] || [];
  const target = selectedTarget[week] || 'mid';
  const payload = computeLineupFromPlayers(players, target);
  const containerId = week === 'this' ? 'lineup-this' : 'lineup-next';
  const title = week === 'this' ? 'This Week Lineup' : 'Next Week Lineup';
  renderLineup(containerId, title, payload);
  addLineupControls(week, 'players', target);
  // Make headers clickable to switch target
  const c = document.getElementById(containerId);
  if (!c) return;
  c.querySelectorAll('th').forEach(th => {
    const txt = (th.textContent || '').toLowerCase();
    if (['floor','mid','ceiling'].some(k => txt.includes(k))) {
      th.style.cursor = 'pointer';
      th.onclick = () => {
        if (txt.includes('floor')) selectedTarget[week] = 'floor';
        else if (txt.includes('mid')) selectedTarget[week] = 'mid';
        else if (txt.includes('ceiling')) selectedTarget[week] = 'ceiling';
        renderLineupFromPlayers(week);
      };
    }
  });
}

async function showLineup(week) {
  if (!appCache.lineupPlayers[week]) {
    const containerId = week === 'this' ? 'lineup-this' : 'lineup-next';
    showContainerLoading(containerId, 'Loading lineup...');
    const mode = getDataMode();
  const url = apiUrl('/projections', { username: val('username') || 'wesnicol', season: val('season') || '2025', week, mode, model: getModel() });
    const { ok, data } = await fetchJSON(url);
    if (!ok) { document.getElementById(containerId).innerHTML = '<div class=\"status\">Failed to load lineup.</div>'; return; }
    appCache.lineupPlayers[week] = data.players || [];
    appCache.lastRateLimit = data;
    selectedTarget[week] = 'mid';
  }
  renderLineupFromPlayers(week);
  updateRateLimitDisplays(appCache.lastRateLimit || {});
}

// UI loading helpers
function disableAllButtons(disabled) {
  document.querySelectorAll('button').forEach(btn => { btn.disabled = !!disabled; });
}
function showGlobalLoading(msg) {
  const overlay = $('globalLoading');
  if (!overlay) return;
  const txt = $('globalLoadingText');
  if (txt) txt.textContent = msg || 'Loading...';
  overlay.classList.remove('hidden');
}
function hideGlobalLoading() {
  const overlay = $('globalLoading');
  if (!overlay) return;
  overlay.classList.add('hidden');
}
function showContainerLoading(containerId, msg) {
  const c = $(containerId);
  if (!c) return;
  c.innerHTML = `<div class="status"><md-circular-progress indeterminate aria-label="Loading"></md-circular-progress> ${msg || 'Loading...'}</div>`;
}

async function fetchJSON(url) {
  const t0 = performance.now();
  dbg('fetchJSON:start', url);
  _incNet();
  const res = await fetch(url, { headers: { 'Accept': 'application/json' } });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch (e) { data = { _parse_error: true, raw: text }; }
  const dt = (performance.now() - t0).toFixed(1);
  dbg('fetchJSON:done', { url, status: res.status, ok: res.ok, ms: dt, bytes: text?.length || 0 });
  _decNet();
  return { ok: res.ok, status: res.status, data };
}

function apiUrl(path, params = {}) {
  const base = val('apiBase') || 'http://127.0.0.1:8000';
  const q = new URLSearchParams(params);
  return `${base}${path}?${q.toString()}`;
}

function getDataMode() {
  const el = document.querySelector('md-radio[name="dataMode"][checked]') || document.querySelector('input[name="dataMode"]:checked');
  if (!el) return 'auto';
  return el.value || el.getAttribute('value') || 'auto';
}

function getModel() {
  const elFloat = document.getElementById('modelSelectFloating');
  if (elFloat && elFloat.value) return elFloat.value;
  const el = document.getElementById('modelSelect');
  return (el && el.value) ? el.value : 'const';
}


function renderLineup(containerId, title, payload) {
  const c = $(containerId);
  const rows = payload?.lineup || [];
  const target = payload?.target || 'mid';
  const total = Number(payload?.total_points ?? 0);
  const ratelimit = payload?.ratelimit || '';
  dbg('renderLineup', { containerId, title, count: rows.length, target, total });
  const headerCols = '<th>Slot</th><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th>';
  const rowHtml = rows.map(r => `
    <tr>
      <td>${r.slot}</td>
      <td><span class="player-name" data-player="${r.name}" title="Open details" style="cursor:pointer; text-decoration:underline;">${r.name}</span></td>
      <td>${r.pos}</td>
      <td>${Number(r.floor).toFixed(2)}</td>
      <td>${Number(r.mid).toFixed(2)}</td>
      <td>${Number(r.ceiling).toFixed(2)}</td>
    </tr>`);
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
  dbg('renderDefenses', { containerId, count: (payload.defenses||[]).length });
  const rows = payload.defenses || [];
  if (!rows.length) {
    c.innerHTML = '<div class="status">No defenses found for this week.</div>';
    return;
  }
  // Ensure sorted by opponent implied total ascending (server already sorts, but keep safe)
  rows.sort((a, b) => (Number(a.implied_total_median) - Number(b.implied_total_median)) || (Number(b.book_count) - Number(a.book_count)));
  const table = [
    '<table><thead><tr><th>Defense</th><th>Owner</th><th>Opponent</th><th>Game Date</th><th>Opp Implied</th><th># Books</th><th>Source</th></tr></thead><tbody>',
    ...rows.map(r => {
      const owner = r.owner ? String(r.owner) : '';
      const mine = !!r.owned_by_current;
      const taken = !!(r.owner);
      const cls = mine ? 'def-row def-mine' : (taken ? 'def-row def-taken' : 'def-row def-available');
      return `<tr class="${cls}"><td>${r.defense}</td><td>${owner || '-'}</td><td>${r.opponent}</td><td>${r.game_date}</td><td>${Number(r.implied_total_median).toFixed(2)}</td><td>${r.book_count}</td><td>${r.source}</td></tr>`;
    }),
    '</tbody></table>',
    `<div class="status">RateLimit: ${payload.ratelimit || ''}</div>`
  ].join('\n');
  c.innerHTML = table;
}

async function loadLineup(week, target) {
  // Use cached data preloaded on refresh
  const cached = appCache.lineups?.[week]?.[target];
  const containerId = week === 'this' ? 'lineup-this' : 'lineup-next';
  const title = week === 'this' ? 'This Week Lineup' : 'Next Week Lineup';
  if (!cached) {
    dbg('loadLineup:no-cache', { week, target });
    showContainerLoading(containerId, 'Loading lineup...');
  const mode = getDataMode();
  const url = apiUrl('/lineup', { username: val('username') || 'wesnicol', season: val('season') || '2025', week, target, mode, model: getModel() });
    const { ok, data } = await fetchJSON(url);
    if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load lineup.</div>'; return; }
    appCache.lineups[week] = appCache.lineups[week] || {};
    appCache.lineups[week][target] = data;
    renderLineup(containerId, title, data);
    updateRateLimitDisplays(data);
    return;
  }
  renderLineup(containerId, title, cached);
  addLineupControls(week, 'api', target);
  updateRateLimitDisplays(appCache.lastRateLimit || cached);
}

function renderPlayers(containerId, players) {
  const c = $(containerId);
  const rows = Array.isArray(players) ? players.slice() : [];
  if (!rows.length) {
    c.innerHTML = '<div class="status">No players found.</div>';
    return;
  }
  // Sort by mid descending
  rows.sort((a, b) => Number(b.mid || 0) - Number(a.mid || 0));
  const table = [
    '<table><thead><tr><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th></tr></thead><tbody>',
    ...rows.map(r => `<tr><td><span class="player-name" data-player="${r.name}" title="Open details" style="cursor:pointer; text-decoration:underline;">${r.name}</span></td><td>${r.pos}</td><td>${Number(r.floor).toFixed(2)}</td><td>${Number(r.mid).toFixed(2)}</td><td>${Number(r.ceiling).toFixed(2)}</td></tr>`),
    '</tbody></table>'
  ].join('\n');
  c.innerHTML = table;
}

// Inject lineup controls (Refresh, Close) into container
function addLineupControls(week, source, target) {
  try {
    const containerId = week === 'this' ? 'lineup-this' : 'lineup-next';
    const c = $(containerId);
    if (!c) return;
    // Remove existing controls to avoid duplicates
    const old = c.querySelector('.lineup-controls');
    if (old && old.parentNode) old.parentNode.removeChild(old);
    const controls = document.createElement('div');
    controls.className = 'btn-row lineup-controls';
    controls.innerHTML = `
      <button onclick="window._refreshLineup('${week}','${target||'mid'}','${source||'api'}')">Refresh</button>
      <button onclick="window._closeLineup('${week}')">Close</button>
    `;
    c.insertAdjacentElement('afterbegin', controls);
  } catch (e) {
    console.error('[ui] addLineupControls:error', e);
  }
}

// Global helpers used by controls
window._closeLineup = function(week) {
  const id = (week === 'this' ? 'lineup-this' : 'lineup-next');
  const el = $(id);
  if (el) el.innerHTML = '';
};

window._refreshLineup = async function(week, target, source) {
  try {
    if (source === 'players') {
      // Force re-fetch projections and re-render local lineup
      appCache.lineupPlayers[week] = null;
      await showLineup(week);
    } else {
      // Force re-fetch lineup from API by clearing cache
      if (appCache.lineups[week]) delete appCache.lineups[week][target||'mid'];
      await loadLineup(week, target||'mid');
    }
  } catch (e) {
    console.error('[ui] _refreshLineup:error', e);
  }
};

async function showPlayers(week) {
  const cached = appCache.projections?.[week];
  const containerId = week === 'this' ? 'players-this' : 'players-next';
  if (!cached) {
    dbg('showPlayers:no-cache', { week });
    showContainerLoading(containerId, 'Loading players...');
  const mode = getDataMode();
  const url = apiUrl('/projections', { username: val('username') || 'wesnicol', season: val('season') || '2025', week, mode, model: getModel() });
    const { ok, data } = await fetchJSON(url);
    if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load players.</div>'; return; }
    appCache.projections[week] = data;
    renderPlayers(containerId, data.players || []);
    updateRateLimitDisplays(data);
    return;
  }
  renderPlayers(containerId, cached.players || []);
  updateRateLimitDisplays(appCache.lastRateLimit || {});
}

async function loadDefenses(week) {
  const cached = appCache.defenses?.[week];
  const containerId = week === 'this' ? 'defenses-this' : 'defenses-next';
  if (!cached) {
    dbg('loadDefenses:no-cache', { week });
    showContainerLoading(containerId, 'Loading defenses...');
  const mode = getDataMode();
  const url = apiUrl('/defenses', { username: val('username') || 'wesnicol', season: val('season') || '2025', week, scope: 'both', mode });
    const { ok, data } = await fetchJSON(url);
    if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load defenses.</div>'; return; }
    appCache.defenses[week] = data;
    renderDefenses(containerId, data);
    updateRateLimitDisplays(data);
    return;
  }
  renderDefenses(containerId, cached);
  updateRateLimitDisplays(appCache.lastRateLimit || cached);
}

async function refreshAll() {
  const username = val('username') || 'wesnicol';
  const season = val('season') || '2025';
  const mode = getDataMode();
  const url = apiUrl('/dashboard', { username, season, mode, weeks: 'this', def_scope: 'owned', include_players: '1', model: getModel() });
  dbg('refreshAll:start', { url, username, season });
  setStatus($('pingStatus'), 'Refreshing...');
  showGlobalLoading('Refreshing dashboard...');
  disableAllButtons(true);
  try {
    const { ok, data } = await fetchJSON(url);
    if (!ok) throw new Error('Request failed: ' + url);
    // Populate cache
    appCache.lineups.this.mid = data?.lineups?.this?.mid || null;
    appCache.lineups.this.floor = data?.lineups?.this?.floor || null;
    appCache.lineups.this.ceiling = data?.lineups?.this?.ceiling || null;
    appCache.lineups.next.mid = data?.lineups?.next?.mid || null;
    appCache.lineups.next.floor = data?.lineups?.next?.floor || null;
    appCache.lineups.next.ceiling = data?.lineups?.next?.ceiling || null;
    appCache.defenses.this = data?.defenses?.this || null;
    appCache.defenses.next = data?.defenses?.next || null;
    appCache.projections.this = data?.projections?.this || null;
    appCache.projections.next = data?.projections?.next || null;
    appCache.lastRateLimit = data;
    setStatus($('pingStatus'), 'Ready');
    dbg('refreshAll:cache-filled', {
      lineups_this: Object.keys(appCache.lineups.this).length,
      lineups_next: Object.keys(appCache.lineups.next).length,
      defenses_this: !!appCache.defenses.this,
      defenses_next: !!appCache.defenses.next,
      players_this: (data?.projections?.this?.players || []).length,
      players_next: (data?.projections?.next?.players || []).length,
    });
    // Render defaults
    loadLineup('this', 'mid');
    loadDefenses('this');
  } catch (e) {
    console.error('[ui] refreshAll:error', e);
    alert('Refresh failed. Check API base URL and server.');
    setStatus($('pingStatus'), 'Error');
  } finally {
    hideGlobalLoading();
    disableAllButtons(false);
  }
}

async function dbgProjections(week) {
  const url = apiUrl('/projections', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week,
    mode: getDataMode(),
    model: getModel()
  });
  showContainerLoading('projectionsDebug', 'Loading projections...');
  const { ok, data } = await fetchJSON(url);
  if (!ok) { dbg('dbgProjections:fail', { week, url }); return alert('Failed to load projections'); }
  $('projectionsDebug').textContent = JSON.stringify(data, null, 2);
  updateRateLimitDisplays(data);
}

// Wire handlers
document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  // Help (More Info) overlay wiring
  try {
    const btnHelp = document.getElementById('btnHelp');
    const help = document.getElementById('helpOverlay');
    const helpClose = document.getElementById('helpClose');
    if (btnHelp && help) {
      btnHelp.addEventListener('click', () => { try { help.classList.remove('hidden'); } catch (e) {} });
    }
    if (helpClose && help) {
      helpClose.addEventListener('click', () => { try { help.classList.add('hidden'); } catch (e) {} });
    }
  } catch (e) { /* ignore */ }
  attachSettingsListeners();
  try { const v = getModel(); const ms = document.getElementById('modelSelect'); const mf = document.getElementById('modelSelectFloating'); if (ms) ms.value = v; if (mf) mf.value = v; } catch (e) {}
  
  // Removed: legacy number-only lineup view button
  document.querySelectorAll('.btn-defenses').forEach(btn => {
    btn.addEventListener('click', () => loadDefenses(btn.dataset.week));
  });
  document.querySelectorAll('.btn-compare-curves').forEach(btn => {
    btn.addEventListener('click', () => {
      try { if (typeof openCompareCurves === 'function') openCompareCurves(btn.dataset.week || 'this'); } catch (e) { console.error(e); }
    });
  });
  document.querySelectorAll('.btn-players').forEach(btn => {
    btn.addEventListener('click', () => showPlayers(btn.dataset.week));
  });
  if (btnProjThis) btnProjThis.addEventListener('click', () => dbgProjections('this'));
  if (btnProjNext) btnProjNext.addEventListener('click', () => dbgProjections('next'));
  dbg('DOMContentLoaded');
  // Click 'Refresh' to load dashboard data when you want to fetch.
  // Global error surfacing for visibility
  window.addEventListener('error', (e) => {
    console.error('[ui] window.error', e?.error || e?.message || e);
  });
  window.addEventListener('unhandledrejection', (e) => {
    console.error('[ui] unhandledrejection', e?.reason || e);
  });
});





// Persist basic settings in localStorage
function saveSettings() {
  try {
    const data = {
      apiBase: ($('apiBase')||{}).value || '',
      username: ($('username')||{}).value || '',
      season: ($('season')||{}).value || '',
      dataMode: (document.querySelector('input[name="dataMode"]:checked')||{}).value || 'auto',
      model: getModel() || 'const',
    };
    localStorage.setItem('ofdash.settings', JSON.stringify(data));
  } catch (e) { /* ignore */ }
}

function loadSettings() {
  try {
    const raw = localStorage.getItem('ofdash.settings');
    if (!raw) return;
    const s = JSON.parse(raw);
    if (s.apiBase && $('apiBase')) $('apiBase').value = s.apiBase;
    if (s.username && $('username')) $('username').value = s.username;
    if (s.season && $('season')) $('season').value = s.season;
    if (s.dataMode) {
      const radio = document.querySelector('input[name="dataMode"][value="'+s.dataMode+'"]');
      if (radio) radio.checked = true;
    }
    if (s.model) {
      const ms = document.getElementById('modelSelect'); if (ms) ms.value = s.model;
      const mf = document.getElementById('modelSelectFloating'); if (mf) mf.value = s.model;
    }
  } catch (e) { /* ignore */ }
}

function attachSettingsListeners() {
  ['apiBase','username','season'].forEach(id => { const el=$(id); if (el) el.addEventListener('change', saveSettings); });
  document.querySelectorAll('input[name="dataMode"]').forEach(r => r.addEventListener('change', saveSettings));
  const ms = document.getElementById('modelSelect'); if (ms) ms.addEventListener('change', () => { try { const mf = document.getElementById('modelSelectFloating'); if (mf) mf.value = ms.value; saveSettings(); refreshAll(); } catch (e) {} });
  const mf = document.getElementById('modelSelectFloating'); if (mf) mf.addEventListener('change', () => { try { const ms2 = document.getElementById('modelSelect'); if (ms2) ms2.value = mf.value; saveSettings(); refreshAll(); } catch (e) {} });
}

// Enable simple table sorting on click
function enableTableSort(table) {
  try {
    if (!table) return;
    const ths = table.querySelectorAll('thead th');
    ths.forEach((th, colIdx) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const tbody = table.querySelector('tbody');
        const rows = Array.from(tbody.querySelectorAll('tr'));
        const dir = (th.getAttribute('data-sort') === 'asc') ? 'desc' : 'asc';
        ths.forEach(h => h.removeAttribute('data-sort'));
        th.setAttribute('data-sort', dir);
        const isNumCol = (colIdx >= 3); // Floor/Mid/Ceiling typically numeric
        rows.sort((a,b) => {
          const av = (a.cells[colIdx] && a.cells[colIdx].textContent || '').trim();
          const bv = (b.cells[colIdx] && b.cells[colIdx].textContent || '').trim();
          const aN = parseFloat(av); const bN = parseFloat(bv);
          let cmp;
          if (isNumCol && !Number.isNaN(aN) && !Number.isNaN(bN)) cmp = aN - bN; else cmp = av.localeCompare(bv);
          return dir === 'asc' ? cmp : -cmp;
        });
        rows.forEach(r => tbody.appendChild(r));
      });
    });
  } catch (e) { /* ignore */ }
}


