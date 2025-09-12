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
    var minX = Math.max(0, Math.min(f, m) - Math.abs(m-f)*0.5);
    var maxX = Math.max(c, m) + Math.abs(c-m)*0.5;
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
    pts.forEach(function(p, i){ var X=p[0], Y=yScale((p[1]/(maxY||1))*0.9); path += (i?'L':'M') + X.toFixed(1) + ',' + Y.toFixed(1); });
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
          '<circle class="hover-dot" cx="0" cy="0" r="4" style="display:none" />',
        '</svg></div>',
        '<div class="fp-tooltip" style="display:none"></div>',
      '</div>'
    ].join('');
    return svg;
  } catch (e) { return ''; }
}

// The rest of details UI code omitted for brevity in this bundled asset; the app
// primarily relies on core functionality in script.js and simple modals.

