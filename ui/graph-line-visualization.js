(function () {
  function formatThreshold(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '—';
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(1);
  }

  function formatProbability(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '—';
    return `${(numeric * 100).toFixed(1)}%`;
  }

  function formatOdds(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return '—';
    return numeric.toFixed(2);
  }

  function niceStep(span, targetTicks = 6) {
    if (!(span > 0)) return 1;
    const rough = span / targetTicks;
    const power = 10 ** Math.floor(Math.log10(rough));
    const scaled = rough / power;
    const multiplier = scaled <= 1 ? 1 : scaled <= 2 ? 2 : scaled <= 5 ? 5 : 10;
    return multiplier * power;
  }

  function statPath(graph, xScale, yScale) {
    const points = graph?.points || [];
    if (!points.length) return '';
    if (graph.kind === 'survival_count') {
      let path = `M${xScale(Number(points[0].x)).toFixed(1)},${yScale(Number(points[0].probability)).toFixed(1)}`;
      for (let index = 1; index < points.length; index++) {
        const point = points[index];
        const x = xScale(Number(point.x)).toFixed(1);
        const y = yScale(Number(point.probability)).toFixed(1);
        path += `H${x}V${y}`;
      }
      return path;
    }
    return scoreProbabilityPath(points, xScale, yScale);
  }

  function marketFor(explorer, playerName, metric) {
    return explorer.marketDetails?.get(playerName)?.[metric] || null;
  }

  function graphKeyHtml() {
    return `<div class="graph-provenance-key" aria-label="Graph key">
      <span><i class="graph-key-line"></i>Fitted probability curve</span>
      <span><i class="graph-key-book"></i>Individual book line</span>
      <span><i class="graph-key-anchor"></i>Consensus anchor</span>
    </div>`;
  }

  function provenanceDetailsHtml(explorer, series, metric) {
    if (metric === 'fantasy_points') return '';
    const players = series.map(({ player }) => {
      const market = marketFor(explorer, player.name, metric) || {};
      const lines = market.lines || [];
      const anchors = market.anchors || [];
      if (!lines.length && !anchors.length) return '';
      const rows = lines.map(line => `<tr>
        <td>${escapeHtml(line.book || '')}</td>
        <td>${line.source === 'alternate' ? 'Alternate' : 'Main'}</td>
        <td class="number">${formatThreshold(line.point)}</td>
        <td class="number">${formatOdds(line.over_odds)}</td>
        <td class="number">${formatOdds(line.under_odds)}</td>
        <td class="number">${formatProbability(line.fair_over)}</td>
      </tr>`).join('');
      const anchorChips = anchors.map(anchor =>
        `<span class="graph-anchor-chip">${formatThreshold(anchor.threshold)} → ${formatProbability(anchor.survival)}</span>`
      ).join('');
      return `<details class="graph-player-provenance">
        <summary>${escapeHtml(player.name)} <span>${lines.length} posted lines · ${anchors.length} consensus anchors</span></summary>
        <div class="graph-anchor-strip"><strong>Consensus:</strong>${anchorChips || '<span class="subtle">none</span>'}</div>
        <div class="table-scroll"><table class="compact-table graph-lines-table">
          <thead><tr><th>Book</th><th>Type</th><th>Threshold</th><th>Over</th><th>Under</th><th>Fair P(over)</th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </details>`;
    }).filter(Boolean).join('');
    if (!players) return '';
    const lineCount = series.reduce((total, { player }) => total + ((marketFor(explorer, player.name, metric)?.lines || []).length), 0);
    return `<details class="graph-provenance-panel" data-graph-provenance>
      <summary>Inspect the betting lines behind this curve <span>${lineCount} lines</span></summary>
      <p class="graph-provenance-note">Each book point is de-vigged first. Books at the same threshold are combined by median, then monotonicity is enforced to produce the larger consensus anchors. The fitted curve passes through/along those anchors and extends into the tails.</p>
      ${players}
    </details>`;
  }

  function renderStatGraph(explorer, metric, series) {
    const width = 940, height = 470, left = 76, right = 22, top = 28, bottom = 64;
    const allX = [];
    series.forEach(({ player, graph }) => {
      (graph.points || []).forEach(point => allX.push(Number(point.x)));
      const market = marketFor(explorer, player.name, metric) || {};
      (market.line_points || []).forEach(point => allX.push(Number(point.threshold)));
      (market.anchors || []).forEach(anchor => allX.push(Number(anchor.threshold)));
    });
    const validX = allX.filter(Number.isFinite);
    const rawMin = Math.min(...validX, 0);
    const rawMax = Math.max(...validX, 1);
    const step = niceStep(Math.max(rawMax - rawMin, 1));
    const xMin = Math.max(0, Math.floor(rawMin / step) * step);
    const xMax = Math.max(xMin + step, Math.ceil(rawMax / step) * step);
    const spanX = xMax - xMin;
    const xScale = x => left + ((x - xMin) / spanX) * (width - left - right);
    const yScale = y => top + (1 - y) * (height - top - bottom);

    let grid = '';
    for (let xValue = xMin; xValue <= xMax + step * 0.01; xValue += step) {
      const x = xScale(xValue);
      grid += `<line class="chart-grid" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" />`;
      grid += `<text class="chart-label graph-axis-value" x="${x}" y="${height-30}" text-anchor="middle">${formatThreshold(xValue)}</text>`;
    }
    [1, 0.75, 0.5, 0.25, 0].forEach(probability => {
      const y = yScale(probability);
      grid += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" />`;
      grid += `<text class="chart-label graph-axis-value" x="${left-12}" y="${y+4}" text-anchor="end">${Math.round(probability * 100)}%</text>`;
    });

    const guideLines = series.map(({ player }) => {
      const market = marketFor(explorer, player.name, metric) || {};
      const colorIndex = explorer.players.findIndex(row => row.name === player.name);
      const color = curveColor(colorIndex);
      return (market.anchors || []).map(anchor => {
        const x = xScale(Number(anchor.threshold));
        const y = yScale(Number(anchor.survival));
        return `<line class="graph-anchor-guide" x1="${x}" y1="${y}" x2="${x}" y2="${height-bottom}" stroke="${color}" />`;
      }).join('');
    }).join('');

    const paths = series.map(({ player, graph }) => {
      const colorIndex = explorer.players.findIndex(row => row.name === player.name);
      return `<path class="graph-fitted-curve" d="${statPath(graph, xScale, yScale)}" fill="none" stroke="${curveColor(colorIndex)}" />`;
    }).join('');

    const bookPoints = series.map(({ player }) => {
      const market = marketFor(explorer, player.name, metric) || {};
      const colorIndex = explorer.players.findIndex(row => row.name === player.name);
      const color = curveColor(colorIndex);
      return (market.line_points || []).map(point => {
        const x = xScale(Number(point.threshold));
        const y = yScale(Number(point.survival));
        return `<circle class="graph-book-point" cx="${x}" cy="${y}" r="4" stroke="${color}">
          <title>${escapeHtml(player.name)} · ${escapeHtml(point.book || '')}: over ${formatThreshold(point.threshold)} → fair ${formatProbability(point.survival)}</title>
        </circle>`;
      }).join('');
    }).join('');

    const anchors = series.map(({ player }) => {
      const market = marketFor(explorer, player.name, metric) || {};
      const colorIndex = explorer.players.findIndex(row => row.name === player.name);
      const color = curveColor(colorIndex);
      return (market.anchors || []).map(anchor => {
        const x = xScale(Number(anchor.threshold));
        const y = yScale(Number(anchor.survival));
        return `<circle class="graph-consensus-anchor" cx="${x}" cy="${y}" r="6" fill="${color}">
          <title>${escapeHtml(player.name)} consensus: over ${formatThreshold(anchor.threshold)} → ${formatProbability(anchor.survival)}</title>
        </circle>`;
      }).join('');
    }).join('');

    const legend = series.map(({ player }) => {
      const colorIndex = explorer.players.findIndex(row => row.name === player.name);
      return `<button class="legend-player player-link" data-player="${escapeHtml(player.name)}" type="button"><span class="legend-dot" style="background:${curveColor(colorIndex)}"></span>${escapeHtml(player.name)}</button>`;
    }).join('');

    return `<p class="chart-explainer">The curve answers <strong>“what is the chance this player exceeds x?”</strong> Hollow dots are individual de-vigged book lines; larger dots are the consensus anchors used to fit the distribution.</p>
      ${graphKeyHtml()}
      <div class="chart-wrap"><svg class="compare-chart graph-stat-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(graphLabel(metric))} sportsbook probability curve">
        ${grid}${guideLines}${paths}${bookPoints}${anchors}
        <text class="chart-axis-title" x="${(left + width-right)/2}" y="${height-5}" text-anchor="middle">${escapeHtml(graphLabel(metric))} threshold</text>
        <text class="chart-axis-title" transform="translate(18 ${(top+height-bottom)/2}) rotate(-90)" text-anchor="middle">Probability player exceeds threshold</text>
      </svg></div>
      <div class="curve-legend">${legend}</div>
      ${provenanceDetailsHtml(explorer, series, metric)}`;
  }

  const previousRenderGraphChart = renderGraphChart;
  renderGraphChart = function renderGraphWithLineProvenance(explorer) {
    const area = $('graphChartArea');
    if (!area) return;
    const metric = explorer.metric;
    const selected = explorer.players.filter(player =>
      explorer.selectedPlayers.has(player.name) && explorer.selectedPositions.has(player.pos)
    );
    const series = selected
      .map(player => ({ player, graph: explorer.graphs.get(player.name)?.[metric] }))
      .filter(item => item.graph?.points?.length);

    if (metric === 'fantasy_points') {
      previousRenderGraphChart(explorer);
      return;
    }

    $('graphTitle').textContent = graphLabel(metric);
    $('graphSubtitle').textContent = 'Sportsbook-implied probability of exceeding each stat threshold';
    if (!series.length) {
      area.innerHTML = '<div class="graph-empty">No selected players have data for this graph.</div>';
      return;
    }
    area.innerHTML = renderStatGraph(explorer, metric, series);
  };

  hydrateStatGraphs = async function hydrateGraphsWithLineProvenance(explorer) {
    explorer.marketDetails = new Map();
    await Promise.all(explorer.players.map(async player => {
      const details = await fetchGraphDetails(player, explorer.week);
      if (!details) return;
      const graphs = explorer.graphs.get(player.name) || {};
      const markets = {};
      Object.entries(details.markets || {}).forEach(([marketKey, market]) => {
        const graph = market?.graph;
        if (graph?.points?.length) graphs[marketKey] = graph;
        markets[marketKey] = market;
      });
      explorer.graphs.set(player.name, graphs);
      explorer.marketDetails.set(player.name, markets);
    }));

    if (window.__graphExplorer !== explorer || !$('graphExplorer')) return;
    const available = new Set(['fantasy_points']);
    explorer.graphs.forEach(graphs => Object.keys(graphs).forEach(key => available.add(key)));
    explorer.metrics = [...available].sort(graphSort);
    const note = $('graphLoadNote');
    if (note) note.textContent = `${explorer.metrics.length} graphs available`;
    renderMetricButtons(explorer);
    renderGraphChart(explorer);
  };

  const previousStyleInjector = injectGraphExplorerStyles;
  injectGraphExplorerStyles = function injectLineVisualizationStyles() {
    previousStyleInjector();
    if (document.getElementById('graphLineVisualizationStyles')) return;
    const style = document.createElement('style');
    style.id = 'graphLineVisualizationStyles';
    style.textContent = `
      .graph-stat-chart .chart-grid { opacity:.55; }
      .graph-axis-value { font-variant-numeric:tabular-nums; }
      .graph-fitted-curve { stroke-width:3.25; stroke-linecap:round; stroke-linejoin:round; }
      .graph-book-point { fill:#0f172a; stroke-width:2; opacity:.9; }
      .graph-consensus-anchor { stroke:#f8fafc; stroke-width:1.6; }
      .graph-anchor-guide { stroke-width:1; stroke-dasharray:4 5; opacity:.22; }
      .graph-provenance-key { display:flex; gap:18px; flex-wrap:wrap; align-items:center; margin:8px 0 12px; color:#94a3b8; font-size:12px; }
      .graph-provenance-key span { display:inline-flex; align-items:center; gap:7px; }
      .graph-key-line { width:22px; height:0; border-top:3px solid #cbd5e1; border-radius:2px; }
      .graph-key-book { width:10px; height:10px; border:2px solid #cbd5e1; border-radius:50%; background:#0f172a; }
      .graph-key-anchor { width:11px; height:11px; border:1.5px solid #f8fafc; border-radius:50%; background:#64748b; }
      .graph-provenance-panel { margin-top:16px; border:1px solid #263449; border-radius:10px; background:#0b1220; }
      .graph-provenance-panel > summary { cursor:pointer; padding:12px 14px; color:#e2e8f0; font-weight:600; }
      .graph-provenance-panel > summary span, .graph-player-provenance > summary span { color:#64748b; font-weight:400; margin-left:8px; font-size:12px; }
      .graph-provenance-note { margin:0; padding:0 14px 12px; color:#94a3b8; font-size:12px; line-height:1.5; }
      .graph-player-provenance { margin:0 12px 10px; border-top:1px solid #1e293b; }
      .graph-player-provenance > summary { cursor:pointer; padding:10px 2px; color:#cbd5e1; font-weight:600; }
      .graph-anchor-strip { display:flex; align-items:center; gap:7px; flex-wrap:wrap; padding:0 2px 10px; color:#94a3b8; font-size:12px; }
      .graph-anchor-chip { border:1px solid #334155; border-radius:999px; padding:3px 7px; color:#cbd5e1; }
      .graph-lines-table { margin-bottom:12px; }
      @media (max-width:760px) {
        .graph-provenance-key { gap:10px; }
        .graph-stat-chart { min-width:720px; }
      }
    `;
    document.head.appendChild(style);
  };
})();
