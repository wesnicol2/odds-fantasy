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

const COUNT_GRAPH_METRICS = new Set([
  'player_pass_tds',
  'player_pass_interceptions',
  'player_rush_tds',
  'player_receptions',
  'player_reception_tds',
  'player_anytime_td',
]);

const graphDetailCache = new Map();

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

function sourceThresholdX(metric, threshold) {
  const value = Number(threshold);
  if (!Number.isFinite(value)) return null;
  if (!COUNT_GRAPH_METRICS.has(metric)) return value;
  if (metric === 'player_anytime_td' && value <= 0) return 1;
  if (value <= 0) return 1;
  return Number.isInteger(value) ? value : Math.ceil(value);
}

function formatGraphNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return Number.isInteger(number) ? String(number) : number.toFixed(1);
}

function formatOdds(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : '—';
}

function graphCurvePath(points, xScale, yScale, kind) {
  if (!points?.length) return '';
  if (kind !== 'survival_step') return scoreProbabilityPath(points, xScale, yScale);
  let path = '';
  points.forEach((point, index) => {
    const x = xScale(Number(point.x));
    const y = yScale(Number(point.probability));
    if (!index) {
      path = `M${x.toFixed(1)},${y.toFixed(1)}`;
      return;
    }
    path += `H${x.toFixed(1)}V${y.toFixed(1)}`;
  });
  return path;
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
    .graph-visual-key { display:flex; flex-wrap:wrap; gap:14px; align-items:center; margin:8px 0 4px; color:#94a3b8; font-size:12px; }
    .graph-key-item { display:inline-flex; gap:6px; align-items:center; }
    .graph-key-line { width:25px; border-top:2px solid #cbd5e1; }
    .graph-key-diamond { width:9px; height:9px; background:#cbd5e1; transform:rotate(45deg); }
    .graph-key-tick { width:2px; height:12px; background:#cbd5e1; opacity:.7; }
    .graph-evidence-actions { display:flex; justify-content:space-between; align-items:center; gap:12px; margin-top:10px; }
    .graph-evidence-actions button { padding:7px 10px; }
    .graph-evidence-panel { margin-top:10px; padding:14px; border:1px solid #263449; border-radius:10px; background:rgba(15,23,42,.55); }
    .graph-evidence-head { display:flex; flex-wrap:wrap; gap:10px; align-items:center; justify-content:space-between; margin-bottom:10px; }
    .graph-evidence-head select { min-width:190px; }
    .graph-evidence-summary { color:#cbd5e1; font-size:13px; line-height:1.45; margin:0 0 12px; }
    .graph-evidence-grid { display:grid; grid-template-columns:minmax(220px,.8fr) minmax(360px,1.4fr); gap:16px; }
    .graph-evidence-grid h4 { margin:0 0 6px; }
    .graph-evidence-panel .table-scroll { max-height:250px; overflow:auto; }
    .graph-anchor-guide { opacity:.16; stroke-dasharray:3 4; }
    .graph-source-tick { opacity:.6; }
    .graph-consensus-marker { stroke:#f8fafc; stroke-width:1.2; }
    @media (max-width:760px) {
      .graph-explorer { grid-template-columns:1fr; }
      .graph-filter-panel { border-right:0; border-bottom:1px solid #263449; padding:0 0 14px; }
      .graph-player-list { max-height:150px; }
      .graph-evidence-grid { grid-template-columns:1fr; }
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

function graphDescription(metric) {
  if (metric === 'fantasy_points') {
    return 'Probability of finishing within x ± 0.5 fantasy points. Floor / Mid / Ceiling calculations are unchanged.';
  }
  return 'The solid line is the fitted probability of reaching or exceeding each stat threshold. Diamonds are de-vigged consensus anchors; small ticks on the x-axis are exact sportsbook thresholds.';
}

function renderGraphEvidence(explorer, series) {
  if (explorer.metric === 'fantasy_points' || !series.length) return '';
  const names = series.map(item => item.player.name);
  if (!names.includes(explorer.explainPlayer)) explorer.explainPlayer = names[0];
  const selected = series.find(item => item.player.name === explorer.explainPlayer) || series[0];
  const graph = selected.graph;
  const anchors = graph.anchors || [];
  const lines = graph.lines || [];
  const options = series.map(item => `<option value="${escapeHtml(item.player.name)}" ${item.player.name === selected.player.name ? 'selected' : ''}>${escapeHtml(item.player.name)}</option>`).join('');
  const anchorRows = anchors.map(anchor => `<tr><td class="number">${formatGraphNumber(anchor.threshold)}</td><td class="number">${formatChartProbability(Number(anchor.survival))}</td></tr>`).join('');
  const lineRows = lines.map(line => `<tr>
    <td>${escapeHtml(line.book || '')}</td>
    <td>${line.source === 'alternate' ? 'Alt' : 'Main'}</td>
    <td class="number">${formatGraphNumber(line.point)}</td>
    <td class="number">${formatOdds(line.over_odds)}</td>
    <td class="number">${formatOdds(line.under_odds)}</td>
  </tr>`).join('');
  const bookCount = new Set(lines.map(line => line.book).filter(Boolean)).size;

  return `<div class="graph-evidence-actions">
      <span class="subtle">${anchors.length} consensus thresholds · ${lines.length} source lines · ${bookCount} books</span>
      <button type="button" data-graph-explain-toggle>${explorer.explainOpen ? 'Hide line details' : 'Explain betting lines'}</button>
    </div>
    ${explorer.explainOpen ? `<div class="graph-evidence-panel">
      <div class="graph-evidence-head">
        <strong>Why this curve has this shape</strong>
        <label class="subtle">Player <select id="graphExplainPlayer">${options}</select></label>
      </div>
      <p class="graph-evidence-summary">For ${escapeHtml(selected.player.name)}, each book's over/under prices are de-vigged first. Books at the same threshold are combined into the consensus diamonds shown on the graph. The fitted curve passes through those market constraints; outside the outermost continuous-stat anchors, the configured tail model continues the curve. The raw prices below are the evidence behind those anchors.</p>
      <div class="graph-evidence-grid">
        <div>
          <h4>Consensus anchors</h4>
          ${anchorRows ? `<table class="compact-table"><thead><tr><th>Threshold</th><th>Fair P(over)</th></tr></thead><tbody>${anchorRows}</tbody></table>` : '<div class="empty">No consensus anchors.</div>'}
        </div>
        <div>
          <h4>Exact sportsbook lines</h4>
          ${lineRows ? `<div class="table-scroll"><table class="compact-table"><thead><tr><th>Book</th><th>Type</th><th>Line</th><th>Over odds</th><th>Under odds</th></tr></thead><tbody>${lineRows}</tbody></table></div>` : '<div class="empty">No source lines.</div>'}
        </div>
      </div>
    </div>` : ''}`;
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
  $('graphSubtitle').textContent = metric === 'fantasy_points'
    ? 'x = fantasy points · y = probability within a 1-point scoring bucket'
    : `x = ${graphLabel(metric).toLowerCase()} threshold · y = probability at or above threshold`;

  if (!series.length) {
    area.innerHTML = '<div class="graph-empty">No selected players have data for this graph.</div>';
    return;
  }

  const width = 900, height = 440, left = 68, right = 20, top = 24, bottom = 54;
  const allCurves = series.map(item => item.graph.points);
  const sourceXs = metric === 'fantasy_points' ? [] : series.flatMap(({ graph }) => [
    ...(graph.anchors || []).map(anchor => sourceThresholdX(metric, anchor.threshold)),
    ...(graph.lines || []).map(line => sourceThresholdX(metric, line.point)),
  ]).filter(Number.isFinite);
  const curveXs = allCurves.flatMap(curve => curve.map(point => Number(point.x))).filter(Number.isFinite);
  let minX = Math.min(...curveXs, ...sourceXs);
  let maxX = Math.max(...curveXs, ...sourceXs);
  if (metric === 'fantasy_points') minX = Math.min(minX, 0);
  const rawSpan = Math.max(maxX - minX, 1);
  const pad = metric === 'fantasy_points' ? 0 : rawSpan * 0.04;
  minX -= pad;
  maxX += pad;
  const spanX = Math.max(maxX - minX, 1);
  const yMax = metric === 'fantasy_points' ? niceProbabilityMax(allCurves) : 1;
  const xScale = x => left + ((x - minX) / spanX) * (width - left - right);
  const yScale = y => top + (1 - y / yMax) * (height - top - bottom);

  let grid = '';
  for (let i = 0; i <= 5; i++) {
    const xValue = minX + spanX * i / 5;
    const x = xScale(xValue);
    const digits = spanX <= 8 && !Number.isInteger(xValue) ? 1 : 0;
    grid += `<line class="chart-grid" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" />`;
    grid += `<text class="chart-label" x="${x}" y="${height-22}" text-anchor="middle">${xValue.toFixed(digits)}</text>`;
  }
  const ySteps = metric === 'fantasy_points' ? 4 : 4;
  for (let i = 0; i <= ySteps; i++) {
    const probability = yMax * (1 - i / ySteps);
    const y = yScale(probability);
    grid += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" />`;
    grid += `<text class="chart-label" x="${left-10}" y="${y+4}" text-anchor="end">${formatChartProbability(probability)}</text>`;
  }

  const paths = series.map(({ player, graph }) => {
    const colorIndex = explorer.players.findIndex(row => row.name === player.name);
    const path = graphCurvePath(graph.points, xScale, yScale, graph.kind);
    return `<path d="${path}" fill="none" stroke="${curveColor(colorIndex)}" stroke-width="2.7" stroke-linejoin="round" stroke-linecap="round" />`;
  }).join('');

  let sourceMarks = '';
  if (metric !== 'fantasy_points') {
    sourceMarks = series.map(({ player, graph }) => {
      const colorIndex = explorer.players.findIndex(row => row.name === player.name);
      const color = curveColor(colorIndex);
      const guides = (graph.anchors || []).map(anchor => {
        const sourceX = sourceThresholdX(metric, anchor.threshold);
        if (!Number.isFinite(sourceX)) return '';
        const x = xScale(sourceX);
        const y = yScale(Number(anchor.survival));
        const size = 5;
        const points = `${x},${y-size} ${x+size},${y} ${x},${y+size} ${x-size},${y}`;
        return `<g><line class="graph-anchor-guide" x1="${x}" y1="${y}" x2="${x}" y2="${height-bottom}" stroke="${color}" />
          <polygon class="graph-consensus-marker" points="${points}" fill="${color}"><title>${escapeHtml(player.name)} · consensus ${formatGraphNumber(anchor.threshold)} · fair over ${formatChartProbability(Number(anchor.survival))}</title></polygon></g>`;
      }).join('');
      const ticks = (graph.lines || []).map(line => {
        const sourceX = sourceThresholdX(metric, line.point);
        if (!Number.isFinite(sourceX)) return '';
        const x = xScale(sourceX);
        const baseline = height - bottom;
        return `<line class="graph-source-tick" x1="${x}" y1="${baseline-11}" x2="${x}" y2="${baseline}" stroke="${color}" stroke-width="2"><title>${escapeHtml(player.name)} · ${escapeHtml(line.book || '')} · line ${formatGraphNumber(line.point)} · over ${formatOdds(line.over_odds)} / under ${formatOdds(line.under_odds)}</title></line>`;
      }).join('');
      return guides + ticks;
    }).join('');
  }

  const legend = series.map(({ player }) => {
    const colorIndex = explorer.players.findIndex(row => row.name === player.name);
    return `<button class="legend-player player-link" data-player="${escapeHtml(player.name)}" type="button"><span class="legend-dot" style="background:${curveColor(colorIndex)}"></span>${escapeHtml(player.name)}</button>`;
  }).join('');

  const visualKey = metric === 'fantasy_points' ? '' : `<div class="graph-visual-key">
    <span class="graph-key-item"><span class="graph-key-line"></span>fitted curve</span>
    <span class="graph-key-item"><span class="graph-key-diamond"></span>consensus fair probability</span>
    <span class="graph-key-item"><span class="graph-key-tick"></span>exact sportsbook threshold</span>
  </div>`;
  const yAxisTitle = metric === 'fantasy_points' ? 'Probability within 1 FP' : 'Probability at or above threshold';
  const xAxisTitle = metric === 'fantasy_points' ? 'Fantasy points' : `${graphLabel(metric)} threshold`;

  area.innerHTML = `<p class="chart-explainer">${escapeHtml(graphDescription(metric))}</p>
    ${visualKey}
    <div class="chart-wrap"><svg class="compare-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(graphLabel(metric))} probability graph">
      ${grid}${paths}${sourceMarks}
      <text class="chart-axis-title" x="${(left + width-right)/2}" y="${height-3}" text-anchor="middle">${escapeHtml(xAxisTitle)}</text>
      <text class="chart-axis-title" transform="translate(16 ${(top+height-bottom)/2}) rotate(-90)" text-anchor="middle">${escapeHtml(yAxisTitle)}</text>
    </svg></div>
    <div class="curve-legend">${legend}</div>
    ${renderGraphEvidence(explorer, series)}`;
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
  explorer.explainOpen = false;
  explorer.explainPlayer = null;
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
      graphs[marketKey] = {
        ...graph,
        anchors: market.anchors || [],
        lines: market.lines || [],
      };
    });
    explorer.graphs.set(player.name, graphs);
  }));

  if (window.__graphExplorer !== explorer || !$('graphExplorer')) return;
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
    const explainButton = event.target.closest('[data-graph-explain-toggle]');
    if (explainButton) {
      explorer.explainOpen = !explorer.explainOpen;
      renderGraphChart(explorer);
      return;
    }
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
    if (event.target.id === 'graphExplainPlayer') {
      explorer.explainPlayer = event.target.value;
      renderGraphChart(explorer);
      return;
    }
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
    selectedPositions: new Set(players.map(player => player.pos).filter(Boolean)),
    explainOpen: false,
    explainPlayer: null,
  };
  window.__graphExplorer = explorer;
  bindGraphExplorer(explorer);
  renderGraphChart(explorer);
  hydrateStatGraphs(explorer);
}

renderComparison = function renderGraphExplorerComparison(players) {
  injectGraphExplorerStyles();
  const withCurves = players.filter(player => player.curve?.length);
  if (!withCurves.length) return '<div class="empty">No player curves available.</div>';
  setTimeout(() => initializeGraphExplorer(withCurves), 0);
  return renderExplorerShell(withCurves);
};