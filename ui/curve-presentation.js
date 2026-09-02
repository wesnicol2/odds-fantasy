const GRAPH_ORDER = [
  'fantasy_points',
  'player_pass_yds',
  'player_pass_tds',
  'player_pass_interceptions',
  'player_rush_yds',
  'player_rush_tds',
  'player_receptions',
  'player_reception_yds',
  'player_reception_tds',
  'player_anytime_td',
];

const GRAPH_LABELS = {
  fantasy_points: 'Fantasy points',
  player_pass_yds: 'Passing yards',
  player_pass_tds: 'Passing TDs',
  player_pass_interceptions: 'Interceptions',
  player_rush_yds: 'Rushing yards',
  player_rush_tds: 'Rushing TDs',
  player_receptions: 'Receptions',
  player_reception_yds: 'Receiving yards',
  player_reception_tds: 'Receiving TDs',
  player_anytime_td: 'Anytime TD',
};

const graphDetailCache = new Map();

function survivalAt(curve, threshold) {
  const points = (curve || [])
    .map(point => ({ x: Number(point.x), survival: Number(point.survival) }))
    .filter(point => Number.isFinite(point.x) && Number.isFinite(point.survival))
    .sort((a, b) => a.x - b.x);
  if (!points.length) return 0;
  if (threshold <= points[0].x) return Math.max(0, Math.min(1, points[0].survival));
  if (threshold > points[points.length - 1].x) return 0;

  for (let i = 1; i < points.length; i++) {
    const right = points[i];
    if (threshold > right.x) continue;
    const left = points[i - 1];
    if (right.x === left.x) return Math.max(0, Math.min(1, right.survival));
    const ratio = (threshold - left.x) / (right.x - left.x);
    const value = left.survival + ratio * (right.survival - left.survival);
    return Math.max(0, Math.min(1, value));
  }
  return 0;
}

function scoreProbabilityCurve(curve, bucketWidth = 1) {
  const xs = (curve || []).map(point => Number(point.x)).filter(Number.isFinite);
  if (!xs.length || bucketWidth <= 0) return [];
  const start = Math.floor(Math.min(...xs));
  const end = Math.ceil(Math.max(...xs));
  const halfWidth = bucketWidth / 2;
  const out = [];
  for (let x = start; x <= end; x += bucketWidth) {
    const lowerSurvival = survivalAt(curve, x - halfWidth);
    const upperSurvival = survivalAt(curve, x + halfWidth);
    out.push({
      x: Number(x.toFixed(2)),
      probability: Math.max(0, Math.min(1, lowerSurvival - upperSurvival)),
    });
  }
  return out;
}

function niceProbabilityMax(curves) {
  const maxProbability = Math.max(
    ...curves.flatMap(curve => (curve || []).map(point => Number(point.probability) || 0)),
    0.01,
  );
  const step = maxProbability <= 0.1 ? 0.02 : 0.05;
  return Math.min(1, Math.max(step, Math.ceil(maxProbability * 1.1 / step) * step));
}

function formatChartProbability(probability) {
  const percent = probability * 100;
  const digits = percent < 10 && percent % 1 !== 0 ? 1 : 0;
  return `${percent.toFixed(digits)}%`;
}

function scoreProbabilityPath(curve, xScale, yScale) {
  return (curve || []).map((point, index) => {
    const x = xScale(Number(point.x));
    const y = yScale(Number(point.probability));
    return `${index ? 'L' : 'M'}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

function graphLabel(key) {
  if (GRAPH_LABELS[key]) return GRAPH_LABELS[key];
  return String(key || '')
    .replace(/^player_/, '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
}

function graphSort(a, b) {
  const ai = GRAPH_ORDER.indexOf(a);
  const bi = GRAPH_ORDER.indexOf(b);
  if (ai === -1 && bi === -1) return graphLabel(a).localeCompare(graphLabel(b));
  if (ai === -1) return 1;
  if (bi === -1) return -1;
  return ai - bi;
}

function injectGraphExplorerStyles() {
  if (document.getElementById('graphExplorerStyles')) return;
  const style = document.createElement('style');
  style.id = 'graphExplorerStyles';
  style.textContent = `
    .graph-explorer { display:grid; grid-template-columns:240px minmax(0,1fr); gap:18px; min-height:520px; }
    .graph-filter-panel { border-right:1px solid #263449; padding-right:16px; min-width:0; }
    .graph-filter-panel h3 { margin:0 0 9px; font-size:13px; text-transform:uppercase; letter-spacing:.06em; color:#94a3b8; }
    .graph-filter-group + .graph-filter-group { margin-top:20px; }
    .graph-filter-list { display:flex; flex-direction:column; gap:6px; }
    .graph-metric-btn { width:100%; text-align:left; border:0; background:transparent; padding:7px 8px; color:#cbd5e1; }
    .graph-metric-btn.active { background:#1d4ed8; color:white; }
    .graph-check { display:flex; gap:8px; align-items:center; padding:3px 0; color:#cbd5e1; font-size:13px; }
    .graph-check input { margin:0; }
    .graph-filter-actions { display:flex; gap:8px; margin-bottom:7px; }
    .graph-filter-actions button { padding:3px 6px; font-size:11px; }
    .graph-player-search { width:100%; margin-bottom:7px; padding:6px 8px; font-size:12px; }
    .graph-player-list { max-height:230px; overflow:auto; padding-right:4px; }
    .graph-stage { min-width:0; }
    .graph-nav { display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:10px; align-items:center; margin-bottom:8px; }
    .graph-nav button { min-width:42px; }
    .graph-title { text-align:center; }
    .graph-title strong { display:block; font-size:18px; color:#f8fafc; }
    .graph-title span { display:block; margin-top:3px; color:#94a3b8; font-size:12px; }
    .graph-load-note { color:#64748b; font-size:12px; margin-top:8px; }
    .graph-empty { padding:80px 20px; text-align:center; color:#94a3b8; }
    @media (max-width:760px) {
      .graph-explorer { grid-template-columns:1fr; }
      .graph-filter-panel { border-right:0; border-bottom:1px solid #263449; padding:0 0 14px; }
      .graph-player-list { max-height:150px; }
    }
  `;
  document.head.appendChild(style);
}

function renderExplorerShell(players) {
  const positions = [...new Set(players.map(player => player.pos).filter(Boolean))].sort();
  const positionChecks = positions.map(pos => `
    <label class="graph-check"><input type="checkbox" data-graph-position="${escapeHtml(pos)}" checked />${escapeHtml(pos)}</label>
  `).join('');
  const playerChecks = players.map(player => `
    <label class="graph-check" data-graph-player-row="${escapeHtml(player.name.toLowerCase())}">
      <input type="checkbox" data-graph-player="${escapeHtml(player.name)}" checked />
      <span>${escapeHtml(player.name)} <span class="subtle">${escapeHtml(player.pos || '')}</span></span>
    </label>
  `).join('');

  return `<div class="graph-explorer" id="graphExplorer">
    <aside class="graph-filter-panel">
      <div class="graph-filter-group">
        <h3>Graphs</h3>
        <div id="graphMetricList" class="graph-filter-list">
          <button class="graph-metric-btn active" data-graph-metric="fantasy_points" type="button">Fantasy points</button>
        </div>
        <div id="graphLoadNote" class="graph-load-note">Loading stat graphs…</div>
      </div>
      <div class="graph-filter-group">
        <h3>Positions</h3>
        <div class="graph-filter-list">${positionChecks}</div>
      </div>
      <div class="graph-filter-group">
        <h3>Players</h3>
        <div class="graph-filter-actions">
          <button type="button" data-graph-action="all">All</button>
          <button type="button" data-graph-action="none">None</button>
        </div>
        <input id="graphPlayerSearch" class="graph-player-search" type="search" placeholder="Filter players" />
        <div id="graphPlayerList" class="graph-player-list">${playerChecks}</div>
      </div>
    </aside>
    <section class="graph-stage">
      <div class="graph-nav">
        <button type="button" data-graph-nav="previous" aria-label="Previous graph">←</button>
        <div class="graph-title"><strong id="graphTitle">Fantasy points</strong><span id="graphSubtitle">Probability at each scoring amount</span></div>
        <button type="button" data-graph-nav="next" aria-label="Next graph">→</button>
      </div>
      <div id="graphChartArea"></div>
    </section>
  </div>`;
}

function graphDescription(graph) {
  if (!graph) return '';
  if (graph.kind === 'exact_count') return 'Exact probability of each integer result.';
  const width = Number(graph.bucket_width) || 1;
  const unit = width === 1 ? '1-unit' : `${width:g}`;
  return `Probability within a ${width}-unit bucket centered on x.`;
}

function renderGraphChart(explorer) {
  const area = $('graphChartArea');
  if (!area) return;
  const metric = explorer.metric;
  const selected = explorer.players.filter(player =>
    explorer.selectedPlayers.has(player.name) && explorer.selectedPositions.has(player.pos)
  );
  const series = selected
    .map(player => ({ player, graph: explorer.graphs.get(player.name)?.[metric] }))
    .filter(item => item.graph?.points?.length);

  $('graphTitle').textContent = graphLabel(metric);
  const sampleGraph = series[0]?.graph;
  $('graphSubtitle').textContent = metric === 'fantasy_points'
    ? '1-point fantasy-score buckets; projection math unchanged'
    : (sampleGraph?.kind === 'exact_count'
      ? 'Exact probability for each count'
      : `${sampleGraph?.bucket_width || 1}-unit buckets from the canonical stat distribution`);

  if (!series.length) {
    area.innerHTML = '<div class="graph-empty">No selected players have data for this graph.</div>';
    return;
  }

  const width = 900, height = 430, left = 58, right = 18, top = 20, bottom = 46;
  const allCurves = series.map(item => item.graph.points);
  const minX = Math.min(...allCurves.flatMap(curve => curve.map(point => Number(point.x))), 0);
  const maxX = Math.max(...allCurves.flatMap(curve => curve.map(point => Number(point.x))), 1);
  const spanX = Math.max(maxX - minX, 1);
  const yMax = niceProbabilityMax(allCurves);
  const xScale = x => left + ((x - minX) / spanX) * (width - left - right);
  const yScale = y => top + (1 - y / yMax) * (height - top - bottom);

  let grid = '';
  for (let i = 0; i <= 5; i++) {
    const xValue = minX + spanX * i / 5;
    const x = xScale(xValue);
    const digits = spanX <= 6 && !Number.isInteger(xValue) ? 1 : 0;
    grid += `<line class="chart-grid" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" />`;
    grid += `<text class="chart-label" x="${x}" y="${height-18}" text-anchor="middle">${xValue.toFixed(digits)}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const probability = yMax * (1 - i / 4);
    const y = yScale(probability);
    grid += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" />`;
    grid += `<text class="chart-label" x="${left-10}" y="${y+4}" text-anchor="end">${formatChartProbability(probability)}</text>`;
  }

  const paths = series.map(({ player, graph }) => {
    const colorIndex = explorer.players.findIndex(row => row.name === player.name);
    return `<path d="${scoreProbabilityPath(graph.points, xScale, yScale)}" fill="none" stroke="${curveColor(colorIndex)}" stroke-width="2.5" />`;
  }).join('');
  const legend = series.map(({ player }) => {
    const colorIndex = explorer.players.findIndex(row => row.name === player.name);
    return `<button class="legend-player player-link" data-player="${escapeHtml(player.name)}" type="button"><span class="legend-dot" style="background:${curveColor(colorIndex)}"></span>${escapeHtml(player.name)}</button>`;
  }).join('');

  const description = metric === 'fantasy_points'
    ? 'Each plotted point is the probability of finishing within x ± 0.5 fantasy points. Floor / Mid / Ceiling calculations are unchanged.'
    : graphDescription(sampleGraph);

  area.innerHTML = `<p class="chart-explainer">${escapeHtml(description)}</p>
    <div class="chart-wrap"><svg class="compare-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(graphLabel(metric))} probability graph">
      ${grid}${paths}
      <text class="chart-axis-title" x="${(left + width-right)/2}" y="${height-2}" text-anchor="middle">${escapeHtml(graphLabel(metric))}</text>
      <text class="chart-axis-title" transform="translate(14 ${(top+height-bottom)/2}) rotate(-90)" text-anchor="middle">Probability at x</text>
    </svg></div>
    <div class="curve-legend">${legend}</div>`;
}

function renderMetricButtons(explorer) {
  const list = $('graphMetricList');
  if (!list) return;
  list.innerHTML = explorer.metrics.map(metric => `
    <button class="graph-metric-btn ${metric === explorer.metric ? 'active' : ''}" data-graph-metric="${escapeHtml(metric)}" type="button">${escapeHtml(graphLabel(metric))}</button>
  `).join('');
}

function setExplorerMetric(explorer, metric) {
  if (!explorer.metrics.includes(metric)) return;
  explorer.metric = metric;
  renderMetricButtons(explorer);
  renderGraphChart(explorer);
}

function cycleExplorerMetric(explorer, direction) {
  const index = explorer.metrics.indexOf(explorer.metric);
  const next = (index + direction + explorer.metrics.length) % explorer.metrics.length;
  setExplorerMetric(explorer, explorer.metrics[next]);
}

async function fetchGraphDetails(player, week) {
  const key = `${week}|${player.name}`;
  if (graphDetailCache.has(key)) return graphDetailCache.get(key);
  const request = fetchJSON(apiUrl('/player/odds', {
    ...identityParams(), week, name: player.name, mode: getDataMode(),
  })).then(({ ok, data }) => ok ? data : null);
  graphDetailCache.set(key, request);
  return request;
}

async function hydrateStatGraphs(explorer) {
  await Promise.all(explorer.players.map(async player => {
    const details = await fetchGraphDetails(player, explorer.week);
    if (!details) return;
    const graphs = explorer.graphs.get(player.name) || {};
    Object.entries(details.markets || {}).forEach(([marketKey, market]) => {
      const graph = market?.graph;
      if (!graph?.points?.length) return;
      graphs[marketKey] = graph;
    });
    explorer.graphs.set(player.name, graphs);
  }));

  const available = new Set(['fantasy_points']);
  explorer.graphs.forEach(graphs => Object.keys(graphs).forEach(key => available.add(key)));
  explorer.metrics = [...available].sort(graphSort);
  const note = $('graphLoadNote');
  if (note) note.textContent = `${explorer.metrics.length} graphs available`;
  renderMetricButtons(explorer);
  renderGraphChart(explorer);
}

function bindGraphExplorer(explorer) {
  const root = $('graphExplorer');
  if (!root) return;

  root.addEventListener('click', event => {
    const metricButton = event.target.closest('[data-graph-metric]');
    if (metricButton) {
      setExplorerMetric(explorer, metricButton.dataset.graphMetric);
      return;
    }
    const navButton = event.target.closest('[data-graph-nav]');
    if (navButton) {
      cycleExplorerMetric(explorer, navButton.dataset.graphNav === 'previous' ? -1 : 1);
      return;
    }
    const actionButton = event.target.closest('[data-graph-action]');
    if (actionButton) {
      const checked = actionButton.dataset.graphAction === 'all';
      root.querySelectorAll('[data-graph-player]').forEach(input => { input.checked = checked; });
      explorer.selectedPlayers = checked ? new Set(explorer.players.map(player => player.name)) : new Set();
      renderGraphChart(explorer);
    }
  });

  root.addEventListener('change', event => {
    const position = event.target.dataset.graphPosition;
    if (position) {
      if (event.target.checked) explorer.selectedPositions.add(position);
      else explorer.selectedPositions.delete(position);
      renderGraphChart(explorer);
      return;
    }
    const playerName = event.target.dataset.graphPlayer;
    if (playerName) {
      if (event.target.checked) explorer.selectedPlayers.add(playerName);
      else explorer.selectedPlayers.delete(playerName);
      renderGraphChart(explorer);
    }
  });

  $('graphPlayerSearch')?.addEventListener('input', event => {
    const query = event.target.value.trim().toLowerCase();
    root.querySelectorAll('[data-graph-player-row]').forEach(row => {
      row.classList.toggle('hidden', Boolean(query) && !row.dataset.graphPlayerRow.includes(query));
    });
  });
}

function initializeGraphExplorer(players) {
  const root = $('graphExplorer');
  if (!root) return;
  const positions = new Set(players.map(player => player.pos).filter(Boolean));
  const graphs = new Map();
  players.forEach(player => {
    graphs.set(player.name, {
      fantasy_points: {
        kind: 'bucket',
        bucket_width: 1,
        points: scoreProbabilityCurve(player.curve),
      },
    });
  });

  const explorer = {
    players,
    week: state.week,
    graphs,
    metrics: ['fantasy_points'],
    metric: 'fantasy_points',
    selectedPlayers: new Set(players.map(player => player.name)),
    selectedPositions: positions,
  };
  window.__graphExplorer = explorer;
  bindGraphExplorer(explorer);
  renderGraphChart(explorer);
  hydrateStatGraphs(explorer);
}

function renderComparison(players) {
  injectGraphExplorerStyles();
  const withCurves = players.filter(player => player.curve?.length);
  if (!withCurves.length) return '<div class="empty">No player curves available.</div>';
  setTimeout(() => initializeGraphExplorer(withCurves), 0);
  return renderExplorerShell(withCurves);
}
