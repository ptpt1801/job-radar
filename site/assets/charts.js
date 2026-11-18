/* Job Radar charts: inline SVG, ported from reference/prototype.html.
   Series colours keep the colour-blind-checked order: --c1 #008A9E, --c2 #E07A4C. */
(function () {
  'use strict';
  const ns = 'http://www.w3.org/2000/svg';
  const J = () => window.JR; // T, fmt, esc provided by app.js
  const el = (tag, attrs, parent) => { const e = document.createElementNS(ns, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  const tip = () => document.getElementById('tip');
  function showTip(html, ev) { const t = tip(); t.innerHTML = html; t.style.opacity = 1; t.style.left = Math.min(ev.clientX + 14, innerWidth - 270) + 'px'; t.style.top = (ev.clientY + 14) + 'px'; }
  function hideTip() { tip().style.opacity = 0; }
  const tableHTML = (pairs, h1, h2) => { const { T, esc, fmt } = J();
    return '<details><summary>' + T('table') + '</summary><table><thead><tr><th>' + h1 + '</th><th>' + h2 + '</th></tr></thead><tbody>' + pairs.map(p => '<tr><td>' + esc(p[0]) + '</td><td class="n">' + fmt(p[1]) + '</td></tr>').join('') + '</tbody></table></details>'; };

  function hbar(id, pairs, unit) {
    const { T, esc, fmt } = J();
    const box = document.getElementById(id); box.innerHTML = '';
    const W = box.clientWidth || 520, rowH = 30, lw = Math.min(220, W * 0.44), H = pairs.length * rowH + 6, max = Math.max(1, ...pairs.map(p => p[1]));
    const svg = el('svg', { width: W, height: H, role: 'img', 'aria-label': pairs.map(p => p[0] + ': ' + p[1]).join(', ') }, box);
    pairs.forEach((p, i) => { const y = i * rowH + 4, bw = Math.max(p[1] ? 4 : 0, (W - lw - 52) * p[1] / max);
      el('text', { x: lw - 10, y: y + 16, 'text-anchor': 'end', 'font-size': 13, fill: '#0E3B40' }, svg).textContent = p[0];
      const r = el('rect', { x: lw, y: y + 4, width: bw, height: 18, rx: 4, fill: 'var(--c1)' }, svg);
      el('text', { x: lw + bw + 6, y: y + 17, 'font-size': 13, 'font-weight': 700, fill: '#4A6A6D' }, svg).textContent = fmt(p[1]);
      const hit = el('rect', { x: 0, y: y, width: W, height: rowH, fill: 'transparent' }, svg);
      hit.addEventListener('mousemove', ev => { r.setAttribute('fill', '#06646D'); showTip('<b>' + fmt(p[1]) + '</b> ' + unit + '<br>' + esc(p[0]), ev); });
      hit.addEventListener('mouseleave', () => { r.setAttribute('fill', 'var(--c1)'); hideTip(); }); });
    if (!pairs.length) box.innerHTML = '<p class="muted">–</p>';
    box.insertAdjacentHTML('beforeend', tableHTML(pairs, T('group'), T('nPosts')));
  }

  // counts: array of {label, n}; last item is the current week
  function trend(id, counts) {
    const { T } = J();
    const box = document.getElementById(id); box.innerHTML = '';
    const weeks = counts.length, c = counts.map(x => x.n), labels = counts.map(x => x.label);
    const W = box.clientWidth || 1000, H = 220, m = { l: 40, r: 16, t: 16, b: 28 }, max = Math.max(4, ...c) * 1.15;
    const x = i => m.l + i * (W - m.l - m.r) / (weeks - 1), y = v => H - m.b - v * (H - m.t - m.b) / max;
    const svg = el('svg', { width: W, height: H, role: 'img', 'aria-label': T('c_trend') }, box);
    [0, Math.round(max / 2), Math.round(max)].forEach(t => { el('line', { x1: m.l, x2: W - m.r, y1: y(t), y2: y(t), stroke: '#D6E9E7' }, svg); el('text', { x: m.l - 8, y: y(t) + 4, 'text-anchor': 'end', 'font-size': 12, fill: '#4A6A6D' }, svg).textContent = t; });
    const step = W < 520 ? 3 : 2;
    labels.forEach((l, i) => { if (i % step === 0 || i === weeks - 1) el('text', { x: x(i), y: H - 8, 'text-anchor': 'middle', 'font-size': 12, fill: '#4A6A6D' }, svg).textContent = l; });
    el('path', { d: c.map((v, i) => (i ? 'L' : 'M') + x(i) + ',' + y(v)).join(''), fill: 'none', stroke: 'var(--c1)', 'stroke-width': 2 }, svg);
    const last = weeks - 1; el('circle', { cx: x(last), cy: y(c[last]), r: 4, fill: 'var(--c1)' }, svg);
    el('text', { x: x(last) - 6, y: y(c[last]) - 10, 'text-anchor': 'end', 'font-size': 13, 'font-weight': 700, fill: '#0E3B40' }, svg).textContent = T('thisWeek', { n: c[last] });
    const cross = el('line', { y1: m.t, y2: H - m.b, stroke: '#0E3B40', 'stroke-dasharray': '3 3', opacity: 0 }, svg), dot = el('circle', { r: 5, fill: 'var(--c1)', stroke: '#fff', 'stroke-width': 2, opacity: 0 }, svg);
    const hit = el('rect', { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: 'transparent' }, svg);
    hit.addEventListener('mousemove', ev => { const bx = svg.getBoundingClientRect(), i = Math.max(0, Math.min(last, Math.round((ev.clientX - bx.left - m.l) / ((W - m.l - m.r) / (weeks - 1)))));
      cross.setAttribute('x1', x(i)); cross.setAttribute('x2', x(i)); cross.setAttribute('opacity', .5); dot.setAttribute('cx', x(i)); dot.setAttribute('cy', y(c[i])); dot.setAttribute('opacity', 1); showTip('<b>' + c[i] + '</b> ' + T('posts') + '<br>' + T('weekOf', { d: labels[i] }), ev); });
    hit.addEventListener('mouseleave', () => { cross.setAttribute('opacity', 0); dot.setAttribute('opacity', 0); hideTip(); });
    box.insertAdjacentHTML('beforeend', tableHTML(labels.map((l, i) => [T('week') + ' ' + l, c[i]]), T('week'), T('nPosts')));
  }

  function hist(id, matches) {
    const { T } = J();
    const box = document.getElementById(id); box.innerHTML = '';
    const bins = Array(10).fill(0); matches.forEach(v => bins[Math.min(9, Math.floor(v / 10))]++);
    const W = box.clientWidth || 520, H = 220, m = { l: 34, r: 8, t: 18, b: 30 }, max = Math.max(1, ...bins) * 1.1, bw = (W - m.l - m.r) / 10;
    const svg = el('svg', { width: W, height: H, role: 'img', 'aria-label': T('c_match') }, box);
    el('line', { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: '#B9D3D0' }, svg);
    bins.forEach((v, i) => { const h = v * (H - m.t - m.b) / max, xx = m.l + i * bw + 1;
      el('rect', { x: xx, y: H - m.b - h, width: bw - 2, height: h, rx: 4, fill: i >= 7 ? 'var(--c2)' : 'var(--c1)' }, svg);
      el('text', { x: xx + (bw - 2) / 2, y: H - m.b - h - 5, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 700, fill: '#4A6A6D' }, svg).textContent = v || '';
      el('text', { x: xx + (bw - 2) / 2, y: H - 10, 'text-anchor': 'middle', 'font-size': 12, fill: '#4A6A6D' }, svg).textContent = i * 10;
      const hit = el('rect', { x: xx, y: m.t, width: bw - 2, height: H - m.t - m.b, fill: 'transparent' }, svg);
      hit.addEventListener('mousemove', ev => showTip('<b>' + v + '</b> ' + T('posts') + '<br>' + T('matchRange', { a: i * 10, b: i * 10 + 9 }), ev)); hit.addEventListener('mouseleave', hideTip); });
    const tx = m.l + 7 * bw; el('line', { x1: tx, x2: tx, y1: m.t - 8, y2: H - m.b, stroke: '#0E3B40', 'stroke-dasharray': '4 3' }, svg);
    el('text', { x: tx + 6, y: m.t, 'font-size': 12, 'font-weight': 700, fill: '#0E3B40' }, svg).textContent = T('threshold');
    box.insertAdjacentHTML('beforeend', tableHTML(bins.map((v, i) => [(i * 10) + '–' + (i * 10 + 9) + '%', v]), T('matchCol'), T('nPosts')));
  }

  const RAMP = ['#F2FAFA', '#CDEEF0', '#9EDDE2', '#6CC8CF', '#3AAFB8', '#14929E', '#097C87', '#05515A'];
  // rows/cols: [{key,label}], grid[i][j] = count
  function heat(id, rows, cols, grid) {
    const { T, esc } = J();
    const box = document.getElementById(id); box.innerHTML = '';
    const max = Math.max(1, ...grid.flat());
    const W = box.clientWidth || 520, lw = Math.min(170, W * 0.36), cw = (W - lw) / cols.length, ch = 30, H = 26 + rows.length * ch;
    const svg = el('svg', { width: W, height: H, role: 'img', 'aria-label': T('c_heat') }, box);
    const small = cw < 80;
    cols.forEach((l, j) => el('text', { x: lw + j * cw + cw / 2, y: 16, 'text-anchor': 'middle', 'font-size': small ? 10 : 12, 'font-weight': 700, fill: '#4A6A6D' }, svg).textContent = small ? l.label.split(' ')[0] : l.label);
    rows.forEach((f, i) => { el('text', { x: lw - 8, y: 26 + i * ch + 19, 'text-anchor': 'end', 'font-size': 13, fill: '#0E3B40' }, svg).textContent = f.label;
      cols.forEach((l, j) => { const v = grid[i][j], k = v ? 1 + Math.round(v / max * 6) : 0;
        const r = el('rect', { x: lw + j * cw + 1, y: 26 + i * ch + 1, width: cw - 2, height: ch - 2, rx: 4, fill: RAMP[k] }, svg);
        el('text', { x: lw + j * cw + cw / 2, y: 26 + i * ch + 20, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 700, fill: k >= 5 ? '#fff' : '#0E3B40', 'pointer-events': 'none' }, svg).textContent = v;
        r.addEventListener('mousemove', ev => showTip('<b>' + v + '</b> ' + T('posts') + '<br>' + esc(f.label) + ', ' + esc(l.label), ev)); r.addEventListener('mouseleave', hideTip); }); });
    box.insertAdjacentHTML('beforeend', tableHTML(rows.flatMap((f, i) => cols.map((l, j) => [f.label + ' – ' + l.label, grid[i][j]])), T('group'), T('nPosts')));
  }

  window.JRCharts = { hbar, trend, hist, heat, hideTip };
})();
