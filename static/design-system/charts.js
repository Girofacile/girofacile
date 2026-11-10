/* GiroFacile · grafici del sistema di stile (SVG, senza librerie esterne).
   Uso: GFCharts.draw(contenitore, tipo, dati), dove il contenitore è un elemento .gf-chart con dentro
   un .gf-chart__canvas e, se serve, una .gf-chart__legend. Tipi: donut, pie, ring, gauge, columns, area, spark.
   Nel catalogo si può anche scrivere <div class="gf-chart" data-chart="tipo" data-chart-data='{…}'>:
   viene disegnato da solo all'apertura della pagina.
   I colori sono i numeri 1–8 delle tinte --gf-chart-N di theme.css, sempre in quest'ordine.
   Passando sopra un elemento compare il dettaglio; la legenda mostra sempre valore e percentuale. */
(function(){
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const tone = t => String(Math.min(8, Math.max(1, Number(t) || 1)));
  const paint = t => `var(--gf-chart-${tone(t)})`;
  const num = (v, d = 0) => Number(v || 0).toLocaleString('it-IT', {minimumFractionDigits: d, maximumFractionDigits: d});
  const fmt = (v, f = {}) => `${f.prefix || ''}${num(v, f.decimals || 0)}${f.suffix || ''}`;
  const pct = (v, total) => total ? `${num(v / total * 100)}%` : '0%';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const el = (name, attrs = {}, parent) => {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (parent) parent.appendChild(node);
    return node;
  };
  const text = (parent, attrs, value) => { const t = el('text', attrs, parent); t.textContent = value; return t; };
  const swatch = t => `<i class="gf-chart__swatch" data-tone="${tone(t)}"></i>`;

  function tooltip(canvas){
    let tip = canvas.querySelector('.gf-chart__tooltip');
    if (!tip){ tip = document.createElement('div'); tip.className = 'gf-chart__tooltip'; tip.hidden = true; canvas.appendChild(tip); }
    return {
      show(evt, title, rows){
        const box = canvas.getBoundingClientRect();
        tip.innerHTML = `<strong>${esc(title)}</strong>` + rows.map(r => `<span>${swatch(r.tone)}${esc(r.text)}</span>`).join('');
        tip.style.left = `${evt.clientX - box.left}px`;
        tip.style.top = `${evt.clientY - box.top}px`;
        tip.hidden = false;
      },
      hide(){ tip.hidden = true; }
    };
  }
  function bind(mark, tip, title, rows){
    mark.classList.add('gf-chart__mark');
    mark.addEventListener('mousemove', e => tip.show(e, title, rows));
    mark.addEventListener('mouseleave', () => tip.hide());
  }
  function legend(host, items, total, f){
    const target = host.querySelector('.gf-chart__legend');
    if (!target) return;
    target.innerHTML = items.map(i => `<li>${swatch(i.tone)}<span>${esc(i.label)}</span><b>${fmt(i.value, f)}</b>${total ? `<span>${pct(i.value, total)}</span>` : ''}</li>`).join('');
  }
  const arc = (cx, cy, r, a0, a1) => {
    const p = a => [cx + r * Math.cos(a), cy + r * Math.sin(a)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 ${a1 - a0 > Math.PI ? 1 : 0} 1 ${x1} ${y1}`;
  };
  // Scala con 4 intervalli "tondi" (1, 2, 2,5, 5, 10 per potenza di dieci).
  const niceMax = v => { const raw = (v || 1) / 4, p = Math.pow(10, Math.floor(Math.log10(raw))), n = raw / p; return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p * 4; };
  const width = canvas => Math.max(320, Math.round(canvas.clientWidth || 640));

  // Ciambella o torta: fette separate da un sottile spazio.
  function donut(host, cfg, canvas, pie){
    const size = 200, c = size / 2, segs = cfg.segments.filter(s => Number(s.value) > 0);
    const total = segs.reduce((s, x) => s + Number(x.value), 0), f = cfg.format || {};
    const svg = el('svg', {viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': cfg.label || ''}, canvas);
    const tip = tooltip(canvas);
    const thick = cfg.thickness || 26, r = pie ? c / 2 : c - thick / 2 - 2;
    if (!pie) el('circle', {cx: c, cy: c, r, fill: 'none', stroke: 'var(--gf-chart-rail)', 'stroke-width': thick}, svg);
    let a = -Math.PI / 2;
    segs.forEach(s => {
      const span = Number(s.value) / total * Math.PI * 2, gap = segs.length > 1 ? (pie ? 0.012 : 0.035) : 0;
      const d = segs.length === 1 ? arc(c, c, r, a, a + Math.PI * 2 - 0.0001) : arc(c, c, r, a + gap / 2, a + span - gap / 2);
      const path = el('path', {d, fill: 'none', stroke: paint(s.tone), 'stroke-width': pie ? c : thick}, svg);
      bind(path, tip, s.label, [{tone: s.tone, text: `${fmt(s.value, f)} · ${pct(s.value, total)}`}]);
      a += span;
    });
    if (!pie && cfg.center){
      text(svg, {x: c, y: c + 6, 'text-anchor': 'middle', class: 'gf-chart__center'}, cfg.center.value);
      text(svg, {x: c, y: c + 28, 'text-anchor': 'middle', class: 'gf-chart__caption'}, cfg.center.label || '');
    }
    legend(host, cfg.segments, total, f);
  }

  // Anello di avanzamento (percentuale), con il valore al centro.
  function ring(host, cfg, canvas){
    const size = 200, c = size / 2, thick = cfg.thickness || 18, r = c - thick / 2 - 2;
    const svg = el('svg', {viewBox: `0 0 ${size} ${size}`, role: 'img', 'aria-label': cfg.label || ''}, canvas);
    const tip = tooltip(canvas);
    el('circle', {cx: c, cy: c, r, fill: 'none', stroke: 'var(--gf-chart-rail)', 'stroke-width': thick}, svg);
    const len = 2 * Math.PI * r, val = Math.max(0, Math.min(100, Number(cfg.value) || 0));
    if (val > 0){
      const circle = el('circle', {cx: c, cy: c, r, fill: 'none', stroke: paint(cfg.tone), 'stroke-width': thick, 'stroke-linecap': 'round',
        'stroke-dasharray': `${len * val / 100} ${len}`, transform: `rotate(-90 ${c} ${c})`}, svg);
      bind(circle, tip, cfg.label || '', [{tone: cfg.tone, text: `${num(val)}%${cfg.note ? ' · ' + cfg.note : ''}`}]);
    }
    text(svg, {x: c, y: c + (cfg.caption ? 6 : 14), 'text-anchor': 'middle', class: 'gf-chart__center', 'data-size': cfg.size || 'lg'}, cfg.display ?? `${num(val)}%`);
    if (cfg.caption) text(svg, {x: c, y: c + 30, 'text-anchor': 'middle', class: 'gf-chart__caption'}, cfg.caption);
  }

  // Semicerchio: un valore su un massimo.
  function gauge(host, cfg, canvas){
    const w = 220, h = 134, cx = w / 2, cy = 112, r = 92, thick = 18, f = cfg.format || {};
    const svg = el('svg', {viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': cfg.label || ''}, canvas);
    const tip = tooltip(canvas);
    el('path', {d: arc(cx, cy, r, Math.PI, 2 * Math.PI), fill: 'none', stroke: 'var(--gf-chart-rail)', 'stroke-width': thick, 'stroke-linecap': 'round'}, svg);
    const v = Math.max(0, Math.min(1, (Number(cfg.value) || 0) / (cfg.max || 1)));
    const path = el('path', {d: arc(cx, cy, r, Math.PI, Math.PI + Math.max(0.001, v * Math.PI)), fill: 'none', stroke: paint(cfg.tone), 'stroke-width': thick, 'stroke-linecap': 'round'}, svg);
    bind(path, tip, cfg.label || '', [{tone: cfg.tone, text: `${fmt(cfg.value, f)} su ${fmt(cfg.max, f)}`}]);
    text(svg, {x: cx, y: cy - 22, 'text-anchor': 'middle', class: 'gf-chart__center'}, cfg.display ?? fmt(cfg.value, f));
    text(svg, {x: cx, y: cy - 2, 'text-anchor': 'middle', class: 'gf-chart__caption'}, cfg.caption || '');
    text(svg, {x: cx - r, y: cy + 22, 'text-anchor': 'middle'}, cfg.minLabel ?? fmt(0, f));
    text(svg, {x: cx + r, y: cy + 22, 'text-anchor': 'middle'}, cfg.maxLabel ?? fmt(cfg.max, f));
  }

  function grid(svg, w, padL, y, max, f){
    for (let k = 0; k <= 4; k++){
      const v = max * k / 4, yy = y(v);
      el('line', {x1: padL, x2: w, y1: yy, y2: yy, stroke: k ? 'var(--gf-chart-grid)' : 'var(--gf-chart-axis)', 'stroke-width': 1}, svg);
      text(svg, {x: padL - 8, y: yy + 4, 'text-anchor': 'end'}, fmt(v, {prefix: f.prefix, suffix: f.axisSuffix || ''}));
    }
  }

  // Colonne su un solo asse: una serie (anche con un colore per colonna), affiancate o impilate.
  function columns(host, cfg, canvas){
    const w = width(canvas), h = cfg.height || 240, padL = 44, padB = 26, padT = 20, n = cfg.labels.length, f = cfg.format || {};
    const svg = el('svg', {viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': cfg.label || ''}, canvas);
    const tip = tooltip(canvas);
    const val = (s, i) => Number(s.values[i]) || 0;
    const totals = cfg.labels.map((_, i) => cfg.stacked ? cfg.series.reduce((s, x) => s + val(x, i), 0) : Math.max(...cfg.series.map(x => val(x, i))));
    const max = niceMax(Math.max(...totals)), ph = h - padB - padT, y = v => padT + ph - v / max * ph;
    grid(svg, w, padL, y, max, f);
    const slot = (w - padL) / Math.max(1, n), groups = cfg.stacked ? 1 : cfg.series.length;
    const bw = Math.min(cfg.barWidth || 34, (slot * 0.62) / groups);
    cfg.labels.forEach((label, i) => {
      const x0 = padL + slot * i + slot / 2 - (bw * groups + 2 * (groups - 1)) / 2;
      let base = 0;
      cfg.series.forEach((s, j) => {
        const v = val(s, i); if (!v) return;
        const top = cfg.stacked ? y(base + v) : y(v), bottom = cfg.stacked ? y(base) : y(0);
        const x = cfg.stacked ? x0 : x0 + j * (bw + 2), hgt = Math.max(1, bottom - top - (cfg.stacked && base ? 2 : 0));
        const r = Math.min(4, bw / 2, hgt), isTop = !cfg.stacked || cfg.series.slice(j + 1).every(t => !val(t, i));
        const d = isTop ? `M${x},${top + hgt} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${top + hgt} Z` : `M${x},${top} h${bw} v${hgt} h${-bw} Z`;
        const t = s.tones ? s.tones[i] : s.tone;
        const bar = el('path', {d, fill: paint(t)}, svg);
        bind(bar, tip, cfg.titles ? cfg.titles[i] : label, cfg.series.map(z => ({tone: z.tones ? z.tones[i] : z.tone, text: `${cfg.series.length > 1 ? z.name + ': ' : ''}${fmt(val(z, i), f)}`})));
        if (cfg.stacked) base += v;
      });
      if (cfg.showValues) text(svg, {x: padL + slot * i + slot / 2, y: y(totals[i]) - 6, 'text-anchor': 'middle', class: 'gf-chart__value'}, fmt(totals[i], f));
      // Etichette accorciate quando la colonna è stretta (circa 6,5 px per carattere); il nome intero resta nel dettaglio.
      const room = Math.max(3, Math.floor((slot - 6) / 6.5)), short = String(label).length > room ? String(label).slice(0, room - 1).trimEnd() + '…' : label;
      if (!cfg.labelEvery || i % cfg.labelEvery === 0) text(svg, {x: padL + slot * i + slot / 2, y: h - 6, 'text-anchor': 'middle'}, short);
    });
    const lg = host.querySelector('.gf-chart__legend');
    if (lg) lg.innerHTML = cfg.series.length > 1 ? cfg.series.map(s => `<li>${swatch(s.tone)}<span>${esc(s.name)}</span><b>${fmt(s.values.reduce((a, b) => a + (Number(b) || 0), 0), f)}</b></li>`).join('') : '';
  }

  // Linee e aree su una scala, con mirino verticale e punto finale evidenziato.
  function area(host, cfg, canvas){
    const w = width(canvas), h = cfg.height || 220, padL = 48, padB = 26, padT = 14, n = cfg.labels.length, f = cfg.format || {};
    const svg = el('svg', {viewBox: `0 0 ${w} ${h}`, role: 'img', 'aria-label': cfg.label || ''}, canvas);
    const tip = tooltip(canvas);
    const max = niceMax(Math.max(...cfg.series.flatMap(s => s.values.map(Number)))), ph = h - padB - padT;
    const step = n > 1 ? (w - padL - 8) / (n - 1) : 0;
    const x = i => n > 1 ? padL + step * i : padL + (w - padL) / 2, y = v => padT + ph - (Number(v) || 0) / max * ph;
    grid(svg, w, padL, y, max, f);
    cfg.series.forEach(s => {
      const pts = s.values.map((v, i) => [x(i), y(v)]);
      const line = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
      if (n > 1 && (cfg.series.length === 1 || s.fill)){
        const gid = 'gfc' + Math.random().toString(36).slice(2);
        const grad = el('linearGradient', {id: gid, x1: 0, y1: 0, x2: 0, y2: 1}, el('defs', {}, svg));
        el('stop', {offset: '0%', 'stop-color': paint(s.tone), 'stop-opacity': 0.28}, grad);
        el('stop', {offset: '100%', 'stop-color': paint(s.tone), 'stop-opacity': 0}, grad);
        el('path', {d: `${line} L${x(n - 1)},${y(0)} L${x(0)},${y(0)} Z`, fill: `url(#${gid})`}, svg);
      }
      el('path', {d: line, fill: 'none', stroke: paint(s.tone), 'stroke-width': 2.5, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'stroke-dasharray': s.dashed ? '6 5' : 'none'}, svg);
      const last = pts[pts.length - 1];
      if (last) el('circle', {cx: last[0], cy: last[1], r: 5, fill: paint(s.tone), stroke: 'var(--gf-color-surface)', 'stroke-width': 2}, svg);
    });
    const every = cfg.labelEvery || Math.max(1, Math.ceil(n / 8));
    cfg.labels.forEach((l, i) => { if (i % every === 0 || i === n - 1) text(svg, {x: x(i), y: h - 6, 'text-anchor': i === n - 1 && n > 1 ? 'end' : 'middle'}, l); });
    const cross = el('line', {y1: padT, y2: padT + ph, stroke: 'var(--gf-chart-axis)', 'stroke-width': 1, 'stroke-dasharray': '3 3', opacity: 0}, svg);
    const dots = cfg.series.map(s => el('circle', {r: 5, fill: paint(s.tone), stroke: 'var(--gf-color-surface)', 'stroke-width': 2, opacity: 0}, svg));
    const hit = el('rect', {x: padL, y: padT, width: w - padL, height: ph, fill: 'transparent'}, svg);
    hit.addEventListener('mousemove', e => {
      const b = svg.getBoundingClientRect(), px = (e.clientX - b.left) / b.width * w;
      const i = n > 1 ? Math.max(0, Math.min(n - 1, Math.round((px - padL) / step))) : 0;
      cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('opacity', 1);
      dots.forEach((d, j) => { d.setAttribute('cx', x(i)); d.setAttribute('cy', y(cfg.series[j].values[i])); d.setAttribute('opacity', 1); });
      tip.show(e, cfg.titles ? cfg.titles[i] : cfg.labels[i], cfg.series.map(s => ({tone: s.tone, text: `${cfg.series.length > 1 ? s.name + ': ' : ''}${fmt(s.values[i], f)}`})));
    });
    hit.addEventListener('mouseleave', () => { tip.hide(); cross.setAttribute('opacity', 0); dots.forEach(d => d.setAttribute('opacity', 0)); });
    const lg = host.querySelector('.gf-chart__legend');
    if (lg) lg.innerHTML = cfg.series.length > 1 ? cfg.series.map(s => `<li>${swatch(s.tone)}<span>${esc(s.name)}</span></li>`).join('') : '';
  }

  // Mini andamento nelle card numeriche.
  function spark(host, cfg, canvas){
    const w = 120, h = 36, values = (cfg.values || []).map(Number), n = values.length;
    if (n < 2) return;
    const max = Math.max(...values), min = Math.min(...values);
    const svg = el('svg', {viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: 'none', 'aria-hidden': 'true'}, canvas);
    const x = i => i / (n - 1) * (w - 4) + 2, y = v => h - 4 - (v - min) / ((max - min) || 1) * (h - 10);
    const line = values.map((v, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(v).toFixed(1)).join(' ');
    const gid = 'gfs' + Math.random().toString(36).slice(2);
    const grad = el('linearGradient', {id: gid, x1: 0, y1: 0, x2: 0, y2: 1}, el('defs', {}, svg));
    el('stop', {offset: '0%', 'stop-color': paint(cfg.tone), 'stop-opacity': 0.25}, grad);
    el('stop', {offset: '100%', 'stop-color': paint(cfg.tone), 'stop-opacity': 0}, grad);
    el('path', {d: `${line} L${x(n - 1)},${h} L${x(0)},${h} Z`, fill: `url(#${gid})`}, svg);
    el('path', {d: line, fill: 'none', stroke: paint(cfg.tone), 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'vector-effect': 'non-scaling-stroke'}, svg);
  }

  const RENDER = {donut: (h, c, v) => donut(h, c, v, false), pie: (h, c, v) => donut(h, c, v, true), ring, gauge, columns, area, spark};
  // Colonne e aree dipendono dalla larghezza reale: si ridisegnano quando cambia (anche se erano nascoste).
  const drawn = new WeakMap();
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(entries => entries.forEach(entry => {
    const canvas = entry.target, host = canvas.closest('.gf-chart'), d = host && drawn.get(host);
    const w = Math.round(entry.contentRect.width);
    if (d && w && Math.abs(w - (d.width || 0)) > 4) paintInto(host, canvas, d.type, d.cfg);
  })) : null;
  function paintInto(host, canvas, type, cfg){
    canvas.querySelectorAll('svg').forEach(s => s.remove());
    const tip = canvas.querySelector('.gf-chart__tooltip'); if (tip) tip.hidden = true;
    RENDER[type](host, cfg, canvas);
    drawn.set(host, {type, cfg, width: Math.round(canvas.clientWidth)});
  }
  function draw(host, type, cfg){
    if (!host || !RENDER[type]) return;
    let canvas = host.querySelector('.gf-chart__canvas');
    if (!canvas){ canvas = document.createElement('div'); canvas.className = 'gf-chart__canvas'; host.appendChild(canvas); }
    paintInto(host, canvas, type, cfg);
    if (observer && (type === 'columns' || type === 'area')) observer.observe(canvas);
  }
  function renderAll(root = document){
    root.querySelectorAll('[data-chart]').forEach(host => {
      const raw = host.dataset.chartData ?? host.querySelector(':scope > script[type="application/json"]')?.textContent;
      if (raw) draw(host, host.dataset.chart, JSON.parse(raw));
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => renderAll());
  else renderAll();
  window.GFCharts = {draw, renderAll, format: fmt};
})();
