/* AOD gaming mode: touch layouts (keyboard + mouse) and Bluetooth controller support.
   Loaded after the main script, so it can use its helpers ($, $$, send, store, info, startVideo, sendCfg, native). */
(() => {
  const css = document.createElement('style');
  css.textContent = `
  #game{position:fixed;inset:0;z-index:50;display:none;touch-action:none;user-select:none;-webkit-user-select:none}
  #game.on{display:block}
  #game .zone{position:absolute;top:0;bottom:0}
  #game .gb{position:absolute;display:flex;align-items:center;justify-content:center;border-radius:50%;
    background:#07060caa;border:2px solid #ffffff55;color:#fff;font:600 13px system-ui;text-align:center;
    touch-action:none;transform:translate(0,0)}
  #game .gb.sq{border-radius:14px}#game .gb.act{background:#a855f7cc;color:#ffffff;border-color:#fff}
  #game .stickbase{position:absolute;width:120px;height:120px;margin:-60px 0 0 -60px;border-radius:50%;border:2px solid #fff6;background:#07060c55;display:none;pointer-events:none}
  #game .stickknob{position:absolute;width:52px;height:52px;margin:-26px 0 0 -26px;border-radius:50%;background:#a855f7aa;display:none;pointer-events:none}
  #game .top{position:absolute;top:6px;left:6px;display:flex;gap:6px;z-index:3}
  #game .top button{opacity:.7;min-height:36px;padding:4px 12px}
  #game .hint{position:absolute;left:0;right:0;top:50px;text-align:center;color:#ffffff88;font-size:12px;pointer-events:none}
  #gpanel{position:absolute;top:48px;left:6px;z-index:4;background:#110f19ee;border:1px solid #262038;border-radius:12px;padding:12px;display:none;flex-direction:column;gap:10px;min-width:250px;color:#efeaf8;font-size:14px}
  #gpanel label{display:flex;justify-content:space-between;align-items:center;gap:10px;color:#9189a8}
  #gpanel select{background:#07060c;color:#efeaf8;border:1px solid #262038;border-radius:8px;padding:6px}
  `;
  document.head.appendChild(css);

  // ---- layouts. Buttons: {t:label, k:key | b:mouse button, at:'css position', s:size px, sq:rounded-square}
  const LAYOUTS = {
    shooter: {
      name: 'Shooter (WASD + mouse look)', stick: {up:'w', down:'s', left:'a', right:'d'}, look: true,
      buttons: [
        {t:'Fire', b:'left', at:'right:7%;bottom:24%', s:84},
        {t:'Aim', b:'right', at:'right:22%;bottom:44%', s:64},
        {t:'Jump', k:'space', at:'right:6%;bottom:52%', s:64},
        {t:'Crouch', k:'ctrl', at:'right:21%;bottom:10%', s:60},
        {t:'Reload', k:'r', at:'right:34%;bottom:26%', s:56},
        {t:'Use', k:'e', at:'right:35%;bottom:46%', s:52},
        {t:'Sprint', k:'shift', at:'left:6%;bottom:58%', s:56},
        {t:'1', k:'1', at:'left:34%;top:8px', s:42, sq:1}, {t:'2', k:'2', at:'left:41%;top:8px', s:42, sq:1},
        {t:'3', k:'3', at:'left:48%;top:8px', s:42, sq:1}, {t:'4', k:'4', at:'left:55%;top:8px', s:42, sq:1},
        {t:'Tab', k:'tab', at:'right:14%;top:8px', s:42, sq:1}, {t:'Esc', k:'esc', at:'right:6%;top:8px', s:42, sq:1}]
    },
    racing: {
      name: 'Racing (A/D steer, W/S pedals)', stick: null, look: false,
      buttons: [
        {t:'◀', k:'a', at:'left:6%;bottom:14%', s:96}, {t:'▶', k:'d', at:'left:24%;bottom:14%', s:96},
        {t:'Gas', k:'w', at:'right:8%;bottom:30%', s:104}, {t:'Brake', k:'s', at:'right:28%;bottom:14%', s:84},
        {t:'Handbrake', k:'space', at:'right:28%;bottom:48%', s:68}, {t:'Boost', k:'shift', at:'right:8%;bottom:64%', s:60},
        {t:'Look back', k:'c', at:'left:6%;top:56px', s:54}, {t:'Esc', k:'esc', at:'right:6%;top:8px', s:42, sq:1}]
    },
    arrows: {
      name: 'Platformer / retro (arrows + Z X C)', stick: {up:'up', down:'down', left:'left', right:'right'}, look: false,
      buttons: [
        {t:'Z', k:'z', at:'right:26%;bottom:18%', s:80}, {t:'X', k:'x', at:'right:8%;bottom:30%', s:80},
        {t:'C', k:'c', at:'right:26%;bottom:48%', s:64}, {t:'Space', k:'space', at:'right:8%;bottom:62%', s:64},
        {t:'Enter', k:'enter', at:'right:6%;top:8px', s:46, sq:1}, {t:'Esc', k:'esc', at:'right:14%;top:8px', s:46, sq:1}]
    },
  };
  const key = (k, d) => send({t:'g_key', k, d: d ? 1 : 0});
  const buzz = ms => { try { navigator.vibrate && navigator.vibrate(ms); } catch {} };

  let on = false, layout = store.get('aod_layout') || 'shooter', look = parseFloat(store.get('aod_look') || '1.6'),
      padFailed = false, raf = 0, saved = null;
  const g = document.createElement('div'); g.id = 'game'; document.body.appendChild(g);

  // ---- build the overlay for the current layout
  function render() {
    const L = LAYOUTS[layout] || LAYOUTS.shooter;
    g.innerHTML = '';
    // touch zones: left = stick, right = mouse look
    const stickZone = el('div', 'zone', 'left:0;width:42%;'), lookZone = el('div', 'zone', 'left:42%;right:0;');
    g.append(stickZone, lookZone);
    const base = el('div', 'stickbase'), knob = el('div', 'stickknob'); g.append(base, knob);

    if (L.stick) bindStick(stickZone, base, knob, L.stick);
    if (L.look) bindLook(lookZone);

    for (const b of L.buttons) {
      const e = el('div', 'gb' + (b.sq ? ' sq' : ''), `${b.at};width:${b.s}px;height:${b.s}px;`);
      e.textContent = b.t;
      const down = ev => { ev.preventDefault(); ev.stopPropagation(); e.classList.add('act'); buzz(8); b.k ? key(b.k, 1) : send({t:'g_btn', b:b.b, d:1}); };
      const up = ev => { ev.preventDefault(); ev.stopPropagation(); e.classList.remove('act'); b.k ? key(b.k, 0) : send({t:'g_btn', b:b.b, d:0}); };
      e.addEventListener('touchstart', down, {passive:false});
      e.addEventListener('touchend', up, {passive:false});
      e.addEventListener('touchcancel', up, {passive:false});
      g.append(e);
    }
    // top-left bar + settings panel
    const top = el('div', 'top');
    const x = el('button'); x.textContent = '✕ Exit'; x.onclick = exit;
    const s = el('button'); s.textContent = '⚙'; s.onclick = () => { const p = $('gpanel'); p.style.display = p.style.display === 'flex' ? 'none' : 'flex'; };
    top.append(x, s); g.append(top);
    const panel = el('div'); panel.id = 'gpanel';
    panel.innerHTML = `
      <label>Layout <select id="gl">${Object.entries(LAYOUTS).map(([k, v]) => `<option value="${k}" ${k === layout ? 'selected' : ''}>${v.name}</option>`).join('')}</select></label>
      <label>Mouse-look speed <input type="range" id="gs" min="3" max="40" value="${Math.round(look * 10)}"></label>
      <div style="display:flex;gap:8px"><button id="gsm" style="flex:1">Smooth (75%)</button><button id="gsh" style="flex:1">Sharp (100%)</button></div>
      <div class="dim" id="gpadstat">Controller: none detected</div>`;
    g.append(panel);
    $('gl').onchange = e => { layout = e.target.value; store.set('aod_layout', layout); render(); };
    $('gs').oninput = e => { look = e.target.value / 10; store.set('aod_look', look); };
    $('gsm').onclick = () => setQuality(75); $('gsh').onclick = () => setQuality(100);
    g.append(Object.assign(el('div', 'hint'), {textContent: L.look ? 'Left: move · Right: look around' : ''}));
  }
  function el(tag, cls, style) { const e = document.createElement(tag); if (cls) e.className = cls; if (style) e.style.cssText = style; return e; }
  function setQuality(pct) { $('sc').value = pct; $('fps').value = pct === 100 ? 45 : 60; sendCfg(); }

  // ---- virtual stick -> 4 keys
  function bindStick(zone, base, knob, map) {
    let id = null, ox = 0, oy = 0; const cur = {up:0, down:0, left:0, right:0}, R = 55, DEAD = 0.3;
    const set = (dir, v) => { if (cur[dir] !== v) { cur[dir] = v; key(map[dir], v); } };
    const release = () => { ['up','down','left','right'].forEach(d => set(d, 0)); base.style.display = knob.style.display = 'none'; id = null; };
    zone.addEventListener('touchstart', e => { e.preventDefault(); if (id !== null) return; const t = e.changedTouches[0]; id = t.identifier; ox = t.clientX; oy = t.clientY;
      base.style.cssText = `display:block;left:${ox}px;top:${oy}px`; knob.style.cssText = `display:block;left:${ox}px;top:${oy}px`; }, {passive:false});
    zone.addEventListener('touchmove', e => { e.preventDefault();
      for (const t of e.changedTouches) if (t.identifier === id) {
        let dx = t.clientX - ox, dy = t.clientY - oy; const m = Math.hypot(dx, dy) || 1, c = Math.min(m, R);
        knob.style.left = (ox + dx / m * c) + 'px'; knob.style.top = (oy + dy / m * c) + 'px';
        const nx = dx / R, ny = dy / R;
        set('left', nx < -DEAD ? 1 : 0); set('right', nx > DEAD ? 1 : 0); set('up', ny < -DEAD ? 1 : 0); set('down', ny > DEAD ? 1 : 0); } }, {passive:false});
    const end = e => { e.preventDefault(); for (const t of e.changedTouches) if (t.identifier === id) release(); };
    zone.addEventListener('touchend', end, {passive:false}); zone.addEventListener('touchcancel', end, {passive:false});
  }

  // ---- mouse look
  function bindLook(zone) {
    let id = null, lx = 0, ly = 0, cx = 0, cy = 0;
    zone.addEventListener('touchstart', e => { e.preventDefault(); if (id !== null) return; const t = e.changedTouches[0]; id = t.identifier; lx = t.clientX; ly = t.clientY; }, {passive:false});
    zone.addEventListener('touchmove', e => { e.preventDefault();
      for (const t of e.changedTouches) if (t.identifier === id) {
        cx += (t.clientX - lx) * look * 2; cy += (t.clientY - ly) * look * 2; lx = t.clientX; ly = t.clientY;
        const dx = Math.trunc(cx), dy = Math.trunc(cy); cx -= dx; cy -= dy;
        if (dx || dy) send({t:'g_mouse', dx, dy}); } }, {passive:false});
    const end = e => { for (const t of e.changedTouches) if (t.identifier === id) id = null; };
    zone.addEventListener('touchend', end); zone.addEventListener('touchcancel', end);
  }

  // ---- Bluetooth controller (Gamepad API). Real Xbox pad if the host has ViGEmBus, else keyboard+mouse.
  const PADKEYS = {0:'space', 1:'ctrl', 2:'r', 3:'e', 4:'q', 5:'shift', 8:'tab', 9:'esc', 10:'shift', 11:'ctrl', 12:'up', 13:'down', 14:'left', 15:'right'};
  const padHeld = {}; let lastPad = '', lookAcc = [0, 0];
  const dz = (v, d = .12) => Math.abs(v) < d ? 0 : v;
  function setPadKey(k, d) { if (!!padHeld[k] !== d) { padHeld[k] = d; key(k, d); } }
  function pollPad() {
    const p = [...(navigator.getGamepads ? navigator.getGamepads() : [])].find(x => x && x.connected);
    const stat = $('gpadstat');
    if (p) {
      const mode = info.pad && !padFailed ? 'Xbox controller' : 'keyboard + mouse';
      if (stat) stat.textContent = `Controller: ${p.id.slice(0, 30)} → ${mode}`;
      const ax = p.axes, bt = p.buttons;
      if (info.pad && !padFailed) {
        const a = [dz(ax[0]), dz(ax[1]), dz(ax[2]), dz(ax[3]), bt[6] ? bt[6].value : 0, bt[7] ? bt[7].value : 0].map(v => Math.round(v * 100) / 100);
        let m = 0; bt.forEach((b, i) => { if (b.pressed && i !== 6 && i !== 7) m |= 1 << i; });
        const s = JSON.stringify([a, m]); if (s !== lastPad) { lastPad = s; send({t:'pad', a, m}); }
      } else {
        setPadKey('a', ax[0] < -.4); setPadKey('d', ax[0] > .4); setPadKey('w', ax[1] < -.4); setPadKey('s', ax[1] > .4);
        for (const [i, k] of Object.entries(PADKEYS)) if (!(i >= 12 && i <= 15 && false)) setPadKey(k, !!(bt[i] && bt[i].pressed));
        const rx = dz(ax[2]), ry = dz(ax[3]); lookAcc[0] += rx * 14 * look; lookAcc[1] += ry * 14 * look;
        const dx = Math.trunc(lookAcc[0]), dy = Math.trunc(lookAcc[1]); lookAcc[0] -= dx; lookAcc[1] -= dy; if (dx || dy) send({t:'g_mouse', dx, dy});
        const lt = !!(bt[6] && bt[6].pressed), rt = !!(bt[7] && bt[7].pressed);
        if (lt !== !!padHeld.rmb) { padHeld.rmb = lt; send({t:'g_btn', b:'right', d: lt ? 1 : 0}); }
        if (rt !== !!padHeld.lmb) { padHeld.lmb = rt; send({t:'g_btn', b:'left', d: rt ? 1 : 0}); }
      }
    } else if (stat) stat.textContent = 'Controller: none detected (pair one in Android Bluetooth settings, then press a button)';
    raf = requestAnimationFrame(pollPad);
  }

  // ---- enter / exit
  async function enter() {
    if (on) return; on = true;
    saved = {sc: $('sc').value, fps: $('fps').value};
    $$('#v-screen .bar,#v-screen .sheet,#nav').forEach(e => e.style.display = 'none'); $('unhide').style.display = 'none';
    try { native && native.setLandscape ? native.setLandscape(true) : (await document.documentElement.requestFullscreen(), await screen.orientation.lock('landscape')); } catch {}
    send({t:'game', on:true}); setQuality(75);
    startVideo();                         // new connection picks up the high-bitrate game profile
    render(); g.classList.add('on'); pollPad();
  }
  function exit() {
    if (!on) return; on = false; cancelAnimationFrame(raf);
    send({t:'g_release'}); Object.keys(padHeld).forEach(k => delete padHeld[k]); lastPad = '';
    g.classList.remove('on'); g.innerHTML = '';
    try { native && native.setLandscape ? native.setLandscape(false) : (document.fullscreenElement && document.exitFullscreen(), screen.orientation.unlock()); } catch {}
    send({t:'game', on:false}); if (saved) { $('sc').value = saved.sc; $('fps').value = saved.fps; sendCfg(); }
    $$('#v-screen .bar,#nav').forEach(e => e.style.display = 'flex');
    startVideo();
  }
  const prevOnMsg = onMsg;
  onMsg = async ev => { if (typeof ev.data === 'string') { try { const m = JSON.parse(ev.data); if (m.t === 'pad_error') { padFailed = true; } } catch {} } return prevOnMsg(ev); };
  window.addEventListener('gamepadconnected', () => { if (on) buzz(30); });

  // toolbar button
  const b = document.createElement('button'); b.id = 'bGame'; b.textContent = '🎮 Game'; b.onclick = enter;
  const bar = $('bKb').parentElement; bar.insertBefore(b, $('bSet'));
})();
