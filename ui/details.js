(function () {
  const MARKET_LABELS = {
    player_pass_yds: 'Passing yards',
    player_pass_tds: 'Passing TDs',
    player_pass_interceptions: 'Interceptions',
    player_rush_yds: 'Rushing yards',
    player_receptions: 'Receptions',
    player_reception_yds: 'Receiving yards',
    player_anytime_td: 'Anytime TD',
  };

  function label(key) { return MARKET_LABELS[key] || key.replace(/^player_/, '').replaceAll('_', ' '); }
  function fmt(value, digits = 2) { return value == null ? '—' : Number(value).toFixed(digits); }

  function playerCurveSvg(curve) {
    if (!curve?.length) return '<div class="empty">No fantasy-points curve available.</div>';
    const width = 820, height = 330, left = 58, right = 18, top = 18, bottom = 44;
    const maxX = Math.max(...curve.map(point => Number(point.x) || 0), 1);
    const xScale = x => left + x / maxX * (width - left - right);
    const yScale = y => top + (1 - y) * (height - top - bottom);
    const path = curve.map((point, index) =>
      `${index ? 'L' : 'M'}${xScale(Number(point.x)).toFixed(1)},${yScale(Number(point.survival)).toFixed(1)}`
    ).join(' ');
    let grid = '';
    for (let i = 0; i <= 5; i++) {
      const xValue = maxX * i / 5;
      const x = xScale(xValue);
      grid += `<line class="chart-grid" x1="${x}" y1="${top}" x2="${x}" y2="${height-bottom}" />`;
      grid += `<text class="chart-label" x="${x}" y="${height-17}" text-anchor="middle">${xValue.toFixed(0)}</text>`;
    }
    for (let i = 0; i <= 4; i++) {
      const p = 1 - i / 4;
      const y = yScale(p);
      grid += `<line class="chart-grid" x1="${left}" y1="${y}" x2="${width-right}" y2="${y}" />`;
      grid += `<text class="chart-label" x="${left-10}" y="${y+4}" text-anchor="end">${Math.round(p*100)}%</text>`;
    }
    return `<div class="chart-wrap"><svg class="detail-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="Fantasy point survival curve">
      ${grid}<path class="primary-curve" d="${path}" />
      <text class="chart-axis-title" x="${(left + width-right)/2}" y="${height-2}" text-anchor="middle">Fantasy points</text>
      <text class="chart-axis-title" transform="translate(14 ${(top+height-bottom)/2}) rotate(-90)" text-anchor="middle">Probability of at least x</text>
    </svg></div>`;
  }

  function renderMarket(key, market) {
    const range = market.stat_range || [];
    const anchors = (market.anchors || []).map(anchor =>
      `<tr><td class="number">${fmt(anchor.threshold)}</td><td class="number">${(Number(anchor.survival) * 100).toFixed(1)}%</td></tr>`
    ).join('');
    const lines = (market.lines || []).map(line =>
      `<tr>
        <td>${escapeHtml(line.book || '')}</td>
        <td>${line.source === 'alternate' ? 'Alt' : 'Main'}</td>
        <td class="number">${fmt(line.point)}</td>
        <td class="number">${fmt(line.over_odds)}</td>
        <td class="number">${fmt(line.under_odds)}</td>
      </tr>`
    ).join('');
    return `<section class="market-section">
      <div class="market-heading">
        <div><h3>${escapeHtml(label(key))}</h3><div class="subtle">Stat 10th / 50th / 90th: ${fmt(range[0])} / ${fmt(range[1])} / ${fmt(range[2])}</div></div>
        <div class="expected-points">Expected FP <strong>${fmt(market.expected_points, 2)}</strong></div>
      </div>
      <div class="market-grid">
        <div>
          <h4>Consensus anchors</h4>
          <p class="small-note">Per-book prices are de-vigged, then the median probability at each threshold becomes an anchor in the stat distribution.</p>
          ${anchors ? `<table class="compact-table"><thead><tr><th>Threshold</th><th>P(over)</th></tr></thead><tbody>${anchors}</tbody></table>` : '<div class="empty">No consensus anchors.</div>'}
        </div>
        <div>
          <h4>Sportsbook lines used</h4>
          ${lines ? `<div class="table-scroll"><table class="compact-table"><thead><tr><th>Book</th><th>Line type</th><th>Point</th><th>Over odds</th><th>Under odds</th></tr></thead><tbody>${lines}</tbody></table></div>` : '<div class="empty">No source lines.</div>'}
        </div>
      </div>
    </section>`;
  }

  window.openPlayerDetails = async function openPlayerDetails(name, week) {
    $('detailsTitle').textContent = name;
    $('detailsBody').innerHTML = '<div class="loading"><span class="spinner"></span> Loading source lines…</div>';
    $('detailsOverlay').classList.remove('hidden');

    const { ok, data } = await fetchJSON(apiUrl('/player/odds', {
      ...identityParams(), week, name, mode: getDataMode(),
    }));
    if (!ok) {
      $('detailsBody').innerHTML = '<div class="empty">Could not load player details.</div>';
      return;
    }

    const player = data.player || { name };
    const projection = data.projection;
    $('detailsTitle').textContent = `${player.name || name} · ${player.pos || ''}`;
    $('rlHeader').textContent = formatRateLimit(data);

    if (!projection) {
      $('detailsBody').innerHTML = `<div class="player-meta-block">${escapeHtml(player.team || '')}</div>
        <div class="empty">No priced, scorable markets were found for this player in this week.</div>`;
      return;
    }

    const cards = `<div class="projection-cards">
      <div class="projection-card"><span>Floor</span><strong>${fmt(projection.floor)}</strong><small>10th percentile</small></div>
      <div class="projection-card emphasis"><span>Mid</span><strong>${fmt(projection.mid)}</strong><small>50th percentile</small></div>
      <div class="projection-card"><span>Ceiling</span><strong>${fmt(projection.ceiling)}</strong><small>90th percentile</small></div>
    </div>`;
    const marketHtml = Object.entries(data.markets || {}).map(([key, market]) => renderMarket(key, market)).join('');

    $('detailsBody').innerHTML = `<div class="player-meta-block">${escapeHtml(player.team || '')}</div>
      ${cards}
      <section class="curve-section">
        <h3>Fantasy-points probability curve</h3>
        <p class="small-note">This is the same backend curve used for the Floor / Mid / Ceiling report—not a curve reconstructed in the browser.</p>
        ${playerCurveSvg(projection.curve)}
      </section>
      <section class="source-section">
        <h3>What created this curve</h3>
        ${marketHtml || '<div class="empty">No contributing markets.</div>'}
      </section>`;
  };
})();