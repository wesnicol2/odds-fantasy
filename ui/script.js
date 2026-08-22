// Simple debug logger
const DEBUG = true; // toggle to enable/disable UI debug logs
function dbg(...args) { if (DEBUG && console && console.log) console.log('[ui]', ...args); }

function $(id) { return document.getElementById(id); }
function val(id) { return ($(id) ? $(id).value : '').trim(); }

// In-memory cache for preloaded data, keyed the same way the API is: by week.
const appCache = {
  lineups: { this: {}, next: {} },
  defenses: { this: null, next: null },
  projections: { this: null, next: null },
  draftBoard: { this: null, next: null },
  lastRateLimit: null,
};

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
  return { username: val('username') || 'wesnicol', season: val('season') || currentNflSeason() };
}

function currentNflSeason() {
  // Mirrors config.current_nfl_season() in Python: Sleeper labels a league
  // by the year its season starts, and Jan/Feb still belongs to last season.
  // Never shown as a field -- there's no reason to ask the user for this.
  const now = new Date();
  const y = now.getUTCFullYear();
  return String((now.getUTCMonth() + 1) >= 3 ? y : y - 1);
}

// League setup, 3 steps: enter Sleeper username (cookie'd) -> pick which of
// your leagues (its league_id gets cookie'd) -> pick your team in it
// (roster_id cookie'd). The league's own Sleeper `status` then decides
// whether to default to the draft board (pre_draft/drafting) or the weekly
// lineup view (in_season/complete/anything else). Username here is only
// ever used to list leagues to choose from -- once a league_id is picked,
// everything downstream is keyed off league_id+roster_id, not username.
const PRE_DRAFT_STATUSES = ['pre_draft', 'drafting'];

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
}

async function submitUsername() {
  const username = ($('leagueUsernameInput').value || '').trim();
  const season = currentNflSeason();
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
    errEl.textContent = `No leagues found for "${username}" in ${season}.`;
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
  el.textContent = `${leagueData.name || leagueData.league_id} · ${team ? team.team_name : '?'} · ${statusLabel}`;
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
  setMode(preSeason ? 'draft' : 'weekly');
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

// Build a lineup client-side from an already-fetched player list. Used only
// by the Compare Curves modal's LINEUP tab (details.js) as a preview, not by
// the primary Lineup view (which calls the server-authoritative /lineup
// endpoint -- see refreshWeeklyView -- so it correctly includes DEF and
// matches what /lineup/diffs compares against).
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

// UI loading helpers
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
  const el = $('dataModeSelect');
  return (el && el.value) ? el.value : 'auto';
}

function getModel() {
  const el = $('modelSelect');
  return (el && el.value) ? el.value : 'market';
}

// A player/lineup row is "incomplete" when the backend had no odds coverage
// to project from -- floor/mid/ceiling are 0 (or null) because there's
// nothing to compute from, not because the player is actually projected for
// zero. Flag it visibly instead of rendering a plain, misleading "0.00".
function _isIncompleteRow(r) {
  return !!r.incomplete || (r.mid == null && r.floor == null && r.ceiling == null);
}
function _statCell(v, incomplete) {
  return incomplete ? '—' : Number(v || 0).toFixed(2);
}
function _nameCell(r, incomplete) {
  const nameSpan = `<span class="player-name" data-player="${r.name}" title="Open details" style="cursor:pointer; text-decoration:underline;">${r.name}</span>`;
  if (!incomplete) return nameSpan;
  return `<span class="incomplete-name">${nameSpan} <span class="pill pill-warn" title="No odds coverage found -- stats unavailable">incomplete</span></span>`;
}

function renderLineup(containerId, title, payload) {
  const c = $(containerId);
  const rows = payload?.lineup || [];
  const target = payload?.target || 'mid';
  const total = Number(payload?.total_points ?? 0);
  const ratelimit = payload?.ratelimit || '';
  dbg('renderLineup', { containerId, title, count: rows.length, target, total });
  const headerCols = '<th>Slot</th><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th>';
  const rowHtml = rows.map(r => {
    const inc = _isIncompleteRow(r);
    return `
    <tr>
      <td>${r.slot}</td>
      <td>${_nameCell(r, inc)}</td>
      <td>${r.pos}</td>
      <td>${_statCell(r.floor, inc)}</td>
      <td>${_statCell(r.mid, inc)}</td>
      <td>${_statCell(r.ceiling, inc)}</td>
    </tr>`;
  });
  const table = [
    `<h3>${title} — target: ${target} (total: ${total.toFixed(2)})</h3>`,
    `<table><thead><tr>${headerCols}</tr></thead><tbody>`,
    ...rowHtml,
    '</tbody></table>',
    `<div class="status">RateLimit: ${ratelimit}</div>`
  ].join('\n');
  c.innerHTML = table;
  try { enableTableSort(c.querySelector('table')); } catch (e) {}
}

function renderDefenses(containerId, payload) {
  const c = $(containerId);
  dbg('renderDefenses', { containerId, count: (payload.defenses||[]).length });
  const rows = payload.defenses || [];
  if (!rows.length) {
    c.innerHTML = '<div class="status">No defenses found for this week.</div>';
    return;
  }
  rows.sort((a, b) => (Number(a.implied_total_median) - Number(b.implied_total_median)) || (Number(b.book_count) - Number(a.book_count)));
  const table = [
    '<table><thead><tr><th>Defense</th><th>Owner</th><th>Opponent</th><th>Game Date</th><th>Opp Implied</th><th>Floor</th><th>Mid</th><th>Ceiling</th></tr></thead><tbody>',
    ...rows.map(r => {
      const owner = r.owner ? String(r.owner) : '';
      const mine = !!r.owned_by_current;
      const taken = !!(r.owner);
      const cls = mine ? 'def-row def-mine' : (taken ? 'def-row def-taken' : 'def-row def-available');
      const fmt = (v) => (v == null ? '-' : Number(v).toFixed(2));
      return `<tr class="${cls}"><td>${r.defense}</td><td>${owner || '-'}</td><td>${r.opponent}</td><td>${r.game_date}</td><td>${fmt(r.implied_total_median)}</td><td>${fmt(r.floor)}</td><td>${fmt(r.mid)}</td><td>${fmt(r.ceiling)}</td></tr>`;
    }),
    '</tbody></table>',
    `<div class="status">RateLimit: ${payload.ratelimit || ''}</div>`
  ].join('\n');
  c.innerHTML = table;
  try { enableTableSort(c.querySelector('table')); } catch (e) {}
}

function renderPlayers(containerId, players) {
  const c = $(containerId);
  const rows = Array.isArray(players) ? players.slice() : [];
  if (!rows.length) {
    c.innerHTML = '<div class="status">No players found.</div>';
    return;
  }
  rows.sort((a, b) => Number(b.mid || 0) - Number(a.mid || 0));
  const table = [
    '<table><thead><tr><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th></tr></thead><tbody>',
    ...rows.map(r => {
      const inc = _isIncompleteRow(r);
      return `<tr><td>${_nameCell(r, inc)}</td><td>${r.pos}</td><td>${_statCell(r.floor, inc)}</td><td>${_statCell(r.mid, inc)}</td><td>${_statCell(r.ceiling, inc)}</td></tr>`;
    }),
    '</tbody></table>'
  ].join('\n');
  c.innerHTML = table;
  try { enableTableSort(c.querySelector('table')); } catch (e) {}
}

// --- Weekly panel (Lineup / All Players / Defenses, This/Next Week) -----
const weeklyState = { week: 'this', view: 'lineup', target: 'mid' };
window.getCurrentWeeklyWeek = () => weeklyState.week;
window.getCurrentWeeklyView = () => weeklyState.view;

async function refreshWeeklyView() {
  const { week, view, target } = weeklyState;
  const containerId = 'weekly-results';
  const mode = getDataMode();
  const model = getModel();

  if (view === 'lineup') {
    const cached = appCache.lineups?.[week]?.[target];
    if (cached) {
      renderLineup(containerId, week === 'this' ? 'This Week Lineup' : 'Next Week Lineup', cached);
      updateRateLimitDisplays(cached);
      return;
    }
    showContainerLoading(containerId, 'Loading lineup...');
    const { ok, data } = await fetchJSON(apiUrl('/lineup', { ...identityParams(), week, target, mode, model }));
    if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load lineup.</div>'; return; }
    appCache.lineups[week] = appCache.lineups[week] || {};
    appCache.lineups[week][target] = data;
    appCache.lastRateLimit = data;
    renderLineup(containerId, week === 'this' ? 'This Week Lineup' : 'Next Week Lineup', data);
    updateRateLimitDisplays(data);
  } else if (view === 'players') {
    const cached = appCache.projections?.[week];
    if (cached) { renderPlayers(containerId, cached.players || []); updateRateLimitDisplays(appCache.lastRateLimit || {}); return; }
    showContainerLoading(containerId, 'Loading players...');
    const { ok, data } = await fetchJSON(apiUrl('/projections', { ...identityParams(), week, mode, model }));
    if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load players.</div>'; return; }
    appCache.projections[week] = data;
    appCache.lastRateLimit = data;
    renderPlayers(containerId, data.players || []);
    updateRateLimitDisplays(data);
  } else if (view === 'defenses') {
    const cached = appCache.defenses?.[week];
    if (cached) { renderDefenses(containerId, cached); updateRateLimitDisplays(appCache.lastRateLimit || cached); return; }
    showContainerLoading(containerId, 'Loading defenses...');
    const { ok, data } = await fetchJSON(apiUrl('/defenses', { ...identityParams(), week, scope: 'both', mode }));
    if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load defenses.</div>'; return; }
    appCache.defenses[week] = data;
    appCache.lastRateLimit = data;
    renderDefenses(containerId, data);
    updateRateLimitDisplays(data);
  }
}

// --- Draft board panel (Week 1 / Week 2, position filter) ----------------
const draftState = { week: 'this' };
window.getCurrentDraftWeek = () => draftState.week;

function _renderDraftBoard(containerId, data) {
  // "Week 1"/"Week 2" are schedule-anchored (earliest games in the odds
  // feed), not tied to today's date -- always show the resolved date range
  // (or the "nothing scheduled yet" message) so it's never ambiguous what's
  // actually loaded. renderPlayers() owns the table itself; this just adds
  // a header in front of it.
  const posFilter = ($('draftPosFilter') || {}).value || '';
  const players = posFilter ? (data.players || []).filter(p => p.pos === posFilter) : (data.players || []);
  renderPlayers(containerId, players);
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
  // and CONTRIBUTING.md's "Odds API quota awareness" section. Fetched once
  // per week and cached client-side; the position filter re-filters the
  // cached board instead of re-fetching (the API doesn't fetch fewer games
  // for a narrower position filter, so there's no cost benefit to a
  // server round-trip on every filter change).
  draftState.week = week;
  const cached = appCache.draftBoard?.[week];
  const containerId = 'draft-board';
  if (!cached) {
    dbg('showDraftBoard:no-cache', { week });
    showContainerLoading(containerId, 'Loading draft board (this can take a bit -- it covers every team playing this week)...');
    const url = apiUrl('/draft-board', { ...identityParams(), week, mode: getDataMode(), model: getModel() });
    const { ok, data } = await fetchJSON(url);
    if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load draft board.</div>'; return; }
    appCache.draftBoard[week] = data;
    appCache.lastRateLimit = data;
    _renderDraftBoard(containerId, data);
    updateRateLimitDisplays(data);
    return;
  }
  _renderDraftBoard(containerId, cached);
  updateRateLimitDisplays(appCache.lastRateLimit || {});
}

// --- Mode switch (Draft Board vs Weekly) ----------------------------------
function setMode(mode) {
  const isDraft = mode === 'draft';
  $('panel-draft').classList.toggle('hidden', !isDraft);
  $('panel-weekly').classList.toggle('hidden', isDraft);
  $('modeDraftBtn').classList.toggle('toggle-active', isDraft);
  $('modeWeeklyBtn').classList.toggle('toggle-active', !isDraft);
  if (isDraft) showDraftBoard(draftState.week);
  else refreshWeeklyView();
}

// Refresh whichever panel is currently visible. Also called by details.js
// after a model change inside a player-detail popup, so it stays meaningful
// as "refresh the background view under the new model" rather than a no-op.
function refreshAll() {
  const draftVisible = !$('panel-draft').classList.contains('hidden');
  // Invalidate caches so the new model/data-mode actually takes effect.
  appCache.lineups = { this: {}, next: {} };
  appCache.defenses = { this: null, next: null };
  appCache.projections = { this: null, next: null };
  appCache.draftBoard = { this: null, next: null };
  if (draftVisible) showDraftBoard(draftState.week);
  else refreshWeeklyView();
}

async function dbgProjections(week) {
  const url = apiUrl('/projections', { ...identityParams(), week, mode: getDataMode(), model: getModel() });
  showContainerLoading('projectionsDebug', 'Loading projections...');
  const { ok, data } = await fetchJSON(url);
  if (!ok) { dbg('dbgProjections:fail', { week, url }); return alert('Failed to load projections'); }
  $('projectionsDebug').textContent = JSON.stringify(data, null, 2);
  updateRateLimitDisplays(data);
}

// Wire handlers
document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  attachSettingsListeners();

  // Settings popover
  const btnSettings = $('btnSettings');
  const settingsPanel = $('settingsPanel');
  if (btnSettings && settingsPanel) {
    btnSettings.addEventListener('click', (e) => { e.stopPropagation(); settingsPanel.classList.toggle('open'); });
    document.addEventListener('click', (e) => {
      if (!settingsPanel.classList.contains('open')) return;
      if (settingsPanel.contains(e.target) || e.target === btnSettings) return;
      settingsPanel.classList.remove('open');
    });
  }
  const btnShowFallbackId = $('btnShowFallbackId');
  const fallbackIdFields = $('fallbackIdFields');
  if (btnShowFallbackId && fallbackIdFields) {
    btnShowFallbackId.addEventListener('click', () => fallbackIdFields.classList.toggle('hidden'));
  }

  // Mode switch
  const modeDraftBtn = $('modeDraftBtn');
  const modeWeeklyBtn = $('modeWeeklyBtn');
  if (modeDraftBtn) modeDraftBtn.addEventListener('click', () => setMode('draft'));
  if (modeWeeklyBtn) modeWeeklyBtn.addEventListener('click', () => setMode('weekly'));

  // Draft panel toggles
  const draftPanel = $('panel-draft');
  if (draftPanel) {
    draftPanel.querySelectorAll('.week-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        draftPanel.querySelectorAll('.week-toggle').forEach(b => b.classList.toggle('toggle-active', b === btn));
        showDraftBoard(btn.dataset.week);
      });
    });
  }
  const draftPosFilter = $('draftPosFilter');
  if (draftPosFilter) draftPosFilter.addEventListener('change', () => showDraftBoard(draftState.week));

  // Weekly panel toggles
  const weeklyPanel = $('panel-weekly');
  if (weeklyPanel) {
    weeklyPanel.querySelectorAll('.week-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        weeklyState.week = btn.dataset.week;
        weeklyPanel.querySelectorAll('.week-toggle').forEach(b => b.classList.toggle('toggle-active', b === btn));
        refreshWeeklyView();
      });
    });
    weeklyPanel.querySelectorAll('.view-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        weeklyState.view = btn.dataset.view;
        weeklyPanel.querySelectorAll('.view-toggle').forEach(b => b.classList.toggle('toggle-active', b === btn));
        const targetRow = $('targetToggleRow');
        if (targetRow) targetRow.classList.toggle('hidden', weeklyState.view !== 'lineup');
        refreshWeeklyView();
      });
    });
    weeklyPanel.querySelectorAll('.target-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        weeklyState.target = btn.dataset.target;
        weeklyPanel.querySelectorAll('.target-toggle').forEach(b => b.classList.toggle('toggle-active', b === btn));
        refreshWeeklyView();
      });
    });
  }

  // Advanced tools (collapsed by default)
  const btnToggleAdvanced = $('btnToggleAdvanced');
  const panelAdvanced = $('panel-advanced');
  if (btnToggleAdvanced && panelAdvanced) {
    btnToggleAdvanced.addEventListener('click', () => {
      const nowHidden = panelAdvanced.classList.toggle('hidden');
      btnToggleAdvanced.textContent = nowHidden ? 'Show Advanced Tools' : 'Hide Advanced Tools';
    });
  }
  document.querySelectorAll('.btn-compare-curves').forEach(btn => {
    btn.addEventListener('click', () => {
      try { if (typeof openCompareCurves === 'function') openCompareCurves(btn.dataset.week || 'this'); } catch (e) { console.error(e); }
    });
  });
  const btnBookCoverage = $('btnBookCoverage');
  if (btnBookCoverage) {
    btnBookCoverage.addEventListener('click', () => {
      try { if (typeof openBookCoverage === 'function') openBookCoverage('this'); } catch (e) { console.error(e); }
    });
  }
  const btnProjThis = $('btnProjThis');
  const btnProjNext = $('btnProjNext');
  if (btnProjThis) btnProjThis.addEventListener('click', () => dbgProjections('this'));
  if (btnProjNext) btnProjNext.addEventListener('click', () => dbgProjections('next'));

  // League/team setup flow: username -> league -> team
  const leagueUserContinue = $('leagueUserContinue');
  if (leagueUserContinue) leagueUserContinue.addEventListener('click', () => submitUsername());
  const leagueUsernameInput = $('leagueUsernameInput');
  if (leagueUsernameInput) leagueUsernameInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitUsername(); });

  const leagueLeagueContinue = $('leagueLeagueContinue');
  if (leagueLeagueContinue) leagueLeagueContinue.addEventListener('click', () => submitLeaguePick());
  const leagueLeagueBack = $('leagueLeagueBack');
  if (leagueLeagueBack) leagueLeagueBack.addEventListener('click', () => {
    $('leagueStepLeague').classList.add('hidden');
    $('leagueStepUser').classList.remove('hidden');
  });

  const leagueTeamContinue = $('leagueTeamContinue');
  if (leagueTeamContinue) leagueTeamContinue.addEventListener('click', () => submitTeamPick());
  const leagueTeamBack = $('leagueTeamBack');
  if (leagueTeamBack) leagueTeamBack.addEventListener('click', () => {
    $('leagueStepTeam').classList.add('hidden');
    $('leagueStepLeague').classList.remove('hidden');
  });

  const leagueSetupClose = $('leagueSetupClose');
  if (leagueSetupClose) leagueSetupClose.addEventListener('click', () => hideLeagueSetupModal());
  const btnChangeLeague = $('btnChangeLeague');
  if (btnChangeLeague) btnChangeLeague.addEventListener('click', () => showLeagueSetupModal());

  dbg('DOMContentLoaded');
  initLeagueFlow();

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
      dataMode: getDataMode(),
      model: getModel(),
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
    if (s.dataMode) { const dm = $('dataModeSelect'); if (dm) dm.value = s.dataMode; }
    if (s.model) { const ms = $('modelSelect'); if (ms) ms.value = s.model; }
  } catch (e) { /* ignore */ }
}

function attachSettingsListeners() {
  ['username','season'].forEach(id => { const el=$(id); if (el) el.addEventListener('change', saveSettings); });
  const dm = $('dataModeSelect'); if (dm) dm.addEventListener('change', () => { saveSettings(); refreshAll(); });
  const ms = $('modelSelect'); if (ms) ms.addEventListener('change', () => { saveSettings(); refreshAll(); });
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
