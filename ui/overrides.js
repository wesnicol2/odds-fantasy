// UI overrides for clearer incomplete indicators and bench rows
(function(){
  function onReady(fn){ if(document.readyState!=='loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  function fmtCell(v){ return (v==null ? '-' : Number(v).toFixed(2)); }
  function shortLabel(k){
    var map = {
      'player_pass_yds':'Pass Yds','player_pass_tds':'Pass TDs','player_pass_interceptions':'INTs','player_rush_yds':'Rush Yds','player_receptions':'Rec','player_reception_yds':'Rec Yds','player_anytime_td':'Any TD'
    };
    try { return map[k] || (typeof window._prettyMarketLabel==='function' ? window._prettyMarketLabel(k) : (k||'')); } catch(e){ return k||''; }
  }
  function esc(s){ try { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); } catch(e){ return ''; } }

  onReady(function(){
    // Remove raw projections + players sections from the page
    try {
      ['projectionsDebug','players-this','players-next'].forEach(function(id){
        var el = document.getElementById(id);
        if (el) {
          var sec = el.closest('section');
          if (sec && sec.parentNode) sec.parentNode.removeChild(sec);
        }
      });
    } catch (e) { }

    // Force fresh=1 on API calls when Fresh mode selected
    try {
      if (typeof window.apiUrl === 'function' && typeof window.getDataMode === 'function') {
        var __origApiUrl = window.apiUrl;
        window.apiUrl = function(path, params){
          params = params || {};
          if (params.fresh == null) {
            params.fresh = (window.getDataMode() === 'fresh' ? '1' : '0');
          }
          if (params.region == null || String(params.region).trim() === '') {
            params.region = 'us,us2';
          }
          return __origApiUrl(path, params);
        };
      }
    } catch (e) { /* ignore */ }
    // Override computeLineupFromPlayers: keep starters, append bench (no effect on total)
    if (typeof window.computeLineupFromPlayers === 'function') {
      var origBy = function(t){ return function(a,b){ return Number(b[t]||0) - Number(a[t]||0); }; };
      window.computeLineupFromPlayers = function(players, target){
        var buckets = { QB: [], RB: [], WR: [], TE: [] };
        function nameKey(s){ try { return String(s||'').toLowerCase().replace(/[\.'`-]/g,'').replace(/\s+/g,' ').trim(); } catch(e){ return String(s||''); } }
        (players||[]).forEach(function(p){ if (buckets[p.pos]) buckets[p.pos].push(p); });
        Object.keys(buckets).forEach(function(pos){ buckets[pos].sort(origBy(target)); });
        var used = new Set();
        function take(pos, n){ var out=[]; for (var i=0;i<buckets[pos].length;i++){ var p=buckets[pos][i]; var k=nameKey(p.name); if(!used.has(k)){ out.push(p); used.add(k); if(out.length===n) break; } } return out; }
        var lineup = { QB: take('QB',1), RB: take('RB',2), WR: take('WR',2), TE: take('TE',1) };
        var flexPool = []; ['WR','RB','TE'].forEach(function(pos){ buckets[pos].forEach(function(p){ var k=nameKey(p.name); if(!used.has(k)) flexPool.push(p); }); });
        flexPool.sort(origBy(target)); lineup.FLEX = flexPool.slice(0,1);
        lineup.FLEX.forEach(function(p){ used.add(nameKey(p.name)); });
        var rows=[]; var total=0;
        function add(slot,p,countTotal){ if(countTotal===undefined) countTotal=true; var pts=Number(p[target]||0); if(countTotal) total+=pts; rows.push({ slot:slot,name:p.name,pos:p.pos,floor:(p.floor!=null?Number(p.floor):null),mid:(p.mid!=null?Number(p.mid):null),ceiling:(p.ceiling!=null?Number(p.ceiling):null), incomplete: !!p.incomplete, missing_markets:(p.missing_markets||[]), fallback_markets:(p.fallback_markets||[]) }); }
        lineup.QB.forEach(function(p){ add('QB',p); });
        lineup.RB.forEach(function(p){ add('RB',p); });
        lineup.WR.forEach(function(p){ add('WR',p); });
        lineup.TE.forEach(function(p){ add('TE',p); });
        lineup.FLEX.forEach(function(p){ add('FLEX',p); });
        var bench=[]; ['QB','RB','WR','TE'].forEach(function(pos){ buckets[pos].forEach(function(p){ var k=nameKey(p.name); if(!used.has(k)) bench.push(p); }); });
        bench.sort(origBy(target)); bench.forEach(function(p){ add('BENCH',p,false); });
        return { target:target, lineup:rows, total_points:Number(total.toFixed(2)) };
      };
    }

    // Override renderLineup to show list of missing markets as a pill (yellow=some, red=all)
    if (typeof window.renderLineup === 'function') {
      var _origRL = window.renderLineup;
      window.renderLineup = function(containerId, title, payload){
        try{
          var c=document.getElementById(containerId); var rows=(payload&&payload.lineup)||[]; var target=(payload&&payload.target)||'mid'; var total=Number((payload&&payload.total_points)||0); var rl=(payload&&payload.ratelimit)||'';
          var header='<th>Slot</th><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th>';
          var body=rows.map(function(r){
            var inc=!!r.incomplete||(r.mid==null&&r.floor==null&&r.ceiling==null);
            var miss=r.missing_markets||[]; var fb=r.fallback_markets||[];
            var missV=(r.missing_vital||[]), fbV=(r.fallback_vital||[]);
            var isCrit=(Array.isArray(missV)&&missV.length>0) || (Array.isArray(fbV)&&fbV.length>0);
            if (missV==null && fbV==null) { isCrit = inc && (!fb.length) && (r.mid==null && r.floor==null && r.ceiling==null); }
            var pillCls=isCrit?'pill-crit':'pill-warn';
            var crit = [];
            if (Array.isArray(missV)) crit = crit.concat(missV);
            if (Array.isArray(fbV)) crit = crit.concat(fbV);
            var showList = isCrit ? crit : miss;
            var missTxt=showList.map(shortLabel).join(', ');
            var tipParts=[];
            if (isCrit) tipParts.push('Vital: '+(crit.map(shortLabel).join(', ')||'-'));
            if (fb.length||miss.length) tipParts.push('All missing: '+(miss.map(shortLabel).join(', ')||'-')+(fb.length?(' | Fallback: '+fb.map(shortLabel).join(', ')) : ''));
            var tip=tipParts.join(' | ');
            var indicator=inc?(' <span class="pill '+pillCls+'" title="'+esc(tip)+'">'+esc(missTxt||'incomplete')+'</span>'):'';
            var displayName = '<span class="player-name" data-player="'+esc(r.name)+'">'+esc(r.name)+'</span>';
            var nameHtml = displayName + indicator;
            if (isCrit) nameHtml = '<span class="incomplete-name">'+nameHtml+'</span>';
            var fmt=function(v){ return (v==null ? '-' : Number(v).toFixed(2)); };
            return '<tr><td>'+ (r.slot||'') +'</td><td>'+ nameHtml +'</td><td>'+ (r.pos||'') +'</td><td>'+ fmt(r.floor) +'</td><td>'+ fmt(r.mid) +'</td><td>'+ fmt(r.ceiling) +'</td></tr>';
          }).join('');
          c.innerHTML=['<h3>'+title+' - target: '+target+' (total: '+total.toFixed(2)+')</h3>','<table><thead><tr>'+header+'</tr></thead><tbody>',body,'</tbody></table>','<div class="status">RateLimit: '+rl+'</div>'].join('\n');
          try { if (window.enableTableSort) { window.enableTableSort(c.querySelector('table')); } } catch(e) {}
        }catch(e){ try{ _origRL(containerId,title,payload); }catch(_){} }
      };
    }

    // Override renderPlayers likewise
    if (typeof window.renderPlayers === 'function'){
      var _orig = window.renderPlayers;
      window.renderPlayers = function(containerId, players){
        try{
          var c=document.getElementById(containerId); var rows=Array.isArray(players)?players.slice():[]; if(!c) return _orig(containerId,players); if(!rows.length){ c.innerHTML='<div class="status">No players found.</div>'; return; }
          rows.sort(function(a,b){ return Number(b.mid||0)-Number(a.mid||0); });
          var body=rows.map(function(r){
            var inc=!!r.incomplete||(r.mid==null&&r.floor==null&&r.ceiling==null);
            var miss=r.missing_markets||[]; var fb=r.fallback_markets||[];
            var missV=(r.missing_vital||[]), fbV=(r.fallback_vital||[]);
            var isCrit=(missV.length>0 || fbV.length>0);
            if (missV==null && fbV==null) { isCrit = inc && (!fb.length) && ((r.markets_used||0)===0); }
            var pillCls=isCrit?'pill-crit':'pill-warn';
            var crit = [];
            if (Array.isArray(missV)) crit = crit.concat(missV);
            if (Array.isArray(fbV)) crit = crit.concat(fbV);
            var showList = isCrit ? crit : miss;
            var missTxt=showList.map(shortLabel).join(', ');
            var tipParts=[];
            if (isCrit) tipParts.push('Vital: '+(crit.map(shortLabel).join(', ')||'-'));
            if (fb.length||miss.length) tipParts.push('All missing: '+(miss.map(shortLabel).join(', ')||'-')+(fb.length?(' | Fallback: '+fb.map(shortLabel).join(', ')) : ''));
            var tip=tipParts.join(' | ');
            var indicator=inc?(' <span class="pill '+pillCls+'" title="'+esc(tip)+'">'+esc(missTxt||'incomplete')+'</span>'):'';
            var displayName = '<span class="player-name" data-player="'+esc(r.name)+'">'+esc(r.name)+'</span>';
            var nameHtml = displayName + indicator;
            if (isCrit) nameHtml = '<span class="incomplete-name">'+nameHtml+'</span>';
            return '<tr><td>'+ nameHtml +'</td><td>'+ (r.pos||'') +'</td><td>'+ fmtCell(r.floor) +'</td><td>'+ fmtCell(r.mid) +'</td><td>'+ fmtCell(r.ceiling) +'</td></tr>';
          }).join('');
          c.innerHTML='<table><thead><tr><th>Name</th><th>Pos</th><th>Floor</th><th>Mid</th><th>Ceiling</th></tr></thead><tbody>'+body+'</tbody></table>';
          try { if (window.enableTableSort) { window.enableTableSort(c.querySelector('table')); } } catch(e) {}
        }catch(e){ try{ _orig(containerId,players); }catch(_){} }
      };
    }
  });
})();

