// Details modal helpers and on-demand odds detail viewers

function showDetails(title, html) {
  var overlay = document.getElementById('detailsOverlay');
  var body = document.getElementById('detailsBody');
  var ttl = document.getElementById('detailsTitle');
  if (ttl) ttl.textContent = title || 'Details';
  if (body) body.innerHTML = html || '';
  if (overlay) overlay.classList.remove('hidden');
}

function hideDetails() {
  var overlay = document.getElementById('detailsOverlay');
  if (overlay) overlay.classList.add('hidden');
}

function _fmt(val, digits=2) {
  return (val==null || Number.isNaN(Number(val))) ? '—' : Number(val).toFixed(digits);
}

function _prettyMarketLabel(key) {
  // Basic prettifier for OddsAPI market keys
  const map = {
    'player_pass_yds': 'Pass Yards',
    'player_pass_tds': 'Pass TDs',
    'player_pass_interceptions': 'Pass INTs',
    'player_rush_yds': 'Rush Yards',
    'player_anytime_td': 'Anytime TD',
    'player_receptions': 'Receptions',
    'player_reception_yds': 'Rec Yards'
  };
  if (map[key]) return map[key];
  try {
    return (key || '').replace(/^player_/, '').replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());
  } catch (e) {
    return key || '';
  }
}

// Collapsible market block rendering
function renderMarketBlock(key, payload) {
  if (!payload) return '';
  var s = payload.summary || {}; var mean = payload.mean_stat; var impact = payload.impact_score || 0;
  var safeKey = (key || '').replace(/[^a-z0-9_]/gi, '_');
  var header = [
    '<div class="market-summary" aria-expanded="false" data-target="mk_', safeKey, '">',
      '<div class="title">', _prettyMarketLabel(key), '</div>',
      '<div class="meta">predicted: ', (mean!=null ? _fmt(mean) : '—'),
      ' <span class="pill">impact ', _fmt(impact), '</span>',
      s && (s.samples!=null) ? (' <span class="pill">n ' + (s.samples||0) + '</span>') : '',
      '</div>',
      '<div class="chev">▶</div>',
    '</div>'
  ].join('');
  var rows = (payload.books || []).map(function(b){
    return '<tr>'
      + '<td>' + (b.book||'') + '</td>'
      + '<td>' + (b.over && b.over.odds!=null?_fmt(b.over.odds):'—') + '</td>'
      + '<td>' + (b.over && b.over.point!=null?_fmt(b.over.point):'—') + '</td>'
      + '<td>' + (b.under && b.under.odds!=null?_fmt(b.under.odds):'—') + '</td>'
      + '<td>' + (b.under && b.under.point!=null?_fmt(b.under.point):'—') + '</td>'
      + '</tr>';
  }).join('');
  var table = '<table><thead><tr><th>Book</th><th>Over Odds</th><th>Over Pt</th><th>Under Odds</th><th>Under Pt</th></tr></thead><tbody>' + rows + '</tbody></table>';
  return '<div class="market">' + header + '<div id="mk_' + safeKey + '" class="market-details hidden">' + table + '</div></div>';
}

async function openPlayerDetails(name, week) {
  showDetails('Player Details', '<div class="status"><span class="spinner"></span> Loading...</div>');
  // Fetch odds detail + projections for fantasy points trio
  var oddsUrl = apiUrl('/player/odds', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week: week,
    name: name,
    mode: getDataMode()
  });
  var projUrl = apiUrl('/projections', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week: week,
    mode: getDataMode()
  });
  var [resp, projResp] = await Promise.all([fetchJSON(oddsUrl), fetchJSON(projUrl)]);
  if (!resp.ok) { showDetails('Player Details', '<div class="status">Failed to load.</div>'); return; }
  var data = resp.data || {};
  var p = data.player || {};
  var primary = data.primary_order || [];
  var markets = data.markets || {};

  // Fantasy points trio from projections
  var floor = null, mid = null, ceiling = null;
  try {
    var players = [];
    if (projResp.ok && projResp.data) {
      if (Array.isArray(projResp.data.players)) players = projResp.data.players;
      else if (projResp.data.projections && projResp.data.projections[week]) players = projResp.data.projections[week].players || [];
    }
    var match = (players || []).find(function(r){ return (r && r.name) === (p.name || name); });
    if (match) { floor = match.floor; mid = match.mid; ceiling = match.ceiling; }
  } catch (e) { /* ignore */ }

  var head = '<div style="margin-bottom:6px;"><strong>' + (p.name || name) + '</strong> <span class="muted">' + (p.pos || '') + ' · ' + (p.team || '') + '</span></div>';
  var predicted = ''
    + '<div class="predicted">'
    +   '<div class="predicted-title">Fantasy Points</div>'
    +   '<div class="predicted-values">'
    +     '<div class="pv floor"><span class="label">Floor</span><span class="val">' + _fmt(floor) + '</span></div>'
    +     '<div class="pv mid"><span class="label">Mid</span><span class="val">' + _fmt(mid) + '</span></div>'
    +     '<div class="pv ceiling"><span class="label">Ceiling</span><span class="val">' + _fmt(ceiling) + '</span></div>'
    +   '</div>'
    + '</div>';

  var primaryHtml = primary.map(function(k){ return renderMarketBlock(k, markets[k]); }).join('');
  if (!primaryHtml) primaryHtml = '<div class="muted">No primary markets.</div>';
  var others = (data.all_order || []).filter(function(k){ return primary.indexOf(k) === -1; });
  var otherHtml = others.map(function(k){ return renderMarketBlock(k, markets[k]); }).join('');
  if (!otherHtml) otherHtml = '<div class="muted">No other markets.</div>';
  var html = [head, predicted, '<h4>Primary Markets</h4>', primaryHtml, '<h4>Other Markets</h4>', otherHtml].join('');
  showDetails('Player Details', html);
}

async function openDefenseDetails(defense, week) {
  showDetails('Defense Details', '<div class="status"><span class="spinner"></span> Loading...</div>');
  var url = apiUrl('/defense/odds', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week: week,
    defense: defense,
    mode: getDataMode()
  });
  var resp = await fetchJSON(url);
  if (!resp.ok) { showDetails('Defense Details', '<div class="status">Failed to load.</div>'); return; }
  var data = resp.data || {};
  var games = data.games || [];
  var blocks = games.map(function(g, idx){
    var id = 'def_' + idx;
    var header = [
      '<div class="market-summary" aria-expanded="false" data-target="', id, '">',
        '<div class="title">', defense, ' vs ', g.opponent, '</div>',
        '<div class="meta">', (g.commence_time||''), ' · Opp Implied Median: <strong>', _fmt(g.implied_total_median), '</strong></div>',
        '<div class="chev">▶</div>',
      '</div>'
    ].join('');
    var rows = (g.books||[]).map(function(b){
      return '<tr>'
        + '<td>' + (b.book||'') + '</td>'
        + '<td>' + (b.total_point!=null?_fmt(b.total_point):'—') + '</td>'
        + '<td>' + (b.opponent_spread!=null?_fmt(b.opponent_spread):'—') + '</td>'
        + '<td>' + (b.opponent_implied!=null?_fmt(b.opponent_implied):'—') + '</td>'
        + '</tr>';
    }).join('');
    var table = '<table><thead><tr><th>Book</th><th>Total</th><th>Opp Spread</th><th>Opp Implied</th></tr></thead><tbody>' + rows + '</tbody></table>';
    return '<div class="market">' + header + '<div id="' + id + '" class="market-details hidden">' + table + '</div></div>';
  }).join('');
  if (!blocks) blocks = '<div class="muted">No games found for this defense.</div>';
  var html = '<div style="margin-bottom:6px;"><strong>' + defense + '</strong> <span class="muted">games this week</span></div>' + blocks;
  showDetails('Defense Details', html);
}

// Event delegation to open details on click in tables and toggle panels
document.addEventListener('DOMContentLoaded', function(){
  var closeBtn = document.getElementById('detailsClose');
  if (closeBtn) closeBtn.addEventListener('click', hideDetails);
  var overlay = document.getElementById('detailsOverlay');
  if (overlay) overlay.addEventListener('click', function(e){
    // Close when clicking outside the inner box
    if (e.target && e.target.id === 'detailsOverlay') hideDetails();
  });
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape') hideDetails();
  });

  // Toggle collapsible market blocks inside details modal
  var body = document.getElementById('detailsBody');
  if (body) {
    body.addEventListener('click', function(e){
      var hdr = e.target.closest('.market-summary');
      if (!hdr) return;
      var tid = hdr.getAttribute('data-target');
      if (!tid) return;
      var panel = document.getElementById(tid);
      if (!panel) return;
      var expanded = hdr.getAttribute('aria-expanded') === 'true';
      hdr.setAttribute('aria-expanded', expanded ? 'false' : 'true');
      panel.classList.toggle('hidden');
    });
  }

  function attachNameHandler(containerId, nameColIndex, week) {
    var el = document.getElementById(containerId); if (!el) return;
    el.addEventListener('click', function(e){
      var td = e.target.closest('td'); if (!td) return;
      if (td.cellIndex !== nameColIndex) return;
      var name = (td.textContent || '').trim(); if (!name) return;
      openPlayerDetails(name, week);
    });
  }
  attachNameHandler('lineup-this', 1, 'this');
  attachNameHandler('lineup-next', 1, 'next');
  attachNameHandler('players-this', 0, 'this');
  attachNameHandler('players-next', 0, 'next');

  // Also allow clicking Floor/Mid/Ceiling cells to open player details
  function attachPlayerStatHandler(containerId, week, cols) {
    var el = document.getElementById(containerId); if (!el) return;
    el.addEventListener('click', function(e){
      var td = e.target.closest('td'); if (!td) return;
      if (!cols.includes(td.cellIndex)) return;
      // Find the name cell in the same row depending on table layout
      var tr = td.parentElement; if (!tr) return;
      // Try typical layouts: lineup: name at index 1; players: name at index 0
      var nameCell = tr.cells[1] || tr.cells[0];
      var name = (nameCell && nameCell.textContent || '').trim(); if (!name) return;
      // Determine week from containerId suffix
      openPlayerDetails(name, week);
    });
  }
  // lineup tables: columns [3,4,5] ; players tables: [2,3,4]
  attachPlayerStatHandler('lineup-this', 'this', [3,4,5]);
  attachPlayerStatHandler('lineup-next', 'next', [3,4,5]);
  attachPlayerStatHandler('players-this', 'this', [2,3,4]);
  attachPlayerStatHandler('players-next', 'next', [2,3,4]);

  function attachDefenseHandler(containerId, week) {
    var el = document.getElementById(containerId); if (!el) return;
    el.addEventListener('click', function(e){
      var td = e.target.closest('td'); if (!td) return;
      var tr = td.parentElement; if (!tr) return;
      // Allow clicking defense name (col 0) or implied median (col 3)
      if (td.cellIndex === 0 || td.cellIndex === 3) {
        var def = (tr.cells[0] && tr.cells[0].textContent || td.textContent || '').trim(); if (!def) return;
        openDefenseDetails(def, week);
      }
    });
  }
  attachDefenseHandler('defenses-this', 'this');
  attachDefenseHandler('defenses-next', 'next');
});
