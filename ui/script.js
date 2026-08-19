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
  draftBoard: { this: null, next: null },
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

// --- League/team identity -----------------------------------------------
// Cookies (not localStorage) per the requested design: league_id/roster_id
// need to survive across the league-setup modal and be readable by every
// fetch call site without threading extra state through. `identityParams()`
// is the single place that decides identity for a request: league_id +
// roster_id (explicit, unambiguous) win over username/season (legacy
// fallback -- and username-based Sleeper lookup silently picks "your first
// league" for that username, which is wrong for anyone in more than one).
function setCookie(name, value, days) {
  const maxAge = days ? `; max-age=${days * 24 * 60 * 60}` : '';
  document.cookie = `${name}=${encodeURIComponent(value)}${maxAge}; path=/; SameSite=Lax`;
}
function getCookie(name) {
  const escaped = name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1');
  const match = document.cookie.match(new RegExp('(?:^|; )' + escaped + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}
function deleteCookie(name) {
  document.cookie = `${name}=; path=/; max-age=0`;
}
function identityParams() {
  const leagueId = getCookie('league_id');
  const rosterId = getCookie('roster_id');
  if (leagueId && rosterId) return { league_id: leagueId, roster_id: rosterId };
  return { username: val('username') || 'wesnicol', season: val('season') || '2025' };
}

// League setup, 3 steps: enter Sleeper username (cookie'd) -> pick which of
// your leagues (its league_id gets cookie'd) -> pick your team in it
// (roster_id cookie'd). The league's own Sleeper `status` then decides
// whether to default to the draft board (pre_draft/drafting) or the weekly
// lineup view (in_season/complete/anything else). Username here is only
// ever used to list leagues to choose from -- once a league_id is picked,
// everything downstream is keyed off league_id+roster_id, not username.
const PRE_DRAFT_STATUSES = ['pre_draft', 'drafting'];

function currentNflSeason() {
  // Mirrors config.current_nfl_season() in Python: Sleeper labels a league
  // by the year its season starts, and Jan/Feb still belongs to last season.
  const now = new Date();
  const y = now.getUTCFullYear();
  return String((now.getUTCMonth() + 1) >= 3 ? y : y - 1);
}

function _openLeagueOverlay() {
  $('leagueSetupOverlay').classList.remove('hidden');
}

function hideLeagueSetupModal() {
  $('leagueSetupOverlay').classList.add('hidden');
}

function showLeagueSetupModal() {
  _openLeagueOverlay();
  $('leagueStepUser').classList.remove('hidden');
  $('leagueStepLeague').classList.add('hidden');
  $('leagueStepTeam').classList.add('hidden');
  $('leagueUserError').textContent = '';
  const existingUser = getCookie('sleeper_username');
  if (existingUser) $('leagueUsernameInput').value = existingUser;
  const seasonInput = $('leagueSeasonInput');
  if (seasonInput && !seasonInput.value) seasonInput.value = currentNflSeason();
}

async function submitUsername() {
  const username = ($('leagueUsernameInput').value || '').trim();
  const season = ($('leagueSeasonInput').value || '').trim() || currentNflSeason();
  const errEl = $('leagueUserError');
  errEl.textContent = '';
  if (!username) { errEl.textContent = 'Please enter your Sleeper username.'; return; }
  errEl.textContent = 'Looking up leagues...';
  const { ok, data } = await fetchJSON(apiUrl('/user/leagues', { username, season }));
  if (!ok || data.error) {
    errEl.textContent = "Couldn't find that Sleeper username -- double check the spelling.";
    return;
  }
  if (!data.leagues || !data.leagues.length) {
    errEl.textContent = `No leagues found for "${username}" in ${season}. Try a different season above.`;
    return;
  }
  errEl.textContent = '';
  setCookie('sleeper_username', username, 365);
  populateLeaguePicker(data);
}

function populateLeaguePicker(leaguesData) {
  _openLeagueOverlay();
  $('leagueStepUser').classList.add('hidden');
  $('leagueStepLeague').classList.remove('hidden');
  $('leagueStepTeam').classList.add('hidden');
  $('leagueLeagueError').textContent = '';
  $('leagueLeaguePrompt').textContent = `Which league, ${leaguesData.username}?`;
  const sel = $('leagueLeagueSelect');
  const leagues = leaguesData.leagues || [];
  sel.innerHTML = '<option value="">-- Select a league --</option>' +
    leagues.map(l => `<option value="${l.league_id}">${(l.name || l.league_id)} (${l.status || 'unknown status'})</option>`).join('');
  const existingLeague = getCookie('league_id');
  if (existingLeague && leagues.some(l => String(l.league_id) === String(existingLeague))) {
    sel.value = existingLeague;
  }
}

async function submitLeaguePick() {
  const sel = $('leagueLeagueSelect');
  const errEl = $('leagueLeagueError');
  errEl.textContent = '';
  if (!sel.value) { errEl.textContent = 'Please pick a league.'; return; }
  errEl.textContent = 'Loading teams...';
  const { ok, data } = await fetchJSON(apiUrl('/league/resolve', { league_id: sel.value }));
  if (!ok || data.error) { errEl.textContent = 'Failed to load that league. Try again.'; return; }
  errEl.textContent = '';
  setCookie('league_id', sel.value, 365);
  populateTeamPicker(data);
}

function populateTeamPicker(leagueData) {
  _openLeagueOverlay();
  $('leagueStepUser').classList.add('hidden');
  $('leagueStepLeague').classList.add('hidden');
  $('leagueStepTeam').classList.remove('hidden');
  $('leagueTeamError').textContent = '';
  $('leagueTeamPrompt').textContent = `Which team is yours in "${leagueData.name || 'this league'}"?`;
  const sel = $('leagueTeamSelect');
  const teams = leagueData.teams || [];
  sel.innerHTML = '<option value="">-- Select your team --</option>' +
    teams.map(t => `<option value="${t.roster_id}">${(t.team_name || ('Team ' + t.roster_id))}</option>`).join('');
  const existingRoster = getCookie('roster_id');
  if (existingRoster && teams.some(t => String(t.roster_id) === String(existingRoster))) {
    sel.value = existingRoster;
  }
}

function submitTeamPick() {
  const sel = $('leagueTeamSelect');
  if (!sel.value) { $('leagueTeamError').textContent = 'Please pick your team.'; return; }
  setCookie('roster_id', sel.value, 365);
  hideLeagueSetupModal();
  applyResolvedLeagueModeAndRefresh(getCookie('league_id'));
}

function updateLeagueIndicator(leagueData) {
  const el = $('leagueIndicator');
  if (!el) return;
  const rosterId = getCookie('roster_id');
  const team = (leagueData.teams || []).find(t => String(t.roster_id) === String(rosterId));
  const statusLabel = PRE_DRAFT_STATUSES.includes(leagueData.status) ? 'pre-draft' : (leagueData.status || '');
  el.textContent = `League: ${leagueData.name || leagueData.league_id} | Team: ${team ? team.team_name : '?'} | ${statusLabel}`;
  el.classList.remove('hidden');
}

async function applyResolvedLeagueModeAndRefresh(leagueId) {
  const { ok, data } = await fetchJSON(apiUrl('/league/resolve', { league_id: leagueId }));
  if (!ok || data.error) {
    // Stale/broken cookie (e.g. league deleted) -- restart setup from scratch.
    deleteCookie('league_id');
    deleteCookie('roster_id');
    showLeagueSetupModal();
    return;
  }
  updateLeagueIndicator(data);
  const preSeason = PRE_DRAFT_STATUSES.includes(data.status);
  dbg('applyResolvedLeagueModeAndRefresh', { status: data.status, preSeason });
  if (preSeason) {
    const draftSection = $('draft-board');
    if (draftSection) draftSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showDraftBoard('this');
  } else {
    refreshAll();
  }
}

async function initLeagueFlow() {
  const leagueId = getCookie('league_id');
  if (!leagueId) {
    // No league picked yet. If we already know the username (e.g. picked a
    // league before but never finished team selection, or cleared just the
    // league_id cookie), skip straight to the league list instead of
    // asking for the username again.
    const savedUsername = getCookie('sleeper_username');
    if (savedUsername) {
      const { ok, data } = await fetchJSON(apiUrl('/user/leagues', { username: savedUsername, season: currentNflSeason() }));
      if (ok && !data.error && data.leagues && data.leagues.length) {
        populateLeaguePicker(data);
        return;
      }
    }
    showLeagueSetupModal();
    return;
  }
  const rosterId = getCookie('roster_id');
  if (!rosterId) {
    // League already known but no team picked yet -- resume at the team
    // step instead of starting over.
    const { ok, data } = await fetchJSON(apiUrl('/league/resolve', { league_id: leagueId }));
    if (!ok || data.error) { deleteCookie('league_id'); showLeagueSetupModal(); return; }
    populateTeamPicker(data);
    return;
  }
  await applyResolvedLeagueModeAndRefresh(leagueId);
}

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
  const targetKey = target || 'mid';
  const by = (t) => (a, b) => Number(b[t] || 0) - Number(a[t] || 0);
  Object.keys(buckets).forEach(pos => buckets[pos].sort(by(targetKey)));
  const nameKey = (s) => String(s || '').toLowerCase().replace(/[\.'`-]/g, '').replace(/\s+/g, ' ').trim();
  const used = new Set();
  const claimFrom = (pos) => {
    const pool = buckets[pos] || [];
    for (const player of pool) {
      const key = nameKey(player.name);
      if (!used.has(key)) {
        used.add(key);
        return player;
      }
    }
    return null;
  };
  const lineup = [];
  let total = 0;
  const addRow = (slot, player) => {
    if (!player) return;
    total += Number(player[targetKey] || 0);
    lineup.push({
      slot,
      name: player.name,
      pos: player.pos,
      floor: Number(player.floor || 0),
      mid: Number(player.mid || 0),
      ceiling: Number(player.ceiling || 0)
    });
  };
  addRow('QB', claimFrom('QB'));
  addRow('RB1', claimFrom('RB'));
  addRow('RB2', claimFrom('RB'));
  addRow('WR1', claimFrom('WR'));
  addRow('WR2', claimFrom('WR'));
  addRow('TE1', claimFrom('TE'));
  const flexCandidate = (() => {
    let best = null;
    for (const pos of ['WR', 'RB', 'TE']) {
      const pool = buckets[pos] || [];
      for (const player of pool) {
        const key = nameKey(player.name);
        if (used.has(key)) continue;
        if (!best || Number(player[targetKey] || 0) > Number(best[targetKey] || 0)) {
          best = player;
        }
      }
    }
    if (best) used.add(nameKey(best.name));
    return best;
  })();
  addRow('FLEX', flexCandidate);
  const bench = [];
  for (const player of (players || [])) {
    const key = nameKey(player.name);
    if (!used.has(key)) bench.push(player);
  }
  bench.sort(by(targetKey));
  bench.forEach(player => {
    lineup.push({
      slot: 'BENCH',
      name: player.name,
      pos: player.pos,
      floor: Number(player.floor || 0),
      mid: Number(player.mid || 0),
      ceiling: Number(player.ceiling || 0)
    });
  });
  return { target: targetKey, lineup, total_points: Number(total.toFixed(2)) };
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
  const url = apiUrl('/projections', { ...identityParams(), week, mode, model: getModel() });
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
  const q = new URLSearchParams(params);
  const query = q.toString();
  return `${path}${query ? `?${query}` : ''}`;
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
  const url = apiUrl('/lineup', { ...identityParams(), week, target, mode, model: getModel() });
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
  const url = apiUrl('/projections', { ...identityParams(), week, mode, model: getModel() });
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

function _renderDraftBoard(containerId, data) {
  // "Week 1"/"Week 2" are schedule-anchored (earliest games in the odds
  // feed), not tied to today's date -- always show the resolved date range
  // (or the "nothing scheduled yet" message) so it's never ambiguous what's
  // actually loaded. renderPlayers() owns the table itself; this just adds
  // a header in front of it.
  renderPlayers(containerId, data.players || []);
  const c = $(containerId);
  if (!c) return;
  let header = '';
  if (data.message) {
    header = `<div class="status draft-board-note">${data.message}</div>`;
  } else if (data.window_start && data.window_end) {
    const fmt = (iso) => {
      try { return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }); }
      catch (e) { return iso; }
    };
    header = `<div class="status draft-board-note">Games: ${fmt(data.window_start)} – ${fmt(data.window_end)}</div>`;
  }
  if (header) c.insertAdjacentHTML('afterbegin', header);
}

async function showDraftBoard(week) {
  // Intentionally not scoped to any roster -- see /draft-board in the API
  // and CONTRIBUTING.md's "Odds API quota awareness" section. Only fetched
  // on click, and cached per-week client-side so re-toggling doesn't
  // re-hit the API.
  const cached = appCache.draftBoard?.[week];
  const containerId = 'draft-board';
  if (!cached) {
    dbg('showDraftBoard:no-cache', { week });
    showContainerLoading(containerId, 'Loading draft board (this can take a bit -- it covers every team playing this week)...');
    const mode = getDataMode();
    const url = apiUrl('/draft-board', { ...identityParams(), week, mode, model: getModel() });
    const { ok, data } = await fetchJSON(url);
    if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load draft board.</div>'; return; }
    appCache.draftBoard[week] = data;
    _renderDraftBoard(containerId, data);
    updateRateLimitDisplays(data);
    return;
  }
  _renderDraftBoard(containerId, cached);
  updateRateLimitDisplays(appCache.lastRateLimit || {});
}

async function loadDefenses(week) {
  const cached = appCache.defenses?.[week];
  const containerId = week === 'this' ? 'defenses-this' : 'defenses-next';
  if (!cached) {
    dbg('loadDefenses:no-cache', { week });
    showContainerLoading(containerId, 'Loading defenses...');
  const mode = getDataMode();
  const url = apiUrl('/defenses', { ...identityParams(), week, scope: 'both', mode });
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
  const mode = getDataMode();
  const url = apiUrl('/dashboard', { ...identityParams(), mode, weeks: 'this', def_scope: 'owned', include_players: '1', model: getModel() });
  dbg('refreshAll:start', { url });
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
    ...identityParams(),
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
  const btnBookCoverage = document.getElementById('btnBookCoverage');
  if (btnBookCoverage) {
    btnBookCoverage.addEventListener('click', () => {
      try { if (typeof openBookCoverage === 'function') openBookCoverage('this'); } catch (e) { console.error(e); }
    });
  }
  document.querySelectorAll('.btn-players').forEach(btn => {
    btn.addEventListener('click', () => showPlayers(btn.dataset.week));
  });
  document.querySelectorAll('.btn-draft-board').forEach(btn => {
    btn.addEventListener('click', () => showDraftBoard(btn.dataset.week));
  });
  if (btnProjThis) btnProjThis.addEventListener('click', () => dbgProjections('this'));
  if (btnProjNext) btnProjNext.addEventListener('click', () => dbgProjections('next'));

  // League/team setup flow: username -> league -> team
  const leagueUserContinue = document.getElementById('leagueUserContinue');
  if (leagueUserContinue) leagueUserContinue.addEventListener('click', () => submitUsername());
  const leagueUsernameInput = document.getElementById('leagueUsernameInput');
  if (leagueUsernameInput) leagueUsernameInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitUsername(); });
  const leagueSeasonInput = document.getElementById('leagueSeasonInput');
  if (leagueSeasonInput) leagueSeasonInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitUsername(); });

  const leagueLeagueContinue = document.getElementById('leagueLeagueContinue');
  if (leagueLeagueContinue) leagueLeagueContinue.addEventListener('click', () => submitLeaguePick());
  const leagueLeagueBack = document.getElementById('leagueLeagueBack');
  if (leagueLeagueBack) leagueLeagueBack.addEventListener('click', () => {
    document.getElementById('leagueStepLeague').classList.add('hidden');
    document.getElementById('leagueStepUser').classList.remove('hidden');
  });

  const leagueTeamContinue = document.getElementById('leagueTeamContinue');
  if (leagueTeamContinue) leagueTeamContinue.addEventListener('click', () => submitTeamPick());
  const leagueTeamBack = document.getElementById('leagueTeamBack');
  if (leagueTeamBack) leagueTeamBack.addEventListener('click', () => {
    document.getElementById('leagueStepTeam').classList.add('hidden');
    document.getElementById('leagueStepLeague').classList.remove('hidden');
  });

  const leagueSetupClose = document.getElementById('leagueSetupClose');
  if (leagueSetupClose) leagueSetupClose.addEventListener('click', () => hideLeagueSetupModal());
  const btnChangeLeague = document.getElementById('btnChangeLeague');
  if (btnChangeLeague) btnChangeLeague.addEventListener('click', () => showLeagueSetupModal());

  dbg('DOMContentLoaded');
  initLeagueFlow();
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
  ['username','season'].forEach(id => { const el=$(id); if (el) el.addEventListener('change', saveSettings); });
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

