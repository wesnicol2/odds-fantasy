function injectFantasyPointSurvivalStyles() {
  if (document.getElementById('fpSurvivalStyles')) return;
  const style = document.createElement('style');
  style.id = 'fpSurvivalStyles';
  style.textContent = `
    .fp-range-guide { opacity:.42; stroke-dasharray:5 5; }
    .fp-range-marker { stroke:#f8fafc; stroke-width:1.2; }
    .fp-range-label { fill:#cbd5e1; font-size:11px; font-weight:700; }
    .fp-range-summary { display:flex; flex-wrap:wrap; gap:8px 14px; margin:8px 0 2px; color:#94a3b8; font-size:12px; }
    .fp-range-summary strong { color:#e2e8f0; }
    .fp-key-marker { width:14px; height:0; border-top:2px dashed #cbd5e1; opacity:.8; }
  `;
  document.head.appendChild(style);
}

function fantasySurvivalPoints(player) {
  return (player?.curve || [])
    .map(point => ({
      x: Number(point.x),
      probability: Number(point.survival),
    }))
    .filter(point => Number.isFinite(point.x) && Number.isFinite(point.probability));
}

function fantasyRangeMarks(series, xScale, yScale, dimensions, explorer) {
  const { top, height, bottom } = dimensions;
  const showLabels = series.length === 1;
  const marks = [
    { key: 'floor', label: 'Floor', survival: 0.90 },
    { key: 'mid', label: 'Mid', survival: 0.50 },
    { key: 'ceiling', label: 'Ceiling', survival: 0.10 },
  ];

  return series.map(({ player }) => {
    const colorIndex = explorer.players.findIndex(row => row.name === player.name);
    const color = curveColor(colorIndex);
    return marks.map(mark => {
      const value = Number(player[mark.key]);
      if (!Number.isFinite(value)) return '';
      const x = xScale(value);
      const y = yScale(mark.survival);
      const label = showLabels
        ? `<text class="fp-range-label" x="${x}" y="${top + 12}" text-anchor="middle">${mark.label} ${value.toFixed(1)}</text>`
        : '';
      return `<g>
        <line class="fp-range-guide" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" stroke="${color}">
          <title>${escapeHtml(player.name)} · ${mark.label} ${value.toFixed(2)}</title>
        </line>
        <circle class="fp-range-marker" cx="${x}" cy="${y}" r="4.5" fill="${color}">
          <title>${escapeHtml(player.name)} · ${mark.label} ${value.toFixed(2)} · ${formatChartProbability(mark.survival)} chance to reach or exceed</title>
        </circle>
        ${label}
      </g>`;
    }).join('');
  }).join('');
}

function fantasyRangeSummary(series, explorer) {
  return `<div class="fp-range-summary">${series.map(({ player }) => {
    const colorIndex = explorer.players.findIndex(row => row.name === player.name);
    return `<span><span class="legend-dot" style="background:${curveColor(colorIndex)}"></span><strong>${escapeHtml(player.name)}</strong> · Floor ${fmt(player.floor)} · Mid ${fmt(player.mid)} · Ceiling ${fmt(player.ceiling)}</span>`;
  }).join('')}</div>`;
}

function renderFantasyPointSurvivalGraph(explorer) {
  injectFantasyPointSurvivalStyles();
  const area = $('graphChartArea');
  if (!area) return;

  const selected = explorer.players.filter(player =>
    explorer.selectedPlayers.has(player.name) && explorer.selectedPositions.has(player.pos)
  );
  const series = selected
    .map(player => ({ player, points: fantasySurvivalPoints(player) }))
    .filter(item => item.points.length);

  $('graphTitle').textContent = 'Fantasy points';
  $('graphSubtitle').textContent = 'x = fantasy point threshold · y = probability of scoring at least x';

  if (!series.length) {
    area.innerHTML = '<div class="graph-empty">No selected players have fantasy-point samples.</div>';
    return;
  }

  const width = 900, height = 440, left = 68, right = 20, top = 34, bottom = 54;
  const curveXs = series.flatMap(item => item.points.map(point => point.x));
  const rangeXs = series.flatMap(({ player }) => [player.floor, player.mid, player.ceiling])
    .map(Number)
    .filter(Number.isFinite);
  const minX = Math.min(0, ...curveXs, ...rangeXs);
  const maxX = Math.max(1, ...curveXs, ...rangeXs);
  const spanX = Math.max(maxX - minX, 1);
  const xScale = x => left + ((x - minX) / spanX) * (width - left - right);
  const yScale = probability => top + (1 - probability) * (height - top - bottom);

  let grid = '';
  for (let i = 0; i <= 5; i++) {
    const xValue = minX + spanX * i / 5;
    const x = xScale(xValue);
    const digits = spanX <= 8 && !Number.isInteger(xValue) ? 1 : 0;
    grid += `<line class="chart-grid" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" />`;
    grid += `<text class="chart-label" x="${x}" y="${height-22}" text-anchor="middle">${xValue.toFixed(digits)}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const probability = 1 - i / 4;
    const y = yScale(probability);
    grid += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" />`;
    grid += `<text class="chart-label" x="${left-10}" y="${y+4}" text-anchor="end">${formatChartProbability(probability)}</text>`;
  }

  const paths = series.map(({ player, points }) => {
    const colorIndex = explorer.players.findIndex(row => row.name === player.name);
    return `<path d="${scoreProbabilityPath(points, xScale, yScale)}" fill="none" stroke="${curveColor(colorIndex)}" stroke-width="2.7" stroke-linejoin="round" stroke-linecap="round" />`;
  }).join('');
  const rangeMarks = fantasyRangeMarks(series, xScale, yScale, { top, height, bottom }, explorer);
  const legend = series.map(({ player }) => {
    const colorIndex = explorer.players.findIndex(row => row.name === player.name);
    return `<button class="legend-player player-link" data-player="${escapeHtml(player.name)}" type="button"><span class="legend-dot" style="background:${curveColor(colorIndex)}"></span>${escapeHtml(player.name)}</button>`;
  }).join('');

  area.innerHTML = `<p class="chart-explainer">Empirical survival curve from the full 4,000 projection samples. The line shows <strong>P(Fantasy Points ≥ x)</strong>; Floor / Mid / Ceiling are the unchanged P10 / P50 / P90 values from those same samples.</p>
    <div class="graph-visual-key">
      <span class="graph-key-item"><span class="graph-key-line"></span>sample survival curve</span>
      <span class="graph-key-item"><span class="fp-key-marker"></span>Floor / Mid / Ceiling</span>
    </div>
    <div class="chart-wrap"><svg class="compare-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Fantasy point survival probability graph">
      ${grid}${paths}${rangeMarks}
      <text class="chart-axis-title" x="${(left + width-right)/2}" y="${height-3}" text-anchor="middle">Fantasy point threshold</text>
      <text class="chart-axis-title" transform="translate(16 ${(top+height-bottom)/2}) rotate(-90)" text-anchor="middle">Probability of scoring at least x</text>
    </svg></div>
    ${fantasyRangeSummary(series, explorer)}
    <div class="curve-legend">${legend}</div>`;
}

const renderGraphChartWithoutFantasySurvival = renderGraphChart;
renderGraphChart = function renderGraphChartWithFantasySurvival(explorer) {
  if (explorer.metric === 'fantasy_points') {
    renderFantasyPointSurvivalGraph(explorer);
    return;
  }
  renderGraphChartWithoutFantasySurvival(explorer);
};
