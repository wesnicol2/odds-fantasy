function $(id) { return document.getElementById(id); }
function val(id) { return $(id).value.trim(); }

// In-memory cache for preloaded data
const appCache = {
  lineups: { this: {}, next: {} },
  defenses: { this: null, next: null },
  lastRateLimit: null,
};

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
  if (!rows.length) {
    c.innerHTML = '<div class="status">No defenses found for this week.</div>';
    return;
  }
  const table = [
    '<table><thead><tr><th>Defense</th><th>Opponent</th><th>Game Date</th><th>Opp Implied</th><th># Books</th><th>Source</th></tr></thead><tbody>',
    ...rows.map(r => `<tr><td>${r.defense}</td><td>${r.opponent}</td><td>${r.game_date}</td><td>${Number(r.implied_total_median).toFixed(2)}</td><td>${r.book_count}</td><td>${r.source}</td></tr>`),
    '</tbody></table>',
    `<div class="status">RateLimit: ${payload.ratelimit || ''}</div>`
  ].join('\n');
  c.innerHTML = table;
}

async function loadLineup(week, target) {
  // Use cached data preloaded on refresh
  const data = appCache.lineups?.[week]?.[target];
  if (!data) return alert('Please click Refresh first.');
  const containerId = week === 'this' ? 'lineup-this' : 'lineup-next';
  const title = week === 'this' ? 'This Week Lineup' : 'Next Week Lineup';
  renderLineup(containerId, title, data);
  updateRateLimitDisplays(appCache.lastRateLimit || data);
}

async function loadDefenses(week) {
  const data = appCache.defenses?.[week];
  if (!data) return alert('Please click Refresh first.');
  const containerId = week === 'this' ? 'defenses-this' : 'defenses-next';
  renderDefenses(containerId, data);
  updateRateLimitDisplays(appCache.lastRateLimit || data);
}

async function refreshAll() {
  const username = val('username') || 'wesnicol';
  const season = val('season') || '2025';

  const reqs = [];
  const pushReq = (keyPath, url) => {
    reqs.push(
      fetchJSON(url).then(({ ok, data }) => {
        if (!ok) throw new Error('Request failed: ' + url);
        // Store data into cache by keyPath
        let ref = appCache;
        for (let i = 0; i < keyPath.length - 1; i++) {
          const k = keyPath[i];
          ref[k] = ref[k] || {};
          ref = ref[k];
        }
        ref[keyPath[keyPath.length - 1]] = data;
        appCache.lastRateLimit = data;
      })
    );
  };

  // Preload lineups for both weeks and all targets
  [ 'this', 'next' ].forEach(week => {
    [ 'mid', 'floor', 'ceiling' ].forEach(target => {
      const url = apiUrl('/lineup', { username, season, week, target });
      pushReq(['lineups', week, target], url);
    });
  });

  // Preload defenses (owned + available)
  [ 'this', 'next' ].forEach(week => {
    const url = apiUrl('/defenses', { username, season, week, scope: 'both' });
    pushReq(['defenses', week], url);
  });

  setStatus($('pingStatus'), 'Refreshing...');
  try {
    await Promise.all(reqs);
    setStatus($('pingStatus'), 'Ready');
    // Render defaults: This week mid lineup + this week defenses
    loadLineup('this', 'mid');
    loadDefenses('this');
  } catch (e) {
    console.error(e);
    alert('Refresh failed. Check API base URL and server.');
    setStatus($('pingStatus'), 'Error');
  }
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
  $('btnRefresh').addEventListener('click', refreshAll);
  document.querySelectorAll('.btn-lineup').forEach(btn => {
    btn.addEventListener('click', () => loadLineup(btn.dataset.week, btn.dataset.target));
  });
  document.querySelectorAll('.btn-defenses').forEach(btn => {
    btn.addEventListener('click', () => loadDefenses(btn.dataset.week));
  });
  $('btnProjThis').addEventListener('click', () => dbgProjections('this'));
  $('btnProjNext').addEventListener('click', () => dbgProjections('next'));
  // Auto refresh on load
  refreshAll();
});
