// Fantasy-points probability curve: a per-player chart built by de-vigging
// and combining each of that player's individual sportsbook prop markets
// (rush/rec/pass yards, receptions, pass TDs, anytime-TD), with checkboxes
// to include/exclude specific books and specific lines and see the curve
// recompute live.
//
// This whole file is an intentional placeholder. The aggregation math here
// (de-vig + naive per-book average + Gaussian-free PMF convolution) is a
// stand-in for a real probability model someone else is building separately.
// When that lands, this file's math functions are the only things that need
// to change -- the data plumbing (buildQuotes/buildBinaryQuotes, reading
// `/player/odds`'s markets + debug_math.scoring_rules) and the rendering
// stay the same. Safe to delete this file, its <script> tag in index.html,
// and its two call sites in details.js (openPlayerDetails) if it's replaced
// outright instead.
(function(){
  "use strict";

  var STAT_DEFS = [
    {key:'player_pass_yds', unit:'yds', kind:'ou'},
    {key:'player_pass_tds', unit:'td', kind:'ou'},
    {key:'player_rush_yds', unit:'yds', kind:'ou'},
    {key:'player_reception_yds', unit:'yds', kind:'ou'},
    {key:'player_receptions', unit:'rec', kind:'ou'},
    {key:'player_anytime_td', unit:'', kind:'binary'},
  ];
  var POINT_STEP = 0.5;

  var BOOK_TITLES = {
    draftkings: 'DraftKings', fanduel: 'FanDuel', betmgm: 'BetMGM',
    williamhill_us: 'Caesars', espnbet: 'ESPN BET', betrivers: 'BetRivers',
    betonlineag: 'BetOnline.ag', ballybet: 'Bally Bet', betparx: 'betPARX',
    fliff: 'Fliff', fanatics: 'Fanatics', hardrockbet: 'Hard Rock Bet',
    bovada: 'Bovada', rebet: 'ReBet', pointsbetus: 'PointsBet',
    wynnbet: 'WynnBET', unibet_us: 'Unibet', betus: 'BetUS',
    lowvig: 'LowVig.ag', mybookieag: 'MyBookie.ag',
  };
  function bookTitle(key){
    return BOOK_TITLES[key] || (key || '').replace(/[_-]/g, ' ').replace(/\b\w/g, function(m){ return m.toUpperCase(); });
  }

  // ---------- data adapters: /player/odds markets -> {book,point,over,under,prob,devigged}[] ----------
  function buildQuotes(statKey, markets){
    var main = markets[statKey];
    var alt = markets[statKey + '_alternate'];
    var byBookPoint = {};
    function addSide(book, point, side, val){
      if (book == null || point == null || val == null) return;
      byBookPoint[book] = byBookPoint[book] || {};
      byBookPoint[book][point] = byBookPoint[book][point] || {};
      byBookPoint[book][point][side] = val;
    }
    ((main && main.books) || []).forEach(function(b){
      if (b.over && b.over.odds != null) addSide(b.book, b.over.point, 'over', b.over.odds);
      if (b.under && b.under.odds != null) addSide(b.book, b.under.point, 'under', b.under.odds);
    });
    if (alt && alt.alts){
      (alt.alts.over || []).forEach(function(it){ addSide(it.book, it.point, 'over', it.odds); });
      (alt.alts.under || []).forEach(function(it){ addSide(it.book, it.point, 'under', it.odds); });
    }
    var quotes = [];
    Object.keys(byBookPoint).forEach(function(book){
      Object.keys(byBookPoint[book]).forEach(function(pointStr){
        var sides = byBookPoint[book][pointStr];
        if (sides.over == null) return;
        var prob, devigged;
        if (sides.under != null){
          var po = 1/sides.over, pu = 1/sides.under;
          prob = po / (po + pu); devigged = true;
        } else { prob = 1/sides.over; devigged = false; }
        quotes.push({book: book, point: parseFloat(pointStr), over: sides.over, under: sides.under || null, prob: prob, devigged: devigged});
      });
    });
    quotes.sort(function(a,b){ return (a.point - b.point) || a.book.localeCompare(b.book); });
    return quotes;
  }
  function buildBinaryQuotes(markets){
    var m = markets['player_anytime_td'];
    return ((m && m.books) || []).filter(function(b){ return b.over && b.over.odds != null; })
      .map(function(b){ return {book: b.book, price: b.over.odds, prob: 1/b.over.odds}; });
  }

  // ---------- math (placeholder — see file header) ----------
  function computeCurve(quotes){
    if (!quotes.length) return null;
    var byBook = {};
    quotes.forEach(function(q){ (byBook[q.book] = byBook[q.book] || []).push(q); });
    Object.keys(byBook).forEach(function(book){
      var arr = byBook[book];
      arr.sort(function(a,b){ return a.point - b.point; });
      if (arr[0].point > 0) arr.unshift({point: 0, prob: 1, book: book, synthetic: true});
    });

    var points = quotes.map(function(q){ return q.point; });
    var min = Math.min.apply(null, points), max = Math.max.apply(null, points);
    var pad = Math.max(max * 0.15, (max - min) * 0.22, 2);
    var gridMin = Math.max(0, floorNice(min - pad));
    var gridMax = ceilNice(max + pad);
    var STEPS = 72, grid = [];
    for (var i = 0; i <= STEPS; i++) grid.push(gridMin + (gridMax - gridMin) * i / STEPS);

    function bookSurvivalAt(arr, x){
      if (x <= arr[0].point) return arr[0].prob;
      if (x >= arr[arr.length-1].point) return arr[arr.length-1].prob;
      for (var j = 0; j < arr.length-1; j++){
        var a = arr[j], b = arr[j+1];
        if (x >= a.point && x <= b.point){
          var t = (x - a.point) / ((b.point - a.point) || 1);
          return a.prob + (b.prob - a.prob) * t;
        }
      }
      return arr[arr.length-1].prob;
    }

    var curve = grid.map(function(x){
      var vals = Object.keys(byBook).map(function(book){ return bookSurvivalAt(byBook[book], x); });
      var mean = vals.reduce(function(s,v){ return s+v; }, 0) / vals.length;
      return {x: x, y: mean};
    });
    for (var k = 1; k < curve.length; k++){ if (curve[k].y > curve[k-1].y) curve[k].y = curve[k-1].y; }
    curve.forEach(function(pt){ pt.y = Math.min(1, Math.max(0, pt.y)); });

    return {curve: curve, gridMin: gridMin, gridMax: gridMax, bookCount: Object.keys(byBook).length};
  }

  function xAtProb(curve, target){
    if (curve[0].y <= target) return curve[0].x;
    if (curve[curve.length-1].y >= target) return curve[curve.length-1].x;
    for (var i = 0; i < curve.length-1; i++){
      var a = curve[i], b = curve[i+1];
      if (a.y >= target && b.y <= target){
        var t = (a.y - target) / ((a.y - b.y) || 1e-9);
        return a.x + (b.x - a.x) * t;
      }
    }
    return curve[curve.length-1].x;
  }
  function yAtX(curve, x){
    if (x <= curve[0].x) return curve[0].y;
    if (x >= curve[curve.length-1].x) return curve[curve.length-1].y;
    for (var i = 0; i < curve.length-1; i++){
      var a = curve[i], b = curve[i+1];
      if (x >= a.x && x <= b.x){
        var t = (x - a.x) / ((b.x - a.x) || 1e-9);
        return a.y + (b.y - a.y) * t;
      }
    }
    return curve[curve.length-1].y;
  }
  function niceStep(range, targetTicks){
    var raw = range / targetTicks;
    var mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
    var norm = raw / mag, step;
    if (norm < 1.5) step = 1; else if (norm < 3) step = 2; else if (norm < 7) step = 5; else step = 10;
    return step * mag;
  }
  function floorNice(v){ var s = niceStep(Math.max(v,10), 6) || 1; return Math.floor(v / s) * s; }
  function ceilNice(v){ var s = niceStep(Math.max(v,10), 6) || 1; return Math.ceil(v / s) * s; }

  function categoryToPointsPMF(curveObj, ptsPerUnit){
    if (!curveObj || !ptsPerUnit) return null;
    var xStep = POINT_STEP / ptsPerUnit;
    var maxX = curveObj.gridMax;
    var nBins = Math.max(1, Math.ceil(maxX / xStep));
    var pmf = [], prevS = yAtX(curveObj.curve, 0);
    for (var i = 0; i < nBins; i++){
      var x1 = Math.min((i+1) * xStep, maxX);
      var s1 = yAtX(curveObj.curve, x1);
      pmf.push(Math.max(0, prevS - s1));
      prevS = s1;
    }
    var total = pmf.reduce(function(a,b){ return a+b; }, 0);
    if (total < 1 && pmf.length) pmf[pmf.length-1] += (1 - total);
    return pmf;
  }
  function tdPMF(prob){
    var idx = Math.round(6 / POINT_STEP);
    var pmf = new Array(idx + 1).fill(0);
    pmf[0] = 1 - prob; pmf[idx] = prob;
    return pmf;
  }
  function convolvePMFs(pmfs){
    var result = [1];
    pmfs.filter(Boolean).forEach(function(pmf){
      var next = new Array(result.length + pmf.length - 1).fill(0);
      for (var i = 0; i < result.length; i++){
        if (!result[i]) continue;
        for (var j = 0; j < pmf.length; j++) next[i+j] += result[i] * pmf[j];
      }
      result = next;
    });
    return result;
  }

  function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function pct(v){ return Math.round(v*100) + '%'; }
  function pct1(v){ return (v*100).toFixed(1) + '%'; }

  // ---------- HTML shell (filled in by attachProbCurveHandlers) ----------
  window.renderProbCurveSection = function(playerName, data){
    return '' +
      '<div class="details-section pcurve">' +
        '<div class="section-title">Fantasy Points &mdash; Probability Curve <span class="pill" title="Placeholder aggregation; a real model will replace this">preview</span></div>' +
        '<div id="pcurveTiles" class="cards"></div>' +
        '<div id="pcurveChartWrap" class="pcurve-chart-wrap"></div>' +
        '<div id="pcurveSub" class="pcurve-sub"></div>' +
        '<div class="pcurve-filters">' +
          '<div class="pcurve-filter-col">' +
            '<div class="pcurve-filter-head">' +
              '<span>Sportsbooks</span>' +
              '<span class="pcurve-mini-actions"><a href="#" data-pcv-action="books-all">all</a> &middot; <a href="#" data-pcv-action="books-none">none</a></span>' +
            '</div>' +
            '<div id="pcurveBooks" class="pcurve-book-list"></div>' +
          '</div>' +
          '<div class="pcurve-filter-col">' +
            '<div class="pcurve-filter-head"><span>Lines</span></div>' +
            '<div id="pcurveLines" class="pcurve-line-stack"></div>' +
          '</div>' +
        '</div>' +
      '</div>';
  };

  window.attachProbCurveHandlers = function(data){
    var markets = data.markets || {};
    var scoringRules = (data.debug_math && data.debug_math.scoring_rules) || {};
    var statMarketMap = (data.debug_math && data.debug_math.stat_market_map) || {};

    var cats = [];
    STAT_DEFS.forEach(function(stat){
      if (stat.kind === 'binary'){
        var bq = buildBinaryQuotes(markets);
        if (bq.length) cats.push({def: stat, quotes: bq});
        return;
      }
      var q = buildQuotes(stat.key, markets);
      if (q.length) cats.push({def: stat, quotes: q});
    });

    if (!cats.length){
      var wrap0 = document.getElementById('pcurveChartWrap');
      if (wrap0) wrap0.innerHTML = '<div class="muted" style="padding:10px 0;">No priced markets for this player this week.</div>';
      var section = document.querySelector('.pcurve');
      if (section) { var f = section.querySelector('.pcurve-filters'); if (f) f.style.display = 'none'; }
      return;
    }

    var disabledBooks = {};   // book -> true
    var disabledLines = {};   // "statKey|book|point" (or "statKey|book" for binary) -> true

    function lineKey(statKey, kind, q){
      return statKey + '|' + q.book + (kind === 'binary' ? '' : ('|' + q.point));
    }
    function isActive(statKey, kind, q){
      if (disabledBooks[q.book]) return false;
      if (disabledLines[lineKey(statKey, kind, q)]) return false;
      return true;
    }

    function computeFantasyCurve(){
      var pmfs = [];
      var tdProb = null, tdBookCount = 0;
      var totalActive = 0, totalQuotes = 0;
      var perCategory = [];

      cats.forEach(function(cat){
        var stat = cat.def;
        totalQuotes += cat.quotes.length;
        if (stat.kind === 'binary'){
          var active = cat.quotes.filter(function(q){ return isActive(stat.key, 'binary', q); });
          totalActive += active.length;
          if (active.length){
            tdProb = active.reduce(function(s,q){ return s+q.prob; }, 0) / active.length;
            tdBookCount = active.length;
            pmfs.push(tdPMF(tdProb));
          }
          perCategory.push({stat: stat, activeQuotes: active, totalCount: cat.quotes.length});
          return;
        }
        var activeQ = cat.quotes.filter(function(q){ return isActive(stat.key, 'ou', q); });
        totalActive += activeQ.length;
        var curveObj = computeCurve(activeQ);
        var sleeperKey = statMarketMap[stat.key];
        var ptsPerUnit = sleeperKey != null ? Number(scoringRules[sleeperKey] || 0) : 0;
        var pmf = categoryToPointsPMF(curveObj, ptsPerUnit);
        if (pmf) pmfs.push(pmf);
        perCategory.push({stat: stat, activeQuotes: activeQ, totalCount: cat.quotes.length, ptsPerUnit: ptsPerUnit});
      });

      var combined = convolvePMFs(pmfs);
      var curve = combined.map(function(_, i){
        var survival = 0;
        for (var k = i; k < combined.length; k++) survival += combined[k];
        return {x: i * POINT_STEP, y: Math.min(1, Math.max(0, survival))};
      });
      if (curve.length < 2) curve.push({x: POINT_STEP, y: curve[0].y});

      return {curve: curve, gridMin: 0, gridMax: (curve.length-1)*POINT_STEP, perCategory: perCategory, tdProb: tdProb, tdBookCount: tdBookCount, totalActive: totalActive, totalQuotes: totalQuotes};
    }

    function renderBookList(){
      var byBook = {};
      cats.forEach(function(cat){
        cat.quotes.forEach(function(q){
          var e = byBook[q.book] = byBook[q.book] || {active: 0, total: 0};
          e.total++;
          if (!disabledLines[lineKey(cat.def.key, cat.def.kind, q)]) e.active++;
        });
      });
      var keys = Object.keys(byBook).sort(function(a,b){ return bookTitle(a).localeCompare(bookTitle(b)); });
      var el = document.getElementById('pcurveBooks');
      if (!el) return;
      el.innerHTML = keys.map(function(book){
        var off = !!disabledBooks[book];
        var c = byBook[book];
        return '<label class="pcurve-book-row' + (off ? ' pcurve-off' : '') + '">' +
          '<input type="checkbox" ' + (off ? '' : 'checked') + ' data-pcv-book="' + esc(book) + '">' +
          '<span class="pcurve-book-title">' + esc(bookTitle(book)) + '</span>' +
          '<span class="pcurve-book-count">' + (off ? 0 : c.active) + '/' + c.total + '</span>' +
        '</label>';
      }).join('');
      el.querySelectorAll('input[data-pcv-book]').forEach(function(inp){
        inp.addEventListener('change', function(e){
          var book = e.target.getAttribute('data-pcv-book');
          if (e.target.checked) delete disabledBooks[book]; else disabledBooks[book] = true;
          renderAll();
        });
      });
    }

    function renderLineDrilldown(){
      var el = document.getElementById('pcurveLines');
      if (!el) return;
      var html = cats.filter(function(c){ return c.def.kind !== 'binary'; }).map(function(cat){
        var stat = cat.def;
        var activeCount = cat.quotes.filter(function(q){ return isActive(stat.key, 'ou', q); }).length;
        var byBook = {};
        cat.quotes.forEach(function(q){ (byBook[q.book] = byBook[q.book] || []).push(q); });
        var bookKeys = Object.keys(byBook).sort(function(a,b){ return bookTitle(a).localeCompare(bookTitle(b)); });
        var rows = '';
        bookKeys.forEach(function(book){
          var arr = byBook[book].slice().sort(function(a,b){ return a.point - b.point; });
          rows += '<tr class="pcurve-book-header"><td colspan="4">' + esc(bookTitle(book)) + '</td></tr>';
          arr.forEach(function(q){
            var key = lineKey(stat.key, 'ou', q);
            var off = !!disabledLines[key] || !!disabledBooks[q.book];
            rows += '<tr class="' + (off ? 'pcurve-line-off' : '') + '">' +
              '<td><input type="checkbox" ' + (disabledLines[key] ? '' : 'checked') + (disabledBooks[q.book] ? ' disabled' : '') + ' data-pcv-line="' + esc(key) + '"></td>' +
              '<td class="num">' + q.point + ' ' + stat.unit + '</td>' +
              '<td class="num">' + q.over.toFixed(2) + '</td>' +
              '<td class="num">' + pct(q.prob) + '</td>' +
            '</tr>';
          });
        });
        return '<details class="pcurve-drilldown">' +
          '<summary>' + esc(_prettyMarketLabel(stat.key)) + ' <span class="pill">' + activeCount + '/' + cat.quotes.length + '</span></summary>' +
          '<div class="pcurve-line-table-wrap"><table><thead><tr><th></th><th>Line</th><th class="num">Odds</th><th class="num">Impl.</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
        '</details>';
      }).join('');
      el.innerHTML = html || '<div class="muted">No line-level markets.</div>';
      el.querySelectorAll('input[data-pcv-line]').forEach(function(inp){
        inp.addEventListener('change', function(e){
          var key = e.target.getAttribute('data-pcv-line');
          if (e.target.checked) delete disabledLines[key]; else disabledLines[key] = true;
          renderAll();
        });
      });
    }

    function renderChartAndTiles(result){
      var tilesEl = document.getElementById('pcurveTiles');
      var wrapEl = document.getElementById('pcurveChartWrap');
      var subEl = document.getElementById('pcurveSub');
      if (!tilesEl || !wrapEl) return;

      var activeCats = result.perCategory.filter(function(c){ return c.activeQuotes.length > 0; }).length;
      if (subEl) subEl.textContent = result.totalActive + ' of ' + result.totalQuotes + ' quotes across ' + activeCats + ' market' + (activeCats===1?'':'s') + ' feeding the curve';

      if (!result.totalActive){
        tilesEl.innerHTML = '';
        wrapEl.innerHTML = '<div class="muted" style="padding:20px 0; text-align:center;">Nothing selected &mdash; turn a sportsbook or line back on.</div>';
        return;
      }

      var curve = result.curve;
      var floor = xAtProb(curve, 0.85), mid = xAtProb(curve, 0.5), ceiling = xAtProb(curve, 0.15);

      tilesEl.innerHTML =
        '<div class="card floor"><div class="label">Floor (85%)</div><div class="value">' + floor.toFixed(1) + '</div></div>' +
        '<div class="card mid"><div class="label">Mid</div><div class="value">' + mid.toFixed(1) + '</div></div>' +
        '<div class="card ceiling"><div class="label">Ceiling (15%)</div><div class="value">' + ceiling.toFixed(1) + '</div></div>' +
        (result.tdProb != null ? ('<div class="card"><div class="label">TD chance</div><div class="value">' + pct1(result.tdProb) + '</div></div>') : '');

      drawSVG(wrapEl, curve, result.gridMin, result.gridMax, {floor: floor, mid: mid, ceiling: ceiling});
    }

    function drawSVG(wrapEl, curve, gridMin, gridMax, refs){
      var W = 640, H = 190, M = {top:12, right:14, bottom:26, left:34};
      var plotW = W - M.left - M.right, plotH = H - M.top - M.bottom;
      var xScale = function(x){ return M.left + (x - gridMin) / ((gridMax - gridMin) || 1) * plotW; };
      var yScale = function(y){ return M.top + (1 - y) * plotH; };

      var xStep = niceStep(gridMax - gridMin, 6);
      var xTicks = [];
      for (var v = Math.ceil(gridMin / xStep) * xStep; v <= gridMax; v += xStep) xTicks.push(Math.round(v*10)/10);
      var yTicks = [0, .5, 1];

      var gridSvg = '';
      yTicks.forEach(function(t){
        var y = yScale(t);
        gridSvg += '<line class="axis" x1="' + M.left + '" x2="' + (W-M.right) + '" y1="' + y + '" y2="' + y + '"/>';
        gridSvg += '<text class="axis-label" x="' + (M.left-6) + '" y="' + (y+3) + '" text-anchor="end">' + Math.round(t*100) + '%</text>';
      });
      xTicks.forEach(function(t){
        var x = xScale(t);
        gridSvg += '<text class="axis-label" x="' + x + '" y="' + (H-M.bottom+16) + '" text-anchor="middle">' + t + '</text>';
      });

      var linePath = curve.map(function(p,i){ return (i===0?'M':'L') + xScale(p.x).toFixed(1) + ' ' + yScale(p.y).toFixed(1); }).join(' ');
      var areaPath = linePath + ' L' + xScale(curve[curve.length-1].x).toFixed(1) + ' ' + yScale(0).toFixed(1) +
        ' L' + xScale(curve[0].x).toFixed(1) + ' ' + yScale(0).toFixed(1) + ' Z';

      var refSvg = '';
      [['floor', refs.floor], ['mid', refs.mid], ['ceiling', refs.ceiling]].forEach(function(pair){
        var val = pair[1];
        if (val < gridMin || val > gridMax) return;
        var x = xScale(val);
        refSvg += '<line class="marker" x1="' + x + '" x2="' + x + '" y1="' + M.top + '" y2="' + (H-M.bottom) + '"/>';
      });

      wrapEl.innerHTML =
        '<div class="fp-visual"><div class="vis-title">P(fantasy points &ge; x)</div><div class="svg-wrap">' +
        '<svg viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' +
          gridSvg + '<path class="curve" d="' + areaPath + '"/>' + refSvg +
          '<line class="hover-x" x1="0" y1="' + M.top + '" x2="0" y2="' + (H-M.bottom) + '" style="display:none"/>' +
          '<circle class="hover-dot" cx="0" cy="0" r="3" style="display:none"/>' +
          '<rect x="' + M.left + '" y="' + M.top + '" width="' + plotW + '" height="' + plotH + '" fill="transparent" style="cursor:crosshair"/>' +
        '</svg></div>' +
        '<div class="fp-tooltip" style="display:none; left:0; top:0;">x: 0, y: 0</div></div>';

      var svg = wrapEl.querySelector('svg');
      var rect = wrapEl.querySelector('rect');
      var hoverX = wrapEl.querySelector('.hover-x');
      var hoverDot = wrapEl.querySelector('.hover-dot');
      var tip = wrapEl.querySelector('.fp-tooltip');
      function onMove(evt){
        var pt = svg.createSVGPoint();
        var svgRect = svg.getBoundingClientRect();
        var clientX = evt.touches ? evt.touches[0].clientX : evt.clientX;
        pt.x = clientX; pt.y = evt.clientY || (evt.touches && evt.touches[0].clientY) || 0;
        var svgP = pt.matrixTransform(svg.getScreenCTM().inverse());
        var xVal = gridMin + (svgP.x - M.left) / plotW * (gridMax - gridMin);
        xVal = Math.min(gridMax, Math.max(gridMin, xVal));
        var yVal = yAtX(curve, xVal);
        var px = xScale(xVal), py = yScale(yVal);
        hoverX.style.display = ''; hoverX.setAttribute('x1', px); hoverX.setAttribute('x2', px);
        hoverDot.style.display = ''; hoverDot.setAttribute('cx', px); hoverDot.setAttribute('cy', py);
        tip.style.display = '';
        tip.textContent = '≥ ' + xVal.toFixed(1) + ' pts · ' + pct1(yVal);
        var leftPct = ((clientX - svgRect.left) / svgRect.width) * 100;
        tip.style.left = leftPct + '%';
        tip.style.top = ((py / H) * 100) + '%';
      }
      function onLeave(){ hoverX.style.display = 'none'; hoverDot.style.display = 'none'; tip.style.display = 'none'; }
      rect.addEventListener('mousemove', onMove);
      rect.addEventListener('mouseleave', onLeave);
      rect.addEventListener('touchmove', onMove, {passive:true});
      rect.addEventListener('touchend', onLeave);
    }

    function renderAll(){
      renderBookList();
      renderLineDrilldown();
      renderChartAndTiles(computeFantasyCurve());
    }

    document.querySelectorAll('[data-pcv-action]').forEach(function(a){
      a.addEventListener('click', function(e){
        e.preventDefault();
        var action = a.getAttribute('data-pcv-action');
        var books = {};
        cats.forEach(function(cat){ cat.quotes.forEach(function(q){ books[q.book] = true; }); });
        if (action === 'books-all') Object.keys(books).forEach(function(b){ delete disabledBooks[b]; });
        else if (action === 'books-none') Object.keys(books).forEach(function(b){ disabledBooks[b] = true; });
        renderAll();
      });
    });

    renderAll();
  };
})();
