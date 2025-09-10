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
  return (val==null || Number.isNaN(Number(val))) ? '-' : Number(val).toFixed(digits);
}

function _escapeHtml(s) {
  try {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  } catch (e) {
    return '';
  }
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
    '<div class="market"summary- aria-expanded="false" data-target="mk_', safeKey, '">',
      '<div class="title">', _prettyMarketLabel(key), '</div>',
      '<div class="meta">predicted: ', (mean!=null ? _fmt(mean) : 'â€”'),
      ' <span class="pill">impact ', _fmt(impact), '</span>',
      s && (s.samples!=null) ? (' <span class="pill">n ' + (s.samples||0) + '</span>') : '',
      '</div>',
      '<div class="chev">&#9656;</div>',
    '</div>'
  ].join('');
  var rows = (payload.books || []).map(function(b){
    return '<tr>'
      + '<td>' + (b.book||'') + '</td>'
      + '<td>' + (b.over && b.over.odds!=null?_fmt(b.over.odds):'â€”') + '</td>'
      + '<td>' + (b.over && b.over.point!=null?_fmt(b.over.point):'â€”') + '</td>'
      + '<td>' + (b.under && b.under.odds!=null?_fmt(b.under.odds):'â€”') + '</td>'
      + '<td>' + (b.under && b.under.point!=null?_fmt(b.under.point):'â€”') + '</td>'
      + '</tr>';
  }).join('');
  var table = '<table><thead><tr><th>Book</th><th>Over Odds</th><th>Over Pt</th><th>Under Odds</th><th>Under Pt</th></tr></thead><tbody>' + rows + '</tbody></table>';
  return '<div class="market">' + header + '<div id="mk_' + safeKey + '" class="market"details hidden->' + table + '</div></div>';
}

// New clean renderer used by redesigned modal
function renderMarketBlock2(key, payload) {
  if (!payload) return '';
  var s = payload.summary || {}; var mean = payload.mean_stat; var impact = payload.impact_score || 0;
  var safeKey = (key || '').replace(/[^a-z0-9_]/gi, '_');
  var header = [
    '<div class="market-summary" aria-expanded="false" data-target="mk_', safeKey, '">',
      '<div class="title">', _prettyMarketLabel(key), '</div>',
      '<div class="meta">predicted: ', (mean!=null ? _fmt(mean) : '-'),
      (s && (s.samples!=null) ? (' <span class="pill">n ' + (s.samples||0) + '</span>') : ''),
      ' <span class="pill">impact ', _fmt(impact), '</span>',
      '</div>',
      '<div class="chev">&#9656;</div>',
    '</div>'
  ].join('');
  var rows = (payload.books || []).map(function(b){
    return '<tr>'
      + '<td>' + (b.book||'') + '</td>'
      + '<td>' + (b.over && b.over.odds!=null?_fmt(b.over.odds):'-') + '</td>'
      + '<td>' + (b.over && b.over.point!=null?_fmt(b.over.point):'-') + '</td>'
      + '<td>' + (b.under && b.under.odds!=null?_fmt(b.under.odds):'-') + '</td>'
      + '<td>' + (b.under && b.under.point!=null?_fmt(b.under.point):'-') + '</td>'
      + '</tr>';
  }).join('');
  var table = '<table><thead><tr><th>Book</th><th>Over Odds</th><th>Over Pt</th><th>Under Odds</th><th>Under Pt</th></tr></thead><tbody>' + rows + '</tbody></table>';
  return '<div class="market">' + header + '<div id="mk_' + safeKey + '" class="market-details hidden">' + table + '</div></div>';
}

async function openPlayerDetails(name, week) {
  try {
    var n = String(name||'');
    n = n.replace(/[\u00B7\u2022\u2219]/g,' ').replace(/[\u00C2]/g,'');
    var STAT_LABELS = ['Any TD','Pass Yds','Pass TDs','INTs','Rush Yds','Rec','Rec Yds'];
    var idx = -1;
    for (var i=0;i<STAT_LABELS.length;i++){ var k = STAT_LABELS[i]; var p = n.indexOf(' '+k); if (p > 0) { idx = (idx<0? p : Math.min(idx,p)); } }
    if (idx > 0) n = n.substring(0, idx);
    n = n.replace(/\s+/g,' ').trim();
    if (n) name = n;
  } catch (e) {}

  showDetails('Player Details', '<div class="status"><span class="spinner"></span> Loading...</div>');
  // Fetch odds detail + projections for fantasy points trio
  var oddsUrl = apiUrl('/player/odds', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week: week,
    name: name,
    region: 'us,us2',
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

  var head = '<div class="player-head">'
    + '<div class="player-name">' + _escapeHtml(p.name || name) + '</div>'
    + '<div class="player-meta">' + _escapeHtml(p.pos || '') + ' · ' + _escapeHtml(p.team || '') + '</div>'
    + '</div>';
  var predicted = ''
    + '<div class="details-section">'
    +   '<div class="section-title">Fantasy Points</div>'
    +   '<div class="cards">'
    +     '<div class="card floor"><div class="label">Floor</div><div class="value">' + _fmt(floor) + '</div></div>'
    +     '<div class="card mid"><div class="label">Mid</div><div class="value">' + _fmt(mid) + '</div></div>'
    +     '<div class="card ceiling"><div class="label">Ceiling</div><div class="value">' + _fmt(ceiling) + '</div></div>'
    +   '</div>'
    + '</div>';

  // Stat coverage summary for this position
  function expectedForPos(pos){
    switch((pos||'').toUpperCase()){
      case 'QB': return ['player_pass_yds','player_pass_tds','player_pass_interceptions','player_rush_yds'];
      case 'RB': return ['player_rush_yds','player_anytime_td','player_receptions','player_reception_yds'];
      case 'WR': return ['player_receptions','player_reception_yds','player_anytime_td'];
      case 'TE': return ['player_receptions','player_reception_yds','player_anytime_td'];
      default: return ['player_anytime_td'];
    }
  }
  var mkeys = Object.keys(markets||{});
  var present = [];
  var fallback = [];
  var missing = [];
  expectedForPos(p.pos).forEach(function(k){
    if (mkeys.indexOf(k) >= 0) {
      if (markets[k] && markets[k].summary) present.push(k); else fallback.push(k);
    } else missing.push(k);
  });
  var covHtml = [
    '<div class="details-section">',
      '<div class="section-title">Coverage</div>',
      '<div class="chips">',
        present.map(function(k){return '<span class="chip ok" title="OK">'+_prettyMarketLabel(k)+'</span>';}).join(' '),
        (fallback.length? (' ' + fallback.map(function(k){return '<span class="chip warn" title="Used fallback (no prob summary)">'+_prettyMarketLabel(k)+'</span>';}).join(' ')) : ''),
        (missing.length? (' ' + missing.map(function(k){return '<span class="chip crit" title="Missing odds/market">'+_prettyMarketLabel(k)+'</span>';}).join(' ')) : ''),
      '</div>',
    '</div>'
  ].join('');

  var primaryHtml = primary.map(function(k){ return renderMarketBlock2(k, markets[k]); }).join('');
  if (!primaryHtml) primaryHtml = '<div class="muted">No primary markets.</div>';
  var others = (data.all_order || []).filter(function(k){ return primary.indexOf(k) === -1; });
  var otherHtml = others.map(function(k){ return renderMarketBlock2(k, markets[k]); }).join('');
  if (!otherHtml) otherHtml = '<div class="muted">No other markets.</div>';
  var debugHtml = renderRawOddsSection(data.raw_odds);
  var marketsHtml = [
    '<div class="details-section">',
      '<div class="section-title">Primary Markets</div>',
      '<div class="market-list">', primaryHtml || '<div class="muted">No primary markets.</div>', '</div>',
    '</div>',
    '<div class="details-section">',
      '<div class="section-title">Other Markets</div>',
      '<div class="market-list">', otherHtml || '<div class="muted">No other markets.</div>', '</div>',
    '</div>'
  ].join('');
  var html = [
    '<div class="details-content">',
      '<div>', head, predicted, covHtml, '</div>',
      '<div>', marketsHtml, '</div>',
    '</div>',
    debugHtml
  ].join('');
  showDetails('Player Details', html);
}

async function openDefenseDetails(defense, week) {
  showDetails('Defense Details', '<div class="status"><span class="spinner"></span> Loading...</div>');
  var url = apiUrl('/defense/odds', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week: week,
    defense: defense,
    region: 'us,us2',
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
        '<div class="title">', _escapeHtml(defense), ' vs ', _escapeHtml(g.opponent||''), '</div>',
        '<div class="meta">', _escapeHtml(_formatISOToLocal(g.commence_time||'')), ' &middot; Opp Implied Median: <strong>', _fmt(g.implied_total_median), '</strong></div>',
        '<div class="chev">&#9656;</div>',
      '</div>'
    ].join('');
    var rows = (g.books||[]).map(function(b){
      return '<tr>'
        + '<td>' + (b.book||'') + '</td>'
        + '<td>' + (b.total_point!=null?_fmt(b.total_point):'â€”') + '</td>'
        + '<td>' + (b.opponent_spread!=null?_fmt(b.opponent_spread):'â€”') + '</td>'
        + '<td>' + (b.opponent_implied!=null?_fmt(b.opponent_implied):'â€”') + '</td>'
        + '</tr>';
    }).join('');
    var table = '<table><thead><tr><th>Book</th><th>Total</th><th>Opp Spread</th><th>Opp Implied</th></tr></thead><tbody>' + rows + '</tbody></table>';
    return '<div class="market">' + header + '<div id="' + id + '" class="market-details hidden">' + table + '</div></div>';
  }).join('');
  if (!blocks) blocks = '<div class="muted">No games found for this defense.</div>';
  var debugHtml = renderRawOddsSection(data.raw_odds);
  var html = '<div class="details-section"><div class="section-title">' + _escapeHtml(defense) + ' &middot; Games This Week</div>' + blocks + '</div>' + debugHtml;
  showDetails('Defense Details', html);
}

// Render deeply nested, collapsible view of raw odds (events -> bookmakers -> markets -> outcomes)
function renderRawOddsSection(raw) {
  try {
    var events = [];
    if (!raw) raw = {};
    if (Array.isArray(raw)) {
      events = raw.map(function(ev){ return { id: ev && ev.id || '', obj: ev }; });
    } else if (typeof raw === 'object') {
      events = Object.keys(raw).map(function(k){ return { id: k, obj: raw[k] }; });
    }
    var out = ['<div class="details-section">', '<div class="section-title">Debug: Raw Odds</div>'];
    if (!events.length) {
      out.push('<div class="muted">No raw odds available.</div>', '</div>');
      return out.join('');
    }
    events.forEach(function(item, eidx){
      var arr = Array.isArray(item.obj) ? item.obj : [item.obj];
      arr.forEach(function(ev, sub){
        if (!ev) return;
        var eid = _escapeHtml(ev.id || item.id || (''+eidx+'_'+sub));
        var hdrTitle = (ev.home_team && ev.away_team) ? (_escapeHtml(ev.away_team) + ' @ ' + _escapeHtml(ev.home_team)) : ('Event ' + eid);
        var meta = (ev.commence_time ? _escapeHtml(_formatISOToLocal(ev.commence_time)) + ' &middot; ' : '') + (ev.sport_key ? _escapeHtml(ev.sport_key) : '');
        var evHeader = '<div class="market-summary" aria-expanded="false" data-target="ev_' + eid + '">' +
                       '<div class="title">' + hdrTitle + '</div>' +
                       '<div class="meta">' + meta + '</div>' +
                       '<div class="chev">&#9656;</div></div>';
        var bms = Array.isArray(ev.bookmakers) ? ev.bookmakers : [];
        var bmBlocks = bms.map(function(bm, bidx){
          var bid = eid + '_bm_' + bidx;
          var btitle = _escapeHtml(bm.title || bm.key || ('Book ' + bidx));
          var bmeta = (bm.key ? _escapeHtml(bm.key) + ' &middot; ' : '') + (bm.last_update ? _escapeHtml(_formatISOToLocal(bm.last_update)) : '');
          var bmHeader = '<div class="market-summary" aria-expanded="false" data-target="' + bid + '">' +
                         '<div class="title">' + btitle + '</div>' +
                         '<div class="meta">' + bmeta + '</div>' +
                         '<div class="chev">&#9656;</div></div>';
          var mkts = Array.isArray(bm.markets) ? bm.markets : [];
          var mBlocks = mkts.map(function(mkt, midx){
            var mid = bid + '_m_' + midx;
            var mtitle = _escapeHtml(mkt.key || ('Market ' + midx));
            var mmeta = 'outcomes: ' + ((mkt.outcomes && mkt.outcomes.length) || 0);
          var mHeader = '<div class="market-summary" aria-expanded="false" data-target="' + mid + '">' +
                        '<div class="title">' + mtitle + '</div>' +
                        '<div class="meta">' + mmeta + '</div>' +
                        '<div class="chev">&#9656;</div></div>';
            var outcomes = Array.isArray(mkt.outcomes) ? mkt.outcomes : [];
            var rows = outcomes.map(function(o){
              var name = _escapeHtml(o.name);
              var price = (o.price!=null? _escapeHtml(o.price) : (o.odds!=null? _escapeHtml(o.odds): 'â€”'));
              var point = (o.point!=null? _escapeHtml(o.point) : 'â€”');
              var other = {};
              Object.keys(o||{}).forEach(function(k){ if (['name','price','odds','point'].indexOf(k)===-1) other[k]=o[k]; });
              var otherStr = (Object.keys(other).length? _escapeHtml(JSON.stringify(other)) : '');
              return '<tr><td>' + name + '</td><td>' + price + '</td><td>' + point + '</td><td>' + otherStr + '</td></tr>';
            }).join('');
            var table = '<table><thead><tr><th>Name</th><th>Price</th><th>Point</th><th>Other</th></tr></thead><tbody>' + rows + '</tbody></table>';
            var mRaw = '<div class="muted" style="margin-top:6px;">Raw market: <code>' + _escapeHtml(JSON.stringify(mkt)) + '</code></div>';
            return '<div class="market">' + mHeader + '<div id="' + mid + '" class="market-details hidden">' + table + mRaw + '</div></div>';
          }).join('');
          var bmRaw = '<div class="muted" style="margin-top:6px;">Raw bookmaker: <code>' + _escapeHtml(JSON.stringify(bm)) + '</code></div>';
          return '<div class="market">' + bmHeader + '<div id="' + bid + '" class="market-details hidden">' + mBlocks + bmRaw + '</div></div>';
        }).join('');
        var evRaw = '<div class="muted" style="margin-top:6px;">Raw event: <code>' + _escapeHtml(JSON.stringify(ev)) + '</code></div>';
        out.push('<div class="market">' + evHeader + '<div id="ev_' + eid + '" class="market-details hidden">' + bmBlocks + evRaw + '</div></div>');
      });
    });
    out.push('</div>');
    return out.join('');
  } catch (e) {
    var safe = '';
    try { safe = _escapeHtml(JSON.stringify(raw, null, 2)); } catch (ee) { safe = _escapeHtml(String(ee)); }
    return '<div class="details-section"><div class="section-title">Debug: Raw Odds (fallback)</div><pre class="debug">' + safe + '</pre></div>';
  }
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
      var nameEl = td.querySelector('.player-name'); var name = nameEl ? (nameEl.getAttribute('data-player') || nameEl.textContent || '').trim() : (td.textContent || '').trim(); if (!name) return;
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
      var nameCell = tr.cells[1] || tr.cells[0]; var nameEl = nameCell ? nameCell.querySelector('.player-name') : null; var name = nameEl ? (nameEl.getAttribute('data-player') || nameEl.textContent || '').trim() : ((nameCell && nameCell.textContent) || '').trim(); if (!name) return;
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

// Fix dropdown markup regression: override with correct HTML structure
(function(){
  function _fmtSafe(v){ return (v==null || Number.isNaN(Number(v))) ? '-' : Number(v).toFixed(2); }
  window.renderMarketBlock = function(key, payload) {
    if (!payload) return '';
    var s = payload.summary || {}; var mean = payload.mean_stat; var impact = payload.impact_score || 0;
    var safeKey = (key || '').replace(/[^a-z0-9_]/gi, '_');
    var header = [
      '<div class="market-summary" aria-expanded="false" data-target="mk_', safeKey, '">',
        '<div class="title">', _prettyMarketLabel(key), '</div>',
        '<div class="meta">predicted: ', (mean!=null ? _fmtSafe(mean) : '-'),
        ' <span class="pill">impact ', _fmtSafe(impact), '</span>',
        (s && s.samples!=null ? (' <span class="pill">n ' + (s.samples||0) + '</span>') : ''),
        '</div>',
        '<div class="chev">&#9656;</div>',
      '</div>'
    ].join('');
    var rows = (payload.books || []).map(function(b){
      return '<tr>'
        + '<td>' + (b.book||'') + '</td>'
        + '<td>' + (b.over && b.over.odds!=null?_fmtSafe(b.over.odds):'-') + '</td>'
        + '<td>' + (b.over && b.over.point!=null?_fmtSafe(b.over.point):'-') + '</td>'
        + '<td>' + (b.under && b.under.odds!=null?_fmtSafe(b.under.odds):'-') + '</td>'
        + '<td>' + (b.under && b.under.point!=null?_fmtSafe(b.under.point):'-') + '</td>'
        + '</tr>';
    }).join('');
    var table = '<table><thead><tr><th>Book</th><th>Over Odds</th><th>Over Pt</th><th>Under Odds</th><th>Under Pt</th></tr></thead><tbody>' + rows + '</tbody></table>';
    return '<div class="market">' + header + '<div id="mk_' + safeKey + '" class="market-details hidden">' + table + '</div></div>';
  };
})();

// ---- UI overrides to highlight incomplete players and avoid zero placeholders ----
// We override rendering helpers defined in script.js to add badges and dashes for missing stats.
(function(){
  // Defensive checks in case functions are renamed
  function fmtCell(v, inc) { return inc ? 'â€”' : Number(v||0).toFixed(2); }

  // Override renderPlayers to show incomplete badge and dashes
  if (typeof window.renderPlayers === 'function') {
    const _orig = window.renderPlayers;
    window.renderPlayers = function(containerId, players) {
      try {
        const c = document.getElementById(containerId);
        const rows = Array.isArray(players) ? players.slice() : [];
        if (!c) return _orig(containerId, players);
        if (!rows.length) { c.innerHTML = '<div class="status">No players found.</div>'; return; }
        rows.sort((a, b) => Number(b.mid || 0) - Number(a.mid || 0));
        const body = rows.map(r => {
          const inc = !!r.incomplete || (r.mid==null && r.floor==null && r.ceiling==null);
          const nameHtml = inc ? (r.name + ' <span class="pill pill"warn- title="Odds missing; stats incomplete">incomplete</span>') : r.name;
          return '<tr>'
            + '<td>' + (inc ? ('<span class="incomplete"name->' + nameHtml + '</span>') : nameHtml) + '</td>'
            + '<td>' + (r.pos || '') + '</td>'
            + '<td>' + fmtCell(r.floor, inc) + '</td>'
            + '<td>' + fmtCell(r.mid, inc) + '</td>'
            + '<td>' + fmtCell(r.ceiling, inc) + '</td>'
            + '</tr>';
        }).join('');
        c.innerHTML = '<table><thead><tr><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th></tr></thead><tbody>' + body + '</tbody></table>';
      } catch (e) { try { _orig(containerId, players); } catch (_) {} }
    }
  }

  // Override computeLineupFromPlayers to propagate incomplete flags
  if (typeof window.computeLineupFromPlayers === 'function') {
    window.computeLineupFromPlayers = function(players, target) {
      const buckets = { QB: [], RB: [], WR: [], TE: [] };
      for (const p of (players || [])) {
        if (buckets[p.pos]) buckets[p.pos].push(p);
      }
      const by = (t) => (a, b) => Number(b[t] || 0) - Number(a[t] || 0);
      Object.keys(buckets).forEach(pos => buckets[pos].sort(by(target)));
      const used = new Set();
      const take = (pos, n) => {
        const out = [];
        for (const p of buckets[pos]) {
          if (!used.has(p.name)) { out.push(p); used.add(p.name); if (out.length === n) break; }
        }
        return out;
      };
      const lineup = { QB: take('QB', 1), RB: take('RB', 2), WR: take('WR', 2), TE: take('TE', 1) };
      const flexPool = [];
      for (const pos of ['WR','RB','TE']) {
        for (const p of buckets[pos]) if (!used.has(p.name)) flexPool.push(p);
      }
      flexPool.sort(by(target));
      lineup.FLEX = flexPool.slice(0, 1);
      const rows = [];
      let total = 0;
      const add = (slot, p, countTotal=true) => {
        const pts = Number(p[target] || 0);
        if (countTotal) total += pts;
        rows.push({ slot, name: p.name, pos: p.pos, floor: (p.floor!=null?Number(p.floor):null), mid: (p.mid!=null?Number(p.mid):null), ceiling: (p.ceiling!=null?Number(p.ceiling):null), incomplete: !!p.incomplete });
      };
      lineup.QB.forEach(p => add('QB', p));
      lineup.RB.forEach(p => add('RB', p));
      lineup.WR.forEach(p => add('WR', p));
      lineup.TE.forEach(p => add('TE', p));
      lineup.FLEX.forEach(p => add('FLEX', p));
      // Append bench (all remaining players by target), but do not add to total
      const bench = [];
      for (const pos of ['QB','RB','WR','TE']) {
        for (const p of buckets[pos]) if (!used.has(p.name)) bench.push(p);
      }
      bench.sort(by(target));
      bench.forEach(p => add('BENCH', p, false));
      return { target, lineup: rows, total_points: Number(total.toFixed(2)) };
      }
  }

  // Override renderLineup to show incomplete badges and dashes
  if (typeof window.renderLineup === 'function') {
    const _origRL = window.renderLineup;
    window.renderLineup = function(containerId, title, payload) {
      try {
        const c = document.getElementById(containerId);
        const rows = (payload && payload.lineup) || [];
        const target = (payload && payload.target) || 'mid';
        const total = Number((payload && payload.total_points) || 0);
        const ratelimit = (payload && payload.ratelimit) || '';
        const headerCols = '<th>Slot</th><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th>';
        const body = rows.map(r => {
          const inc = !!r.incomplete || (r.mid==null && r.floor==null && r.ceiling==null);
          const nameHtml = inc ? (r.name + ' <span class="pill pill"warn- title="Odds missing; stats incomplete">incomplete</span>') : r.name;
          const fmt = (v) => inc ? 'â€”' : Number(v||0).toFixed(2);
          return '<tr>'
            + '<td>' + (r.slot||'') + '</td>'
            + '<td>' + (inc ? ('<span class="incomplete"name->' + nameHtml + '</span>') : nameHtml) + '</td>'
            + '<td>' + (r.pos||'') + '</td>'
            + '<td>' + fmt(r.floor) + '</td>'
            + '<td>' + fmt(r.mid) + '</td>'
            + '<td>' + fmt(r.ceiling) + '</td>'
            + '</tr>';
        }).join('');
        c.innerHTML = [
          `<h3>${title} - target: ${target} (total: ${total.toFixed(2)})</h3>`,
          `<table><thead><tr>${headerCols}</tr></thead><tbody>`,
          body,
          '</tbody></table>',
          `<div class="status">RateLimit: ${ratelimit}</div>`
        ].join('\n');
      } catch (e) { try { _origRL(containerId, title, payload); } catch (_) {} }
    }
  }
})();

// Load overrides (for clearer incomplete indicators and bench rows)
try {
  document.addEventListener('DOMContentLoaded', function(){
    try {
      var s = document.createElement('script');
      s.src = '/ui/overrides.js';
      document.body.appendChild(s);
    } catch (e) { /* ignore */ }
  });
} catch (e) { /* ignore */ }





