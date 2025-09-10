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

async function openPlayerDetails(name, week) {
  showDetails('Player Details', '<div class="status"><span class="spinner"></span> Loading...</div>');
  var url = apiUrl('/player/odds', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week: week,
    name: name,
    mode: getDataMode()
  });
  var resp = await fetchJSON(url);
  if (!resp.ok) { showDetails('Player Details', '<div class="status">Failed to load.</div>'); return; }
  var data = resp.data || {};
  var p = data.player || {};
  var primary = data.primary_order || [];
  var markets = data.markets || {};
  var head = '<div><strong>' + (p.name || name) + '</strong> <span class="muted">' + (p.pos || '') + ' · ' + (p.team || '') + '</span></div>';
  var primaryHtml = primary.map(function(k){ return renderMarketBlock(k, markets[k]); }).join('');
  if (!primaryHtml) primaryHtml = '<div class="muted">No primary markets.</div>';
  var others = (data.all_order || []).filter(function(k){ return primary.indexOf(k) === -1; });
  var otherHtml = others.map(function(k){ return renderMarketBlock(k, markets[k]); }).join('');
  if (!otherHtml) otherHtml = '<div class="muted">No other markets.</div>';
  var html = [head, '<h4>Primary Markets</h4>', primaryHtml, '<h4>Other Markets</h4>', otherHtml].join('');
  showDetails('Player Details', html);
}

function renderMarketBlock(key, payload) {
  if (!payload) return '';
  var s = payload.summary || {}; var mean = payload.mean_stat; var impact = payload.impact_score || 0;
  var hdr = '<div style="margin:6px 0;"><strong>' + key + '</strong> <span class="pill">impact ' + impact.toFixed(2) + '</span> '
    + '<span class="muted">mean: ' + (mean!=null ? Number(mean).toFixed(2) : '–')
    + ' · thr: ' + Number(s.avg_threshold||0).toFixed(2)
    + ' · pO: ' + Number(s.avg_over_prob||0).toFixed(2)
    + ' · pU: ' + Number(s.avg_under_prob||0).toFixed(2)
    + ' · n=' + (s.samples||0) + '</span></div>';
  var rows = (payload.books || []).map(function(b){
    return '<tr>'
      + '<td>' + (b.book||'') + '</td>'
      + '<td>' + (b.over?Number(b.over.odds).toFixed(2):'–') + '</td>'
      + '<td>' + (b.over && b.over.point!=null?Number(b.over.point).toFixed(2):'–') + '</td>'
      + '<td>' + (b.under?Number(b.under.odds).toFixed(2):'–') + '</td>'
      + '<td>' + (b.under && b.under.point!=null?Number(b.under.point).toFixed(2):'–') + '</td>'
      + '</tr>';
  }).join('');
  var table = '<table><thead><tr><th>Book</th><th>Over Odds</th><th>Over Pt</th><th>Under Odds</th><th>Under Pt</th></tr></thead><tbody>' + rows + '</tbody></table>';
  return hdr + table;
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
  var blocks = games.map(function(g){
    var hdr = '<div style="margin:6px 0;"><strong>' + defense + '</strong> vs <strong>' + g.opponent + '</strong> '
      + '<span class="muted">' + (g.commence_time||'') + '</span> '
      + '<span class="pill">median ' + (g.implied_total_median!=null?Number(g.implied_total_median).toFixed(2):'–') + '</span></div>';
    var rows = (g.books||[]).map(function(b){
      return '<tr>'
        + '<td>' + (b.book||'') + '</td>'
        + '<td>' + (b.total_point!=null?Number(b.total_point).toFixed(2):'–') + '</td>'
        + '<td>' + (b.opponent_spread!=null?Number(b.opponent_spread).toFixed(2):'–') + '</td>'
        + '<td>' + (b.opponent_implied!=null?Number(b.opponent_implied).toFixed(2):'–') + '</td>'
        + '</tr>';
    }).join('');
    var table = '<table><thead><tr><th>Book</th><th>Total</th><th>Opp Spread</th><th>Opp Implied</th></tr></thead><tbody>' + rows + '</tbody></table>';
    return hdr + table;
  }).join('');
  if (!blocks) blocks = '<div class="muted">No games found for this defense.</div>';
  showDetails('Defense Details', blocks);
}

// Event delegation to open details on click in tables
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

  function attachDefenseHandler(containerId, week) {
    var el = document.getElementById(containerId); if (!el) return;
    el.addEventListener('click', function(e){
      var td = e.target.closest('td'); if (!td) return;
      if (td.cellIndex !== 0) return;
      var def = (td.textContent || '').trim(); if (!def) return;
      openDefenseDetails(def, week);
    });
  }
  attachDefenseHandler('defenses-this', 'this');
  attachDefenseHandler('defenses-next', 'next');
});
