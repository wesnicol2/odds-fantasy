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

// Multi-curve comparison popup for a position and week
function openCompareCurves(week) {
  try {
    showDetails('Compare Curves', '<div class="status"><span class="spinner"></span> Loading curves...</div>');
  var projUrl = apiUrl('/projections', { username: val('username') || 'wesnicol', season: val('season') || '2025', week: week, mode: getDataMode(), model: (typeof getModel==='function'? getModel() : ((document.getElementById('modelSelect') && document.getElementById('modelSelect').value) || 'const')) });
    fetchJSON(projUrl).then(function(res){
      if (!res.ok) { hideDetails(); alert('Failed to load projections'); return; }
      var all = (res.data && res.data.players) || [];
      // Compute global FP range across all players and store globally
      try {
        var gMax = 0;
        (all||[]).forEach(function(p){ var c = Number(p.ceiling||0); if (c > gMax) gMax = c; });
        if (!(gMax > 0)) gMax = 1;
        window.GLOBAL_FP_RANGE = { minX: 0, maxX: gMax };
      } catch (e) {}
      var curTarget = 'mid';
      var posTabs = ['LINEUP','ALL','QB','RB','WR','TE','FLEX'];
      var tabsHtml = '<div class="details-section"><div class="section-title">Select (' + (week==='next'?'Next Week':'This Week') + ')</div>'
        + posTabs.map(function(p){ return '<button class="pill" data-pos="'+p+'">'+p+'</button>'; }).join(' ')
        + ' <span class="muted" style="margin-left:10px;">Target:</span> '
        + ['floor','mid','ceiling'].map(function(t){ return '<button class="pill target-pill" data-target="'+t+'">'+t.toUpperCase()+'</button>'; }).join(' ')
        + '</div>';
      var controls = '<div class="cmp-controls">'
        + '<input id="cmpSearch" class="cmp-search" type="text" placeholder="Search players" />'
        + '<label class="muted"><input id="cmpShowPinned" type="checkbox" /> Show selected only</label>'
        + '<span class="muted" style="margin-left:10px;">Model:</span> '
        + '<select id="cmpModelGlobal"><option value="const">Constantini</option><option value="puelz">Puelz</option><option value="angelini">Angelini</option><option value="baseline">Baseline</option></select>'
        + '<button id="cmpApplyGlobal" class="secondary" style="margin-left:6px;">Apply</button>'
        + '</div>';
      var grid = controls + '<div class="compare-grid"><div class="compare-list" id="cmpList"></div><div class="compare-graph"><svg id="cmpSvg" viewBox="0 0 800 360" preserveAspectRatio="none"></svg><div class="compare-legend">Hover a player to highlight; click to lock highlight.</div></div></div>';
      var body = document.getElementById('detailsBody');
      body.innerHTML = tabsHtml + grid + '<div class="details-section" id="cmpLineup" style="display:none"></div>';
      function _renderTargetPills(){ try{ var pills=body.querySelectorAll('.target-pill'); pills.forEach(function(btn){ var t=btn.getAttribute('data-target'); btn.classList.toggle('pill-active', String(t)===String(curTarget)); }); }catch(e){} }
      try { var mg = document.getElementById('cmpModelGlobal'); if (mg) mg.value = (typeof getModel==='function'? getModel() : 'const'); } catch (e) {}
      try {
        var apply = document.getElementById('cmpApplyGlobal');
        if (apply) apply.addEventListener('click', function(){
          try {
            var mg = document.getElementById('cmpModelGlobal'); var chosen = (mg && mg.value) || 'const';
            var ms = document.getElementById('modelSelect'); var mf = document.getElementById('modelSelectFloating');
            if (ms) ms.value = chosen; if (mf) mf.value = chosen;
            try { if (typeof saveSettings==='function') saveSettings(); } catch(e){}
            openCompareCurves(week);
            try { if (typeof refreshAll==='function') refreshAll(); } catch(e){}
          } catch (e) {}
        });
      } catch (e) {}
      function renderForPos(pos){
        var pool = all.filter(function(p){ return pos==='FLEX' ? (['WR','RB','TE'].indexOf(p.pos)>=0) : ((pos==='ALL'||pos==='LINEUP') ? true : (p.pos===pos)); }).slice();
        var slotByName = {};
        if ((pos==='ALL' || pos==='LINEUP') && typeof computeLineupFromPlayers==='function'){
          try { var lp = computeLineupFromPlayers(all, curTarget||'mid'); (lp.lineup||[]).forEach(function(r){ if (r.slot!=='BENCH') slotByName[r.name]=r.slot; }); pool = all.filter(function(p){ return !!slotByName[p.name]; }); } catch(e){}
        }
        pool.sort(function(a,b){ return Number(b.mid||0) - Number(a.mid||0); });
        pool = pool.slice(0, 20);
        var z85=1.036;
        var minX = (window && window.GLOBAL_FP_RANGE ? Number(window.GLOBAL_FP_RANGE.minX)||0 : 0);
        var maxX = (window && window.GLOBAL_FP_RANGE ? Number(window.GLOBAL_FP_RANGE.maxX)||1 : 1);
        var W=800,H=360,PAD=24;
        function xScale(x){ return PAD + (x - minX) * (W - 2*PAD) / (maxX - minX); }
        function yScale(y){ return H - PAD - y * (H - 2*PAD); }
        function pathFor(floor, mid, ceil){ var f=Number(floor||0), m=Number(mid||0), c=Number(ceil||0); var sigR=Math.max(0.1, Math.abs(c-m)/z85), sigL=Math.max(0.1, Math.abs(m-f)/z85); var N=120; var pts=[], maxY=0; for (var i=0;i<=N;i++){ var x=minX+(maxX-minX)*i/N; var s=(x>=m?sigR:sigL); var y=Math.exp(-0.5*Math.pow((x-m)/s,2)); if (y>maxY) maxY=y; pts.push([xScale(x), y]); } var d=''; pts.forEach(function(p,i){ var X=p[0],Y=yScale((p[1]/(maxY||1))*1); d+=(i?'L':'M')+X.toFixed(1)+','+Y.toFixed(1); }); return d; }
        // Keep curve params for hover density calculations
        var curves = pool.map(function(p){ var f=Number(p.floor||0), m=Number(p.mid||0), c=Number(p.ceiling||0); return { f:f, m:m, c:c, sigR: Math.max(0.1, Math.abs(c-m)/z85), sigL: Math.max(0.1, Math.abs(m-f)/z85) }; });
        function pdfAt(i, x){ var cur=curves[i]; var s=(x>=cur.m?cur.sigR:cur.sigL); return Math.exp(-0.5*Math.pow((x-cur.m)/s,2)); }
        // Build a palette with maximum visual spread given number of players
        var palette = (function(){
          var n = pool.length; var cols = [];
          if (n <= 0) return cols;
          if (n === 1) { cols.push('hsl(0,80%,60%)'); return cols; }
          if (n === 2) { cols = ['hsl(0,80%,58%)','hsl(130,75%,52%)']; return cols; }
          var sat = 72, light = 58;
          for (var i=0;i<n;i++) { var hue = Math.round((360*i)/n) % 360; cols.push('hsl('+hue+','+sat+'%,'+light+'%)'); }
          return cols;
        })();
        var list = document.getElementById('cmpList');
        list.innerHTML = pool.map(function(p,idx){
          var col=palette[idx]||'hsl(200,70%,55%)';
          var slot = slotByName[p.name] ? ('<span class="pill" title="Lineup slot">'+slotByName[p.name]+'</span> ') : '';
          var nums = '<span class="muted fmc">F '+Number(p.floor||0).toFixed(1)+' Â· M '+Number(p.mid||0).toFixed(1)+' Â· C '+Number(p.ceiling||0).toFixed(1)+'</span>';
          var detailsBtn = '<button class="mini details" data-name="'+_escapeHtml(p.name)+'" title="Details">âŸ²</button>';
          var nameBtn = '<button class="name-link" data-name="'+_escapeHtml(p.name)+'">'+_escapeHtml(p.name)+'</button>';
          return '<div class="player" data-idx="'+idx+'" data-name="'+_escapeHtml(p.name.toLowerCase())+'">'
            + '<span class="left"><span class="dot" style="background:'+col+'"></span>'+slot+nameBtn+'</span>'
            + '<span class="right">'+nums+' '+detailsBtn+'</span>'
            + '</div>';
        }).join('');
        var svg = document.getElementById('cmpSvg');
        var grid=''; for (var gi=1; gi<=6; gi++){ var xv=minX+(maxX-minX)*gi/7; grid += '<line class="grid" x1="'+xScale(xv)+'" y1="'+yScale(0)+'" x2="'+xScale(xv)+'" y2="'+yScale(1)+'" />'; }
        var ax = grid + '<line class="axis" x1="'+xScale(minX)+'" y1="'+yScale(0)+'" x2="'+xScale(maxX)+'" y2="'+yScale(0)+'" />';
        var labels='<text class="axis-label" x="'+xScale(maxX)+'" y="'+(yScale(0)+16)+'" text-anchor="end">Fantasy Points (pts)</text>'+
                    '<text class="axis-label" transform="translate('+(xScale(minX)-12)+','+(H/2)+') rotate(-90)" text-anchor="middle">Density</text>';
        svg.innerHTML = ax + labels + pool.map(function(p,idx){ var d=pathFor(p.floor,p.mid,p.ceiling); var col=palette[idx]||'hsl(200,70%,55%)'; return '<path class="curve-line" data-idx="'+idx+'" stroke="'+col+'" d="'+d+'" />'; }).join('') + '<line class="hover-x" x1="0" y1="'+yScale(1)+'" x2="0" y2="'+yScale(0)+'" style="display:none" />' + '<circle class="hover-dot" cx="0" cy="0" r="3" style="display:none" />';
        // Tooltip element inside graph
        var graph = svg.parentElement; var tip = graph.querySelector('.fp-tooltip'); if (!tip){ tip = document.createElement('div'); tip.className='fp-tooltip'; tip.style.display='none'; graph.appendChild(tip); }
        var pinned=new Set(); var hoverIdx=null; var showPinnedOnly=false; var locked=null;
        function setHighlight(i){ hoverIdx = (i==null ? null : String(i)); applyHighlight(); }
        function applyHighlight(){ var paths=svg.querySelectorAll('.curve-line'); var items=list.querySelectorAll('.player'); var anyPinned = pinned.size>0; var focusSet = new Set(anyPinned ? Array.from(pinned) : (hoverIdx!=null?[String(hoverIdx)]:[])); paths.forEach(function(p){ var idx=p.getAttribute('data-idx'); p.classList.remove('highlight'); p.classList.remove('dim'); var show=true; if (showPinnedOnly && anyPinned && !focusSet.has(idx)) show=false; if (!show) { p.style.display='none'; return; } p.style.display=''; if (focusSet.size===0) return; if (focusSet.has(idx)) p.classList.add('highlight'); else p.classList.add('dim'); }); items.forEach(function(it){ var idx=it.getAttribute('data-idx'); it.classList.toggle('active', focusSet.has(idx)); if (showPinnedOnly && anyPinned && !focusSet.has(idx)) it.style.display='none'; else it.style.display=''; }); }
        list.querySelectorAll('.player').forEach(function(it){
          it.addEventListener('mouseenter', function(){ hoverIdx = it.getAttribute('data-idx'); if (pinned.size===0) applyHighlight(); });
          it.addEventListener('mouseleave', function(){ hoverIdx = null; if (pinned.size===0) applyHighlight(); });
          it.addEventListener('click', function(){
            var idx=it.getAttribute('data-idx');
            if (pinned.has(idx)) pinned.delete(idx); else pinned.add(idx);
            locked = (pinned.size>0 ? parseInt(Array.from(pinned)[0]) : null);
            applyHighlight();
          });
        });
        // Details buttons
        list.querySelectorAll('.player .details').forEach(function(btn){ btn.addEventListener('click', function(e){ e.stopPropagation(); var name=btn.getAttribute('data-name')||''; openPlayerDetails(name, week); }); });
        // Clicking the name opens the single-player popup
        list.querySelectorAll('.player .name-link').forEach(function(btn){ btn.addEventListener('click', function(e){ e.stopPropagation(); var name=btn.getAttribute('data-name')||''; openPlayerDetails(name, week); }); });
        var search = document.getElementById('cmpSearch'); if (search){ search.value=''; search.oninput = function(){ var q=(search.value||'').toLowerCase().trim(); list.querySelectorAll('.player').forEach(function(it){ var name=(it.getAttribute('data-name')||''); it.style.display = (q==='' || name.indexOf(q)>=0) ? '' : 'none'; }); }; }
        var chk = document.getElementById('cmpShowPinned'); if (chk){ chk.checked=false; chk.onchange = function(){ showPinnedOnly = !!chk.checked; applyHighlight(); }; }
        applyHighlight();
        // Hover over SVG to show nearest curve values
        var hoverX = svg.querySelector('.hover-x'); var hoverDot = svg.querySelector('.hover-dot');
        function onMove(evt){
          var rect = svg.getBoundingClientRect();
          var localX = Math.min(W-PAD, Math.max(PAD, (evt.clientX-rect.left)*(W/rect.width)));
          var localY = Math.min(H-PAD, Math.max(PAD, (evt.clientY-rect.top)*(H/rect.height)));
          // Search nearest point on any curve within a small x-window around cursor
          var best = { idx: null, xPx: localX, yPx: localY, xVal: null, dens: -1, dist2: Infinity };
          var windowPx = 14; // +/- px horizontally to allow nearest on curve (not just same x)
          var steps = 24;
          for (var i=0;i<curves.length;i++){
            for (var s=-steps; s<=steps; s++){
              var candXpx = localX + (s*windowPx/steps);
              if (candXpx < PAD || candXpx > (W-PAD)) continue;
              var candXVal = minX + (candXpx-PAD)*(maxX-minX)/(W-2*PAD);
              var dens = pdfAt(i, candXVal);
          var candYpx = yScale(dens*1);
              var dx = candXpx - localX; var dy = candYpx - localY; var d2 = dx*dx + dy*dy;
              if (d2 < best.dist2){ best = { idx: i, xPx: candXpx, yPx: candYpx, xVal: candXVal, dens: dens, dist2: d2 }; }
            }
          }
          if (best.idx != null){
            if (locked==null) setHighlight(best.idx);
            if (hoverX){ hoverX.setAttribute('x1', best.xPx); hoverX.setAttribute('x2', best.xPx); hoverX.style.display='block'; }
            if (hoverDot){ hoverDot.setAttribute('cx', best.xPx); hoverDot.setAttribute('cy', best.yPx); hoverDot.style.display='block'; }
            if (tip){ var bx=graph.getBoundingClientRect(); tip.style.display='block'; tip.style.left=(evt.clientX-bx.left+8)+'px'; tip.style.top=(evt.clientY-bx.top-8)+'px'; tip.textContent='FP: ' + best.xVal.toFixed(2) + ' pts, Density: ' + best.dens.toFixed(3); }
          }
        }
        function onLeave(){ if (locked==null) setHighlight(null); if (hoverX) hoverX.style.display='none'; if (hoverDot) hoverDot.style.display='none'; if (tip) tip.style.display='none'; }
        svg.addEventListener('mousemove', onMove); svg.addEventListener('mouseleave', onLeave);
        // Render lineup table when LINEUP tab is active
        try {
          var lc = document.getElementById('cmpLineup');
          if (pos === 'LINEUP') {
            if (lc) { lc.style.display='block'; }
            if (typeof computeLineupFromPlayers==='function') {
              var lpp = computeLineupFromPlayers(all, curTarget||'mid');
              if (lc) renderLineup('cmpLineup', 'Optimal Lineup', lpp);
            }
          } else {
            if (lc) { lc.style.display='none'; lc.innerHTML=''; }
          }
        } catch(e){}
      }
      function saveLastPos(pos){ try{ localStorage.setItem('ofdash.cmp.lastPos.'+week, pos);}catch(e){} }
      function loadLastPos(){ try{ return localStorage.getItem('ofdash.cmp.lastPos.'+week) || 'LINEUP'; }catch(e){ return 'LINEUP'; } }
      function activateTab(pos){ var pills = body.querySelectorAll('.details-section .pill[data-pos]'); pills.forEach(function(b){ b.classList.toggle('pill-active', b.getAttribute('data-pos')===pos); }); saveLastPos(pos); renderForPos(pos); }
      body.querySelectorAll('.details-section .pill[data-pos]').forEach(function(btn){ btn.addEventListener('click', function(){ activateTab(btn.getAttribute('data-pos')); }); });
      // Target selector for lineup optimization
      body.querySelectorAll('.target-pill').forEach(function(btn){ btn.addEventListener('click', function(){ curTarget = btn.getAttribute('data-target')||'mid'; _renderTargetPills(); var active = body.querySelector('.details-section .pill.pill-active[data-pos]'); var pos = active ? active.getAttribute('data-pos') : 'LINEUP'; renderForPos(pos||'LINEUP'); }); });
      _renderTargetPills();
      activateTab(loadLastPos());
      try { history.replaceState({ detailsOpen: true, modal: 'compare', week: week }, '', '#details'); } catch (e) {}
    }).catch(function(e){
      try { console.error('[compare] error', e); } catch(_){ }
      hideDetails();
      alert('Failed to load data: ' + (e && (e.message || e.toString ? e.toString() : e)));
    });
  } catch (e) { try { hideDetails(); } catch(_){} }
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
        var yNorm = (pdf(xVal)/(maxY||1))*0.9; var yPx = yScale(yNorm);
        if (hoverX){ hoverX.setAttribute('x1', localX); hoverX.setAttribute('x2', localX); hoverX.style.display='block'; }
        if (hoverDot){ hoverDot.setAttribute('cx', localX); hoverDot.setAttribute('cy', yPx); hoverDot.style.display='block'; }
        if (tip){ tip.style.display='block'; var bx = box.getBoundingClientRect(); tip.style.left = (evt.clientX - bx.left + 8) + 'px'; tip.style.top = (evt.clientY - bx.top - 8) + 'px'; tip.textContent = 'FP: ' + xVal.toFixed(2) + ' pts, Density: ' + yNorm.toFixed(3); }
      }
      function onEnter(){ if (hoverX) hoverX.style.display='block'; if (hoverDot) hoverDot.style.display='block'; if (tip) tip.style.display='block'; }
      function onLeave(){ if (hoverX) hoverX.style.display='none'; if (hoverDot) hoverDot.style.display='none'; if (tip) tip.style.display='none'; }
      svg.addEventListener('mousemove', onMove);
      svg.addEventListener('mouseenter', onEnter);
      svg.addEventListener('mouseleave', onLeave);
    });
  } catch (e) { /* ignore */ }
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
      '<div class="meta">predicted: ', (mean!=null ? _fmt(mean) : 'Ã¢â‚¬â€'),
      ' <span class="pill">impact ', _fmt(impact), '</span>',
      s && (s.samples!=null) ? (' <span class="pill">n ' + (s.samples||0) + '</span>') : '',
      '</div>',
      '<div class="chev">&#9656;</div>',
    '</div>'
  ].join('');
  var rows = (payload.books || []).map(function(b){
    return '<tr>'
      + '<td>' + (b.book||'') + '</td>'
      + '<td>' + (b.over && b.over.odds!=null?_fmt(b.over.odds):'Ã¢â‚¬â€') + '</td>'
      + '<td>' + (b.over && b.over.point!=null?_fmt(b.over.point):'Ã¢â‚¬â€') + '</td>'
      + '<td>' + (b.under && b.under.odds!=null?_fmt(b.under.odds):'Ã¢â‚¬â€') + '</td>'
      + '<td>' + (b.under && b.under.point!=null?_fmt(b.under.point):'Ã¢â‚¬â€') + '</td>'
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
  var fpStrip = '<div id="imp_' + safeKey + '" class="impact-strip hidden">FP impact â€” Floor: <strong>' + _fmt(fp.fp_floor) + '</strong> Â· Mid: <strong>' + _fmt(fp.fp_mid) + '</strong> Â· Ceiling: <strong>' + _fmt(fp.fp_ceiling) + '</strong></div>';
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
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week: week,
    name: name,
    region: 'us,us2',
    mode: getDataMode(),
    model: (document.getElementById('modelSelect') && document.getElementById('modelSelect').value) || 'const'
  });
  var projUrl = apiUrl('/projections', {
    username: val('username') || 'wesnicol',
    season: val('season') || '2025',
    week: week,
    mode: getDataMode(),
    model: (document.getElementById('modelSelect') && document.getElementById('modelSelect').value) || 'const'
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
    + '<div class="player-meta">' + _escapeHtml(p.pos || '') + ' Â· ' + _escapeHtml(p.team || '') + '</div>'
    + '</div>';
  var predicted = ''
    + '<div class="details-section">'
      +   '<div class="section-title">Fantasy Points</div>'
      +   '<div class="cards">'
        +     '<div class="card floor"><div class="label">Floor</div><div class="value">' + _fmt(floor) + '</div></div>'
        +     '<div class="card mid"><div class="label">Mid</div><div class="value">' + _fmt(mid) + '</div></div>'
        +     '<div class="card ceiling"><div class="label">Ceiling</div><div class="value">' + _fmt(ceiling) + '</div></div>'
      +   '</div>'
      +   '<div class="btn-row" style="margin-top:8px">'
      +     '<label class="muted">Model: '
      +       '<select id="pdModelSel">'
      +         '<option value="const">Constantini</option>'
      +         '<option value="puelz">Puelz</option>'
      +         '<option value="angelini">Angelini</option>'
      +         '<option value="baseline">Baseline</option>'
      +       '</select>'
      +     '</label>'
      +     '<button id="pdApplyModelBtn" class="secondary">Apply Model</button>'
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

  var primaryHtml = primary.map(function(k){ return renderMarketBlock2(k, markets[k]); }).join('');
  if (!primaryHtml) primaryHtml = '<div class="muted">No primary markets.</div>';
  var others = (data.all_order || []).filter(function(k){ return primary.indexOf(k) === -1; });
  var otherHtml = others.map(function(k){ return renderMarketBlock2(k, markets[k]); }).join('');
  if (!otherHtml) otherHtml = '<div class="muted">No other markets.</div>';
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
  ].join('');
  showDetails('Player Details', html);
  try {
    var btn = document.getElementById('showDebugMathBtn');
    if (btn) {
      btn.addEventListener('click', function(e){ e.stopPropagation(); _openDebugMathOverlay(data); });
    }
  } catch (e) { /* ignore */ }
  // Hook up model apply button: sets global model and refreshes this popup
  try {
    var ms = document.getElementById('modelSelect') || null;
    var mf = document.getElementById('modelSelectFloating') || null;
    var pdSel = document.getElementById('pdModelSel');
    var current = (mf && mf.value) || (ms && ms.value) || 'const';
    if (pdSel) pdSel.value = current;
    var apply = document.getElementById('pdApplyModelBtn');
    if (apply) apply.addEventListener('click', async function(){
      try {
        var chosen = (pdSel && pdSel.value) || 'const';
        if (ms) ms.value = chosen; if (mf) mf.value = chosen;
        try { if (typeof saveSettings === 'function') saveSettings(); } catch (e) {}
        // Refresh this popup under the new model
        await openPlayerDetails(p.name || name, week, { noHistory: true });
        // Optionally refresh header data in the background
        try { if (typeof refreshAll === 'function') refreshAll(); } catch (e) {}
      } catch (e) {}
    });
  } catch (e) { /* ignore */ }
  try {
    var hdr = document.querySelector('.details-header');
    if (hdr && !hdr.querySelector('#detailsBack')) {
      var bk = document.createElement('button');
      bk.id = 'detailsBack';
      bk.className = 'back-btn';
      bk.setAttribute('aria-label','Back');
      bk.textContent = 'â† Back';
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
  // Compare controls (Model A = current global, Model B selectable)
  var currentModel = (document.getElementById('modelSelectFloating') && document.getElementById('modelSelectFloating').value) || (document.getElementById('modelSelect') && document.getElementById('modelSelect').value) || 'const';
  var cmpControls = '<div class="btn-row"><label class="muted">Compare vs: <select id="cmpModelSel"><option value="">(None)</option><option value="const">Constantini</option><option value="puelz">Puelz</option><option value="angelini">Angelini</option><option value="baseline">Baseline</option></select></label><button id="cmpApplyBtn" class="secondary">Use This Model</button></div>';
  var modelCheckboxes = '<div class="btn-row">'
    + '<span class="muted">Show models:</span> '
    + '<label class="muted"><input type="checkbox" class="mdlChk" value="const" checked> Constantini</label>'
    + '<label class="muted"><input type="checkbox" class="mdlChk" value="puelz"> Puelz</label>'
    + '<label class="muted"><input type="checkbox" class="mdlChk" value="angelini"> Angelini</label>'
    + '<label class="muted"><input type="checkbox" class="mdlChk" value="baseline"> Baseline</label>'
    + '</div>';
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
      '<div class="section-title">Model</div>',
      '<div>Active: <strong>'+_escapeHtml(String(currentModel||''))+'</strong></div>',
      cmpControls,
    '</div>',
    '<div class="details-section">',
      '<div class="section-title">', _escapeHtml(nice), '</div>',
      modelCheckboxes,
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
  try {
    var sel = document.getElementById('cmpModelSel');
    if (sel) sel.addEventListener('change', async function(){
      var modelB = (sel && sel.value) || '';
      var host = document.getElementById('statGraphHost');
      if (!host) return;
      if (!modelB) { host.innerHTML = _renderStatGraph(nice, baseKey, m, (summ && summ.avg_threshold), points); try { _attachStatVisualHandlers(host); } catch (e) {} return; }
      try {
        var st = (history && history.state) || {};
        var oddsUrlB = apiUrl('/player/odds', {
          username: val('username') || 'wesnicol',
          season: val('season') || '2025',
          week: (st && st.week) || 'this',
          name: (data && data.player && data.player.name) || '',
          region: 'us,us2',
          mode: getDataMode(),
          model: modelB
        });
        var respB = await fetchJSON(oddsUrlB);
        if (!respB.ok) { host.innerHTML = _renderStatGraph(nice, baseKey, m, (summ && summ.avg_threshold), points); return; }
        var perB = ((respB.data||{}).debug_math||{}).per_market || {}; var mB = perB[mkey] || {};
        host.innerHTML = _renderStatGraphCompare(nice, baseKey, m, mB, (summ && summ.avg_threshold), points, modelB);
        try { _attachStatVisualHandlers(host); } catch (e) {}
      } catch (e) { host.innerHTML = _renderStatGraph(nice, baseKey, m, (summ && summ.avg_threshold), points); }
    });
    // Apply comparison model globally and refresh
    var applyBtn = document.getElementById('cmpApplyBtn');
    if (applyBtn) applyBtn.addEventListener('click', async function(){
      try {
        var modelB = (sel && sel.value) || '';
        if (!modelB) return;
        var ms = document.getElementById('modelSelect');
        var mf = document.getElementById('modelSelectFloating');
        if (ms) ms.value = modelB; if (mf) mf.value = modelB;
        try { if (typeof saveSettings === 'function') saveSettings(); } catch (e) {}
        // Close debug overlay and refresh Player Details under new model
        try { var ov = document.getElementById('debugOverlay'); if (ov) ov.classList.add('hidden'); } catch (e) {}
        await openPlayerDetails((data && data.player && data.player.name) || '', (history && history.state && history.state.week) || 'this', { noHistory: true });
        try { if (typeof refreshAll === 'function') refreshAll(); } catch (e) {}
      } catch (e) {}
    });
    // Multi-model checkboxes overlay
    var mdlChecks = Array.prototype.slice.call(document.querySelectorAll('.mdlChk'));
    var mdlCache = {};
    var activeLabelColor = { const: '#60a5fa', puelz: '#f59e0b', angelini: '#22c55e', baseline: '#ef4444' };
    function _fetchModelStat(modelKey){
      return new Promise(async function(resolve){
        if (mdlCache[modelKey]) { resolve(mdlCache[modelKey]); return; }
        try {
          var st = (history && history.state) || {};
          var oddsUrl = apiUrl('/player/odds', {
            username: val('username') || 'wesnicol',
            season: val('season') || '2025',
            week: (st && st.week) || 'this',
            name: (data && data.player && data.player.name) || '',
            region: 'us,us2',
            mode: getDataMode(),
            model: modelKey
          });
          var r = await fetchJSON(oddsUrl);
          var pm = ((r.data||{}).debug_math||{}).per_market || {};
          var mX = pm[mkey] || {};
          mdlCache[modelKey] = mX;
          resolve(mX);
        } catch (e) { resolve({}); }
      });
    }
    function _updateMulti(){
      var host = document.getElementById('statGraphHost'); if (!host) return;
      var selected = mdlChecks.filter(function(c){ return c && c.checked; }).map(function(c){ return c.value; });
      if (!selected.length) { host.innerHTML = _renderStatGraph(nice, baseKey, m, (summ && summ.avg_threshold), points); return; }
      Promise.all(selected.map(_fetchModelStat)).then(function(all){
        var map = {}; for (var i=0;i<selected.length;i++){ map[selected[i]] = all[i] || {}; }
        host.innerHTML = _renderStatGraphMulti(nice, baseKey, map, (summ && summ.avg_threshold), points, activeLabelColor);
        try { _attachStatVisualHandlers(host); } catch (e) {}
      });
    }
    mdlChecks.forEach(function(ch){ ch.addEventListener('change', _updateMulti); });
  } catch (e) {}
}

// Render a two-model overlay of the stat graph (Model A: active; Model B: selected)
function _renderStatGraphCompare(title, baseKey, mA, mB, summaryThreshold, bookPoints, labelB) {
  try {
    function buildOne(m) {
      var mean = Number(m.mean||0);
      var q15 = Number(m.q15||0), q85 = Number(m.q85||0);
      var sigma = Number(m.sigma||0.000001);
      return { mean, q15, q85, sigma };
    }
    var A = buildOne(mA), B = buildOne(mB);
    // Compute axis range from both
    var minX = 0;
    var maxX = Math.max(A.mean, A.q85||0, B.mean, B.q85||0, summaryThreshold||0, (bookPoints||[]).reduce(function(mx,p){ return Math.max(mx, Number(p.point||0)); }, 0));
    if (!(maxX > 0)) maxX = 1;
    maxX = maxX * 1.2;
    var W = 600, H = 140, PAD = 14;
    function xScale(x){ return PAD + (x - minX) * (W - 2*PAD) / (maxX - minX); }
    function yScale(y){ return H - PAD - y * (H - 2*PAD); }
    function pathFor(m){ var N=80, pts=[], maxY=0; function pdf(x){ return Math.exp(-0.5*Math.pow((x-m.mean)/(m.sigma||1e-6),2)); } for (var i=0;i<=N;i++){ var x=minX+(maxX-minX)*i/N; var y=pdf(x); if (y>maxY) maxY=y; pts.push([x,y]); } var d=pts.map(function(p,i){ var X=xScale(p[0]).toFixed(1),Y=yScale((p[1]/(maxY||1))*1).toFixed(1); return (i?'L':'M')+X+','+Y; }).join(''); return d + ' L ' + xScale(maxX).toFixed(1) + ',' + yScale(0) + ' L ' + xScale(minX).toFixed(1) + ',' + yScale(0) + ' Z'; }
    function vline(x, cls){ return '<line class="marker '+cls+'" x1="'+x+'" y1="'+yScale(0)+'" x2="'+x+'" y2="'+yScale(1)+'" />'; }
    var grid = (function(){ var out=''; for (var gi=1; gi<=5; gi++){ var xv=minX+(maxX-minX)*gi/6; out += '<line class="grid" x1="'+xScale(xv)+'" y1="'+yScale(0)+'" x2="'+xScale(xv)+'" y2="'+yScale(1)+'" />'; } return out; })();
    var mk = [];
    if (summaryThreshold!=null) mk.push(vline(xScale(Number(summaryThreshold)), 'summary'));
    var bookMarks = (bookPoints||[]).map(function(p){ return vline(xScale(p.point), 'book'); });
    var svg = [
      '<div class="stat-visual" data-min="', minX, '" data-max="', maxX, '" data-pad="', PAD, '" data-w="', W, '" data-h="', H, '" data-mean="', A.mean, '" data-sigma="', A.sigma, '">',
        '<div class="vis-title">', _escapeHtml(title), ' (stat, compare)</div>',
        '<div class="svg-wrap"><svg viewBox="0 0 ', W, ' ', H, '" preserveAspectRatio="none">',
          grid,
          '<line class="axis" x1="', xScale(minX), '" y1="', yScale(0), '" x2="', xScale(maxX), '" y2="', yScale(0), '" />',
          '<path class="curve" d="', pathFor(A), '" />',
          '<path class="curve2" d="', pathFor(B), '" />',
          vline(xScale(A.q15), 'q15'), vline(xScale(A.mean), 'mean'), vline(xScale(A.q85), 'q85'),
          vline(xScale(B.q15), 'q15 m2'), vline(xScale(B.mean), 'mean m2'), vline(xScale(B.q85), 'q85 m2'),
          bookMarks.join(''),
          '<line class="hover-x" x1="0" y1="', yScale(1), '" x2="0" y2="', yScale(0), '" style="display:none" />',
          '<circle class="hover-dot" cx="0" cy="0" r="3" style="display:none" />',
        '</svg></div>',
        '<div class="legend">',
          '<span><span class="dot q15"></span>A: Q15/Mean/Q85</span>',
          '<span><span class="dot" style="background:#f472b6"></span>B: ', _escapeHtml(String(labelB||'model B')), '</span>',
          (summaryThreshold!=null? '<span><span class="dot summary"></span>Summary T</span>' : ''),
          (bookPoints && bookPoints.length? '<span><span class="dot book"></span>Book lines</span>' : ''),
        '</div>',
        '<div class="fp-tooltip" style="display:none; left:0; top:0;">x: 0, density: 0</div>',
      '</div>'
    ].join('');
    return svg;
  } catch (e) { return _renderStatGraph(title, baseKey, mA, summaryThreshold, bookPoints); }
}

// Multi-model overlay renderer (modelsMap: key -> per-market m)
function _renderStatGraphMulti(title, baseKey, modelsMap, summaryThreshold, bookPoints, colorMap) {
  try {
    var keys = Object.keys(modelsMap || {});
    // Compute bounds across models
    var minX = 0;
    var maxX = 1;
    keys.forEach(function(k){ var m=modelsMap[k]||{}; var mx=Math.max(Number(m.mean||0), Number(m.q85||0)); if (mx > maxX) maxX = mx; });
    if (summaryThreshold!=null && Number(summaryThreshold) > maxX) maxX = Number(summaryThreshold);
    if (bookPoints && bookPoints.length){ bookPoints.forEach(function(p){ var v=Number(p.point||0); if (v>maxX) maxX=v; }); }
    if (!(maxX > 0)) maxX = 1;
    maxX = maxX * 1.2;
    var W=600,H=140,PAD=14;
    function xScale(x){ return PAD + (x - minX) * (W - 2*PAD) / (maxX - minX); }
    function yScale(y){ return H - PAD - y * (H - 2*PAD); }
    function pathFor(m){ var N=100, pts=[], maxY=0; var mean=Number(m.mean||0); var sigma=Number(m.sigma||0.000001); function pdf(x){ return Math.exp(-0.5*Math.pow((x-mean)/(sigma||1e-6),2)); } for (var i=0;i<=N;i++){ var x=minX+(maxX-minX)*i/N; var y=pdf(x); if (y>maxY) maxY=y; pts.push([x,y]); } var d=pts.map(function(p,i){ var X=xScale(p[0]).toFixed(1),Y=yScale((p[1]/(maxY||1))*1).toFixed(1); return (i?'L':'M')+X+','+Y; }).join(''); return d + ' L ' + xScale(maxX).toFixed(1) + ',' + yScale(0) + ' L ' + xScale(minX).toFixed(1) + ',' + yScale(0) + ' Z'; }
    function vline(x, cls){ return '<line class="marker '+cls+'" x1="'+x+'" y1="'+yScale(0)+'" x2="'+x+'" y2="'+yScale(1)+'" />'; }
    var grid = (function(){ var out=''; for (var gi=1; gi<=5; gi++){ var xv=minX+(maxX-minX)*gi/6; out += '<line class="grid" x1="'+xScale(xv)+'" y1="'+yScale(0)+'" x2="'+xScale(xv)+'" y2="'+yScale(1)+'" />'; } return out; })();
    var mk = [];
    if (summaryThreshold!=null) mk.push(vline(xScale(Number(summaryThreshold)), 'summary'));
    var bookMarks = (bookPoints||[]).map(function(p){ return vline(xScale(p.point), 'book'); });
    var legendParts = [];
    var curves = keys.map(function(k){ var m=modelsMap[k]||{}; var color=(colorMap&&colorMap[k])||'#888'; legendParts.push('<span><span class="dot" style="background:'+color+'"></span>'+k+'</span>'); return '<path class="curve-line" stroke="'+color+'" fill="rgba(0,0,0,0.0)" d="'+pathFor(m)+'" />'; });
    var svg = [
      '<div class="stat-visual">',
        '<div class="vis-title">', _escapeHtml(title), ' (stat, multi-model)</div>',
        '<div class="svg-wrap"><svg viewBox="0 0 ', W, ' ', H, '" preserveAspectRatio="none">',
          grid,
          '<line class="axis" x1="', xScale(minX), '" y1="', yScale(0), '" x2="', xScale(maxX), '" y2="', yScale(0), '" />',
          curves.join(''),
          mk.join(''),
          bookMarks.join(''),
        '</svg></div>',
        '<div class="legend">', legendParts.join(' '), (summaryThreshold!=null? ' <span><span class="dot summary"></span>Summary T</span>':''), (bookPoints && bookPoints.length? ' <span><span class="dot book"></span>Book lines</span>':''), '</div>',
      '</div>'
    ].join('');
    return svg;
  } catch (e) { return ''; }
}

// Render a stat-specific PDF with markers for thresholds and book points
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
        + '<td>' + (b.total_point!=null?_fmt(b.total_point):'Ã¢â‚¬â€') + '</td>'
        + '<td>' + (b.opponent_spread!=null?_fmt(b.opponent_spread):'Ã¢â‚¬â€') + '</td>'
        + '<td>' + (b.opponent_implied!=null?_fmt(b.opponent_implied):'Ã¢â‚¬â€') + '</td>'
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
              var price = (o.price!=null? _escapeHtml(o.price) : (o.odds!=null? _escapeHtml(o.odds): 'Ã¢â‚¬â€'));
              var point = (o.point!=null? _escapeHtml(o.point) : 'Ã¢â‚¬â€');
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
        var yNorm = (pdf(xVal)/(maxY||1))*0.9; var yPx = yScale(yNorm);
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
      if (st && st.modal === 'compare') { try { openCompareCurves(st.week || 'this', { noHistory: true }); return; } catch(_) {}
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
  function fmtCell(v, inc) { return inc ? 'Ã¢â‚¬â€' : Number(v||0).toFixed(2); }

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
          const fmt = (v) => inc ? 'Ã¢â‚¬â€' : Number(v||0).toFixed(2);
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
      var mean = parseFloat(box.getAttribute('data-mean')||'0');
      var sigma = parseFloat(box.getAttribute('data-sigma')||'0.000001');
      function xScale(x){ return PAD + (x - minX) * (W - 2*PAD) / (maxX - minX); }
      function yScale(y){ return H - PAD - y * (H - 2*PAD); }
      function pdf(x){ var s = (sigma||1e-6); return Math.exp(-0.5 * Math.pow((x - mean) / s, 2)); }
      var maxY = pdf(mean) || 1;
      function onMove(evt){
        var rect = svg.getBoundingClientRect();
        var localX = Math.min(W-PAD, Math.max(PAD, (evt.clientX - rect.left) * (W/rect.width)));
        var xVal = minX + (localX - PAD)*(maxX-minX)/(W-2*PAD);
        var yNorm = (pdf(xVal)/(maxY||1))*0.9; var yPx = yScale(yNorm);
        if (hoverX){ hoverX.setAttribute('x1', localX); hoverX.setAttribute('x2', localX); hoverX.style.display='block'; }
        if (hoverDot){ hoverDot.setAttribute('cx', localX); hoverDot.setAttribute('cy', yPx); hoverDot.style.display='block'; }
        if (tip){ tip.style.display='block'; var bx = box.getBoundingClientRect(); tip.style.left = (evt.clientX - bx.left + 8) + 'px'; tip.style.top = (evt.clientY - bx.top - 8) + 'px'; tip.textContent = 'x: ' + xVal.toFixed(2) + ', density: ' + yNorm.toFixed(3); }
      }
      function onEnter(){ if (hoverX) hoverX.style.display='block'; if (hoverDot) hoverDot.style.display='block'; if (tip) tip.style.display='block'; }
      function onLeave(){ if (hoverX) hoverX.style.display='none'; if (hoverDot) hoverDot.style.display='none'; if (tip) tip.style.display='none'; }
      svg.addEventListener('mousemove', onMove);
      svg.addEventListener('mouseenter', onEnter);
      svg.addEventListener('mouseleave', onLeave);
    });
  } catch (e) { /* ignore */ }
}
