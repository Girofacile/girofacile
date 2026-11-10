/* Anteprime Report · proposta di componente grafico (SVG, senza librerie esterne).
   Ogni grafico è un elemento [data-chart="tipo"] con i dati in un <script type="application/json">
   al suo interno. Tipi: donut, pie, ring, gauge, columns, area, spark. Passando sopra un elemento
   compare il dettaglio; la legenda mostra sempre valore e percentuale (colori a basso contrasto). */
(function(){
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const fmt = (v, d = 0) => Number(v).toLocaleString('it-IT', {minimumFractionDigits: d, maximumFractionDigits: d});
  const el = (name, attrs = {}, parent) => {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  };
  const color = c => c && c.startsWith('--') ? `var(${c})` : (c || 'var(--gf-chart-1)');

  function tooltip(host){
    let tip = host.querySelector('.gf-chart__tooltip');
    if (!tip){ tip = document.createElement('div'); tip.className = 'gf-chart__tooltip'; tip.hidden = true; host.appendChild(tip); }
    return {
      show(evt, title, rows){
        const box = host.getBoundingClientRect();
        tip.innerHTML = `<strong>${title}</strong>` + rows.map(r => `<span><i class="gf-chart__swatch" style="--swatch:${color(r.color)}"></i>${r.text}</span>`).join('');
        tip.style.left = `${evt.clientX - box.left}px`; tip.style.top = `${evt.clientY - box.top}px`; tip.hidden = false;
      },
      hide(){ tip.hidden = true; }
    };
  }
  function bind(mark, tip, title, rows){
    mark.classList.add('gf-chart__mark');
    mark.addEventListener('mousemove', e => tip.show(e, title, rows));
    mark.addEventListener('mouseleave', () => tip.hide());
  }
  function legend(target, items, total, unit = ''){
    if (!target) return;
    target.innerHTML = items.map(i => {
      const pct = total ? ` · ${fmt(i.value / total * 100)}%` : '';
      return `<li><i class="gf-chart__swatch" style="--swatch:${color(i.color)}"></i><span>${i.label}</span><b>${fmt(i.value, i.decimals || 0)}${unit}</b><span>${pct.replace(' · ', '')}</span></li>`;
    }).join('');
  }
  const arc = (cx, cy, r, a0, a1) => {
    const p = a => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1} ${y1}`;
  };

  // Ciambella o torta: fette con 2px di spazio tra l'una e l'altra.
  function donut(host, cfg, canvas, pie){
    const size = 200, c = size / 2, total = cfg.segments.reduce((s, x) => s + x.value, 0);
    const svg = el('svg', {viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': cfg.aria || cfg.title || ''}, canvas);
    const tip = tooltip(canvas);
    const thick = pie ? c : (cfg.thickness || 26), r = pie ? c / 2 : c - thick / 2 - 2;
    let a = -Math.PI / 2;
    cfg.segments.forEach(s => {
      const span = s.value / total * Math.PI * 2, gap = cfg.segments.length > 1 ? (pie ? 0.012 : 0.035) : 0;
      const path = el('path', {d: arc(c, c, r, a + gap / 2, a + span - gap / 2), fill: 'none', stroke: color(s.color), 'stroke-width': pie ? c - 4 : thick, 'stroke-linecap': 'butt'}, svg);
      if (pie) path.setAttribute('stroke-width', c);
      bind(path, tip, s.label, [{color: s.color, text: `${fmt(s.value, s.decimals || 0)}${cfg.unit || ''} · ${fmt(s.value / total * 100)}%`}]);
      a += span;
    });
    if (pie){ const ring = el('circle', {cx: c, cy: c, r: c - 1, fill: 'none', stroke: 'var(--gf-color-surface)', 'stroke-width': 2}, svg); ring.style.pointerEvents = 'none'; }
    if (!pie && cfg.center){
      el('text', {x: c, y: c + 6, 'text-anchor': 'middle', class: 'gf-chart__center', style: 'font-size:32px'}, svg).textContent = cfg.center.value;
      el('text', {x: c, y: c + 26, 'text-anchor': 'middle', style: 'font-size:12px'}, svg).textContent = cfg.center.label;
    }
    legend(host.querySelector('.gf-chart__legend'), cfg.segments, total, cfg.unit || '');
  }

  // Anelli di avanzamento concentrici (percentuali), ognuno con il proprio colore.
  function ring(host, cfg, canvas){
    const size = 200, c = size / 2, thick = cfg.thickness || 14, gap = 6;
    const svg = el('svg', {viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': cfg.aria || ''}, canvas);
    const tip = tooltip(canvas);
    cfg.rings.forEach((g, i) => {
      const r = c - thick / 2 - 2 - i * (thick + gap);
      el('circle', {cx: c, cy: c, r, fill: 'none', stroke: 'var(--gf-chart-track)', 'stroke-width': thick}, svg);
      const len = 2 * Math.PI * r, val = Math.max(0, Math.min(100, g.value));
      const circle = el('circle', {cx: c, cy: c, r, fill: 'none', stroke: color(g.color), 'stroke-width': thick, 'stroke-linecap': 'round',
        'stroke-dasharray': `${len * val / 100} ${len}`, transform: `rotate(-90 ${c} ${c})`}, svg);
      bind(circle, tip, g.label, [{color: g.color, text: `${fmt(g.value)}%${g.note ? ' · ' + g.note : ''}`}]);
    });
    if (cfg.center){
      el('text', {x: c, y: c + (cfg.center.label ? 4 : 10), 'text-anchor': 'middle', class: 'gf-chart__center', style: `font-size:${cfg.rings.length > 1 ? 28 : 38}px`}, svg).textContent = cfg.center.value;
      if (cfg.center.label) el('text', {x: c, y: c + 24, 'text-anchor': 'middle', style: 'font-size:12px'}, svg).textContent = cfg.center.label;
    }
    const lg = host.querySelector('.gf-chart__legend');
    if (lg) lg.innerHTML = cfg.rings.map(g => `<li><i class="gf-chart__swatch" style="--swatch:${color(g.color)}"></i><span>${g.label}</span><b>${fmt(g.value)}%</b></li>`).join('');
  }

  // Semicerchio con lancetta implicita: valore su un obiettivo.
  function gauge(host, cfg, canvas){
    const w = 220, h = 130, cx = w / 2, cy = 116, r = 92, thick = 18;
    const svg = el('svg', {viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': cfg.aria || ''}, canvas);
    const tip = tooltip(canvas);
    el('path', {d: arc(cx, cy, r, Math.PI, 2 * Math.PI), fill: 'none', stroke: 'var(--gf-chart-track)', 'stroke-width': thick, 'stroke-linecap': 'round'}, svg);
    const v = Math.max(0, Math.min(1, cfg.value / cfg.max));
    const path = el('path', {d: arc(cx, cy, r, Math.PI, Math.PI + Math.max(0.001, v * Math.PI)), fill: 'none', stroke: color(cfg.color), 'stroke-width': thick, 'stroke-linecap': 'round'}, svg);
    bind(path, tip, cfg.label, [{color: cfg.color, text: `${fmt(cfg.value, cfg.decimals || 0)}${cfg.unit || ''} su ${fmt(cfg.max, cfg.decimals || 0)}${cfg.unit || ''}`}]);
    el('text', {x: cx, y: cy - 22, 'text-anchor': 'middle', class: 'gf-chart__center', style: 'font-size:30px'}, svg).textContent = cfg.display || fmt(cfg.value);
    el('text', {x: cx, y: cy - 2, 'text-anchor': 'middle', style: 'font-size:12px'}, svg).textContent = cfg.caption || '';
    el('text', {x: cx - r, y: cy + 14, 'text-anchor': 'middle'}, svg).textContent = cfg.minLabel ?? '0';
    el('text', {x: cx + r, y: cy + 14, 'text-anchor': 'middle'}, svg).textContent = cfg.maxLabel ?? fmt(cfg.max);
  }

  const niceMax = v => { const raw = (v || 1) / 4, p = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p * 4; };

  // Colonne (semplici, affiancate o impilate) su un solo asse.
  function columns(host, cfg, canvas){
    const w = Math.max(320, Math.round(canvas.clientWidth || 640)), h = cfg.height || 240, padL = 36, padB = 26, padT = 16, n = cfg.labels.length;
    const svg = el('svg', {viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': cfg.aria || ''}, canvas);
    const tip = tooltip(canvas);
    const totals = cfg.labels.map((_, i) => cfg.stacked ? cfg.series.reduce((s, x) => s + x.values[i], 0) : Math.max(...cfg.series.map(x => x.values[i])));
    const max = niceMax(Math.max(...totals)), ph = h - padB - padT, y = v => padT + ph - v / max * ph;
    for (let k = 0; k <= 4; k++){
      const v = max * k / 4, yy = y(v);
      el('line', {x1: padL, x2: w, y1: yy, y2: yy, stroke: k ? 'var(--gf-chart-grid)' : 'var(--gf-chart-axis)', 'stroke-width': 1}, svg);
      el('text', {x: padL - 8, y: yy + 4, 'text-anchor': 'end'}, svg).textContent = fmt(v);
    }
    const slot = (w - padL) / n, groups = cfg.stacked ? 1 : cfg.series.length;
    const bw = Math.min(cfg.barWidth || 22, (slot * 0.7) / groups);
    cfg.labels.forEach((label, i) => {
      const x0 = padL + slot * i + slot / 2 - (bw * groups + 2 * (groups - 1)) / 2;
      let base = 0;
      cfg.series.forEach((s, j) => {
        const v = s.values[i]; if (!v) return;
        const top = cfg.stacked ? y(base + v) : y(v), bottom = cfg.stacked ? y(base) : y(0);
        const x = cfg.stacked ? x0 : x0 + j * (bw + 2), hgt = Math.max(1, bottom - top - (cfg.stacked && base ? 2 : 0));
        const r = Math.min(4, bw / 2), isTop = !cfg.stacked || j === cfg.series.length - 1 || cfg.series.slice(j + 1).every(t => !t.values[i]);
        const d = isTop ? `M${x},${top + hgt} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${top + hgt} Z` : `M${x},${top} h${bw} v${hgt} h${-bw} Z`;
        const bar = el('path', {d, fill: color(s.color)}, svg);
        bind(bar, tip, cfg.tipTitle ? cfg.tipTitle[i] : label, cfg.series.map(t => ({color: t.color, text: `${t.name}: ${fmt(t.values[i])}${cfg.unit || ''}`})));
        if (cfg.stacked) base += v;
      });
      if (cfg.showTotals){ el('text', {x: padL + slot * i + slot / 2, y: y(totals[i]) - 6, 'text-anchor': 'middle', class: 'gf-chart__value'}, svg).textContent = fmt(totals[i]); }
      if (!cfg.labelEvery || i % cfg.labelEvery === 0) el('text', {x: padL + slot * i + slot / 2, y: h - 6, 'text-anchor': 'middle'}, svg).textContent = label;
    });
    const lg = host.querySelector('.gf-chart__legend');
    if (lg && cfg.series.length > 1) lg.innerHTML = cfg.series.map(s => `<li><i class="gf-chart__swatch" style="--swatch:${color(s.color)}"></i><span>${s.name}</span><b>${fmt(s.values.reduce((a, b) => a + b, 0))}${cfg.unit || ''}</b></li>`).join('');
  }

  // Linee e aree (una scala), con mirino verticale e punto finale evidenziato.
  function area(host, cfg, canvas){
    const w = Math.max(320, Math.round(canvas.clientWidth || 640)), h = cfg.height || 220, padL = 40, padB = 26, padT = 14, n = cfg.labels.length;
    const svg = el('svg', {viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': cfg.aria || ''}, canvas);
    const tip = tooltip(canvas);
    const max = niceMax(Math.max(...cfg.series.flatMap(s => s.values))), ph = h - padB - padT;
    const x = i => padL + (w - padL - 8) * (n === 1 ? 0.5 : i / (n - 1)), y = v => padT + ph - v / max * ph;
    for (let k = 0; k <= 4; k++){
      const v = max * k / 4, yy = y(v);
      el('line', {x1: padL, x2: w, y1: yy, y2: yy, stroke: k ? 'var(--gf-chart-grid)' : 'var(--gf-chart-axis)', 'stroke-width': 1}, svg);
      el('text', {x: padL - 8, y: yy + 4, 'text-anchor': 'end'}, svg).textContent = fmt(v);
    }
    cfg.series.forEach((s, j) => {
      const pts = s.values.map((v, i) => [x(i), y(v)]);
      const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
      if (cfg.fill !== false && (cfg.series.length === 1 || s.fill)){
        const gid = 'g' + Math.random().toString(36).slice(2);
        const defs = el('defs', {}, svg), grad = el('linearGradient', {id: gid, x1: 0, y1: 0, x2: 0, y2: 1}, defs);
        el('stop', {offset: '0%', 'stop-color': color(s.color), 'stop-opacity': 0.28}, grad);
        el('stop', {offset: '100%', 'stop-color': color(s.color), 'stop-opacity': 0}, grad);
        el('path', {d: `${line} L${x(n - 1)},${y(0)} L${x(0)},${y(0)} Z`, fill: `url(#${gid})`}, svg);
      }
      el('path', {d: line, fill: 'none', stroke: color(s.color), 'stroke-width': 2.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-dasharray': s.dashed ? '6 5' : 'none'}, svg);
      const last = pts[pts.length - 1];
      el('circle', {cx: last[0], cy: last[1], r: 5, fill: color(s.color), stroke: 'var(--gf-color-surface)', 'stroke-width': 2}, svg);
    });
    cfg.labels.forEach((l, i) => { if (!cfg.labelEvery || i % cfg.labelEvery === 0 || i === n - 1) el('text', {x: x(i), y: h - 6, 'text-anchor': 'middle'}, svg).textContent = l; });
    const cross = el('line', {y1: padT, y2: padT + ph, stroke: 'var(--gf-chart-axis)', 'stroke-width': 1, 'stroke-dasharray': '3 3', opacity: 0}, svg);
    const dots = cfg.series.map(s => el('circle', {r: 5, fill: color(s.color), stroke: 'var(--gf-color-surface)', 'stroke-width': 2, opacity: 0}, svg));
    const hit = el('rect', {x: padL, y: padT, width: w - padL, height: ph, fill: 'transparent'}, svg);
    hit.addEventListener('mousemove', e => {
      const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) / b.width * w;
      const i = Math.max(0, Math.min(n - 1, Math.round((px - padL) / ((w - padL - 8) / (n - 1)))));
      cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('opacity', 1);
      dots.forEach((d, j) => { d.setAttribute('cx', x(i)); d.setAttribute('cy', y(cfg.series[j].values[i])); d.setAttribute('opacity', 1); });
      tip.show(e, cfg.tipTitle ? cfg.tipTitle[i] : cfg.labels[i], cfg.series.map(s => ({color: s.color, text: `${s.name}: ${fmt(s.values[i], s.decimals || 0)}${cfg.unit || ''}`})));
    });
    hit.addEventListener('mouseleave', () => { tip.hide(); cross.setAttribute('opacity', 0); dots.forEach(d => d.setAttribute('opacity', 0)); });
    const lg = host.querySelector('.gf-chart__legend');
    if (lg && cfg.series.length > 1) lg.innerHTML = cfg.series.map(s => `<li><i class="gf-chart__swatch" style="--swatch:${color(s.color)}"></i><span>${s.name}</span></li>`).join('');
  }

  // Mini andamento nei riquadri indicatore.
  function spark(host, cfg, canvas){
    const w = 120, h = 36, n = cfg.values.length, max = Math.max(...cfg.values), min = Math.min(...cfg.values);
    const svg = el('svg', {viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: 'none', 'aria-hidden': 'true'}, canvas);
    const x = i => i / (n - 1) * (w - 4) + 2, y = v => h - 4 - (v - min) / ((max - min) || 1) * (h - 10);
    const line = cfg.values.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(v).toFixed(1)).join(' ');
    if (cfg.bars){
      const bw = (w - 4) / n - 3;
      cfg.values.forEach((v, i) => el('rect', {x: 2 + i * ((w - 4) / n), y: y(v), width: bw, height: h - y(v), rx: 2, fill: color(cfg.color), opacity: i === n - 1 ? 1 : 0.45}, svg));
      return;
    }
    const gid = 's' + Math.random().toString(36).slice(2);
    const grad = el('linearGradient', {id: gid, x1: 0, y1: 0, x2: 0, y2: 1}, el('defs', {}, svg));
    el('stop', {offset: '0%', 'stop-color': color(cfg.color), 'stop-opacity': 0.25}, grad); el('stop', {offset: '100%', 'stop-color': color(cfg.color), 'stop-opacity': 0}, grad);
    el('path', {d: `${line} L${x(n - 1)},${h} L${x(0)},${h} Z`, fill: `url(#${gid})`}, svg);
    el('path', {d: line, fill: 'none', stroke: color(cfg.color), 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'vector-effect': 'non-scaling-stroke'}, svg);
  }

  const RENDER = {donut: (h, c, v) => donut(h, c, v, false), pie: (h, c, v) => donut(h, c, v, true), ring, gauge, columns, area, spark};
  function render(root = document){
    root.querySelectorAll('[data-chart]').forEach(host => {
      const data = host.querySelector('script[type="application/json"]');
      if (!data) return;
      const cfg = JSON.parse(data.textContent);
      let canvas = host.querySelector('.gf-chart__canvas');
      if (!canvas){ canvas = document.createElement('div'); canvas.className = 'gf-chart__canvas'; host.appendChild(canvas); }
      canvas.querySelectorAll('svg').forEach(s => s.remove());
      RENDER[host.dataset.chart]?.(host, cfg, canvas);
    });
  }
  let resize;
  window.addEventListener('resize', () => { clearTimeout(resize); resize = setTimeout(() => render(), 150); });
  document.addEventListener('DOMContentLoaded', () => {
    render();
    // Selettore del periodo nelle anteprime: solo l'aspetto, i dati restano quelli di esempio.
    document.querySelectorAll('.gf-period').forEach(group => group.addEventListener('click', e => {
      const b = e.target.closest('button'); if (!b) return;
      group.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    }));
  });
  window.GFCharts = {render};
})();
