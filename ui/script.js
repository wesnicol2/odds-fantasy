const state = {
  week: 'this',
  reports: { this: null, next: null },
  inflight: 0,
};

function $(id) { return document.getElementById(id); }
function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}
function setCookie(name, value, days = 365) {
  document.cookie = `${name}=${encodeURIComponent(value)}; max-age=${days * 86400}; path=/; SameSite=Lax`;
}
function getCookie(name) {
  const key = `${name}=`;
  const row = document.cookie.split('; ').find(item => item.startsWith(key));
  return row ? decodeURIComponent(row.slice(key.length)) : null;
}
function deleteCookie(name) { document.cookie = `${name}=; max-age=0; path=/`; }
function currentNflSeason() {
  const now = new Date();
  return String(now.getUTCMonth() + 1 >= 3 ? now.getUTCFullYear() : now.getUTCFullYear() - 1);
}
function identityParams() {
  const leagueId = getCookie('league_id');
  const rosterId = getCookie('roster_id');
  if (leagueId && rosterId) return { league_id: leagueId, roster_id: rosterId };
  const username = getCookie('sleeper_username');
  return { username: username || '', season: currentNflSeason() };
}
function apiUrl(path, params = {}) {
  const query = new URLSearchParams(params).toString();
  return query ? `${path}?${query}` : path;
}
function setNetwork(delta) {
  state.inflight = Math.max(0, state.inflight + delta);
  $('netSpin')?.classList.toggle('hidden', state.inflight === 0);
}
async function fetchJSON(url) {
  setNetwork(1);
  try {
    const response = await fetch(url, { headers: { Accept: 'application/json' } });
    const data = await response.json();
    return { ok: response.ok, status: response.status, data };
  } catch (error) {
    return { ok: false, status: 0, data: { error: String(error) } };
  } finally {
    setNetwork(-1);
  }
}
function getDataMode() { return $('dataModeSelect')?.value || 'auto'; }
function formatRateLimit(payload) {
  const info = payload?.ratelimit_info;
  if (!info) return payload?.ratelimit || '';
  const remaining = info.remaining ?? '?';
  const used = info.used ?? '?';
  const total = info.total ?? ((typeof remaining === 'number' && typeof used === 'number') ? remaining + used : '?');
  return `Odds API ${remaining}/${total} remaining`;
}
function fmt(value) { return value == null ? '—' : Number(value).toFixed(2); }

function renderPlayerReport(payload) {
  const players = Array.isArray(payload?.players) ? payload.players : [];
  $('reportStatus').textContent = payload?.message || '';
  $('rlHeader').textContent = formatRateLimit(payload);
  if (!players.length) {
    $('playerReport').innerHTML = '<div class="empty">No roster players available for this week.</div>';
    $('btnCompareCurves').disabled = true;
    return;
  }

  const rows = players.map(player => {
    const noProjection = !player.has_projection;
    const nameNote = noProjection ? '<span class="row-note">no priced markets</span>' : '';
    return `<tr class="${noProjection ? 'no-projection' : ''}">
      <td><button class="player-link" data-player="${escapeHtml(player.name)}" type="button">${escapeHtml(player.name)}</button>${nameNote}</td>
      <td>${escapeHtml(player.pos || '')}</td>
      <td>${escapeHtml(player.team || '')}</td>
      <td class="number">${fmt(player.floor)}</td>
      <td class="number mid-value">${fmt(player.mid)}</td>
      <td class="number">${fmt(player.ceiling)}</td>
    </tr>`;
  }).join('');

  $('playerReport').innerHTML = `<table class="report-table">
    <thead><tr><th>Player</th><th>Pos</th><th>Team</th><th>Floor</th><th>Mid</th><th>Ceiling</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
  $('btnCompareCurves').disabled = players.filter(p => p.curve?.length).length < 2;
}

async function refreshReport({ force = false } = {}) {
  const week = state.week;
  if (!force && state.reports[week]) {
    renderPlayerReport(state.reports[week]);
    return;
  }
  $('reportStatus').textContent = 'Loading sportsbook lines…';
  $('playerReport').innerHTML = '<div class="loading"><span class="spinner"></span> Building projections…</div>';
  const mode = getDataMode();
  const { ok, data } = await fetchJSON(apiUrl('/projections', { ...identityParams(), week, mode }));
  if (!ok) {
    $('reportStatus').textContent = 'Could not load projections.';
    $('playerReport').innerHTML = '<div class="empty">Request failed.</div>';
    return;
  }
  state.reports[week] = data;
  renderPlayerReport(data);
}

function curvePath(curve, xScale, yScale) {
  return (curve || []).map((point, index) => {
    const x = xScale(Number(point.x));
    const y = yScale(Number(point.survival));
    return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}
function curveColor(index) { return `hsl(${(index * 47 + 205) % 360} 72% 62%)`; }
function renderComparison(players) {
  const withCurves = players.filter(player => player.curve?.length);
  if (!withCurves.length) return '<div class="empty">No player curves available.</div>';

  const width = 900, height = 430, left = 58, right = 18, top = 20, bottom = 46;
  const maxX = Math.max(...withCurves.flatMap(player => player.curve.map(point => Number(point.x) || 0)), 1);
  const xScale = x => left + (x / maxX) * (width - left - right);
  const yScale = y => top + (1 - y) * (height - top - bottom);
  let grid = '';
  for (let i = 0; i <= 5; i++) {
    const xValue = maxX * i / 5;
    const x = xScale(xValue);
    grid += `<line class="chart-grid" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" />`;
    grid += `<text class="chart-label" x="${x}" y="${height-18}" text-anchor="middle">${xValue.toFixed(0)}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const probability = 1 - i / 4;
    const y = yScale(probability);
    grid += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" />`;
    grid += `<text class="chart-label" x="${left-10}" y="${y+4}" text-anchor="end">${Math.round(probability*100)}%</text>`;
  }

  const paths = withCurves.map((player, index) =>
    `<path d="${curvePath(player.curve, xScale, yScale)}" fill="none" stroke="${curveColor(index)}" stroke-width="2.5" />`
  ).join('');
  const legend = withCurves.map((player, index) =>
    `<button class="legend-player player-link" data-player="${escapeHtml(player.name)}" type="button"><span class="legend-dot" style="background:${curveColor(index)}"></span>${escapeHtml(player.name)}</button>`
  ).join('');

  return `<p class="chart-explainer">Each line is the backend's actual <strong>P(fantasy points ≥ x)</strong> curve. Click a player in the legend for the source lines.</p>
    <div class="chart-wrap"><svg class="compare-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Roster fantasy point probability curves">
      ${grid}${paths}
      <text class="chart-axis-title" x="${(left + width-right)/2}" y="${height-2}" text-anchor="middle">Fantasy points</text>
      <text class="chart-axis-title" transform="translate(14 ${(top+height-bottom)/2}) rotate(-90)" text-anchor="middle">Probability of at least x</text>
    </svg></div>
    <div class="curve-legend">${legend}</div>`;
}
function openCompareCurves() {
  const report = state.reports[state.week];
  if (!report) return;
  $('compareBody').innerHTML = renderComparison(report.players || []);
  $('compareOverlay').classList.remove('hidden');
}

function showLeagueSetup(step = 'user') {
  $('leagueSetupOverlay').classList.remove('hidden');
  $('leagueStepUser').classList.toggle('hidden', step !== 'user');
  $('leagueStepLeague').classList.toggle('hidden', step !== 'league');
  $('leagueStepTeam').classList.toggle('hidden', step !== 'team');
  const username = getCookie('sleeper_username');
  if (username) $('leagueUsernameInput').value = username;
}
function hideLeagueSetup() { $('leagueSetupOverlay').classList.add('hidden'); }

async function submitUsername() {
  const username = $('leagueUsernameInput').value.trim();
  if (!username) { $('leagueUserError').textContent = 'Enter a Sleeper username.'; return; }
  $('leagueUserError').textContent = 'Finding leagues…';
  const { ok, data } = await fetchJSON(apiUrl('/user/leagues', { username, season: currentNflSeason() }));
  if (!ok || data.error || !data.leagues?.length) {
    $('leagueUserError').textContent = 'No leagues found for that username.';
    return;
  }
  setCookie('sleeper_username', username);
  $('leagueUserError').textContent = '';
  $('leagueLeaguePrompt').textContent = `Choose a league for ${username}.`;
  $('leagueLeagueSelect').innerHTML = '<option value="">Choose a league…</option>' + data.leagues.map(league =>
    `<option value="${escapeHtml(league.league_id)}">${escapeHtml(league.name || league.league_id)}</option>`
  ).join('');
  showLeagueSetup('league');
}
async function submitLeague() {
  const leagueId = $('leagueLeagueSelect').value;
  if (!leagueId) { $('leagueLeagueError').textContent = 'Choose a league.'; return; }
  $('leagueLeagueError').textContent = 'Loading teams…';
  const { ok, data } = await fetchJSON(apiUrl('/league/resolve', { league_id: leagueId }));
  if (!ok || data.error) { $('leagueLeagueError').textContent = 'Could not load that league.'; return; }
  setCookie('league_id', leagueId);
  $('leagueLeagueError').textContent = '';
  $('leagueTeamPrompt').textContent = `Choose your team in ${data.name || 'this league'}.`;
  $('leagueTeamSelect').innerHTML = '<option value="">Choose a team…</option>' + (data.teams || []).map(team =>
    `<option value="${team.roster_id}">${escapeHtml(team.team_name || `Team ${team.roster_id}`)}</option>`
  ).join('');
  showLeagueSetup('team');
}
async function submitTeam() {
  const rosterId = $('leagueTeamSelect').value;
  if (!rosterId) { $('leagueTeamError').textContent = 'Choose your team.'; return; }
  setCookie('roster_id', rosterId);
  hideLeagueSetup();
  state.reports = { this: null, next: null };
  await updateLeagueIndicator();
  await refreshReport({ force: true });
}
async function updateLeagueIndicator() {
  const leagueId = getCookie('league_id');
  const rosterId = getCookie('roster_id');
  if (!leagueId || !rosterId) return;
  const { ok, data } = await fetchJSON(apiUrl('/league/resolve', { league_id: leagueId }));
  if (!ok || data.error) return;
  const team = (data.teams || []).find(row => String(row.roster_id) === String(rosterId));
  $('leagueIndicator').textContent = `${data.name || leagueId} · ${team?.team_name || `Team ${rosterId}`}`;
  $('leagueIndicator').classList.remove('hidden');
}
async function initLeague() {
  if (getCookie('league_id') && getCookie('roster_id')) {
    await updateLeagueIndicator();
    await refreshReport();
    return;
  }
  showLeagueSetup('user');
}

async function loadBuildStamp() {
  const { ok, data } = await fetchJSON('/health');
  const build = ok ? data.build : null;
  if (!build?.commit || build.commit === 'unknown') { $('buildText').textContent = 'build unknown'; return; }
  $('buildText').textContent = `build ${build.commit_short || build.commit.slice(0, 7)} · ${build.image_tag || build.branch || ''}`;
}

function bindEvents() {
  document.querySelectorAll('.week-toggle').forEach(button => button.addEventListener('click', async () => {
    state.week = button.dataset.week;
    document.querySelectorAll('.week-toggle').forEach(item => item.classList.toggle('active', item === button));
    await refreshReport();
  }));
  $('btnCompareCurves').addEventListener('click', openCompareCurves);
  $('compareClose').addEventListener('click', () => $('compareOverlay').classList.add('hidden'));
  $('detailsClose').addEventListener('click', () => $('detailsOverlay').classList.add('hidden'));
  $('btnChangeLeague').addEventListener('click', () => {
    deleteCookie('league_id'); deleteCookie('roster_id');
    $('leagueIndicator').classList.add('hidden');
    state.reports = { this: null, next: null };
    showLeagueSetup('user');
  });
  $('btnSettings').addEventListener('click', () => $('settingsPanel').classList.toggle('hidden'));
  $('dataModeSelect').addEventListener('change', () => { state.reports = { this: null, next: null }; });
  $('leagueSetupClose').addEventListener('click', hideLeagueSetup);
  $('leagueUserContinue').addEventListener('click', submitUsername);
  $('leagueLeagueContinue').addEventListener('click', submitLeague);
  $('leagueTeamContinue').addEventListener('click', submitTeam);
  $('leagueLeagueBack').addEventListener('click', () => showLeagueSetup('user'));
  $('leagueTeamBack').addEventListener('click', () => showLeagueSetup('league'));

  document.addEventListener('click', event => {
    const button = event.target.closest('.player-link');
    if (!button) return;
    const name = button.dataset.player;
    if (!name || typeof window.openPlayerDetails !== 'function') return;
    $('compareOverlay').classList.add('hidden');
    window.openPlayerDetails(name, state.week);
  });
  document.querySelectorAll('.overlay').forEach(overlay => overlay.addEventListener('click', event => {
    if (event.target === overlay && overlay.id !== 'leagueSetupOverlay') overlay.classList.add('hidden');
  }));
}

document.addEventListener('DOMContentLoaded', () => {
  bindEvents();
  loadBuildStamp();
  initLeague();
});