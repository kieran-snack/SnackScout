/* SnackScout shared UI helpers (every page). */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const root = document.documentElement;
  const loggedIn = !!document.body.dataset.user;
  const motion = () => root.dataset.motion || 'full';
  const store = {
    get(k, d) { try { const v = localStorage.getItem('ss.' + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('ss.' + k, JSON.stringify(v)); } catch (e) {} },
  };

  // ---------------------------------------------------------------- loading circles: never visibly restart
  // Pages re-draw spinners while polling. Starting every spinner at the same point of one shared clock means a
  // freshly drawn spinner continues exactly where the old one was, so it looks like one smooth, endless spin.
  const SPIN_MS = 900;
  const syncSpin = el => { el.style.animationDelay = -(performance.now() % SPIN_MS) + 'ms'; };
  const scanSpins = node => {
    if (node.nodeType !== 1) return;
    if (node.classList.contains('spin')) syncSpin(node);
    node.querySelectorAll?.('.spin').forEach(syncSpin);
  };
  scanSpins(document.body);
  new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(scanSpins))).observe(document.body, {childList: true, subtree: true});

  // ---------------------------------------------------------------- toasts (also replaces alert())
  function toast(msg, kind = '', ms = 3200) {
    const box = $('#toasts'); if (!box) return;
    const el = document.createElement('div');
    el.className = 'toast ' + kind; el.textContent = msg; box.appendChild(el);
    setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, ms);
  }
  window.toast = toast;
  window.alert = msg => toast(String(msg), /fail|error|couldn't|could not/i.test(msg) ? 'bad' : '', 5000);

  // ---------------------------------------------------------------- preferences / theme
  async function savePrefs(changes) {
    if (!loggedIn) return null;
    const cur = await (await fetch('/api/prefs', {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(Object.assign(window.__prefs || {}, changes))})).json();
    window.__prefs = cur.prefs; applyPrefs(cur.prefs, cur.css); return cur.prefs;
  }
  function applyPrefs(p, css) {
    if (css) $('#theme-vars').textContent = css;
    if (p.theme === 'light' || p.theme === 'dark') root.dataset.theme = p.theme; else delete root.dataset.theme;
    root.dataset.motion = p.motion; root.dataset.density = p.density;
  }
  function isDark() { return root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; }
  function cycleTheme() {
    const next = isDark() ? 'light' : 'dark';
    root.classList.add('theme-fade'); setTimeout(() => root.classList.remove('theme-fade'), 450);
    root.dataset.theme = next;
    if (loggedIn) savePrefs({theme: next}); else store.set('theme', next), localStorage.setItem('ss.theme', next);
    toast(next === 'dark' ? '🌙 Dark mode' : '☀️ Light mode', '', 1200);
  }

  // ---------------------------------------------------------------- user menu
  const avatar = $('#avatar-btn'), menu = $('#user-menu');
  if (avatar && menu) {
    avatar.onclick = e => { e.stopPropagation(); menu.hidden = !menu.hidden; };
    document.addEventListener('click', e => { if (!menu.hidden && !menu.contains(e.target)) menu.hidden = true; });
  }
  $('#theme-btn')?.addEventListener('click', () => { cycleTheme(); if (menu) menu.hidden = true; });

  // ---------------------------------------------------------------- cloud status pill
  const pill = $('#cloud-pill');
  async function cloudPill() {
    if (!pill) return;
    try {
      const s = await (await fetch('/api/cloud/status')).json();
      const t = pill.querySelector('.ctext');
      pill.className = 'cloud-pill ' + (!s.configured ? 'off' : s.running ? 'busy' : s.ok === false ? 'bad' : s.pending ? 'busy' : 'good');
      t.textContent = !s.configured ? 'Local only' : s.running ? 'Syncing…' : s.ok === false ? 'Offline' : s.pending ? `${s.pending} to sync` : 'Synced';
      pill.title = !s.configured ? 'Team cloud not set up: scouting is saved on this laptop only' :
        s.ok === false ? (s.error || 'Cannot reach the team cloud') : 'Team cloud: everyone sees the same scouting';
    } catch (e) {}
  }
  if (pill) { cloudPill(); setInterval(cloudPill, 12000); }

  // ---------------------------------------------------------------- keyboard shortcuts
  document.addEventListener('keydown', e => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
    if (e.key === 'Escape') { if (typing) document.activeElement.blur(); if (menu) menu.hidden = true; }
    if (typing || e.ctrlKey || e.metaKey || e.altKey || !loggedIn) return;
    if (e.key === '/') { e.preventDefault(); const q = $('#q'); q?.focus(); q?.select(); }
    else if (e.key === 't') cycleTheme();
    else if (e.key === ',') location.href = '/settings';
  });

  // ---------------------------------------------------------------- loading indicator for slow pages
  function loading(msg) {
    $('#loadbar')?.classList.add('on');
    const m = $('#loadmsg'); if (m) { m.querySelector('span:last-child').textContent = msg; clearTimeout(m._t); m._t = setTimeout(() => m.classList.add('on'), 600); }
  }
  window.addEventListener('pageshow', () => { $('#loadbar')?.classList.remove('on'); const m = $('#loadmsg'); if (m) { clearTimeout(m._t); m.classList.remove('on'); } });
  document.addEventListener('click', e => {
    const a = e.target.closest('a[href]');
    if (!a || a.target === '_blank' || e.ctrlKey || e.metaKey || e.shiftKey || a.hasAttribute('download')) return;
    const u = new URL(a.href, location.href);
    if (u.origin !== location.origin || (u.hash && u.pathname === location.pathname)) return;
    loading(/^\/team/.test(u.pathname) ? 'Loading team… the first time can take ~10 s' :
            /^\/event\//.test(u.pathname) ? 'Loading event & predictions…' : 'Loading…');
  });
  document.addEventListener('submit', e => {
    const f = e.target;
    if (f.matches('.search, [data-loading]') && !e.defaultPrevented) loading(f.dataset.loading || 'Searching…');
  });

  // ---------------------------------------------------------------- click ripple on buttons
  document.addEventListener('pointerdown', e => {
    const b = e.target.closest('button, .btn');
    if (!b || b.disabled || motion() === 'off') return;
    const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2.2;
    const s = document.createElement('span');
    s.className = 'ripple';
    s.style.cssText = `width:${d}px;height:${d}px;left:${e.clientX - r.left - d / 2}px;top:${e.clientY - r.top - d / 2}px`;
    b.appendChild(s); setTimeout(() => s.remove(), 600);
  });

  // ---------------------------------------------------------------- reveal on scroll (cards, panels, rows)
  if (motion() !== 'off' && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver(es => es.forEach(en => { if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); } }),
      {rootMargin: '0px 0px -40px 0px'});
    $$('.cards, .ev-list, .match-cards, .team-chips, .tags').forEach(group =>
      [...group.children].forEach((el, i) => { el.classList.add('pop'); el.style.setProperty('--i', Math.min(i, 12)); io.observe(el); }));
    $$('.panel, .hero, .table-wrap, .next-ev, .next-hero').forEach(el => { el.classList.add('pop'); io.observe(el); });
  }

  // ---------------------------------------------------------------- back to top
  const top = $('#totop');
  if (top) {
    addEventListener('scroll', () => top.classList.toggle('on', scrollY > 900), {passive: true});
    top.onclick = () => scrollTo({top: 0});
  }

  // ---------------------------------------------------------------- sortable + filterable tables
  function cellVal(td) {
    const raw = (td?.dataset.sort ?? td?.innerText ?? '').trim();
    const n = parseFloat(raw.replace(/[#%,]/g, ''));
    return raw === '–' || raw === '' ? null : isNaN(n) ? raw.toLowerCase() : n;
  }
  function makeSortable(table) {
    const head = table.tHead?.rows[0] || table.rows[0];
    [...head.cells].forEach((th, i) => {
      if (th.dataset.nosort != null || !th.innerText.trim()) return;
      th.classList.add('sortable');
      th.title = th.title || 'Click to sort';
      th.addEventListener('click', () => {
        const desc = !th.classList.contains('sort-desc');
        [...head.cells].forEach(c => c.classList.remove('sort-asc', 'sort-desc'));
        th.classList.add(desc ? 'sort-desc' : 'sort-asc');
        const body = table.tBodies[0];
        const rows = [...body.rows].filter(r => r !== head);
        rows.sort((a, b) => {
          const x = cellVal(a.cells[i]), y = cellVal(b.cells[i]);
          if (x === null) return 1; if (y === null) return -1;
          return (x > y ? 1 : x < y ? -1 : 0) * (desc ? -1 : 1);
        });
        rows.forEach((r, k) => { body.appendChild(r); if (motion() === 'full') { r.style.animation = 'none'; r.offsetHeight; r.style.animation = `rowIn .35s ${k * 12}ms both`; } });
      });
    });
  }
  $$('table[data-sortable]').forEach(makeSortable);
  $$('input[data-filter]').forEach(inp => {
    const table = document.getElementById(inp.dataset.filter);
    inp.addEventListener('input', () => {
      const q = inp.value.trim().toLowerCase();
      [...table.tBodies[0].rows].forEach(r => { if (!r.querySelector('th')) r.hidden = q && !r.innerText.toLowerCase().includes(q); });
    });
  });

  // ---------------------------------------------------------------- favorites + recently viewed teams (per person)
  const pfx = (document.body.dataset.user || 'guest') + '.';
  const teams = {
    favs: () => store.get(pfx + 'favs', store.get('favs', [])),
    recent: () => store.get(pfx + 'recent', store.get('recent', [])),
    isFav: n => teams.favs().some(t => t.n == n),
    toggleFav(n, name) {
      let f = teams.favs();
      if (f.some(t => t.n == n)) { f = f.filter(t => t.n != n); toast(`Removed ${n} from favorites`); }
      else { f.unshift({n, name}); toast(`★ Added ${n} to favorites`); }
      store.set(pfx + 'favs', f.slice(0, 40));
      return teams.isFav(n);
    },
    visit(n, name) { store.set(pfx + 'recent', [{n, name}, ...teams.recent().filter(t => t.n != n)].slice(0, 12)); },
  };
  window.SS = {store, teams, toast, loading, savePrefs, applyPrefs,
    esc: s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])),
    copy: async (text, msg = 'Copied') => {
      try { await navigator.clipboard.writeText(text); toast(msg); }
      catch (e) { const t = document.createElement('textarea'); t.value = text; document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove(); toast(msg); }
    },
    ago(ts) { const s = Math.round((Date.now() - ts) / 1000); return s < 10 ? 'just now' : s < 60 ? s + ' s ago' : Math.round(s / 60) + ' min ago'; },
  };

  // star buttons: <button data-fav="16750" data-name="Technototes">
  $$('[data-fav]').forEach(b => {
    const paint = on => { b.classList.toggle('on', on); b.textContent = on ? '★' : '☆'; b.title = on ? 'Remove from favorites' : 'Add to favorites'; };
    paint(teams.isFav(b.dataset.fav));
    b.addEventListener('click', () => { const on = teams.toggleFav(b.dataset.fav, b.dataset.name); paint(on); if (on) { b.classList.remove('burst-anim'); b.offsetWidth; b.classList.add('burst-anim'); } });
  });
  // lists: <div data-team-list="favs|recent">
  $$('[data-team-list]').forEach(box => {
    const list = teams[box.dataset.teamList]();
    box.innerHTML = list.length ? list.map(t => `<a href="/team/${t.n}"><b>${t.n}</b> ${SS.esc(t.name || '')}</a>`).join('')
      : `<span class="muted small">${box.dataset.empty || 'Nothing yet.'}</span>`;
  });
  const visit = document.body.dataset.visit;
  if (visit) { const [n, ...name] = visit.split('|'); teams.visit(n, name.join('|')); }
})();
