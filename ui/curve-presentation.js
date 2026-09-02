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
  const step = 0.05;
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

function renderComparison(players) {
  const withCurves = players
    .filter(player => player.curve?.length)
    .map(player => ({ ...player, displayCurve: scoreProbabilityCurve(player.curve) }))
    .filter(player => player.displayCurve.length);
  if (!withCurves.length) return '<div class="empty">No player curves available.</div>';

  const width = 900, height = 430, left = 58, right = 18, top = 20, bottom = 46;
  const minX = Math.min(...withCurves.flatMap(player => player.displayCurve.map(point => point.x)), 0);
  const maxX = Math.max(...withCurves.flatMap(player => player.displayCurve.map(point => point.x)), 1);
  const spanX = Math.max(maxX - minX, 1);
  const yMax = niceProbabilityMax(withCurves.map(player => player.displayCurve));
  const xScale = x => left + ((x - minX) / spanX) * (width - left - right);
  const yScale = y => top + (1 - y / yMax) * (height - top - bottom);
  let grid = '';
  for (let i = 0; i <= 5; i++) {
    const xValue = minX + spanX * i / 5;
    const x = xScale(xValue);
    grid += `<line class="chart-grid" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" />`;
    grid += `<text class="chart-label" x="${x}" y="${height-18}" text-anchor="middle">${xValue.toFixed(0)}</text>`;
  }
  for (let i = 0; i <= 4; i++) {
    const probability = yMax * (1 - i / 4);
    const y = yScale(probability);
    grid += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" />`;
    grid += `<text class="chart-label" x="${left-10}" y="${y+4}" text-anchor="end">${formatChartProbability(probability)}</text>`;
  }

  const paths = withCurves.map((player, index) =>
    `<path d="${scoreProbabilityPath(player.displayCurve, xScale, yScale)}" fill="none" stroke="${curveColor(index)}" stroke-width="2.5" />`
  ).join('');
  const legend = withCurves.map((player, index) =>
    `<button class="legend-player player-link" data-player="${escapeHtml(player.name)}" type="button"><span class="legend-dot" style="background:${curveColor(index)}"></span>${escapeHtml(player.name)}</button>`
  ).join('');

  return `<p class="chart-explainer">Each line shows the probability of finishing within a <strong>1-point bucket centered on x (x ± 0.5 FP)</strong>, derived only from the backend curve. Floor / Mid / Ceiling calculations are unchanged. Click a player in the legend for the source lines.</p>
    <div class="chart-wrap"><svg class="compare-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Roster fantasy point score probability curves">
      ${grid}${paths}
      <text class="chart-axis-title" x="${(left + width-right)/2}" y="${height-2}" text-anchor="middle">Fantasy points</text>
      <text class="chart-axis-title" transform="translate(14 ${(top+height-bottom)/2}) rotate(-90)" text-anchor="middle">Probability near x</text>
    </svg></div>
    <div class="curve-legend">${legend}</div>`;
}
