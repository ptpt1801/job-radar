/* Job Radar front end. Ported from reference/prototype.html; reads data/*.json produced by the pipeline.
   Match scores come pre-computed in jobs.json (the CV never reaches the browser). */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const store = { get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
                  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} } };
  const TZ = 'Asia/Ho_Chi_Minh', DAY = 864e5;
  let lang = store.get('jr-lang', 'vi'); if (!['vi', 'en'].includes(lang)) lang = 'vi';
  let I18N = { vi: {}, en: {} }, TAX = {}, META = {}, jobs = [], archive = [], loadState = 'loading';
  const T = (k, p) => { let s = (I18N[lang][k] ?? I18N.vi[k] ?? k); if (p) for (const x in p) s = s.split('{' + x + '}').join(p[x]); return s; };
  const fmt = n => Number(n).toLocaleString(lang === 'en' ? 'en-GB' : 'vi-VN');
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  window.JR = { T, fmt, esc };

  // label for a neutral key from taxonomy.json
  const SEC = { level: 'levels', func: 'functions', city: 'cities', industry: 'industries', mode: 'work_modes', region: 'regions',
                langs: 'languages', source: 'sources', skill: 'skills', hq: 'countries' };
  const L = (group, key) => { if (key == null) return T('unknownMode'); const t = (TAX[SEC[group]] || {})[key]; return t ? (t[lang] || t.vi) : key; };
  const FIELD = { level: 'level', func: 'function', city: 'city', industry: 'industry', mode: 'work_mode', region: 'region', langs: 'languages_required', source: 'source' };

  // dates relative to "today" in Vietnam
  const vnDate = d => new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
  const dayNum = s => Math.floor(Date.parse(s.slice(0, 10) + 'T00:00:00Z') / DAY);
  let TODAY = dayNum(vnDate(new Date()));

  // Private skill tags: the public data has no have/missing lists. The owner opens a private link
  // (#me=<base64url JSON array of skill keys>) once; the list lives only in her browser's localStorage.
  (function readPrivateLink() {
    const m = location.hash.match(/^#me=(.*)$/);
    if (!m) return;
    if (m[1] === 'clear') store.set('jr-my-skills', null);
    else { try { const arr = JSON.parse(decodeURIComponent(escape(atob(m[1].replace(/-/g, '+').replace(/_/g, '/'))))); if (Array.isArray(arr)) store.set('jr-my-skills', arr); } catch (e) {} }
    history.replaceState(null, '', location.pathname + location.search + '#viec-lam');
  })();
  const MY_SKILLS = new Set(store.get('jr-my-skills', null) || []);
  function prep(j) {
    j.daysAgo = Math.max(0, TODAY - dayNum(j.posted_at || j.first_seen_at));
    j.deadlineIn = j.deadline ? dayNum(j.deadline) - TODAY : null;
    j.skills = j.skills || []; j.languages_required = j.languages_required || []; j.benefits = j.benefits || [];
    if (!Array.isArray(j.have) && MY_SKILLS.size && j.skills) {
      j.have = j.skills.filter(x => MY_SKILLS.has(x)); j.missing = j.skills.filter(x => !MY_SKILLS.has(x));
    }
    j.hasTags = Array.isArray(j.have);
    j._search = [j.title, j.company, L('industry', j.industry), ...j.skills, ...j.skills.map(s => (TAX.skills[s] || {}).vi || ''), ...j.skills.map(s => (TAX.skills[s] || {}).en || '')].join(' ').toLowerCase();
    return j;
  }
  const hasMatch = () => !!META.has_profile && jobs.some(j => j.match != null);

  // ---------- filters (values come from the real data) ----------
  const jf = $('jf');
  let my = store.get('jr-status', {});
  let GROUPS = {};
  function orderedKeys(group, present) {
    const sec = TAX[SEC[group]] || {}; const known = Object.keys(sec).filter(k => present.has(k));
    return known.concat([...present].filter(k => !known.includes(k) && k != null));
  }
  function computeGroups() {
    GROUPS = {};
    for (const g of Object.keys(FIELD)) {
      const present = new Set();
      jobs.forEach(j => { const v = j[FIELD[g]]; if (Array.isArray(v)) v.forEach(x => present.add(x)); else if (v != null) present.add(v); });
      GROUPS[g] = orderedKeys(g, present);
    }
  }
  function buildGroups() {
    const keep = {}; document.querySelectorAll('[data-group] input').forEach(c => { if (c.checked) (keep[c.name] = keep[c.name] || []).push(c.value); });
    document.querySelectorAll('[data-group]').forEach(box => { const g = box.dataset.group;
      box.innerHTML = (GROUPS[g] || []).map(v => '<label><input type="checkbox" name="' + g + '" value="' + esc(v) + '"' + ((keep[g] || []).includes(v) ? ' checked' : '') + '> ' + esc(L(g, v)) + ' <span class="muted" style="margin-left:auto;font-size:13px" data-c="' + esc(g + '|' + v) + '"></span></label>').join(''); });
  }
  const els = name => { const e = jf.elements[name]; return !e ? [] : (e instanceof RadioNodeList ? [...e] : [e]); };
  const QUICK = [['q_intern', () => setCheck('level', 'internship')], ['q_grad', () => setCheck('level', 'graduate')], ['q_hn', () => setCheck('city', 'hanoi')],
    ['q_70', () => { const r = jf.elements.minmatch; r.value = r.value === '70' ? '0' : '70'; }, true],
    ['q_3d', () => { const r = els('posted').find(x => x.value === '3'); if (r.checked) els('posted')[0].checked = true; else r.checked = true; }]];
  function setCheck(name, v) { const c = els(name).find(x => x.value === v); if (c) c.checked = !c.checked; }
  function buildQuick() {
    $('quick').innerHTML = QUICK.map((q, i) => (q[2] && !hasMatch()) ? '' : '<button type="button" class="qchip" data-q="' + i + '" aria-pressed="false">' + T(q[0]) + '</button>').join('');
    document.querySelectorAll('.qchip').forEach(b => b.onclick = () => { QUICK[+b.dataset.q][1](); renderJobs(true); });
  }
  function readFilters() {
    const f = {}; for (const g of Object.keys(GROUPS)) f[g] = els(g).filter(c => c.checked).map(c => c.value);
    f.minmatch = hasMatch() ? +jf.elements.minmatch.value : 0;
    f.posted = +jf.querySelector('[name=posted]:checked').value; f.exp = +jf.querySelector('[name=exp]:checked').value;
    ['salaryOnly', 'deadlineSoon', 'hideHidden', 'savedOnly', 'hideApplied'].forEach(k => f[k] = jf.elements[k].checked);
    f.q = $('q').value.trim().toLowerCase(); return f;
  }
  function passJob(j, f, skip) {
    for (const g of Object.keys(GROUPS)) { if (g === skip || !f[g] || !f[g].length) continue; const v = j[FIELD[g]];
      if (g === 'langs') { if (!f.langs.every(l => v.includes(l))) return false; } else if (!f[g].includes(v)) return false; }
    if (f.minmatch && (j.match ?? 0) < f.minmatch) return false;
    if (f.posted < 999 && j.daysAgo >= f.posted) return false;
    if (f.exp < 99 && j.experience_min_years != null && j.experience_min_years > f.exp) return false;
    if (j.deadlineIn != null && j.deadlineIn < 0) return false;
    if (f.salaryOnly && !j.salary) return false; if (f.deadlineSoon && (j.deadlineIn == null || j.deadlineIn > 7)) return false;
    if (f.hideHidden && my[j.id] === 'hidden') return false; if (f.savedOnly && my[j.id] !== 'saved') return false; if (f.hideApplied && my[j.id] === 'applied') return false;
    if (f.q && !j._search.includes(f.q)) return false;
    return true;
  }

  // ---------- job cards ----------
  const ringStyle = m => m >= 80 ? 'background:var(--yellow);color:var(--ink)' : m >= 60 ? 'background:var(--teal-soft);color:var(--teal-dark)' : 'background:#EEF2F2;color:var(--muted)';
  function salaryText(s) {
    if (!s) return T('notDisclosed');
    const per = s.period || 'month', cur = s.currency || 'VND', u = T('u_' + cur + '_' + per);
    const conv = v => v == null ? null : (cur === 'VND' && per !== 'hour' ? fmt(Math.round(v / 1e5) / 10) : fmt(v));
    const a = conv(s.min), b = conv(s.max);
    const txt = a && b && a !== b ? T('salRange', { a, b, u }) : a ? (b ? a + ' ' + u : T('salFrom', { a, u })) : T('salTo', { b, u });
    return txt + (s.is_allowance ? T('allowance') : '');
  }
  const DETAILS = {};
  async function loadDetails(id) {
    if (DETAILS[id]) return;
    try { const r = await fetch('data/details/' + id + '.json', { cache: 'no-cache' }); DETAILS[id] = r.ok ? await r.json() : {}; }
    catch (e) { DETAILS[id] = {}; }
    renderJobs(false);
  }
  let shown = 15, openId = null;
  function jobCard(j) {
    const st = my[j.id], isOpen = openId === j.id, showM = j.match != null;
    if (isOpen && j.has_details && !DETAILS[j.id]) loadDetails(j.id);
    const det = Object.assign({}, j, DETAILS[j.id] || {});
    const dl = j.deadlineIn == null ? '<span class="muted">' + T('noDeadline') + '</span>'
      : j.deadlineIn === 0 ? '<span style="color:var(--warn);font-weight:700">' + T('deadlineToday') + '</span>'
      : j.deadlineIn <= 7 ? '<span style="color:var(--warn);font-weight:700">' + T('daysLeft', { n: j.deadlineIn }) + '</span>' : T('deadlineIn', { n: j.deadlineIn });
    const tags = j.hasTags
      ? j.have.map(s => '<span class="tag have">' + esc(L('skill', s)) + '</span>').join('') + j.missing.map(s => '<span class="tag miss">' + T('miss') + esc(L('skill', s)) + '</span>').join('')
      : j.skills.slice(0, 8).map(s => '<span class="tag neutral">' + esc(L('skill', s)) + '</span>').join('');
    const srcLabel = L('source', j.source);
    const addr = [j.address_raw, L('city', j.city)].filter(Boolean);
    return '<article class="card job' + (showM ? '' : ' noring') + '" data-id="' + esc(j.id) + '">'
      + (showM ? '<div class="ring" style="' + ringStyle(j.match) + '">' + j.match + '%</div>' : '')
      + '<div><button class="toggle" aria-expanded="' + isOpen + '" data-open="' + esc(j.id) + '"><h3>' + esc(j.title) + '</h3></button>'
      + '<div class="meta"><b style="color:var(--ink)">' + esc(j.company) + '</b><span>' + esc(L('city', j.city)) + '</span><span>' + esc(L('industry', j.industry)) + '</span><span>' + esc(L('level', j.level)) + '</span>' + (j.work_mode ? '<span>' + esc(L('mode', j.work_mode)) + '</span>' : '') + '</div>'
      + '<div class="tags">' + tags + '</div></div>'
      + '<div class="side">' + (j.daysAgo < 2 ? '<span class="badge-new">' + T('isNew') + '</span>' : '') + '<b>' + esc(salaryText(j.salary)) + '</b><span class="muted" style="font-size:13px">' + (j.daysAgo ? T('postedAgo', { n: j.daysAgo }) : T('postedToday')) + '</span><span style="font-size:13px">' + dl + '</span>' + (st ? '<span class="tag" style="background:var(--yellow-soft)">' + T('st_' + st) + '</span>' : '') + '</div>'
      + (isOpen ? '<div class="open"><dl><dt>' + T('address') + '</dt><dd>' + esc(addr.join(' · ') || T('notDisclosed')) + '</dd><dt>' + T('hq') + '</dt><dd>' + esc(L('hq', j.hq_country)) + ' (' + esc(L('region', j.region)) + ')</dd>'
          + '<dt>' + T('exp') + '</dt><dd>' + (j.experience_min_years ? T('expN', { n: j.experience_min_years }) : j.experience_min_years === 0 ? T('noExp') : T('notDisclosed')) + '</dd>'
          + '<dt>' + T('langs') + '</dt><dd>' + esc(j.languages_required.map(x => L('langs', x)).join(', ') || T('notDisclosed')) + '</dd>'
          + (j.employment_type ? '<dt>' + T('empType') + '</dt><dd>' + esc(T('emp_' + j.employment_type)) + '</dd>' : '')
          + '<dt>' + T('lastVerified') + '</dt><dd title="' + esc(T('lastVerifiedNote')) + '">' + esc(fmtTime(j.last_seen_at)) + '</dd>'
          + '<dt>' + T('source') + '</dt><dd>' + esc(srcLabel) + (j.also_on && j.also_on.length ? '<br><span class="muted">' + T('alsoOn') + ' ' + j.also_on.length + '</span>' : '') + '</dd></dl>'
          + '<div><b>' + T('reqSkills') + '</b>' + (j.skills.length ? '<ul>' + j.skills.map(s => '<li>' + esc(L('skill', s)) + (j.hasTags && j.have.includes(s) ? T('youHaveIt') : '') + '</li>').join('') + '</ul>' : '<p class="muted" style="margin:4px 0 0;font-size:14px">' + T('notDisclosed') + '</p>')
          + (det.description_excerpt ? '<p class="excerpt"><b>' + T('summary') + ':</b> ' + esc(det.description_excerpt) + '</p>' : '') + '</div>'
          + '<div><b>' + T('benefits') + '</b>' + ((det.benefits || []).length ? '<ul>' + det.benefits.map(b => '<li>' + esc(b) + '</li>').join('') + '</ul>' : '<p class="muted" style="margin:4px 0 0;font-size:14px">' + T('notDisclosed') + '</p>') + '</div>'
          + '<div class="actions"><a class="btn" href="' + esc(j.url) + '" target="_blank" rel="noopener">' + T('openSrc', { s: esc(srcLabel) }) + '<span class="sr"> ' + T('newTab') + '</span></a><button class="btn ghost" data-act="saved" data-id="' + esc(j.id) + '">' + (st === 'saved' ? T('unsave') : T('save')) + '</button><button class="btn ghost" data-act="applied" data-id="' + esc(j.id) + '">' + (st === 'applied' ? T('unapply') : T('apply')) + '</button><button class="btn ghost" data-act="hidden" data-id="' + esc(j.id) + '">' + T('hide') + '</button></div></div>' : '')
      + '</article>';
  }
  function stateBox(kind) {
    if (kind === 'loading') return '<div class="card state" role="status"><div class="spinner" aria-hidden="true"></div><p>' + T('loading') + '</p></div>';
    if (kind === 'error') return '<div class="card state" role="alert"><h3>' + T('loadErrT') + '</h3><p class="muted">' + T('loadErrS') + '</p><button class="btn" type="button" onclick="location.reload()">' + T('reload') + '</button></div>';
    return '<div class="card state"><h3>' + T('noDataT') + '</h3><p class="muted">' + T('noDataS') + '</p></div>';
  }
  function renderJobs(resetPage) {
    if (resetPage) shown = 15;
    const m = hasMatch();
    $('reco-box').hidden = !m; $('f-match-box').hidden = !m; $('sort-match').hidden = !m;
    if (!m && $('sort').value === 'match') $('sort').value = 'new';
    if (loadState !== 'ready' || !jobs.length) {
      $('list').innerHTML = stateBox(loadState === 'ready' ? 'empty' : loadState); $('more').hidden = true; $('count').textContent = ''; $('reco-box').hidden = true; return;
    }
    $('minmatch-v').textContent = jf.elements.minmatch.value + '%';
    const f = readFilters(), list = jobs.filter(j => passJob(j, f)), sort = $('sort').value;
    const dl = j => j.deadlineIn == null ? 1e9 : j.deadlineIn;
    list.sort(sort === 'new' ? (a, b) => a.daysAgo - b.daysAgo || (b.match ?? 0) - (a.match ?? 0) : sort === 'deadline' ? (a, b) => dl(a) - dl(b) || a.daysAgo - b.daysAgo : (a, b) => (b.match ?? 0) - (a.match ?? 0) || a.daysAgo - b.daysAgo);
    $('count').textContent = T('count', { n: fmt(list.length) });
    $('list').innerHTML = list.length ? list.slice(0, shown).map(jobCard).join('') : '<div class="card empty"><h3>' + T('emptyT') + '</h3><p class="muted">' + T('emptyS') + '</p></div>';
    $('more').hidden = list.length <= shown;
    for (const g of Object.keys(GROUPS)) { const base = jobs.filter(j => passJob(j, f, g)); GROUPS[g].forEach(v => {
      const n = g === 'langs' ? base.filter(j => j.languages_required.includes(v)).length : base.filter(j => j[FIELD[g]] === v).length;
      const s = document.querySelector('[data-c="' + CSS.escape(g + '|' + v) + '"]'); if (s) s.textContent = n; }); }
    const qs = [...document.querySelectorAll('.qchip')];
    const states = { 0: f.level.includes('internship'), 1: f.level.includes('graduate'), 2: f.city.includes('hanoi'), 3: f.minmatch === 70, 4: f.posted === 3 };
    qs.forEach(b => b.setAttribute('aria-pressed', !!states[+b.dataset.q]));
    if (m) {
      const reco = jobs.filter(j => (j.deadlineIn == null || j.deadlineIn >= 0) && !my[j.id] && j.match != null).sort((a, b) => b.match - a.match || a.daysAgo - b.daysAgo).slice(0, 3);
      $('reco').innerHTML = reco.map(j => '<button class="rcard" data-goto="' + esc(j.id) + '"><div style="display:flex;align-items:baseline;gap:6px"><span class="score">' + j.match + '</span><span class="muted">' + T('pctMatch') + '</span></div><div class="meter" aria-hidden="true"><span style="width:' + j.match + '%"></span></div><h3 style="font-size:19px">' + esc(j.title) + '</h3><span class="muted">' + esc(j.company) + ', ' + esc(L('city', j.city)) + '</span>'
        + (j.hasTags ? '<span style="font-size:14px"><b>' + T('youHave') + '</b> ' + esc(j.have.map(s => L('skill', s)).join(', ') || T('noOverlap')) + '</span>' + (j.missing.length ? '<span style="font-size:14px;color:var(--warn)"><b>' + T('missing') + '</b> ' + esc(j.missing.map(s => L('skill', s)).join(', ')) + '</span>' : '') : '') + '</button>').join('');
    }
  }
  jf.addEventListener('input', () => renderJobs(true)); $('q').addEventListener('input', () => renderJobs(true));
  $('sort').onchange = () => renderJobs(true);
  $('more').onclick = () => { shown += 15; renderJobs(false); };
  $('jf-reset').onclick = () => { jf.reset(); $('q').value = ''; renderJobs(true); };
  $('jf-save').onclick = () => { store.set('jr-filter', readFilters()); $('jf-saved').textContent = T('saved'); };
  $('view-viec-lam').addEventListener('click', ev => {
    const o = ev.target.closest('[data-open]'); if (o) { const id = o.dataset.open; openId = openId === id ? null : id; renderJobs(false); const b = document.querySelector('[data-open="' + CSS.escape(id) + '"]'); if (b) b.focus(); return; }
    const a = ev.target.closest('[data-act]'); if (a) { const id = a.dataset.id, act = a.dataset.act; if (my[id] === act) delete my[id]; else my[id] = act; store.set('jr-status', my); renderJobs(false); return; }
    const g = ev.target.closest('[data-goto]'); if (g) { openId = g.dataset.goto; jf.reset(); $('sort').value = 'match'; renderJobs(true);
      let idx = -1; const all = document.querySelectorAll('.job'); all.forEach((e, i) => { if (e.dataset.id === openId) idx = i; });
      if (idx < 0) { shown = 999; renderJobs(false); }
      const e = document.querySelector('.job[data-id="' + CSS.escape(openId) + '"]'); if (e) e.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' }); }
  });

  // ---------- TAB 2 ----------
  const fa = $('fa'), C = () => window.JRCharts;
  function fillSelects() { ['city', 'industry', 'func', 'level', 'region', 'source'].forEach(n => { const s = fa.elements[n], v = s.value;
    s.innerHTML = '<option value="">' + T('all') + '</option>' + (GROUPS[n] || []).map(o => '<option value="' + esc(o) + '"' + (o === v ? ' selected' : '') + '>' + esc(L(n, o)) + '</option>').join(''); }); }
  fa.addEventListener('change', renderA); $('fa-reset').onclick = () => { fa.reset(); renderA(); };
  function passA(d, f, ignoreDays) {
    return (ignoreDays || d.daysAgo < +f.days) && (!f.city || d.city === f.city) && (!f.industry || d.industry === f.industry) && (!f.func || d.function === f.func) && (!f.level || d.level === f.level)
      && (!f.region || d.region === f.region) && (!f.source || d.source === f.source)
      && (f.salary === '' || (f.salary === '1') === !!d.salary) && (!f.match || f.match === '' || (f.match === '80' ? d.match >= 80 : f.match === '60' ? d.match >= 60 && d.match < 80 : (d.match ?? 0) < 60));
  }
  const countBy = (arr, key, order) => { const m = new Map((order || []).map(k => [k, 0])); arr.forEach(d => { const v = d[key]; if (v != null) m.set(v, (m.get(v) || 0) + 1); }); return [...m]; };
  function weekly(arr) {
    const weeks = 13, todayMs = TODAY * DAY, dow = (new Date(todayMs).getUTCDay() + 6) % 7, monday = TODAY - dow;
    const c = Array(weeks).fill(0);
    arr.forEach(d => { if (!d.posted_at) return; const w = Math.floor((monday - dayNum(d.posted_at)) / 7) + 1; const idx = dayNum(d.posted_at) >= monday ? weeks - 1 : weeks - 1 - w; if (idx >= 0 && idx < weeks) c[idx]++; });
    return c.map((n, i) => { const dt = new Date((monday - (weeks - 1 - i) * 7) * DAY); return { n, label: dt.getUTCDate() + '/' + (dt.getUTCMonth() + 1) }; });
  }
  function renderA() {
    const m = hasMatch(); $('fa-match').hidden = !m; $('c-match-box').hidden = !m;
    if (loadState !== 'ready') { $('ka').innerHTML = stateBox(loadState === 'ready' ? 'empty' : loadState); return; }
    const f = Object.fromEntries(new FormData(fa)); if (!m) f.match = '';
    const arr = jobs.filter(d => passA(d, f)), n = arr.length;
    const kp = [[fmt(n), T('k1')], [fmt(arr.filter(d => d.daysAgo < 7).length), T('k2')], [(n ? Math.round(arr.filter(d => d.salary).length / n * 100) : 0) + '%', T('k3')]];
    if (m) kp.push([fmt(arr.filter(d => d.match >= 70).length), T('k4')]);
    $('ka').innerHTML = kp.map(k => '<div class="card kpi"><div class="v">' + k[0] + '</div><div class="l">' + k[1] + '</div></div>').join('');
    const trendArr = jobs.concat(archive).filter(d => passA(d, f, true));
    C().trend('a-trend', weekly(trendArr));
    const tr = (g, pairs) => pairs.filter(p => p[1] > 0).map(p => [L(g, p[0]), p[1]]);
    C().hbar('a-ind', tr('industry', countBy(arr, 'industry', GROUPS.industry).sort((a, b) => b[1] - a[1])), T('posts'));
    C().hbar('a-city', tr('city', countBy(arr, 'city', GROUPS.city).sort((a, b) => b[1] - a[1])), T('posts'));
    if (m) C().hist('a-match', arr.filter(d => d.match != null).map(d => d.match));
    const fs = GROUPS.func.filter(k => arr.some(d => d.function === k)), ls = (GROUPS.level || []);
    C().heat('a-heat', fs.map(k => ({ key: k, label: L('func', k) })), ls.map(k => ({ key: k, label: L('level', k) })), fs.map(fk => ls.map(lk => arr.filter(d => d.function === fk && d.level === lk).length)));
    const sk = new Map(); arr.forEach(d => d.skills.forEach(s => sk.set(s, (sk.get(s) || 0) + 1)));
    C().hbar('a-skill', [...sk].sort((a, b) => b[1] - a[1]).slice(0, 8).map(p => [L('skill', p[0]), p[1]]), T('postsNeed'));
    C().hbar('a-hq', tr('hq', countBy(arr, 'hq_country').sort((a, b) => b[1] - a[1])), T('posts'));
  }

  // ---------- language, status, routing ----------
  const fmtTime = s => { if (!s) return '–'; const d = new Date(s);
    return new Intl.DateTimeFormat(lang === 'en' ? 'en-GB' : 'vi-VN', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hour12: false }).format(d) + ', ' + new Intl.DateTimeFormat('en-GB', { timeZone: TZ, day: 'numeric', month: 'numeric' }).format(d); };
  function cvMonth() { const v = META.cv_version; if (!v || !/^\d{4}-\d{2}/.test(v)) return null; const [y, mo] = v.split('-');
    return lang === 'en' ? new Date(Date.UTC(+y, +mo - 1, 1)).toLocaleString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' }) : (+mo) + '/' + y; }
  function applyLang() {
    document.documentElement.lang = lang;
    document.querySelectorAll('[data-i18n]').forEach(e => e.textContent = T(e.dataset.i18n));
    document.querySelectorAll('[data-i18n-ph]').forEach(e => e.placeholder = T(e.dataset.i18nPh));
    document.querySelectorAll('[data-i18n-aria]').forEach(e => e.setAttribute('aria-label', T(e.dataset.i18nAria)));
    document.querySelectorAll('.lang button').forEach(b => b.setAttribute('aria-pressed', b.dataset.lang === lang));
    $('st-upd').innerHTML = T('upd', { t: esc(fmtTime(META.last_run_at)) }); $('st-next').innerHTML = T('next', { t: esc(fmtTime(META.next_run_at)) });
    const cm = cvMonth(); $('reco-note').textContent = cm ? T('recoLinkM', { m: cm }) : T('recoLink');
    $('jf-saved').textContent = '';
    buildGroups(); buildQuick(); fillSelects(); route();
  }
  document.querySelectorAll('.lang button').forEach(b => b.onclick = () => { lang = b.dataset.lang; store.set('jr-lang', lang); applyLang(); });
  function route() {
    const tab = ['viec-lam', 'thi-truong'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'viec-lam';
    document.querySelectorAll('.view').forEach(v => v.hidden = v.id !== 'view-' + tab);
    document.querySelectorAll('nav.tabs a').forEach(a => a.setAttribute('aria-current', a.dataset.tab === tab ? 'page' : 'false'));
    if (tab === 'viec-lam') renderJobs(false); else renderA();
  }
  addEventListener('hashchange', route);
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { if (location.hash === '#thi-truong') renderA(); }, 150); });
  function restore() { const f = store.get('jr-filter', null); if (!f) return;
    for (const g of Object.keys(GROUPS)) els(g).forEach(c => c.checked = (f[g] || []).includes(c.value));
    if (f.minmatch != null) jf.elements.minmatch.value = f.minmatch;
    const setRadio = (n, v) => { const r = els(n).find(x => +x.value === v); if (r) r.checked = true; };
    setRadio('posted', f.posted); setRadio('exp', f.exp);
    ['salaryOnly', 'deadlineSoon', 'hideHidden', 'savedOnly', 'hideApplied'].forEach(k => { if (k in f) jf.elements[k].checked = !!f[k]; }); }

  const getJSON = async (u, opt) => { const r = await fetch(u); if (!r.ok) { if (opt) return null; throw new Error(u + ' ' + r.status); } return r.json(); };
  (async function boot() {
    // start every request at once; render the shell as soon as the strings arrive
    const pData = Promise.all([getJSON('i18n/taxonomy.json'), getJSON('data/meta.json', true), getJSON('data/jobs.json'), getJSON('data/archive.json', true)]);
    pData.catch(() => {});
    try { [I18N.vi, I18N.en] = await Promise.all([getJSON('i18n/vi.json'), getJSON('i18n/en.json')]); }
    catch (e) { document.body.insertAdjacentHTML('afterbegin', '<p role="alert" style="padding:16px">Không tải được giao diện / The page failed to load. Please reload.</p>'); return; }
    applyLang();
    try {
      const [tax, meta, data, arch] = await pData;
      TAX = tax || {}; META = meta || {}; TAX.skills = TAX.skills || {};
      TODAY = dayNum(vnDate(new Date()));
      jobs = (data.jobs || []).map(prep);
      archive = ((arch && arch.jobs) || []).map(j => ({ posted_at: j.posted_at, first_seen_at: j.first_seen_at, city: j.city, industry: j.industry, function: j.function, level: j.level, region: j.region, source: j.source, salary: j.salary, match: j.match }));
      loadState = 'ready';
    } catch (e) { loadState = 'error'; console.warn(e); }
    computeGroups(); buildGroups(); restore(); applyLang();
  })();
})();
