/* SnackScout: celebrate (or commiserate) our latest match result.
   Plays once per new result on this device: when SnackScout opens, on refresh, or when a result comes in (checked every 90 s).
   Five animations, each with a "we won" and a "we lost" version, picked at random. */
(function () {
  if (!document.body.dataset.user) return;
  const SEEN = 'ss.' + document.body.dataset.user + '.seenResult';
  const css = `
  .cele { position: fixed; inset: 0; z-index: 300; display: grid; place-items: center; pointer-events: auto; cursor: pointer;
    background: radial-gradient(circle at 50% 45%, color-mix(in srgb, var(--panel) 92%, transparent), color-mix(in srgb, var(--bg) 70%, transparent));
    backdrop-filter: blur(2px); animation: celeIn .3s ease; overflow: hidden; }
  .cele.out { animation: celeOut .45s ease forwards; }
  @keyframes celeIn { from { opacity: 0; } } @keyframes celeOut { to { opacity: 0; } }
  .cele-card { text-align: center; position: relative; z-index: 2; }
  .cele-title { font: 800 clamp(26px, 6vw, 44px)/1.1 var(--display, inherit); margin-top: 6px; }
  .cele-sub { color: var(--muted); font-size: 16px; margin-top: 4px; }
  .cele-stage { position: relative; width: 300px; height: 260px; margin: 0 auto; }
  .em { position: absolute; left: 50%; top: 50%; font-size: 96px; line-height: 1; transform: translate(-50%, -50%); }
  .p { position: absolute; font-size: 28px; left: 50%; top: 50%; }
  /* 1 monkey */
  /* the vine and the monkey swing together from one pivot at the top */
  .hang { position: absolute; left: 50%; top: -6px; width: 0; height: 0; transform-origin: 0 0; }
  .hang .vine { position: absolute; left: -2px; top: 0; width: 4px; height: 128px; background: linear-gradient(#5aa043, #3f7a2f); border-radius: 2px; }
  .hang .mk { position: absolute; left: -48px; top: 112px; font-size: 96px; line-height: 1; }
  .swing { animation: swing 1.3s ease-in-out infinite alternate; } @keyframes swing { from { transform: rotate(30deg); } to { transform: rotate(-30deg); } }
  .droop { animation: droop 3.2s ease-in-out infinite; } @keyframes droop { 0%, 100% { transform: rotate(4deg); } 50% { transform: rotate(-4deg); } }
  .tear { animation: tear 1.6s ease-in infinite; } @keyframes tear { from { transform: translate(14px, 0); opacity: 1; } to { transform: translate(14px, 70px); opacity: 0; } }
  /* 2 popcorn */
  .pop { animation: pop 1.4s cubic-bezier(.2,.8,.3,1) infinite; opacity: 0; }
  @keyframes pop { 0% { transform: translate(-50%, 0) scale(.3); opacity: 0; } 15% { opacity: 1; }
    100% { transform: translate(calc(-50% + var(--dx)), var(--dy)) rotate(var(--r)) scale(1); opacity: 0; } }
  .fizz { animation: fizz .5s ease-in-out infinite alternate; } @keyframes fizz { to { transform: translate(-50%, -2px) rotate(8deg); } }
  .puff { animation: puff 2.2s ease-out infinite; opacity: 0; } @keyframes puff { 0% { opacity: .9; transform: translate(-50%, 0) scale(.5); } 100% { opacity: 0; transform: translate(-50%, -80px) scale(1.4); } }
  /* 3 confetti / rain */
  .conf { width: 10px; height: 16px; top: -20px; border-radius: 2px; animation: fall linear forwards; }
  @keyframes fall { to { transform: translate(var(--dx), 110vh) rotate(var(--r)); } }
  .drop { width: 3px; height: 14px; background: #6aa0f0; border-radius: 2px; animation: rain .8s linear infinite; opacity: .8; }
  @keyframes rain { from { transform: translateY(-30px); } to { transform: translateY(110px); opacity: 0; } }
  /* 4 trophy / balloon */
  .bounce { animation: bounce .9s cubic-bezier(.3,1.6,.5,1) infinite alternate; } @keyframes bounce { from { transform: translate(-50%, -30%) scale(.95); } to { transform: translate(-50%, -62%) scale(1.08); } }
  .spark { animation: spark 1.2s ease-in-out infinite; } @keyframes spark { 0%, 100% { opacity: 0; transform: scale(.4); } 50% { opacity: 1; transform: scale(1.2) rotate(30deg); } }
  .deflate { animation: deflate 2.8s ease-in forwards; transform-origin: 50% 100%; }
  @keyframes deflate { 0% { transform: translate(-50%, -55%) scale(1); } 60% { transform: translate(-50%, -40%) scale(.75, .55) rotate(-12deg); } 100% { transform: translate(-50%, 0%) scale(.45, .3) rotate(-25deg); } }
  /* 5 robot */
  .dance { animation: dance .5s ease-in-out infinite alternate; } @keyframes dance { from { transform: translate(-50%, -50%) rotate(-12deg) translateY(0); } to { transform: translate(-50%, -50%) rotate(12deg) translateY(-18px); } }
  .note { animation: note 1.6s ease-out infinite; opacity: 0; } @keyframes note { 0% { opacity: 0; transform: translate(0, 0); } 30% { opacity: 1; } 100% { opacity: 0; transform: translate(var(--dx), -90px) rotate(20deg); } }
  .topple { animation: topple 2.4s ease-in forwards; transform-origin: 50% 100%; } @keyframes topple { 0%, 30% { transform: translate(-50%, -50%) rotate(0); } 100% { transform: translate(-50%, -38%) rotate(78deg); } }
  .zap { animation: zap .25s steps(2) infinite; } @keyframes zap { 50% { opacity: 0; } }
  @media (prefers-reduced-motion: reduce) { .cele * { animation-duration: .001s !important; animation-iteration-count: 1 !important; } }`;

  const rnd = (a, b) => a + Math.random() * (b - a);
  const el = (cls, txt, style = '') => `<span class="${cls}" style="${style}">${txt}</span>`;
  const ANIMS = {
    monkey: won => won
      ? `<span class="hang swing"><span class="vine"></span><span class="mk">🐒</span></span>${el('p spark', '✨', 'left:22%;top:30%')}${el('p spark', '🍌', 'left:74%;top:34%;animation-delay:.4s')}`
      : `<span class="hang droop"><span class="vine"></span><span class="mk">🙈</span></span>${el('p tear', '💧', 'left:50%;top:72%')}`,
    popcorn: won => won
      ? el('em', '🍿', 'top:72%;font-size:88px') + Array.from({length: 16}, (_, i) => el('p pop', i % 3 ? '🍿' : '⭐',
          `top:62%;--dx:${rnd(-140, 140)}px;--dy:${rnd(-210, -90)}px;--r:${rnd(-200, 200)}deg;animation-delay:${(i * .09).toFixed(2)}s`)).join('')
      : el('em', '🫙', 'top:68%;font-size:80px') + [-40, 0, 40].map((x, i) => el('p fizz', '🌽', `left:calc(50% + ${x}px);top:46%;font-size:30px;animation-delay:${i * .15}s`)).join('')
        + el('p puff', '💨', 'top:40%;font-size:40px'),
    party: won => won
      ? el('em', '🎉', 'font-size:104px') + Array.from({length: 70}, () => `<span class="p conf" style="left:${rnd(0, 100)}vw;background:hsl(${rnd(0, 360)},85%,60%);--dx:${rnd(-80, 80)}px;--r:${rnd(200, 900)}deg;animation-duration:${rnd(2.2, 4).toFixed(2)}s;animation-delay:${rnd(0, .8).toFixed(2)}s;position:fixed"></span>`).join('')
      : el('em', '🌧️', 'top:28%;font-size:96px') + Array.from({length: 14}, (_, i) => `<span class="p drop" style="left:calc(50% + ${rnd(-55, 55)}px);top:42%;animation-delay:${(i * .07).toFixed(2)}s"></span>`).join('')
        + el('em', '😞', 'top:82%;font-size:56px'),
    trophy: won => won
      ? el('em bounce', '🏆', 'font-size:110px') + [[22, 24], [76, 22], [18, 66], [80, 64], [50, 8]].map(([x, y], i) => el('p spark', '✨', `left:${x}%;top:${y}%;animation-delay:${i * .2}s`)).join('')
      : el('em deflate', '🎈', 'font-size:110px') + el('p', '💨', 'left:60%;top:70%;font-size:34px;opacity:.7'),
    robot: won => won
      ? el('em dance', '🤖', 'font-size:104px') + [-1, 1, -1, 1].map((d, i) => el('p note', i % 2 ? '🎵' : '🎶', `left:calc(50% + ${d * 60}px);top:40%;--dx:${d * 30}px;animation-delay:${i * .35}s`)).join('')
      : el('em topple', '🤖', 'font-size:104px') + el('p zap', '⚡', 'left:62%;top:34%;font-size:36px') + el('p zap', '💥', 'left:36%;top:44%;font-size:30px;animation-delay:.12s'),
  };
  const WIN_LINES = ['We won!', 'Victory!', 'Snack attack successful!', 'That’s how it’s done!', 'W for Snack Time!'];
  const LOSS_LINES = ['Tough one.', 'We’ll get the next one.', 'Shake it off.', 'Regroup and refuel.', 'Not our match.'];

  function play(r) {
    if ((document.documentElement.dataset.motion || 'full') === 'off') {
      toast(`${r.result === 'W' ? '🎉 We won' : r.result === 'L' ? 'We lost' : 'Tie in'} ${r.match}: ${r.us}–${r.them}`, r.result === 'W' ? 'good' : '', 6000);
      return;
    }
    if (!document.getElementById('cele-css')) { const s = document.createElement('style'); s.id = 'cele-css'; s.textContent = css; document.head.appendChild(s); }
    const won = r.result === 'W', tie = r.result === 'T';
    const keys = Object.keys(ANIMS), key = keys[Math.floor(Math.random() * keys.length)];
    const stage = tie ? el('em', '🤝') : ANIMS[key](won);
    const lines = won ? WIN_LINES : LOSS_LINES;
    const box = document.createElement('div');
    box.className = 'cele'; box.setAttribute('role', 'status');
    box.innerHTML = `<div class="cele-card"><div class="cele-stage">${stage}</div>
      <div class="cele-title">${tie ? 'A tie!' : lines[Math.floor(Math.random() * lines.length)]}</div>
      <div class="cele-sub">${SS.esc(r.match)} · ${r.us}–${r.them} · ${SS.esc(r.event || '')}</div>
      <div class="cele-sub" style="font-size:13px;margin-top:12px">Tap anywhere to continue</div></div>`;
    document.body.appendChild(box);
    const done = () => { box.classList.add('out'); setTimeout(() => box.remove(), 450); };
    box.addEventListener('click', done);
    setTimeout(done, won ? 5200 : 4600);
  }
  SS.celebrate = play;  // for testing: SS.celebrate({result: 'W', match: 'Q-8', us: 68, them: 44, event: 'Saline'})

  async function check() {
    try {
      const r = (await (await fetch('/api/our-latest-result')).json()).result;
      if (!r || !r.recent) return;
      let seen = null; try { seen = localStorage.getItem(SEEN); } catch (e) {}
      if (seen === r.key) return;
      try { localStorage.setItem(SEEN, r.key); } catch (e) {}
      if (!document.getElementById('ss-modal')) play(r);
    } catch (e) {}
  }
  setTimeout(check, 1200);
  setInterval(() => { if (!document.hidden) check(); }, 90000);
})();
