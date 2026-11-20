/* SnackScout charts: small hand-made SVG charts that work offline at venues.
   SSChart.columns(el, opts)  vertical bars, optionally stacked (points per match, score spread)
   SSChart.hbars(el, opts)    horizontal bars, optionally stacked (team OPR)
   SSChart.line(el, opts)     line with markers (OPR across events)
   Colors come from CSS classes (.cs1, .cs2 …) so light/dark and theme changes apply on their own. */
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const fmt = v => v == null ? '–' : Math.abs(v) >= 100 || Number.isInteger(v) ? String(Math.round(v)) : v.toFixed(1);

  // ---------- shared tooltip
  let tip;
  function showTip(html, x, y) {
    if (!tip) { tip = document.createElement('div'); tip.className = 'chart-tip'; tip.setAttribute('role', 'tooltip'); document.body.appendChild(tip); }
    tip.innerHTML = html; tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight, vw = document.documentElement.clientWidth;
    let left = x + 14, top = y - h - 12;
    if (left + w > vw - 8) left = x - w - 14;
    if (top < 8) top = y + 16;
    tip.style.left = Math.max(8, left) + scrollX + 'px'; tip.style.top = top + scrollY + 'px';
  }
  const hideTip = () => { if (tip) tip.hidden = true; };
  addEventListener('scroll', hideTip, {passive: true});

  // ---------- helpers
  function el(tag, attrs, parent) {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) if (attrs[k] != null) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  }
  function niceMax(v, ticks = 4) {
    if (!(v > 0)) return {max: 10, step: 2.5};
    const raw = v / ticks, mag = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    return {max: Math.ceil(v / step) * step, step};
  }
  // bar with only its data end rounded (r px), anchored flat on the baseline
  function barPath(x, y, w, h, r, end) { // end: 'top' | 'right' | 'none'
    if (h <= 0 || w <= 0) return '';
    if (end === 'top') { r = Math.min(r, w / 2, h); return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`; }
    if (end === 'right') { r = Math.min(r, h / 2, w); return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`; }
    return `M${x},${y}h${w}v${h}h${-w}Z`;
  }
  function legend(host, series) {
    if (series.length < 2) return;
    const lg = document.createElement('div'); lg.className = 'chart-legend';
    lg.innerHTML = series.map((s, i) => `<span><i class="sw cs${s.slot || i + 1}"></i>${esc(s.name)}</span>`).join('');
    host.appendChild(lg);
  }
  // draws once now and again whenever the box changes size (hidden tabs start at width 0)
  function mount(host, draw) {
    host.classList.add('chart');
    let last = -1;
    const run = () => {
      const w = Math.floor(host.clientWidth);
      if (!w || w === last) return;
      host.querySelectorAll('svg, .chart-legend').forEach(n => n.remove());
      try { draw(w); last = w; } catch (e) { host.dataset.chartError = e.message; console.error('chart', e); } // one bad chart never breaks the page
    };
    if ('ResizeObserver' in window) new ResizeObserver(run).observe(host);
    addEventListener('resize', run); addEventListener('load', run); addEventListener('hashchange', () => setTimeout(run, 50));
    run(); setTimeout(run, 120);
  }
  const rowsOf = o => o.series.map(s => s.values);

  // ---------- vertical columns
  function columns(host, o) {
    const n = o.labels.length; if (!n) return;
    mount(host, W => {
      legend(host, o.series);
      const H = o.height || 220, padL = 34, padR = 6, padT = 8, padB = o.groups ? 34 : 22;
      const totals = o.labels.map((_, i) => o.stacked ? o.series.reduce((a, s) => a + (s.values[i] || 0), 0) : Math.max(...rowsOf(o).map(v => v[i] || 0)));
      const {max, step} = niceMax(Math.max(...totals, o.minMax || 0));
      const plotW = W - padL - padR, plotH = H - padT - padB;
      const svg = el('svg', {width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.title || ''}, null);
      host.appendChild(svg);
      const y = v => padT + plotH - v / max * plotH;
      for (let t = 0; t <= max + 1e-9; t += step) {
        el('line', {x1: padL, x2: W - padR, y1: y(t), y2: y(t), class: t === 0 ? 'c-base' : 'c-grid'}, svg);
        el('text', {x: padL - 6, y: y(t) + 4, class: 'c-tick', 'text-anchor': 'end'}, svg).textContent = fmt(t);
      }
      // groups (events) get a little extra room between them
      const groupGap = o.groups ? 6 : 0, groupsN = o.groups ? new Set(o.groups).size : 1;
      const slot = (plotW - groupGap * (groupsN - 1)) / n, gap = Math.min(2, slot * 0.2), bw = Math.max(1, Math.min(o.maxBar || 28, slot - gap));
      let gi = 0; const xs = [];
      for (let i = 0; i < n; i++) {
        if (o.groups && i && o.groups[i] !== o.groups[i - 1]) gi++;
        xs.push(padL + gi * groupGap + i * slot + (slot - bw) / 2);
      }
      const bars = [];
      for (let i = 0; i < n; i++) {
        const g = el('g', {class: 'c-col'}, svg); let acc = 0;
        const k = o.series.length, sub = o.stacked ? bw : (bw - 2 * (k - 1)) / k; // grouped bars sit side by side, 2px apart
        if (o.stacked) {
          const parts = o.series.map((s, si) => ({s, si, v: s.values[i] || 0})).filter(p => p.v > 0);
          parts.forEach((p, j) => {
            const yTop = y(acc + p.v), h = y(acc) - yTop - (j > 0 ? 2 : 0); // 2px surface gap between stacked pieces
            el('path', {d: barPath(xs[i], yTop, bw, Math.max(0, h), 4, j === parts.length - 1 ? 'top' : 'none'), class: `cs${p.s.slot || p.si + 1}`}, g);
            acc += p.v;
          });
        } else {
          o.series.forEach((s, si) => {
            const v = s.values[i] || 0;
            if (v > 0) el('path', {d: barPath(xs[i] + si * (sub + 2), y(v), sub, y(0) - y(v), 4, 'top'), class: `cs${s.slot || si + 1}` + (o.mark && o.mark[i] ? ' c-mark' : '')}, g);
          });
        }
        el('rect', {x: xs[i] - gap / 2 - (slot - bw) / 2, y: padT, width: slot, height: plotH, class: 'c-hit'}, g);
        bars.push(g);
      }
      // x labels: group names under each group, or every Nth label
      if (o.groups) {
        let start = 0;
        for (let i = 1; i <= n; i++) if (i === n || o.groups[i] !== o.groups[start]) {
          const x0 = xs[start], x1 = xs[i - 1] + bw;
          el('line', {x1: x0, x2: x1, y1: H - padB + 6, y2: H - padB + 6, class: 'c-base'}, svg);
          const t = el('text', {x: (x0 + x1) / 2, y: H - padB + 20, class: 'c-tick', 'text-anchor': 'middle'}, svg);
          const room = Math.max(3, Math.floor((x1 - x0 + 20) / 6.5)), name = o.groups[start];
          t.textContent = name.length > room ? name.slice(0, room - 1) + '…' : name;
          start = i;
        }
      } else {
        const every = Math.ceil(n / Math.max(1, Math.floor(plotW / 34)));
        const room = Math.max(3, Math.floor(slot * every / 6.2));
        o.labels.forEach((l, i) => { if (i % every === 0) el('text', {x: xs[i] + bw / 2, y: H - 6, class: 'c-tick', 'text-anchor': 'middle'}, svg)
          .textContent = l.length > room ? l.slice(0, room - 1) + '…' : l; });
      }
      bars.forEach((g, i) => {
        const on = e => { svg.classList.add('hovering'); g.classList.add('on'); showTip(o.tooltip(i), e.clientX, e.clientY); };
        g.addEventListener('pointermove', on); g.addEventListener('pointerenter', on);
        g.addEventListener('pointerleave', () => { svg.classList.remove('hovering'); g.classList.remove('on'); hideTip(); });
        if (o.onClick) { g.style.cursor = 'pointer'; g.addEventListener('click', () => o.onClick(i)); }
      });
    });
  }

  // ---------- horizontal bars (one row per item)
  function hbars(host, o) {
    const n = o.labels.length; if (!n) return;
    mount(host, W => {
      legend(host, o.series);
      const row = 22, padT = 4, padB = 22, labelW = o.labelWidth || 64, padR = 34;
      const H = padT + n * row + padB, plotW = W - labelW - padR;
      const totals = o.labels.map((_, i) => o.series.reduce((a, s) => a + Math.max(0, s.values[i] || 0), 0));
      const {max, step} = niceMax(Math.max(...totals));
      const x = v => labelW + v / max * plotW;
      const svg = el('svg', {width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.title || ''}, null);
      host.appendChild(svg);
      for (let t = 0; t <= max + 1e-9; t += step) {
        el('line', {x1: x(t), x2: x(t), y1: padT, y2: H - padB, class: t === 0 ? 'c-base' : 'c-grid'}, svg);
        el('text', {x: x(t), y: H - 6, class: 'c-tick', 'text-anchor': 'middle'}, svg).textContent = fmt(t);
      }
      for (let i = 0; i < n; i++) {
        const g = el('g', {class: 'c-col' + (o.highlight && o.highlight[i] ? ' c-us' : '')}, svg), yy = padT + i * row + 3, bh = row - 6;
        if (o.highlight && o.highlight[i]) el('rect', {x: 0, y: padT + i * row, width: W, height: row, rx: 6, class: 'c-band'}, g);
        const lab = el('text', {x: labelW - 8, y: yy + bh / 2 + 4, class: 'c-label', 'text-anchor': 'end'}, g); lab.textContent = o.labels[i];
        let acc = 0;
        const parts = o.series.map((s, si) => ({s, si, v: Math.max(0, s.values[i] || 0)})).filter(p => p.v > 0);
        parts.forEach((p, k) => {
          const x0 = x(acc) + (k ? 2 : 0), w = x(acc + p.v) - x0;
          el('path', {d: barPath(x0, yy, Math.max(0, w), bh, 4, k === parts.length - 1 ? 'right' : 'none'), class: `cs${p.s.slot || p.si + 1}`}, g);
          acc += p.v;
        });
        el('text', {x: x(acc) + 5, y: yy + bh / 2 + 4, class: 'c-val'}, g).textContent = fmt(totals[i]);
        el('rect', {x: 0, y: padT + i * row, width: W, height: row, class: 'c-hit'}, g);
        const on = e => { svg.classList.add('hovering'); g.classList.add('on'); showTip(o.tooltip(i), e.clientX, e.clientY); };
        g.addEventListener('pointermove', on);
        g.addEventListener('pointerleave', () => { svg.classList.remove('hovering'); g.classList.remove('on'); hideTip(); });
        if (o.onClick) { g.style.cursor = 'pointer'; g.addEventListener('click', () => o.onClick(i)); }
      }
    });
  }

  // ---------- line with markers and a crosshair
  function line(host, o) {
    const n = o.labels.length; if (!n) return;
    mount(host, W => {
      legend(host, o.series);
      const H = o.height || 200, padL = 34, padR = 14, padT = 12, padB = 24, plotW = W - padL - padR, plotH = H - padT - padB;
      const {max, step} = niceMax(Math.max(...rowsOf(o).flat().filter(v => v != null)));
      const x = i => n === 1 ? padL + plotW / 2 : padL + 8 + i * (plotW - 16) / (n - 1), y = v => padT + plotH - v / max * plotH;
      const svg = el('svg', {width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.title || ''}, null);
      host.appendChild(svg);
      for (let t = 0; t <= max + 1e-9; t += step) {
        el('line', {x1: padL, x2: W - padR, y1: y(t), y2: y(t), class: t === 0 ? 'c-base' : 'c-grid'}, svg);
        el('text', {x: padL - 6, y: y(t) + 4, class: 'c-tick', 'text-anchor': 'end'}, svg).textContent = fmt(t);
      }
      const every = Math.ceil(n / Math.max(1, Math.floor(plotW / 90)));
      o.labels.forEach((l, i) => {
        if (i % every) return;
        const room = Math.max(4, Math.floor(plotW / Math.min(n, Math.floor(plotW / 90) || 1) / 6.5));
        el('text', {x: x(i), y: H - 6, class: 'c-tick', 'text-anchor': n === 1 ? 'middle' : i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}, svg)
          .textContent = l.length > room ? l.slice(0, room - 1) + '…' : l;
      });
      const cross = el('line', {y1: padT, y2: H - padB, class: 'c-cross', visibility: 'hidden'}, svg);
      o.series.forEach((s, si) => {
        const pts = s.values.map((v, i) => v == null ? null : [x(i), y(v)]).filter(Boolean);
        if (pts.length > 1) el('path', {d: 'M' + pts.map(p => p.join(',')).join('L'), class: `c-line cl${s.slot || si + 1}`}, svg);
        pts.forEach(p => el('circle', {cx: p[0], cy: p[1], r: 4.5, class: `c-dot cs${s.slot || si + 1}`}, svg));
      });
      const hit = el('rect', {x: padL, y: padT, width: plotW, height: plotH, class: 'c-hit'}, svg);
      hit.addEventListener('pointermove', e => {
        const r = svg.getBoundingClientRect(), px = e.clientX - r.left;
        let best = 0; for (let i = 1; i < n; i++) if (Math.abs(x(i) - px) < Math.abs(x(best) - px)) best = i;
        cross.setAttribute('x1', x(best)); cross.setAttribute('x2', x(best)); cross.setAttribute('visibility', 'visible');
        showTip(o.tooltip(best), e.clientX, e.clientY);
      });
      hit.addEventListener('pointerleave', () => { cross.setAttribute('visibility', 'hidden'); hideTip(); });
    });
  }

  // tooltip body helper: rows of [swatch slot or null, label, value]
  function tipHtml(title, rows) {
    return `<b>${esc(title)}</b>` + rows.map(([slot, k, v]) =>
      `<div class="tr">${slot ? `<i class="sw cs${slot}"></i>` : '<i class="sw none"></i>'}<span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
  }

  // "Upper Bracket  Round 2 M3" -> "UB R2 M3"
  const short = l => String(l).replace(/Upper Bracket/i, 'UB').replace(/Lower Bracket/i, 'LB').replace(/Finals?/i, 'F')
    .replace(/Round\s*/i, 'R').replace(/Match\s*/i, 'M').replace(/\s+/g, ' ').trim();

  window.SSChart = {columns, hbars, line, tipHtml, fmt, short};
})();
