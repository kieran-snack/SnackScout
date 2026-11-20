/* SnackScout: the "scout a match" window and the in-app video player (used on event and team pages). */
(function () {
  const esc = s => SS.esc(s);
  const post = async (url, body) => (await fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})).json();
  const fmt = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };

  // ------------------------------------------------------------------ modal shell
  function modal(html, cls = '') {
    close();
    const wrap = document.createElement('div');
    wrap.className = 'modal-bg'; wrap.id = 'ss-modal';
    wrap.innerHTML = `<div class="modal ${cls}" role="dialog" aria-modal="true"><button class="modal-x ghost" type="button" aria-label="Close">✕</button>${html}</div>`;
    document.body.appendChild(wrap);
    document.body.classList.add('modal-open');
    wrap.addEventListener('click', e => { if (e.target === wrap || e.target.closest('.modal-x')) close(); });
    return wrap.querySelector('.modal');
  }
  function close() {
    const m = document.getElementById('ss-modal');
    if (m) { m.remove(); document.body.classList.remove('modal-open'); }
  }
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });

  // ------------------------------------------------------------------ video player
  // YouTube's own page can resume where you last stopped watching. The embedded player always starts at `start`.
  function playerHtml(v) {
    return `<iframe class="player" src="${v.embed || `https://www.youtube-nocookie.com/embed/${v.video_id}?start=${v.start}&autoplay=1&rel=0`}"
      allow="autoplay; encrypted-media; fullscreen" allowfullscreen title="Match video"></iframe>
      <div class="player-cap"><a class="btn ghost small" href="${ytUrl(v)}" target="_blank" rel="noopener">YouTube ↗</a>
        <span class="small muted">${esc(v.title)} · starts ${fmt(v.start)}. Won't play here? Its owner turned off playback on other sites, so use YouTube ↗.</span></div>`;
  }
  const ytUrl = v => `https://www.youtube.com/watch?v=${v.video_id}&t=${v.start}s`;
  SS.ytUrl = ytUrl;

  // "YouTube ↗" on event pages: the window opens right away (so pop-up blockers allow it), then goes to the match
  SS.youtubeMatch = async (code, key) => {
    const w = window.open('about:blank', '_blank');
    try {
      const v = await (await fetch(`/api/event/${code}/match/${encodeURIComponent(key)}/video`)).json();
      if (v.video) { if (w) w.location = ytUrl(v.video); else location.href = ytUrl(v.video); return; }
      if (w) w.close(); toast(v.reason || 'No video for this match.');
    } catch (e) { if (w) w.close(); toast("Couldn't look up the video.", 'bad'); }
  };

  SS.openPlayer = (v, title) => {
    const m = modal(`<h2 style="margin:0 0 10px">▶ ${esc(title || 'Match video')}</h2>${playerHtml(v)}`, 'wide');
  };

  // ------------------------------------------------------------------ scouting form for one team
  const COUNTERS = [['auto_pollen', 'Auto pollen'], ['teleop_pollen', 'Teleop pollen'], ['missed', 'Missed shots'],
                    ['nectar', 'Nectar'], ['hive_tips', 'Hive tips caused']];
  const opt = (list, cur) => list.map(o => `<option ${String(cur ?? '') === String(o) ? 'selected' : ''}>${esc(o)}</option>`).join('');
  function teamForm(t, me) {
    const n = t.note || {};
    return `<form class="note-form" data-team="${t.number}">
      <div class="form-grid">
        ${COUNTERS.map(([k, label]) => `<label>${label}<span class="counter">
          <button type="button" class="ghost small" data-bump="-1" aria-label="minus">−</button>
          <input name="${k}" inputmode="numeric" value="${n[k] ?? ''}">
          <button type="button" class="ghost small" data-bump="1" aria-label="plus">+</button></span></label>`).join('')}
        <label>Mostly scored in<select name="scored_where">${opt(['', 'Hive', 'Flower', 'Garden', 'Mixed', "Didn't score"], n.scored_where)}</select></label>
        <label>Endgame<select name="park">${opt(['', 'None', 'Partial park', 'Full park'], n.park)}</select></label>
        <label>Driver rating (1-5)<select name="rating">${opt(['', 1, 2, 3, 4, 5], n.rating)}</select></label>
        <label class="check"><input type="checkbox" name="defense" ${n.defense ? 'checked' : ''}> Played defense</label>
        <label class="check"><input type="checkbox" name="broke_down" ${n.broke_down ? 'checked' : ''}> Broke down / stuck</label>
      </div>
      <label class="small muted notes-label">Notes<textarea name="notes" placeholder="Fast cycles? Good defense? Tipped over?">${esc(n.notes || '')}</textarea></label>
      <div class="btn-row"><input name="scouter" value="${esc(n.scouter || me)}" style="width:150px" aria-label="Scouter">
        <button>💾 Save ${t.number}</button><span class="saved small muted">${n.by ? 'Last saved by ' + esc(n.by) : ''}</span></div>
    </form>`;
  }

  // ------------------------------------------------------------------ scout a whole match
  SS.scoutMatch = async (code, key, opts = {}) => {
    const box = modal(`<div class="modal-loading"><span class="spin"></span> Loading ${esc(key)}…</div>`, 'wide');
    let d;
    try {
      const r = await fetch(`/api/event/${code}/match/${encodeURIComponent(key)}${opts.team ? '?team=' + opts.team : ''}`);
      if (!r.ok) throw new Error(r.status);
      d = await r.json();
    } catch (e) { box.innerHTML = '<p>Couldn\'t load that match. Is SnackScout still running?</p>'; return; }
    const m = d.match;
    const teamTab = t => `<button type="button" class="tab ${t.alliance}" data-tab="t${t.number}">${t.ours ? '⭐ ' : ''}${t.number}${t.note ? ' ✓' : ''}</button>`;
    const score = m.played ? `<b>${m.red_score}</b> – <b>${m.blue_score}</b>` : `predicted ${m.pred_red}–${m.pred_blue} · Red ${m.p_red}%`;
    box.innerHTML = `<button class="modal-x ghost" type="button" aria-label="Close">✕</button>
      <div class="ev-head" style="margin-bottom:10px">
        <div><div class="small muted">${esc(d.event.name || code)}</div><h2 style="margin:2px 0 0">📝 Scout ${esc(m.description)}</h2></div>
        <div class="match-score">${score}${m.time ? `<div class="small muted">${m.time.slice(11, 16)}${m.field ? ' · field ' + m.field : ''}</div>` : ''}</div>
      </div>
      <div class="scout-grid">
        <div><div class="vid-slot"><div class="vid-empty"><span class="spin"></span> Finding the video…</div></div>
          ${m.tips && m.tips.length ? `<div class="panel flat" style="margin-top:10px"><b>💡 Our strategy</b><ul class="tips">${m.tips.map(t => `<li>${esc(t)}</li>`).join('')}</ul></div>` : ''}
          ${m.insight ? `<p class="small muted" style="margin-top:8px">👀 ${esc(m.insight)}</p>` : ''}
        </div>
        <div>
          <div class="tabs-row" role="tablist">${d.teams.map(teamTab).join('')}<button type="button" class="tab" data-tab="debrief">🗒 Match notes</button></div>
          ${d.teams.map(t => `<div class="tabpane" data-pane="t${t.number}" hidden>
              <div class="small" style="margin:8px 0"><b>${t.number}</b> ${esc(t.name || '')} · <span class="chip ${t.alliance}">${t.alliance}</span>
              ${t.opr != null ? ` · OPR ${t.opr.toFixed(1)}` : ''} · <a href="/team/${t.number}">team page</a></div>${teamForm(t, d.me)}</div>`).join('')}
          <div class="tabpane" data-pane="debrief" hidden>
            <p class="small muted" style="margin:8px 0">Notes about the whole match: what happened, what to change next time. Everyone on the team sees them.</p>
            <textarea id="debrief" style="width:100%;min-height:150px" placeholder="e.g. Partner's auto collided with ours, so start from the far side next time.">${esc(d.debrief)}</textarea>
            <div class="btn-row" style="margin-top:8px"><button type="button" id="save-debrief">💾 Save match notes</button><span class="small muted" id="debrief-saved"></span></div>
          </div>
        </div>
      </div>`;
    const tabs = [...box.querySelectorAll('.tab')], panes = [...box.querySelectorAll('.tabpane')];
    const show = id => { tabs.forEach(t => t.classList.toggle('on', t.dataset.tab === id)); panes.forEach(p => p.hidden = p.dataset.pane !== id); };
    tabs.forEach(t => t.onclick = () => show(t.dataset.tab));
    const first = d.teams.find(t => t.ours) || d.teams.find(t => String(t.number) === String(opts.focus)) || d.teams[0];
    show(opts.debrief ? 'debrief' : first ? 't' + first.number : 'debrief');

    box.addEventListener('click', e => {
      const b = e.target.closest('[data-bump]'); if (!b) return;
      const inp = b.parentElement.querySelector('input'); inp.value = Math.max(0, (parseInt(inp.value) || 0) + +b.dataset.bump);
    });
    box.querySelectorAll('form.note-form').forEach(f => f.addEventListener('submit', async e => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f));
      data.defense = f.defense.checked; data.broke_down = f.broke_down.checked;
      Object.assign(data, {team: +f.dataset.team, event: code, match_id: m.match_id, label: m.label});
      const r = await post('/api/match-note', data);
      f.querySelector('.saved').textContent = r.ok ? 'Saved ✓' : 'Error saving';
      if (r.ok) { toast(`Saved ${f.dataset.team} in ${m.label}`, 'good'); const t = box.querySelector(`[data-tab="t${f.dataset.team}"]`); if (t && !t.textContent.includes('✓')) t.textContent += ' ✓'; }
    }));
    box.querySelector('#save-debrief').onclick = async () => {
      const r = await post(`/api/event/${code}/match/${encodeURIComponent(key)}/debrief`, {text: box.querySelector('#debrief').value});
      box.querySelector('#debrief-saved').textContent = r.ok ? 'Saved ✓' : 'Error saving';
      if (r.ok) { toast('Match notes saved', 'good'); document.querySelectorAll(`[data-mnote="${key}"]`).forEach(el => el.hidden = false); }
    };
    box.addEventListener('keydown', e => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { const f = e.target.closest('form'); if (f) { e.preventDefault(); f.requestSubmit(); } }
    });

    // video loads after the form, so scouts can start typing right away
    const slot = box.querySelector('.vid-slot');
    try {
      const v = await (await fetch(`/api/event/${code}/match/${encodeURIComponent(key)}/video`)).json();
      slot.innerHTML = v.video ? playerHtml(v.video) : `<div class="vid-empty">🎬 ${esc(v.reason || 'No video for this match.')}</div>`;
    } catch (e) { slot.innerHTML = '<div class="vid-empty">🎬 Couldn\'t look up the video.</div>'; }
  };

  // ------------------------------------------------------------------ "▶ Watch" buttons that only know event + match
  SS.watchMatch = async (code, key, label) => {
    const box = modal(`<div class="modal-loading"><span class="spin"></span> Finding the video for ${esc(label || key)}…</div>`, 'wide');
    try {
      const v = await (await fetch(`/api/event/${code}/match/${encodeURIComponent(key)}/video`)).json();
      if (!v.video) { box.innerHTML = `<button class="modal-x ghost" type="button">✕</button><p>🎬 ${esc(v.reason)}</p>`; return; }
      box.innerHTML = `<button class="modal-x ghost" type="button" aria-label="Close">✕</button><h2 style="margin:0 0 10px">▶ ${esc(label || key)}</h2>${playerHtml(v.video)}
        <div class="btn-row" style="margin-top:10px"><button type="button" class="ghost" onclick="SS.scoutMatch('${code}', '${key}')">📝 Scout this match</button></div>`;
    } catch (e) { box.innerHTML = '<p>Couldn\'t look up the video.</p>'; }
  };
  SS.closeModal = close;
})();
