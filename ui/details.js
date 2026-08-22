// Details modal helpers and on-demand odds detail viewers

function showDetails(title, html) {
  var overlay = document.getElementById('detailsOverlay');
  var body = document.getElementById('detailsBody');
  var ttl = document.getElementById('detailsTitle');
  if (ttl) ttl.textContent = title || 'Details';
  if (body) body.innerHTML = html || '';
  if (overlay) overlay.classList.remove('hidden');
  try { history.pushState({ detailsOpen: true }, '', '#details'); } catch (e) {}
  // Focus trap and a11y
  try {
    var dialog = overlay && overlay.querySelector('.details-box');
    if (dialog) {
      dialog.setAttribute('role','dialog');
      dialog.setAttribute('aria-modal','true');
      dialog.setAttribute('aria-labelledby','detailsTitle');
      var focusables = dialog.querySelectorAll('a, button, input, select, textarea, [tabindex]:not([tabindex="-1"])');
      var first = focusables[0]; var last = focusables[focusables.length-1];
      if (first) first.focus();
      dialog.addEventListener('keydown', function(e){
        if (e.key === 'Tab') {
          if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last && last.focus(); }
          else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first && first.focus(); }
        }
      });
    }
  } catch (e) { /* ignore */ }
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

function _renderFpVisual(floor, mid, ceil) {
  try {
    var f = Number(floor||0), m = Number(mid||0), c = Number(ceil||0);
    // Use global FP range when available to keep all graphs comparable
    var gmax = null;
    try { if (window && window.GLOBAL_FP_RANGE) { gmax = Number(window.GLOBAL_FP_RANGE.maxX) || null; } } catch (e) {}
    var minX = 0;
    var maxX = (gmax && gmax > 0) ? gmax : (Math.max(c, m) + Math.abs(c-m)*0.5);
    if (maxX <= minX) { maxX = minX + 1; }
    var W = 600, H = 140, PAD = 14;
    var z85 = 1.036; // approx z for 85th
    var sigR = Math.max(0.1, Math.abs(c - m) / z85);
    var sigL = Math.max(0.1, Math.abs(m - f) / z85);
    function xScale(x){ return PAD + (x - minX) * (W - 2*PAD) / (maxX - minX); }
    function yScale(y){ return H - PAD - y * (H - 2*PAD); }
    function pdf(x){
      var s = (x >= m ? sigR : sigL);
      var v = Math.exp(-0.5 * Math.pow((x - m) / s, 2));
      return v;
    }
    // sample curve
    var N = 80; var pts = [];
    var maxY = 0;
    for (var i=0;i<=N;i++){
      var x = minX + (maxX-minX)*i/N;
      var y = pdf(x);
      if (y > maxY) maxY = y;
      pts.push([xScale(x), y]);
    }
    // normalize y to [0,1] and map to pixels
    var path = '';
    pts.forEach(function(p, i){ var X=p[0], Y=yScale((p[1]/(maxY||1))*1); path += (i?'L':'M') + X.toFixed(1) + ',' + Y.toFixed(1); });
    // close area to baseline
    var area = path + ' L ' + xScale(maxX).toFixed(1) + ',' + yScale(0).toFixed(1) + ' L ' + xScale(minX).toFixed(1) + ',' + yScale(0).toFixed(1) + ' Z';
    // Build gridlines (x: 5 ticks)
    var grid = (function(){ var parts=[]; for (var i=1;i<=5;i++){ var xv=minX + (maxX-minX)*i/6; parts.push('<line class="grid" x1="'+xScale(xv)+'" y1="'+yScale(0)+'" x2="'+xScale(xv)+'" y2="'+yScale(1)+'" />'); } return parts.join(''); })();
    var svg = [
      '<div class="fp-visual" data-min="', minX.toFixed(6),'" data-max="',maxX.toFixed(6),'" data-pad="',PAD,'" data-w="',W,'" data-h="',H,'" data-floor="',f,'" data-mid="',m,'" data-ceil="',c,'">',
        '<div class="vis-title">Fantasy Points (visual)</div>',
        '<div class="svg-wrap"><svg viewBox="0 0 ', W, ' ', H, '" preserveAspectRatio="none">',
          grid,
          '<line class="axis" x1="', xScale(minX), '" y1="', yScale(0), '" x2="', xScale(maxX), '" y2="', yScale(0), '" />',
          '<text class="axis-label" x="', xScale(maxX)-2, '" y="', yScale(0)+14, '" text-anchor="end">Fantasy Points (pts)</text>',
          '<text class="axis-label" transform="translate(12,', (H/2).toFixed(1), ') rotate(-90)" text-anchor="middle">Density</text>',
          '<path class="curve" d="', area, '" />',
          '<line class="marker" x1="', xScale(f), '" y1="', yScale(0), '" x2="', xScale(f), '" y2="', yScale(1), '" />',
          '<text class="axis-label" x="', xScale(f)+2, '" y="', yScale(1)+12, '">Floor ', _fmt(floor), '</text>',
          '<line class="marker" x1="', xScale(m), '" y1="', yScale(0), '" x2="', xScale(m), '" y2="', yScale(1), '" />',
          '<text class="axis-label" x="', xScale(m)+2, '" y="', yScale(1)+12, '">Mid ', _fmt(mid), '</text>',
          '<line class="marker" x1="', xScale(c), '" y1="', yScale(0), '" x2="', xScale(c), '" y2="', yScale(1), '" />',
          '<text class="axis-label" x="', xScale(c)+2, '" y="', yScale(1)+12, '">Ceil ', _fmt(ceil), '</text>',
          '<line class="hover-x" x1="0" y1="', yScale(1), '" x2="0" y2="', yScale(0), '" style="display:none" />',
          '<circle class="hover-dot" cx="0" cy="0" r="3" style="display:none" />',
        '</svg></div>',
        '<div class="legend">',
          '<span class="floor"><span class="dot"></span>Floor ', _fmt(floor), '</span>',
          '<span class="mid"><span class="dot"></span>Mid ', _fmt(mid), '</span>',
          '<span class="ceiling"><span class="dot"></span>Ceiling ', _fmt(ceil), '</span>',
        '</div>',
        '<div class="fp-tooltip" style="display:none; left:0; top:0;">x: 0, y: 0</div>',
      '</div>'
    ].join('');
    return svg;
  } catch (e) {
    return '';
  }
}

function _formatISOToLocal(iso) {
  try {
    var d = new Date(iso);
    if (String(d) === 'Invalid Date') return iso || '';
    return d.toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  } catch (e) { return iso || ''; }
}

function _weekdayKey(iso) {
  try { var d = new Date(iso); return d.toLocaleDateString([], { weekday: 'long' }); } catch (e) { return ''; }
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
      '<div class="meta">predicted: ', (mean!=null ? _fmt(mean) : '-'),
      (s && (s.samples!=null) ? (' <span class="pill">n ' + (s.samples||0) + '</span>') : ''),
      ' <span class="pill impact-pill" data-mkey="', _escapeHtml(key), '" data-safe="', safeKey, '" title="Click to show FP impact">impact ', _fmt(impact), '</span>',
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
  var fp = payload || {};
  var fpStrip = '<div id="imp_' + safeKey + '" class="impact-strip hidden">FP impact — Floor: <strong>' + _fmt(fp.fp_floor) + '</strong> · Mid: <strong>' + _fmt(fp.fp_mid) + '</strong> · Ceiling: <strong>' + _fmt(fp.fp_ceiling) + '</strong></div>';
  return '<div class="market">' + header + fpStrip + '<div id="mk_' + safeKey + '" class="market-details hidden">' + table + '</div></div>';
}

async function openPlayerDetails(name, week, opts) {
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

  if (!opts || !opts.noHistory) {
    showDetails('Player Details', '<div class="status"><span class="spinner"></span> Loading...</div>');
  } else {
    try {
      var ov0 = document.getElementById('detailsOverlay'); if (ov0) ov0.classList.remove('hidden');
      var tt0 = document.getElementById('detailsTitle'); if (tt0) tt0.textContent = 'Player Details';
      var bd0 = document.getElementById('detailsBody'); if (bd0) bd0.innerHTML = '<div class="status"><span class="spinner"></span> Loading...</div>';
    } catch (e) {}
  }
  // Fetch odds detail + projections for fantasy points trio
  var oddsUrl = apiUrl('/player/odds', {
    ...identityParams(),
    week: week,
    name: name,
    region: 'us,us2',
    mode: getDataMode()
  });
  var projUrl = apiUrl('/projections', {
    ...identityParams(),
    week: week,
    mode: getDataMode()
  });
  try {
    var players = [];
    if (projResp.ok && projResp.data) {
      if (Array.isArray(projResp.data.players)) players = projResp.data.players;
      else if (projResp.data.projections && projResp.data.projections[week]) players = projResp.data.projections[week].players || [];
    }
    // Update global FP range for consistent axes across views
    var gMaxAll = 0; (players||[]).forEach(function(r){ var cc = Number(r.ceiling||0); if (cc > gMaxAll) gMaxAll = cc; });
    if (!(gMaxAll > 0)) gMaxAll = 1;
    try { window.GLOBAL_FP_RANGE = { minX: 0, maxX: gMaxAll }; } catch (e) {}
  } catch (e) { /* ignore */ }
 
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
      + '</div>'
    + '<div class="details-section">' + _renderFpVisual(floor, mid, ceiling) + '</div>'
    + '<div class="details-section">'
    +   '<div class="btn-row"><button id="showDebugMathBtn" class="secondary">Debug Math</button></div>'
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
  var vitalSet = new Set((data.vital_keys||[]));
  var minorSet = new Set((data.minor_keys||[]));
  function chipFor(k, type){
    var cls = 'warn';
    if (type === 'present') cls = 'ok';
    else if (type === 'missing') cls = (vitalSet.has(k) ? 'crit' : 'warn');
    else if (type === 'fallback') cls = 'warn';
    return '<span class="chip '+cls+'" title="'+_escapeHtml(type)+'">'+_prettyMarketLabel(k)+'</span>';
  }
  var covHtml = [
    '<div class="details-section">',
      '<div class="section-title">Coverage</div>',
      '<div class="chips">',
        present.map(function(k){return chipFor(k, 'present');}).join(' '),
        (fallback.length? (' ' + fallback.map(function(k){return chipFor(k, 'fallback');}).join(' ')) : ''),
        (missing.length? (' ' + missing.map(function(k){return chipFor(k, 'missing');}).join(' ')) : ''),
        '</div>',
        '<div class="fp-tooltip" style="display:none; left:0; top:0;">x: 0, density: 0</div>',
      '</div>'
    ].join('');

  var primaryHtml = primary.map(function(k){ return renderMarketBlock(k, markets[k]); }).join('');
  if (!primaryHtml) primaryHtml = '<div class="muted">No primary markets.</div>';
  var others = (data.all_order || []).filter(function(k){ return primary.indexOf(k) === -1; });
  var otherHtml = others.map(function(k){ return renderMarketBlock(k, markets[k]); }).join('');
  if (!otherHtml) otherHtml = '<div class="muted">No other markets.</div>';
  // Build a single-column layout: remove markets panel to maximize graph space
  var pcurveHtml = (typeof window.renderProbCurveSection === 'function') ? window.renderProbCurveSection(p.name || name, data) : '';
  var html = [
    '<div class="details-content" style="grid-template-columns: 1fr;">',
      '<div style="grid-column: 1 / -1;">', head, predicted, pcurveHtml, covHtml, '</div>',
    '</div>'
  ].join('');
  showDetails('Player Details', html);
  try {
    if (typeof window.attachProbCurveHandlers === 'function') window.attachProbCurveHandlers(data);
  } catch (e) { /* ignore -- prob-curve.js is an optional add-on */ }
  try {
    var btn = document.getElementById('showDebugMathBtn');
    if (btn) {
      btn.addEventListener('click', function(e){ e.stopPropagation(); _openDebugMathOverlay(data); });
    }
  } catch (e) { /* ignore */ }
  try {
    var hdr = document.querySelector('.details-header');
    if (hdr && !hdr.querySelector('#detailsBack')) {
      var bk = document.createElement('button');
      bk.id = 'detailsBack';
      bk.className = 'back-btn';
      bk.setAttribute('aria-label','Back');
      bk.textContent = '← Back';
      bk.addEventListener('click', function(e){ e.stopPropagation(); try { history.back(); } catch(_) { hideDetails(); } });
      hdr.insertBefore(bk, hdr.firstChild);
    }
  } catch (e) {}
  try { history.replaceState({ detailsOpen: true, modal: 'player', name: (p.name || name), week: week }, '', '#details'); } catch (e) {}
  try { _attachFpVisualHandlers(document.getElementById('detailsBody')); } catch (e) {}
}

// ---- Debug Math overlay (drill-down) ----
function _openDebugMathOverlay(data) {
  try {
    var ov = document.getElementById('debugOverlay'); var body = document.getElementById('debugBody'); var ttl = document.getElementById('debugTitle');
    if (!ov || !body) return;
    if (ttl) ttl.textContent = (data && data.player && data.player.name ? (data.player.name + ' · Debug Math') : 'Debug Math');
    ov.classList.remove('hidden');
    var back = document.getElementById('debugBack'); if (back) back.onclick = function(){ _renderDebugStatList(data); };
    var close = document.getElementById('debugClose'); if (close) close.onclick = function(){ ov.classList.add('hidden'); };
    _renderDebugStatList(data);
  } catch (e) {}
}

function _fmtNum(x, d){ try { var n=Number(x); if (!isFinite(n)) return '-'; return n.toFixed(d==null?2:d); } catch(e){ return '-'; } }

function _renderDebugStatList(data) {
  var body = document.getElementById('debugBody'); if (!body) return;
  var dm = (data && data.debug_math) || {}; var markets = data && data.markets || {};
  var means = dm.mean_stats || {};
  var keys = Object.keys(means);
  if (!keys.length) keys = Object.keys(markets||{});
  // Order by impact when available
  keys.sort(function(a,b){ var ia=(markets[a]&&markets[a].impact_score)||0, ib=(markets[b]&&markets[b].impact_score)||0; return ib-ia; });
  var rows = keys.map(function(k){
    var nice = _prettyMarketLabel(k);
    var mean = means[k]; if (mean==null && markets[k]) mean = markets[k].mean_stat;
    var pm = (dm.per_market && dm.per_market[k]) || {};
    var midFp = pm.fp_mid; var mult = pm.multiplier;
    var info = 'mean ' + _fmtNum(mean,2) + (mult!=null? (' · FP mid ' + _fmtNum(midFp,2)) : '');
    return '<div class="dbg-stat" data-mkey="'+_escapeHtml(k)+'"><div class="left">'+nice+'</div><div class="right">'+info+' ▸</div></div>';
  }).join('');
  var html = [
    '<div class="details-section">',
      '<div class="section-title">Predicted Stats</div>',
      '<div class="dbg-list">', rows || '<div class="muted">No stats available.</div>', '</div>',
    '</div>'
  ].join('');
  body.innerHTML = html;
  try {
    body.querySelectorAll('.dbg-stat').forEach(function(el){ el.addEventListener('click', function(){ var k=el.getAttribute('data-mkey'); _renderDebugStatDetail(data, k); }); });
  } catch (e) {}
  try { _attachFpVisualHandlers(document.getElementById('detailsBody')); } catch (e) {}
}

function _renderDebugStatDetail(data, mkey) {
  var body = document.getElementById('debugBody'); if (!body) return;
  var dm = (data && data.debug_math) || {}; var per = dm.per_market || {}; var m = per[mkey] || {};
  var markets = data && data.markets || {}; var entry = markets[mkey] || {};
  var nice = _prettyMarketLabel(mkey);
  var summ = entry.summary || {};
  // Collect base + alternate book points
  function _gatherBookPoints(key){
    var e = markets[key] || {}; var out=[];
    // Base books
    (e.books||[]).forEach(function(b){
      var pt = (b.over && b.over.point!=null ? b.over.point : (b.under && b.under.point!=null ? b.under.point : null));
      if (pt!=null && isFinite(Number(pt))) out.push({ book: b.book||'', point: Number(pt) });
    });
    // Alternates if present
    try {
      if (e.alts && (Array.isArray(e.alts.over) || Array.isArray(e.alts.under))) {
        (e.alts.over||[]).forEach(function(it){ if (it && it.point!=null) out.push({ book: it.book||'', point: Number(it.point) }); });
        (e.alts.under||[]).forEach(function(it){ if (it && it.point!=null) out.push({ book: it.book||'', point: Number(it.point) }); });
      }
    } catch (err) {}
    return out;
  }
  var baseKey = mkey.replace('_alternate','');
  var points = _gatherBookPoints(baseKey).concat(_gatherBookPoints(baseKey + '_alternate'));
  // Deduplicate identical (book, point) combos
  var seen = new Set();
  points = points.filter(function(p){ var k = (p.book||'')+'@'+p.point; if (seen.has(k)) return false; seen.add(k); return true; });
  // Stat graph container (we will re-render if user enables comparison)
  var statGraph = '<div id="statGraphHost">' + _renderStatGraph(nice, baseKey, m, (summ && summ.avg_threshold), points) + '</div>';
  // Aggregated view
  var aggRows = [
    '<tr><th>Threshold (T)</th><td>'+_fmtNum(m.threshold!=null?m.threshold:summ.avg_threshold,2)+'</td></tr>',
    '<tr><th>p_over (norm)</th><td>'+(m.p_over_norm==null?'-':_fmtNum(m.p_over_norm,3))+'</td></tr>',
    '<tr><th>Mean</th><td>'+_fmtNum(m.mean,2)+'</td></tr>',
    '<tr><th>Q15</th><td>'+_fmtNum(m.q15,2)+'</td></tr>',
    '<tr><th>Q50</th><td>'+_fmtNum(m.q50,2)+'</td></tr>',
    '<tr><th>Q85</th><td>'+_fmtNum(m.q85,2)+'</td></tr>',
    '<tr><th>Multiplier</th><td>'+_fmtNum(m.multiplier,2)+'</td></tr>',
    '<tr><th>FP Floor/Mid/Ceil</th><td>'+_fmtNum(m.fp_floor,2)+' / '+_fmtNum(m.fp_mid,2)+' / '+_fmtNum(m.fp_ceil,2)+'</td></tr>'
  ].join('');
  var agg = '<table><tbody>'+aggRows+'</tbody></table>';
  // Books breakdown
  var bookRows = (entry.books||[]).map(function(b){
    var over=b.over||{}; var under=b.under||{}; var o=Number(over.odds||NaN); var u=Number(under.odds||NaN);
    var oImp = (isFinite(o)? (1/o) : null); var uImp = (isFinite(u)? (1/u) : null);
    var norm = (oImp!=null && uImp!=null) ? (oImp/(oImp+uImp)) : null;
    var pt = (over.point!=null?over.point:under.point);
    return '<tr>'
      + '<td>'+_escapeHtml(b.book||'')+'</td>'
      + '<td>'+ (over.odds!=null? _fmtNum(over.odds,2) : '-') +'</td>'
      + '<td>'+ (over.point!=null? _fmtNum(over.point,2) : '-') +'</td>'
      + '<td>'+ (under.odds!=null? _fmtNum(under.odds,2) : '-') +'</td>'
      + '<td>'+ (under.point!=null? _fmtNum(under.point,2) : '-') +'</td>'
      + '<td>'+ (oImp!=null? _fmtNum(oImp,3): '-') +'</td>'
      + '<td>'+ (uImp!=null? _fmtNum(uImp,3): '-') +'</td>'
      + '<td>'+ (norm!=null? _fmtNum(norm,3): '-') +'</td>'
      + '</tr>';
  }).join('');
  var booksTbl = '<table><thead><tr><th>Book</th><th>Over</th><th>Over Pt</th><th>Under</th><th>Under Pt</th><th>Imp(Over)</th><th>Imp(Under)</th><th>p_over(norm)</th></tr></thead><tbody>'+ (bookRows||'') +'</tbody></table>';
  var html = [
    '<div class="details-section">',
      '<div class="section-title">', _escapeHtml(nice), '</div>',
      statGraph,
      '<div class="muted">Aggregated from bookmaker lines (click Back to choose another stat)</div>',
      agg,
    '</div>',
    '<div class="details-section">',
      '<div class="section-title">Books Lines</div>',
      (bookRows? booksTbl : '<div class="muted">No per-book lines found.</div>'),
    '</div>'
  ].join('');
  body.innerHTML = html;
  try { _attachStatVisualHandlers(document.getElementById('debugBody')); } catch (e) {}
}

function _renderStatGraph(title, baseKey, m, summaryThreshold, bookPoints) {
  try {
    var mean = Number(m.mean||0);
    var q15 = Number(m.q15||0), q85 = Number(m.q85||0);
    var sigma = Number(m.sigma||0.000001);
    var isBinary = (baseKey === 'player_anytime_td') || (Number(m.threshold||0) === 0 && !isFinite(sigma));
    var minX = 0;
    var maxX = Math.max(mean, q85 || 0, summaryThreshold || 0, (bookPoints||[]).reduce(function(mx,p){ return Math.max(mx, Number(p.point||0)); }, 0));
    if (!(maxX > 0)) maxX = 1;
    // Add margin
    maxX = maxX * 1.2;
    var W = 600, H = 140, PAD = 14;
    function xScale(x){ return PAD + (x - minX) * (W - 2*PAD) / (maxX - minX); }
    function yScale(y){ return H - PAD - y * (H - 2*PAD); }
    var path = '';
    var legend = '';
    if (!isBinary) {
      // Build normal pdf curve
      var N = 80; var pts = []; var maxY = 0;
      function pdf(x){ return Math.exp(-0.5 * Math.pow((x - mean) / (sigma || 1e-6), 2)); }
      for (var i=0;i<=N;i++){
        var x = minX + (maxX-minX)*i/N; var y = pdf(x); if (y > maxY) maxY = y; pts.push([x, y]);
      }
      var d = pts.map(function(p,i){ var X=xScale(p[0]).toFixed(1), Y=yScale((p[1]/(maxY||1))*1).toFixed(1); return (i?'L':'M')+X+','+Y; }).join('');
      var area = d + ' L ' + xScale(maxX).toFixed(1) + ',' + yScale(0) + ' L ' + xScale(minX).toFixed(1) + ',' + yScale(0) + ' Z';
      // Markers: summary threshold, mean (q50), q15, q85, books
      var mk = [];
      function vline(x, cls){ return '<line class="marker '+cls+'" x1="'+x+'" y1="'+yScale(0)+'" x2="'+x+'" y2="'+yScale(1)+'" />'; }
      var xF = xScale(q15), xM = xScale(Number(m.q50||mean)), xC = xScale(q85);
      mk.push(vline(xF, 'q15'));
      mk.push(vline(xM, 'mean'));
      mk.push(vline(xC, 'q85'));
      if (summaryThreshold!=null) mk.push(vline(xScale(Number(summaryThreshold)), 'summary'));
      // Book markers
      var bookMarks = (bookPoints||[]).map(function(p){ return vline(xScale(p.point), 'book'); });
      var grid = (function(){ var out=''; for (var gi=1; gi<=5; gi++){ var xv=minX+(maxX-minX)*gi/6; out += '<line class="grid" x1="'+xScale(xv)+'" y1="'+yScale(0)+'" x2="'+xScale(xv)+'" y2="'+yScale(1)+'" />'; } return out; })();
      var svg = [
        '<div class="stat-visual" data-min="', minX.toFixed(6),'" data-max="', maxX.toFixed(6),'" data-pad="', PAD, '" data-w="', W, '" data-h="', H, '" data-mean="', mean, '" data-sigma="', sigma, '">',
          '<div class="vis-title">', _escapeHtml(title), ' (stat only)</div>',
          '<div class="svg-wrap"><svg viewBox="0 0 ', W, ' ', H, '" preserveAspectRatio="none">',
            grid,
            '<line class="axis" x1="', xScale(minX), '" y1="', yScale(0), '" x2="', xScale(maxX), '" y2="', yScale(0), '" />',
            '<path class="curve" d="', area, '" />',
            mk.join(''),
            bookMarks.join(''),
            '<line class="hover-x" x1="0" y1="', yScale(1), '" x2="0" y2="', yScale(0), '" style="display:none" />',
            '<circle class="hover-dot" cx="0" cy="0" r="3" style="display:none" />',
          '</svg></div>',
          '<div class="legend">',
            '<span><span class="dot q15"></span>Q15</span>',
            '<span><span class="dot mean"></span>Mean</span>',
            '<span><span class="dot q85"></span>Q85</span>',
            (summaryThreshold!=null? '<span><span class="dot summary"></span>Summary T</span>' : ''),
            (bookPoints && bookPoints.length? '<span><span class="dot book"></span>Book lines</span>' : ''),
          '</div>',
          '<div class="fp-tooltip" style="display:none; left:0; top:0;">x: 0, density: 0</div>',
        '</div>'
      ].join('');
      return svg;
    } else {
      // Simple binary visualization
      var p = (m.p_over_norm==null ? 0.5 : Number(m.p_over_norm));
      var bar0 = '<div class="bin-bar"><div class="bin" style="width:' + ((1-p)*100).toFixed(1) + '%"></div></div>';
      var bar1 = '<div class="bin-bar"><div class="bin" style="width:' + (p*100).toFixed(1) + '%; background:#60a5fa"></div></div>';
      return '<div class="stat-visual"><div class="vis-title">'+_escapeHtml(title)+' (probability)</div>'+bar0+bar1+'<div class="legend"><span>0</span><span>1</span></div></div>';
    }
  } catch (e) { return ''; }
}

async function openDefenseDetails(defense, week) {
  showDetails('Defense Details', '<div class="status"><span class="spinner"></span> Loading...</div>');
  var url = apiUrl('/defense/odds', {
    ...identityParams(),
    week: week,
    defense: defense,
    region: 'us,us2',
    mode: getDataMode()
  });
  var resp = await fetchJSON(url);
  if (!resp.ok) { showDetails('Defense Details', '<div class="status">Failed to load.</div>'); return; }
  var data = resp.data || {};
  var games = data.games || [];
  // Build day-of-week index counters
  var dayCounts = {};
  games.forEach(function(g){ var k=_weekdayKey(g.commence_time||''); dayCounts[k] = (dayCounts[k]||0)+1; });
  var daySeen = {};
  var blocks = games.map(function(g, idx){
    var id = 'def_' + idx;
    var dow = _weekdayKey(g.commence_time||'');
    daySeen[dow] = (daySeen[dow]||0) + 1;
    var label = dow + (dayCounts[dow] > 1 ? (' ' + daySeen[dow]) : '');
    var header = [
      '<div class="market-summary" aria-expanded="false" data-target="', id, '">',
        '<div class="title">', _escapeHtml(defense), ' vs ', _escapeHtml(g.opponent||''), '</div>',
        '<div class="meta">', _escapeHtml(label), ' &middot; ', _escapeHtml(_formatISOToLocal(g.commence_time||'')), ' &middot; Opp Implied Median: <strong>', _fmt(g.implied_total_median), '</strong></div>',
        '<div class="chev">&#9656;</div>',
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
              var price = (o.price!=null? _escapeHtml(o.price) : (o.odds!=null? _escapeHtml(o.odds): '—'));
              var point = (o.point!=null? _escapeHtml(o.point) : '—');
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

function _attachFpVisualHandlers(root) {
  try {
    var container = root || document;
    (container.querySelectorAll ? container.querySelectorAll('.fp-visual') : []).forEach(function(box){
      var svg = box.querySelector('svg'); if(!svg) return;
      var hoverX = svg.querySelector('.hover-x');
      var hoverDot = svg.querySelector('.hover-dot');
      var tip = box.querySelector('.fp-tooltip');
      var minX = parseFloat(box.getAttribute('data-min')||'0');
      var maxX = parseFloat(box.getAttribute('data-max')||'1');
      var PAD = parseFloat(box.getAttribute('data-pad')||'6');
      var W = parseFloat(box.getAttribute('data-w')||'600');
      var H = parseFloat(box.getAttribute('data-h')||'120');
      var floor = parseFloat(box.getAttribute('data-floor')||'0');
      var mid = parseFloat(box.getAttribute('data-mid')||'0');
      var ceil = parseFloat(box.getAttribute('data-ceil')||'0');
      var z85 = 1.036; var sigR = Math.max(0.1, Math.abs(ceil - mid) / z85); var sigL = Math.max(0.1, Math.abs(mid - floor) / z85);
      function xScale(x){ return PAD + (x - minX) * (W - 2*PAD) / (maxX - minX); }
      function yScale(y){ return H - PAD - y * (H - 2*PAD); }
      function pdf(x){ var s = (x >= mid ? sigR : sigL); return Math.exp(-0.5 * Math.pow((x - mid) / s, 2)); }
      var maxY = pdf(mid) || 1;
      function onMove(evt){
        var rect = svg.getBoundingClientRect();
        var localX = Math.min(W-PAD, Math.max(PAD, (evt.clientX - rect.left) * (W/rect.width)));
        var xVal = minX + (localX - PAD)*(maxX-minX)/(W-2*PAD);
        var yNorm = (pdf(xVal)/(maxY||1)); var yPx = yScale(yNorm);
        if (hoverX){ hoverX.setAttribute('x1', localX); hoverX.setAttribute('x2', localX); hoverX.style.display='block'; }
        if (hoverDot){ hoverDot.setAttribute('cx', localX); hoverDot.setAttribute('cy', yPx); hoverDot.style.display='block'; }
        if (tip){ tip.style.display='block'; var bx = box.getBoundingClientRect(); tip.style.left = (evt.clientX - bx.left + 8) + 'px'; tip.style.top = (evt.clientY - bx.top - 8) + 'px'; tip.textContent = 'x: ' + xVal.toFixed(2) + ', y: ' + yNorm.toFixed(3); }
      }
      function onEnter(){ if (hoverX) hoverX.style.display='block'; if (hoverDot) hoverDot.style.display='block'; if (tip) tip.style.display='block'; }
      function onLeave(){ if (hoverX) hoverX.style.display='none'; if (hoverDot) hoverDot.style.display='none'; if (tip) tip.style.display='none'; }
      svg.addEventListener('mousemove', onMove);
      svg.addEventListener('mouseenter', onEnter);
      svg.addEventListener('mouseleave', onLeave);
    });
  } catch (e) { /* ignore */ }
}

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
  // Mobile back button: close modal via history pop
  try {
    window.addEventListener('popstate', function(ev){
      var st = ev.state || {};
      if (st && st.modal === 'player') { try { openPlayerDetails(st.name, st.week || 'this', { noHistory: true }); return; } catch(_) {}
      }
      var overlay = document.getElementById('detailsOverlay');
      if (overlay && !overlay.classList.contains('hidden')) hideDetails();
    });
  } catch (e) {}

  // Toggle collapsible market blocks inside details modal
  var body = document.getElementById('detailsBody');
  if (body) {
    body.addEventListener('click', function(e){
      var pill = e.target.closest('.impact-pill');
      if (pill) {
        e.stopPropagation();
        var safe = pill.getAttribute('data-safe');
        var panel = document.getElementById('imp_' + safe);
        if (panel) panel.classList.toggle('hidden');
        return;
      }
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

  // The main UI now has ONE results container per panel (#weekly-results,
  // shared across the Lineup/All Players/Defenses views; #draft-board) that
  // gets re-rendered in place as the week/view toggles change, instead of
  // one static container per week. So rather than binding a handler per old
  // per-week container with a hardcoded week, bind one delegated handler per
  // container that reads the CURRENT week/view from script.js's small
  // accessor globals at click time. Matching by the `.player-name` marker
  // (present in every row renderLineup/renderPlayers produce) instead of a
  // fixed column index also means this doesn't care whether the row it
  // clicked came from the lineup table or the players table.
  function attachWeeklyResultsHandler(containerId, getWeek, getView) {
    var el = document.getElementById(containerId); if (!el) return;
    el.addEventListener('click', function(e){
      var td = e.target.closest('td'); if (!td) return;
      var tr = td.parentElement; if (!tr) return;
      var week = (typeof getWeek === 'function' && getWeek()) || 'this';
      var view = (typeof getView === 'function' && getView()) || 'lineup';
      if (view === 'defenses') {
        if (td.cellIndex !== 0 && td.cellIndex !== 3) return;
        var def = (tr.cells[0] && tr.cells[0].textContent || '').trim(); if (!def) return;
        e.stopPropagation();
        openDefenseDetails(def, week);
        return;
      }
      var nameEl = tr.querySelector('.player-name');
      var name = nameEl ? (nameEl.getAttribute('data-player') || nameEl.textContent || '').trim() : '';
      if (!name) return;
      e.stopPropagation();
      openPlayerDetails(name, week);
    });
  }
  attachWeeklyResultsHandler('weekly-results', window.getCurrentWeeklyWeek, window.getCurrentWeeklyView);
  attachWeeklyResultsHandler('draft-board', window.getCurrentDraftWeek, function () { return 'lineup'; });

  // Global fallback for any other .player-name click (e.g. inside the
  // Compare Curves / Book Coverage modals) that the handler above didn't
  // already claim via stopPropagation.
  try {
    document.addEventListener('click', function(e){
      var el = e.target.closest('.player-name');
      if (!el) return;
      var name = (el.getAttribute('data-player') || el.textContent || '').trim();
      if (!name) return;
      openPlayerDetails(name, 'this');
    });
  } catch (e) {}
});


// Note: "incomplete" badge rendering (players/lineup rows missing odds
// coverage) lives in script.js's renderPlayers/renderLineup now. It used to be
// a pair of runtime overrides here; see "The overrides.js trap" in AGENTS.md
// before deleting any UI file that looks unreferenced.






// Hover handlers for stat graphs (single/compare/multi)
function _attachStatVisualHandlers(root) {
  try {
    var container = root || document;
    (container.querySelectorAll ? container.querySelectorAll('.stat-visual') : []).forEach(function(box){
      var svg = box.querySelector('svg'); if(!svg) return;
      var hoverX = svg.querySelector('.hover-x');
      var hoverDot = svg.querySelector('.hover-dot');
      var tip = box.querySelector('.fp-tooltip');
      var minX = parseFloat(box.getAttribute('data-min')||'0');
      var maxX = parseFloat(box.getAttribute('data-max')||'1');
      var PAD = parseFloat(box.getAttribute('data-pad')||'14');
      var W = parseFloat(box.getAttribute('data-w')||'600');
      var H = parseFloat(box.getAttribute('data-h')||'140');
      var meanA = parseFloat(box.getAttribute('data-mean')||'');
      var sigmaA = parseFloat(box.getAttribute('data-sigma')||'');
      var meanB = parseFloat(box.getAttribute('data-mean-b')||'');
      var sigmaB = parseFloat(box.getAttribute('data-sigma-b')||'');
      function xScale(x){ return PAD + (x - minX) * (W - 2*PAD) / (maxX - minX); }
      function yScale(y){ return H - PAD - y * (H - 2*PAD); }
      function pdfFor(mn, sg, x){ var s=(parseFloat(sg)||1e-6); var mu=parseFloat(mn)||0; return Math.exp(-0.5 * Math.pow((x - mu) / s, 2)); }
      // Candidate curves (A, B, and any multi-model paths with data attrs)
      var candidates = [];
      if (!isNaN(meanA) && !isNaN(sigmaA) && (sigmaA>0)) candidates.push({ key:'A', mean: meanA, sigma: sigmaA });
      if (!isNaN(meanB) && !isNaN(sigmaB) && (sigmaB>0)) candidates.push({ key:'B', mean: meanB, sigma: sigmaB });
      var multi = svg.querySelectorAll('.curve-line[data-mean]');
      multi.forEach(function(p){ var mn=parseFloat(p.getAttribute('data-mean')||''); var sg=parseFloat(p.getAttribute('data-sigma')||''); var key=p.getAttribute('data-model')||'M'; if(!isNaN(mn)&&!isNaN(sg)&&sg>0) candidates.push({ key, mean: mn, sigma: sg }); });
      // Default draw baseline from first candidate or zeros
      var def = candidates[0] || { mean: (isNaN(meanA)?0:meanA), sigma: (isNaN(sigmaA)?1e-6:sigmaA) };
      function pdf(x){ return pdfFor(def.mean, def.sigma, x); }
      var maxY = pdf(def.mean) || 1;
      // Range selection across a locked curve
      var locked = null; // key of selected curve
      var selStart = null, selEnd = null;
      var rangePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      rangePath.setAttribute('class', 'range-area');
      rangePath.setAttribute('fill', 'rgba(34,197,94,0.18)');
      rangePath.setAttribute('stroke', '#22c55e');
      rangePath.setAttribute('stroke-width', '1');
      svg.appendChild(rangePath);
      var readout = box.querySelector('.range-readout');
      if (!readout) { readout = document.createElement('div'); readout.className='range-readout'; readout.style.display='none'; box.appendChild(readout); }
      function _formatPct(p){ try { return (p*100).toFixed(1)+'%'; } catch(e){ return '0.0%'; } }
      function _integral(mn, sg, a, b, steps){ var n=Math.max(10,steps||400); var dx=(b-a)/n; var area=0; var prev=pdfFor(mn,sg,a); for(var i=1;i<=n;i++){ var x=a+i*dx; var cur=pdfFor(mn,sg,x); area += 0.5*(prev+cur)*dx; prev=cur; } return Math.max(0,area); }
      function _updateRange(){
        if (!locked || selStart==null || selEnd==null){ rangePath.setAttribute('d',''); if(readout) readout.style.display='none'; return; }
        var c = candidates.find(c=>c.key===locked) || def;
        var a = Math.max(minX, Math.min(selStart, selEnd));
        var b = Math.min(maxX, Math.max(selStart, selEnd));
        if (!(b>a)){ rangePath.setAttribute('d',''); if(readout) readout.style.display='none'; return; }
        var N=100, d=''; for(var i=0;i<=N;i++){ var x=a+(b-a)*i/N; var y=(pdfFor(c.mean,c.sigma,x)/(maxY||1))*1; var X=xScale(x).toFixed(1), Y=yScale(y).toFixed(1); d += (i?' L ':'M ')+X+','+Y; } d += ' L '+xScale(b).toFixed(1)+','+yScale(0).toFixed(1); d += ' L '+xScale(a).toFixed(1)+','+yScale(0).toFixed(1)+' Z'; rangePath.setAttribute('d', d);
        var total=_integral(c.mean,c.sigma,minX,maxX,800); var part=_integral(c.mean,c.sigma,a,b,400); var pct=(total>0?(part/total):0);
        if(readout){ readout.innerHTML='Model <span class="val">'+locked+'</span> · Range <span class="val"></span> · Chance <span class="val">'+_formatPct(pct)+'</span> <span class="clear" role="button" tabindex="0">Clear</span>'; readout.style.display=''; var clr=readout.querySelector('.clear'); if(clr) clr.onclick=function(){ selStart=null; selEnd=null; locked=null; _updateRange(); }; }
      }
      function onMove(evt){
        var rect = svg.getBoundingClientRect();
        var localX = Math.min(W-PAD, Math.max(PAD, (evt.clientX - rect.left) * (W/rect.width)));
        var xVal = minX + (localX - PAD)*(maxX-minX)/(W-2*PAD);
        var yNorm = (pdf(xVal)/(maxY||1)); var yPx = yScale(yNorm);
        if (hoverX){ hoverX.setAttribute('x1', localX); hoverX.setAttribute('x2', localX); hoverX.style.display='block'; }
        if (hoverDot){ hoverDot.setAttribute('cx', localX); hoverDot.setAttribute('cy', yPx); hoverDot.style.display='block'; }
        if (tip){ tip.style.display='block'; var bx = box.getBoundingClientRect(); tip.style.left = (evt.clientX - bx.left + 8) + 'px'; tip.style.top = (evt.clientY - bx.top - 8) + 'px'; tip.textContent = 'x: ' + xVal.toFixed(2) + ', density: ' + yNorm.toFixed(3); }
      }
      function onEnter(){ if (hoverX) hoverX.style.display='block'; if (hoverDot) hoverDot.style.display='block'; if (tip) tip.style.display='block'; }
      function onLeave(){ if (hoverX) hoverX.style.display='none'; if (hoverDot) hoverDot.style.display='none'; if (tip) tip.style.display='none'; }
      function onClick(evt){
        var rect = svg.getBoundingClientRect();
        var localX = Math.min(W-PAD, Math.max(PAD, (evt.clientX - rect.left) * (W/rect.width)));
        var localY = Math.min(H, Math.max(0, (evt.clientY - rect.top) * (H/rect.height)));
        var xVal = minX + (localX - PAD)*(maxX-minX)/(W-2*PAD);
        // Determine curve nearest the click
        if (candidates.length > 0){
          var best=null, bestDy=1e9;
          candidates.forEach(function(c){ var y = (pdfFor(c.mean,c.sigma,xVal)/(maxY||1)); var yPx=yScale(y); var dy=Math.abs(yPx - localY); if (dy < bestDy){ bestDy=dy; best=c; } });
          if (bestDy < 14) { locked = best.key; } // snap if close enough
        }
        if (!locked && candidates[0]) locked = candidates[0].key;
        if (selStart == null || (selStart!=null && selEnd!=null)) { selStart = xVal; selEnd = null; _updateRange(); }
        else { selEnd = xVal; _updateRange(); }
      }
      svg.addEventListener('mousemove', onMove);
      svg.addEventListener('mouseenter', onEnter);
      svg.addEventListener('mouseleave', onLeave);
      svg.addEventListener('click', onClick);
    });
  } catch (e) { /* ignore */ }
}

