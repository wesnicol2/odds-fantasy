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
  setMode(preSeason ? 'predraft' : 'season');
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
  // One readout, in the header. There used to be a second copy in a footer
  // showing the identical string.
  const info = payload?.ratelimit_info;
  setStatus($('rlHeader'), formatRateLimit(info, payload?.ratelimit));
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

// ---- Build stamp ------------------------------------------------------
// Deployment is pull-based (Watchtower recreates the container when the GHCR
// digest moves), so nothing else tells you which commit is actually serving
// this page. /health reports it; this renders it in the footer.
const GITHUB_REPO_URL = 'https://github.com/wesnicol2/odds-fantasy';

function _renderBuildFooter(build) {
  const el = $('buildText');
  if (!el) return;
  el.textContent = '';
  if (!build || !build.commit || build.commit === 'unknown') {
    el.textContent = 'build unknown';
    el.title = 'This build carries no commit stamp.';
    return;
  }

  // Built as DOM nodes rather than an HTML string: the commit goes into an
  // href, and there is no escaping to get wrong this way.
  const pieces = [];
  const link = document.createElement('a');
  link.className = 'build-mono';
  link.href = GITHUB_REPO_URL + '/commit/' + encodeURIComponent(build.commit);
  link.target = '_blank';
  link.rel = 'noopener';
  link.textContent = build.commit_short || build.commit.slice(0, 7);
  const stamp = document.createElement('span');
  stamp.append('build ', link);
  pieces.push(stamp);

  // A dirty tree means the running code is not the commit named, so say so
  // rather than showing a stamp that quietly isn't true.
  if (build.dirty) {
    const warn = document.createElement('span');
    warn.className = 'build-warn';
    warn.textContent = '+local changes';
    pieces.push(warn);
  }

  const labels = [];
  if (build.image_tag) labels.push(build.image_tag);
  else if (build.source === 'git') labels.push('source');
  if (build.branch) labels.push(build.branch);
  if (labels.length) pieces.push(document.createTextNode(labels.join(' ')));
  if (build.built_at) pieces.push(document.createTextNode(build.built_at));

  pieces.forEach((piece, i) => {
    if (i > 0) {
      const sep = document.createElement('span');
      sep.className = 'build-sep';
      sep.textContent = '·';
      el.appendChild(sep);
    }
    el.appendChild(piece);
  });
  el.title = build.commit + (build.dirty ? ' (working tree had uncommitted changes)' : '');
}

async function loadBuildFooter() {
  try {
    const { ok, data } = await fetchJSON(apiUrl('/health'));
    if (ok && data) _renderBuildFooter(data.build);
    else _renderBuildFooter(null);
  } catch (e) {
    _renderBuildFooter(null);
  }
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
    '</tbody></table>'
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
    '</tbody></table>'
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
  
  if (view === 'lineup') {
    const cached = appCache.lineups?.[week]?.[target];
    if (cached) {
      renderLineup(containerId, week === 'this' ? 'This Week Lineup' : 'Next Week Lineup', cached);
      updateRateLimitDisplays(cached);
      return;
    }
    showContainerLoading(containerId, 'Loading lineup...');
    const { ok, data } = await fetchJSON(apiUrl('/lineup', { ...identityParams(), week, target, mode }));
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
    const { ok, data } = await fetchJSON(apiUrl('/projections', { ...identityParams(), week, mode }));
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

// --- Pre-draft board -----------------------------------------------------
// Every draftable player on the slate, ranked, for breaking ties between
// players you already rate similarly.
//
// There is deliberately no season total here. The books only post props for
// the upcoming slate, so a "season projection" could only be this number
// multiplied by a games constant -- identical ordering, no extra information,
// and it would read as a market number when it isn't one.
const draftState = { week: 'this' };
window.getCurrentDraftWeek = () => draftState.week;

function _upside(r) {
  return Number(r.ceiling || 0) - Number(r.mid || 0);
}

function renderDraftBoard(containerId, data) {
  const c = $(containerId);
  if (!c) return;
  const posFilter = ($('draftPosFilter') || {}).value || '';
  const all = (data.players || []).slice().sort((a, b) => Number(b.mid || 0) - Number(a.mid || 0));

  // Positional rank comes from the whole board, so filtering to one position
  // doesn't renumber it -- "WR7" has to mean the same thing in both views.
  const posSeen = {};
  all.forEach(r => {
    posSeen[r.pos] = (posSeen[r.pos] || 0) + 1;
    r._posRank = posSeen[r.pos];
  });
  const rows = posFilter ? all.filter(r => r.pos === posFilter) : all;

  // "Week 1"/"Week 2" are anchored to the earliest games in the odds feed,
  // not to today's date, so always show the range actually loaded.
  let note = '';
  if (data.message) {
    note = data.message;
  } else if (data.window_start && data.window_end) {
    const fmt = (iso) => {
      try { return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }); }
      catch (e) { return iso; }
    };
    note = `Per-game market read, ${fmt(data.window_start)} – ${fmt(data.window_end)}. Upside = ceiling − mid.`;
  }

  if (!rows.length) {
    c.innerHTML = `<div class="status">${note || 'No players found.'}</div>`;
    return;
  }

  const body = rows.map((r, i) => {
    const inc = _isIncompleteRow(r);
    const books = Number(r.books_used || 0);
    const thin = books > 0 && books < 3;
    const booksCell = books
      ? `<td class="${thin ? 'thin-coverage' : ''}" ${thin ? 'title="Backed by few books -- weak basis for a tiebreak"' : ''}>${books}</td>`
      : '<td class="thin-coverage" title="No book coverage">—</td>';
    return `<tr>
      <td class="rank">${i + 1}</td>
      <td>${_nameCell(r, inc)}</td>
      <td>${r.pos || ''}${r._posRank ? `<span class="pos-rank">${r._posRank}</span>` : ''}</td>
      <td>${r.team || ''}</td>
      <td>${_statCell(r.floor, inc)}</td>
      <td>${_statCell(r.mid, inc)}</td>
      <td>${_statCell(r.ceiling, inc)}</td>
      <td>${inc ? '—' : _upside(r).toFixed(2)}</td>
      ${booksCell}
    </tr>`;
  });

  c.innerHTML = [
    note ? `<div class="status draft-board-note">${note}</div>` : '',
    '<table><thead><tr>',
    '<th>#</th><th>Name</th><th>Pos</th><th>Team</th>',
    '<th>Floor</th><th>Mid</th><th>Ceiling</th><th>Upside</th><th>Books</th>',
    '</tr></thead><tbody>',
    ...body,
    '</tbody></table>'
  ].join('\n');
  try { enableTableSort(c.querySelector('table')); } catch (e) {}
}

async function showDraftBoard(week) {
  // Intentionally not scoped to any roster -- see /draft-board in the API and
  // CONTRIBUTING.md's "Odds API quota awareness" section. Fetched once per
  // week and cached client-side; the position filter re-filters the cached
  // board rather than re-fetching, since the API fetches the same games
  // either way.
  draftState.week = week;
  const containerId = 'draft-board';
  const cached = appCache.draftBoard?.[week];
  if (cached) {
    renderDraftBoard(containerId, cached);
    updateRateLimitDisplays(appCache.lastRateLimit || {});
    return;
  }
  dbg('showDraftBoard:no-cache', { week });
  showContainerLoading(containerId, 'Loading the board (it covers every team playing this week)...');
  const url = apiUrl('/draft-board', { ...identityParams(), week, mode: getDataMode() });
  const { ok, data } = await fetchJSON(url);
  if (!ok) { $(containerId).innerHTML = '<div class="status">Failed to load the board.</div>'; return; }
  appCache.draftBoard[week] = data;
  appCache.lastRateLimit = data;
  renderDraftBoard(containerId, data);
  updateRateLimitDisplays(data);
}

// --- Mode switch (Pre-Draft vs In-Season) ---------------------------------
function setMode(mode) {
  const isPredraft = mode === 'predraft';
  $('panel-predraft').classList.toggle('hidden', !isPredraft);
  $('panel-season').classList.toggle('hidden', isPredraft);
  $('modePredraftBtn').classList.toggle('toggle-active', isPredraft);
  $('modeSeasonBtn').classList.toggle('toggle-active', !isPredraft);
  if (isPredraft) showDraftBoard(draftState.week);
  else refreshWeeklyView();
}

// Refresh whichever panel is visible, discarding cached payloads first so a
// changed data mode actually takes effect.
function refreshAll() {
  const predraftVisible = !$('panel-predraft').classList.contains('hidden');
  appCache.lineups = { this: {}, next: {} };
  appCache.defenses = { this: null, next: null };
  appCache.projections = { this: null, next: null };
  appCache.draftBoard = { this: null, next: null };
  if (predraftVisible) showDraftBoard(draftState.week);
  else refreshWeeklyView();
}

// Wire handlers
document.addEventListener('DOMContentLoaded', () => {
  loadBuildFooter();
  loadSettings();
  attachSettingsListeners();

  // Settings popover
  const btnSettings = $('btnSettings');
  const settingsPanel = $('settingsPanel');
  if (btnSettings && settingsPanel) {
    // The panel ships hidden. It used to toggle a class `open` that no rule
    // acted on, while `.hidden` stayed put at `display: none !important` --
    // so the gear did nothing at all and the controls inside were
    // unreachable. Toggle the class that actually governs visibility.
    btnSettings.addEventListener('click', (e) => { e.stopPropagation(); settingsPanel.classList.toggle('hidden'); });
    document.addEventListener('click', (e) => {
      if (settingsPanel.classList.contains('hidden')) return;
      if (settingsPanel.contains(e.target) || e.target === btnSettings) return;
      settingsPanel.classList.add('hidden');
    });
  }
  const btnShowFallbackId = $('btnShowFallbackId');
  const fallbackIdFields = $('fallbackIdFields');
  if (btnShowFallbackId && fallbackIdFields) {
    btnShowFallbackId.addEventListener('click', () => fallbackIdFields.classList.toggle('hidden'));
  }

  // Mode switch
  const modePredraftBtn = $('modePredraftBtn');
  const modeSeasonBtn = $('modeSeasonBtn');
  if (modePredraftBtn) modePredraftBtn.addEventListener('click', () => setMode('predraft'));
  if (modeSeasonBtn) modeSeasonBtn.addEventListener('click', () => setMode('season'));

  // Pre-draft panel toggles
  const draftPanel = $('panel-predraft');
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
  const weeklyPanel = $('panel-season');
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
  } catch (e) { /* ignore */ }
}

function attachSettingsListeners() {
  ['username','season'].forEach(id => { const el=$(id); if (el) el.addEventListener('change', saveSettings); });
  const dm = $('dataModeSelect'); if (dm) dm.addEventListener('change', () => { saveSettings(); refreshAll(); });
}

// Enable simple table sorting on click.
//
// Which columns are numeric is read from the data rather than assumed from a
// column index -- the tables here don't share a column order, and a hardcoded
// index quietly sorted a text column as numbers when one of them changed.
// Numeric columns sort highest-first on the first click, which is the
// direction you want on every one of them (points, upside, book counts).
function enableTableSort(table) {
  try {
    if (!table) return;
    const ths = table.querySelectorAll('thead th');
    const bodyRows = () => Array.from(table.querySelectorAll('tbody tr'));
    const cellText = (row, i) => ((row.cells[i] && row.cells[i].textContent) || '').trim();
    const isNumericColumn = (i) => {
      const values = bodyRows().map(r => cellText(r, i)).filter(v => v && v !== '—' && v !== '-');
      if (!values.length) return false;
      return values.every(v => !Number.isNaN(parseFloat(v)));
    };
    ths.forEach((th, colIdx) => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        const tbody = table.querySelector('tbody');
        const rows = bodyRows();
        const numeric = isNumericColumn(colIdx);
        const previous = th.getAttribute('data-sort');
        const dir = previous ? (previous === 'asc' ? 'desc' : 'asc') : (numeric ? 'desc' : 'asc');
        ths.forEach(h => h.removeAttribute('data-sort'));
        th.setAttribute('data-sort', dir);
        rows.sort((a, b) => {
          const av = cellText(a, colIdx);
          const bv = cellText(b, colIdx);
          let cmp;
          if (numeric) {
            // Blank/em-dash cells are "no data" -- keep them last either way.
            const aN = parseFloat(av), bN = parseFloat(bv);
            if (Number.isNaN(aN) && Number.isNaN(bN)) cmp = 0;
            else if (Number.isNaN(aN)) return 1;
            else if (Number.isNaN(bN)) return -1;
            else cmp = aN - bN;
          } else {
            cmp = av.localeCompare(bv);
          }
          return dir === 'asc' ? cmp : -cmp;
        });
        rows.forEach(r => tbody.appendChild(r));
      });
    });
  } catch (e) { /* ignore */ }
}
