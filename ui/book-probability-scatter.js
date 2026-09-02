(function () {
  const SVG_NS = 'http://www.w3.org/2000/svg';

  function renderBookProbabilityPoints(explorer) {
    if (explorer.metric === 'fantasy_points') return;
    const svg = document.querySelector('#graphChartArea svg.compare-chart');
    if (!svg) return;

    const selected = explorer.players.filter(player =>
      explorer.selectedPlayers.has(player.name) && explorer.selectedPositions.has(player.pos)
    );
    const series = selected
      .map(player => ({ player, graph: explorer.graphs.get(player.name)?.[explorer.metric] }))
      .filter(item => item.graph?.points?.length);
    if (!series.length) return;

    const width = 900, height = 440, left = 68, right = 20, top = 24, bottom = 54;
    const sourceXs = series.flatMap(({ graph }) => [
      ...(graph.anchors || []).map(anchor => sourceThresholdX(explorer.metric, anchor.threshold)),
      ...(graph.lines || []).map(line => sourceThresholdX(explorer.metric, line.point)),
    ]).filter(Number.isFinite);
    const curveXs = series.flatMap(({ graph }) =>
      (graph.points || []).map(point => Number(point.x))
    ).filter(Number.isFinite);
    let minX = Math.min(...curveXs, ...sourceXs);
    let maxX = Math.max(...curveXs, ...sourceXs);
    const rawSpan = Math.max(maxX - minX, 1);
    const pad = rawSpan * 0.04;
    minX -= pad;
    maxX += pad;
    const spanX = Math.max(maxX - minX, 1);
    const xScale = x => left + ((x - minX) / spanX) * (width - left - right);
    const yScale = y => top + (1 - y) * (height - top - bottom);

    series.forEach(({ player, graph }) => {
      const colorIndex = explorer.players.findIndex(row => row.name === player.name);
      const color = curveColor(colorIndex);
      (graph.line_points || []).forEach(point => {
        const sourceX = sourceThresholdX(explorer.metric, point.threshold);
        const probability = Number(point.survival);
        if (!Number.isFinite(sourceX) || !Number.isFinite(probability)) return;
        const circle = document.createElementNS(SVG_NS, 'circle');
        circle.setAttribute('class', 'graph-book-probability-point');
        circle.setAttribute('cx', xScale(sourceX).toFixed(2));
        circle.setAttribute('cy', yScale(probability).toFixed(2));
        circle.setAttribute('r', '3.8');
        circle.setAttribute('fill', '#0f172a');
        circle.setAttribute('stroke', color);
        circle.setAttribute('stroke-width', '2');
        const title = document.createElementNS(SVG_NS, 'title');
        title.textContent = `${player.name} · ${point.book}: ${formatGraphNumber(point.threshold)} · fair over ${formatChartProbability(probability)}`;
        circle.appendChild(title);
        svg.appendChild(circle);
      });
    });

    const key = document.querySelector('#graphChartArea .graph-visual-key');
    if (key && !key.querySelector('.graph-key-book-point')) {
      key.insertAdjacentHTML(
        'beforeend',
        '<span class="graph-key-item"><span class="graph-key-book-point"></span>individual book fair probability</span>',
      );
    }
  }

  const baseRenderGraphEvidence = renderGraphEvidence;
  renderGraphEvidence = function renderGraphEvidenceWithFairPrices(explorer, series) {
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
      <td class="number">${line.fair_over == null ? '—' : formatChartProbability(Number(line.fair_over))}</td>
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
        <p class="graph-evidence-summary">For ${escapeHtml(selected.player.name)}, each book is first converted to a fair over probability. Those individual book probabilities are the hollow circles on the graph. Books at the same threshold are then combined into the consensus diamonds; monotonicity is enforced before the fitted curve is reconstructed. This lets you distinguish disagreement between books from the consensus shape itself.</p>
        <div class="graph-evidence-grid">
          <div>
            <h4>Consensus anchors</h4>
            ${anchorRows ? `<table class="compact-table"><thead><tr><th>Threshold</th><th>Fair P(over)</th></tr></thead><tbody>${anchorRows}</tbody></table>` : '<div class="empty">No consensus anchors.</div>'}
          </div>
          <div>
            <h4>Exact sportsbook lines</h4>
            ${lineRows ? `<div class="table-scroll"><table class="compact-table"><thead><tr><th>Book</th><th>Type</th><th>Line</th><th>Over odds</th><th>Under odds</th><th>Fair P(over)</th></tr></thead><tbody>${lineRows}</tbody></table></div>` : '<div class="empty">No source lines.</div>'}
          </div>
        </div>
      </div>` : ''}`;
  };

  const baseRenderGraphChart = renderGraphChart;
  renderGraphChart = function renderGraphChartWithBookPoints(explorer) {
    baseRenderGraphChart(explorer);
    renderBookProbabilityPoints(explorer);
  };

  hydrateStatGraphs = async function hydrateStatGraphsWithBookPoints(explorer) {
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
          line_points: market.line_points || [],
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
  };

  const baseInjectGraphExplorerStyles = injectGraphExplorerStyles;
  injectGraphExplorerStyles = function injectGraphExplorerStylesWithBookPoints() {
    baseInjectGraphExplorerStyles();
    if (document.getElementById('bookProbabilityScatterStyles')) return;
    const style = document.createElement('style');
    style.id = 'bookProbabilityScatterStyles';
    style.textContent = `
      .graph-book-probability-point { opacity:.92; }
      .graph-key-book-point { width:10px; height:10px; border:2px solid #cbd5e1; border-radius:50%; background:#0f172a; }
    `;
    document.head.appendChild(style);
  };

  void baseRenderGraphEvidence;
})();
