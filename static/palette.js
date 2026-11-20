/* SnackScout quick actions (Ctrl+K or the ⚡ button): every page and setting in one searchable list. */
(function () {
  if (!document.body.dataset.user) return;
  const admin = document.body.dataset.admin === '1';
  const ev = document.body.dataset.currentEvent || '';
  const our = document.body.dataset.ourTeam || '';
  const go = url => () => { location.href = url; };
  const ACTIONS = [
    ...(ev ? [['🏆', "Today's competition", 'event hub schedule', go(`/event/${ev}`)],
              ['📝', 'Scout our next match', 'scout watch notes', go(`/event/${ev}#ours`)],
              ['🗓', 'All matches at this competition', 'schedule every match', go(`/event/${ev}#all`)],
              ['🤝', 'Alliance selection / pick list', 'picks alliance', go(`/event/${ev}#alliance`)],
              ['🏅', 'Live rankings', 'rank standings', go(`/event/${ev}#rankings`)]] : []),
    ['🏆', 'Competitions (pick an event)', 'events today', go('/events')],
    ...(our ? [['⭐', `Our team (${our})`, 'us report', go(`/team/${our}`)]] : []),
    ['⚖️', 'Compare teams', 'versus side by side', go('/compare')],
    ['🏠', 'Home', 'dashboard favorites recent', go('/')],
    ['❓', 'How to use SnackScout', 'help guide tutorial', go('/help')],
    ['✨', "What's new", 'version changelog', go('/whats-new')],
    ['🎨', 'Colors & theme', 'palette settings dark light', go('/settings?tab=look')],
    ['🌓', 'Toggle dark mode', 'theme night', () => document.getElementById('theme-btn')?.click()],
    ['📝', 'Scouting settings', 'auto refresh columns', go('/settings?tab=scouting')],
    ['👤', 'Account & password', 'google link password name', go('/settings?tab=account')],
    ['☁️', 'Team cloud status / sync', 'supabase sync', go('/settings?tab=cloud')],
    ...(admin ? [['👥', 'Teammates & team code', 'admin users code', go('/settings?tab=team')],
                 ['💬', 'Slack settings', 'slack bot reminders', go('/settings?tab=slack')]] : []),
    ['↩', 'Log out', 'sign out', go('/logout')],
  ];

  let box, input, list, sel = 0, shown = [];
  function render() {
    const q = input.value.trim().toLowerCase();
    shown = ACTIONS.filter(([, label, words]) => !q || (label + ' ' + words).toLowerCase().includes(q));
    if (q) {
      if (/^\d{2,6}$/.test(q)) shown.unshift(['👥', `Open team ${q}`, '', go(`/team/${q}`)]);
      shown.push(['🔍', `Search teams & competitions for “${input.value.trim()}”`, '', go('/search?q=' + encodeURIComponent(input.value.trim()))]);
    }
    sel = Math.min(sel, shown.length - 1);
    list.innerHTML = shown.map(([ic, label], i) => `<li class="${i === sel ? 'on' : ''}" data-i="${i}"><span class="pic">${ic}</span>${SS.esc(label)}</li>`).join('');
  }
  function open() {
    if (box) return;
    box = document.createElement('div');
    box.className = 'modal-bg'; box.id = 'ss-palette';
    box.innerHTML = `<div class="modal palette"><input id="pal-in" placeholder="Type to find a page, setting, team or competition…" autocomplete="off" aria-label="Quick actions">
      <ul class="pal-list" role="listbox"></ul><div class="tiny muted">↑ ↓ to move · Enter to open · Esc to close</div></div>`;
    document.body.appendChild(box);
    input = box.querySelector('input'); list = box.querySelector('ul');
    input.addEventListener('input', () => { sel = 0; render(); });
    input.addEventListener('keydown', e => {
      if (e.key === 'ArrowDown') { sel = Math.min(sel + 1, shown.length - 1); render(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { sel = Math.max(sel - 1, 0); render(); e.preventDefault(); }
      else if (e.key === 'Enter' && shown[sel]) { const f = shown[sel][3]; close(); f(); }
      else if (e.key === 'Escape') close();
    });
    list.addEventListener('click', e => { const li = e.target.closest('li'); if (li) { const f = shown[+li.dataset.i][3]; close(); f(); } });
    box.addEventListener('click', e => { if (e.target === box) close(); });
    render(); input.focus();
  }
  function close() { box?.remove(); box = null; }
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); box ? close() : open(); }
  });
  document.getElementById('quick-btn')?.addEventListener('click', open);
  SS.quickActions = open;
})();
