/* AOD extras: Apps tab (shortcut buttons, app launcher, run command), smart settings, PC notifications.
   Loaded after the main script and game.js, so it can use $, $$, api, send, store, native, esc, onMsg. */
(() => {
  const css = document.createElement('style');
  css.textContent = `
  .sc{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-height:74px;padding:6px;font-size:13px;position:relative}
  .sc .ic{font-size:26px;line-height:1}.sc.edit{border-style:dashed;border-color:var(--accent)}
  #apps-page input[type=text],#apps-page input[type=search],#scEd input,#scEd select,#scEd textarea{width:100%;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:10px;font:inherit}
  #cmdOut{white-space:pre-wrap;word-break:break-word;background:#000;border:1px solid var(--line);border-radius:10px;padding:10px;font:12px ui-monospace,monospace;max-height:220px;overflow:auto;display:none}
  #scEd{position:fixed;inset:0;z-index:80;background:#000a;display:none;align-items:flex-end;justify-content:center}
  #scEd .box{background:var(--panel);border:1px solid var(--line);border-radius:16px 16px 0 0;width:100%;max-width:520px;padding:16px;display:flex;flex-direction:column;gap:10px}
  #toast{position:fixed;left:50%;bottom:84px;transform:translateX(-50%);background:#110f19f0;border:1px solid var(--line);color:var(--fg);padding:10px 16px;border-radius:12px;z-index:90;display:none;max-width:86%;text-align:center}
  #banner{position:fixed;top:10px;left:10px;right:10px;z-index:95;background:#110f19;border:1px solid var(--accent);border-radius:14px;padding:12px 14px;display:none;box-shadow:0 6px 24px #000a}
  #banner b{display:block;color:var(--accent)}
  .row2{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}
  .row2 small{color:var(--dim);display:block}
  .sc.scene{background:linear-gradient(160deg,#241a38,#140f1f)}
  #gamesPanel{position:fixed;inset:0;z-index:85;background:var(--bg);display:none;flex-direction:column}
  #gamesPanel .gvh{display:flex;align-items:center;gap:10px;padding:14px 16px;font-size:20px;font-weight:700}
  #gamesPanel .gbody{flex:1;overflow-y:auto;padding:0 14px 20px}
  .ggrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
  .gcard{border-radius:12px;overflow:hidden;background:#15101f;border:1px solid var(--line);position:relative;cursor:pointer}
  .gcard .art{width:100%;aspect-ratio:460/215;background:linear-gradient(160deg,#241a38,#140f1f) center/cover no-repeat}
  .gcard .nm{padding:8px 10px;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .gcard .cfg{position:absolute;top:6px;right:6px;width:28px;height:28px;border-radius:8px;background:#000a;display:flex;align-items:center;justify-content:center;font-size:14px}
  #gSet{position:fixed;inset:0;z-index:95;background:#000a;display:none;align-items:flex-end;justify-content:center}
  #gSet .box{background:var(--panel);border:1px solid var(--line);border-radius:16px 16px 0 0;width:100%;max-width:420px;padding:16px;display:flex;flex-direction:column;gap:10px}
  #gSet select{width:100%;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:10px}`;
  document.head.appendChild(css);

  const toastEl = Object.assign(document.createElement('div'), {id: 'toast'});
  const banner = Object.assign(document.createElement('div'), {id: 'banner'});
  document.body.append(toastEl, banner);
  let tt, bt;
  const toast = window.toast = m => { toastEl.textContent = m; toastEl.style.display = 'block'; clearTimeout(tt); tt = setTimeout(() => toastEl.style.display = 'none', 3200); };
  const post = (path, body) => api(path, {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify(body)}).then(r => r.json());

  // ---------- notification banner (PC -> phone, while the app is open)
  const prevOnMsg = onMsg;
  onMsg = async ev => {
    if (typeof ev.data === 'string') {
      try { const m = JSON.parse(ev.data);
        if (m.t === 'notify') { banner.innerHTML = `<b>${esc(m.title)}</b>${esc(m.text)}`; banner.style.display = 'block';
          try { navigator.vibrate && navigator.vibrate(40); } catch {} clearTimeout(bt); bt = setTimeout(() => banner.style.display = 'none', 6000); }
      } catch {}
    }
    return prevOnMsg(ev);
  };
  banner.onclick = () => banner.style.display = 'none';

  // ---------- Apps tab
  const page = $('apps-page');
  page.innerHTML = `
    <div style="display:flex;justify-content:space-between;align-items:center"><h3 style="margin:6px 0">My shortcuts</h3>
      <div style="display:flex;gap:6px"><button id="gamesBtn" style="min-height:34px;padding:2px 12px">🎮 Games</button><button id="scEdit" style="min-height:34px;padding:2px 12px">Edit</button><button id="scNew" class="primary" style="min-height:34px;padding:2px 12px">+ New</button></div></div>
    <div class="grid" id="scGrid"></div><p class="dim" id="scEmpty" style="display:none">No shortcuts yet. Tap <b>+ New</b> to make a button for a key combo, some text, an app, a website or a command.</p>
    <h3>Open an app</h3><input type="search" id="appQ" placeholder="Search apps on your PC…"><div class="list" id="appList" style="margin-top:6px"></div>
    <h3>Run a command</h3><div style="display:flex;gap:8px"><input type="text" id="cmdIn" placeholder="e.g. ipconfig  or  shutdown /a"><button id="cmdRun" class="primary">Run</button></div>
    <pre id="cmdOut"></pre>`;

  let shortcuts = [], editMode = false;
  const KEYALIAS = {windows: 'win', control: 'ctrl', return: 'enter', escape: 'esc', del: 'delete', pgup: 'pageup', pgdn: 'pagedown'};
  async function loadShortcuts() { try { shortcuts = await (await api('/api/shortcuts')).json(); } catch { shortcuts = []; } renderShortcuts(); }
  function renderShortcuts() {
    $('scGrid').innerHTML = shortcuts.map(s => `<button class="sc${editMode ? ' edit' : ''}${s.type === 'scene' ? ' scene' : ''}" data-id="${esc(s.id)}"><span class="ic">${esc(s.icon || (s.type === 'scene' ? '🎬' : '⚡'))}</span>${esc(s.label)}</button>`).join('');
    $('scEmpty').style.display = shortcuts.length ? 'none' : 'block'; $('scEdit').classList.toggle('on', editMode);
  }
  async function saveShortcuts() { shortcuts = await (await api('/api/shortcuts', {method: 'PUT', headers: {'content-type': 'application/json'}, body: JSON.stringify(shortcuts)})).json(); renderShortcuts(); }
  async function runShortcut(s) {
    buzz();
    if (s.type === 'keys') { send({t: 'key', keys: s.value.toLowerCase().split('+').map(x => x.trim()).filter(Boolean).map(x => KEYALIAS[x] || x)}); toast('Sent ' + s.value); }
    else if (s.type === 'text') { send({t: 'text', s: s.value}); toast('Typed'); }
    else if (s.type === 'launch') { const r = await post('/api/launch', {target: s.value}); toast(r.ok ? 'Opening ' + s.label : 'Could not open that'); }
    else if (s.type === 'run') { const r = await post('/api/run', {cmd: s.value}); showOut(r); toast('Ran ' + s.label); }
    else if (s.type === 'power') { if (['shutdown', 'restart', 'logoff', 'sleep'].includes(s.value) && !confirm(s.label + '?')) return; await post('/api/power', {action: s.value}); toast(s.label); }
    else if (s.type === 'scene') {
      const r = await post('/api/scenes/run', {id: s.id});
      if (r.error) return toast(r.error);
      const c = r.client || {};
      if (c.sc != null) { $('sc').value = Math.round(c.sc * 100); }
      if (c.q != null) $('q').value = c.q;
      if (c.fps != null) $('fps').value = c.fps;
      if (c.sc != null || c.q != null || c.fps != null) sendCfg();
      toast('Scene applied: ' + s.label);
    }
  }
  function buzz() { try { navigator.vibrate && navigator.vibrate(12); } catch {} }
  function showOut(r) { const o = $('cmdOut'); o.style.display = 'block'; o.textContent = (r.out || '(no output)') + (r.code ? `\n[exit ${r.code}]` : ''); o.scrollTop = o.scrollHeight; }
  $('scGrid').onclick = e => { const b = e.target.closest('[data-id]'); if (!b) return; const s = shortcuts.find(x => x.id === b.dataset.id); if (!s) return; editMode ? openEditor(s) : runShortcut(s); };
  $('scEdit').onclick = () => { editMode = !editMode; renderShortcuts(); };
  $('scNew').onclick = () => openEditor(null);

  // editor sheet
  const ed = Object.assign(document.createElement('div'), {id: 'scEd'});
  ed.innerHTML = `<div class="box"><b id="edT">New shortcut</b>
    <div style="display:flex;gap:8px"><input id="edIcon" style="width:64px;text-align:center;font-size:22px" maxlength="2" placeholder="⚡"><input id="edLabel" placeholder="Name" maxlength="24"></div>
    <select id="edType"><option value="keys">Press keys</option><option value="text">Type text</option><option value="launch">Open app / file / website</option><option value="run">Run a command (shows output)</option><option value="power">Power action</option><option value="scene">Scene (launch + volume + quality)</option></select>
    <input id="edVal"><select id="edPower" style="display:none"><option value="lock">Lock</option><option value="sleep">Sleep</option><option value="restart">Restart</option><option value="shutdown">Shut down</option><option value="logoff">Sign out</option></select>
    <div id="edScene" style="display:none;flex-direction:column;gap:8px">
      <input id="scLaunch" placeholder="App / file / website to open (optional)">
      <div><small class="dim">Volume on apply: <span id="scVolN">70</span>%</small><input id="scVol" type="range" min="0" max="100" value="70" style="width:100%"></div>
      <select id="scQuality"><option value="low">Quality: Low (saves data/battery)</option><option value="balanced" selected>Quality: Balanced</option><option value="high">Quality: High</option></select>
    </div>
    <small class="dim" id="edHelp"></small>
    <div style="display:flex;gap:8px"><button id="edDel" class="bad" style="display:none">Delete</button><span style="flex:1"></span><button id="edCancel">Cancel</button><button id="edSave" class="primary">Save</button></div></div>`;
  document.body.appendChild(ed);
  const HELP = {keys: 'Example: ctrl+shift+m   or   win+d   or   alt+f4', text: 'This text is typed on the PC wherever the cursor is.', launch: 'A program path, a website (https://…), a folder, or a command.', run: 'Runs on the PC and shows the result here.', power: '', scene: 'One tap: opens something, sets PC volume, and switches your screen quality.'};
  const PRESETS = {low: {sc: 0.5, q: 45, fps: 15}, balanced: {sc: 0.7, q: 60, fps: 24}, high: {sc: 0.9, q: 80, fps: 45}};
  let editing = null;
  function syncType() { const t = $('edType').value; $('edVal').style.display = (t === 'power' || t === 'scene') ? 'none' : 'block'; $('edPower').style.display = t === 'power' ? 'block' : 'none'; $('edScene').style.display = t === 'scene' ? 'flex' : 'none'; $('edHelp').textContent = HELP[t]; $('edVal').placeholder = (HELP[t] || '').split(':')[0]; }
  $('scVol').oninput = () => $('scVolN').textContent = $('scVol').value;
  $('edType').onchange = syncType;
  function openEditor(s) {
    editing = s; $('edT').textContent = s ? 'Edit shortcut' : 'New shortcut';
    $('edIcon').value = s ? s.icon : ''; $('edLabel').value = s ? s.label : ''; $('edType').value = s ? s.type : 'keys';
    $('edVal').value = s && s.type !== 'power' && s.type !== 'scene' ? s.value : ''; if (s && s.type === 'power') $('edPower').value = s.value;
    if (s && s.type === 'scene') { try { const c = JSON.parse(s.value); $('scLaunch').value = c.launch || ''; $('scVol').value = c.volume != null ? c.volume : 70; $('scVolN').textContent = $('scVol').value;
      const q = c.client || {}; $('scQuality').value = q.fps >= 40 ? 'high' : q.fps <= 16 ? 'low' : 'balanced'; } catch { $('scLaunch').value = ''; } }
    else { $('scLaunch').value = ''; $('scVol').value = 70; $('scVolN').textContent = '70'; $('scQuality').value = 'balanced'; }
    $('edDel').style.display = s ? 'block' : 'none'; syncType(); ed.style.display = 'flex';
  }
  $('edCancel').onclick = () => ed.style.display = 'none';
  $('edSave').onclick = async () => {
    const type = $('edType').value;
    let value = type === 'power' ? $('edPower').value : $('edVal').value.trim();
    if (type === 'scene') value = JSON.stringify({launch: $('scLaunch').value.trim(), volume: +$('scVol').value, client: PRESETS[$('scQuality').value]});
    const label = $('edLabel').value.trim() || (type === 'scene' ? 'Scene' : value.slice(0, 14));
    if (type !== 'scene' && !value) { toast('Enter what it should do'); return; }
    const item = {id: editing ? editing.id : Math.random().toString(36).slice(2, 10), label, icon: $('edIcon').value.trim() || (type === 'scene' ? '🎬' : '⚡'), type, value};
    shortcuts = editing ? shortcuts.map(x => x.id === editing.id ? item : x) : [...shortcuts, item];
    ed.style.display = 'none'; await saveShortcuts();
  };
  $('edDel').onclick = async () => { if (!confirm('Delete this shortcut?')) return; shortcuts = shortcuts.filter(x => x.id !== editing.id); ed.style.display = 'none'; await saveShortcuts(); };

  // app launcher
  let appTimer;
  async function loadApps() { const q = $('appQ').value; const apps = await (await api('/api/apps?q=' + encodeURIComponent(q))).json();
    $('appList').innerHTML = apps.map(a => `<div data-p="${esc(a.path)}" data-n="${esc(a.name)}"><span>🗔</span><span class="n">${esc(a.name)}</span><span class="dim">Open</span></div>`).join('') || '<div class="dim">No apps found</div>'; }
  $('appQ').oninput = () => { clearTimeout(appTimer); appTimer = setTimeout(loadApps, 250); };
  $('appList').onclick = async e => { const r = e.target.closest('[data-p]'); if (!r) return; const res = await post('/api/launch', {target: r.dataset.p}); toast(res.ok ? 'Opening ' + r.dataset.n : 'Could not open it'); };
  $('cmdRun').onclick = async () => { const c = $('cmdIn').value.trim(); if (!c) return; $('cmdRun').disabled = true; try { showOut(await post('/api/run', {cmd: c})); } finally { $('cmdRun').disabled = false; } };
  $('cmdIn').onkeydown = e => { if (e.key === 'Enter') $('cmdRun').click(); };
  document.querySelector('#nav [data-view="apps"]').addEventListener('click', () => { loadShortcuts(); loadApps(); });

  // ---------- Game library (Steam)
  const GPRESETS = {low: {sc: 0.5, q: 45, fps: 15}, balanced: {sc: 0.7, q: 60, fps: 24}, high: {sc: 0.9, q: 80, fps: 45}};
  const gamePanel = Object.assign(document.createElement('div'), {id: 'gamesPanel'});
  gamePanel.innerHTML = `<div class="gvh"><span style="flex:1">🎮 Games</span><button id="gBack" style="min-height:34px;padding:2px 12px">Back</button></div><div class="gbody" id="gBody"></div>`;
  document.body.appendChild(gamePanel);
  const gSet = Object.assign(document.createElement('div'), {id: 'gSet'});
  gSet.innerHTML = `<div class="box"><b id="gSetT"></b><small class="dim">Applied automatically when you launch this game.</small><select id="gSetQ"><option value="low">Low (saves data/battery)</option><option value="balanced">Balanced</option><option value="high">High</option></select><div style="display:flex;gap:8px;justify-content:flex-end"><button id="gSetCancel">Cancel</button><button id="gSetSave" class="primary">Save</button></div></div>`;
  document.body.appendChild(gSet);
  const gKey = id => 'aod_gq_' + id;
  const gPreset = id => { try { return store.get(gKey(id)) || 'balanced'; } catch { return 'balanced'; } };
  $('gamesBtn').onclick = async () => {
    gamePanel.style.display = 'flex'; $('gBody').innerHTML = '<p class="dim">Looking for installed Steam games…</p>';
    let games = []; try { games = await (await api('/api/games')).json(); } catch {}
    if (!games.length) { $('gBody').innerHTML = '<p class="dim">No Steam games found on this PC, or Steam isn\'t installed.</p>'; return; }
    $('gBody').innerHTML = `<div class="ggrid">${games.map(g => `<div class="gcard" data-id="${esc(g.appid)}"><div class="art" style="background-image:url('/api/games/art/${g.appid}?token=${encodeURIComponent(tok())}')"></div><div class="nm">${esc(g.name)}</div><button class="cfg" data-cfg="${esc(g.appid)}">⚙</button></div>`).join('')}</div>`;
  };
  $('gBack').onclick = () => gamePanel.style.display = 'none';
  let gEditing = null;
  gamePanel.onclick = async e => {
    const cfg = e.target.closest('[data-cfg]');
    if (cfg) { gEditing = cfg.dataset.cfg; $('gSetT').textContent = 'Quality for this game'; $('gSetQ').value = gPreset(gEditing); gSet.style.display = 'flex'; return; }
    const card = e.target.closest('[data-id]'); if (!card) return;
    const id = card.dataset.id, p = GPRESETS[gPreset(id)];
    $('sc').value = Math.round(p.sc * 100); $('q').value = p.q; $('fps').value = p.fps; sendCfg();
    const r = await post('/api/games/launch', {appid: id});
    toast(r.ok ? 'Launching…' : 'Could not launch that game');
    gamePanel.style.display = 'none';
    document.querySelector('#nav [data-view="screen"]').click();
  };
  $('gSetCancel').onclick = () => gSet.style.display = 'none';
  $('gSetSave').onclick = () => { try { store.set(gKey(gEditing), $('gSetQ').value); } catch {} gSet.style.display = 'none'; toast('Saved'); };

  // ---------- Power tab: smart settings
  const power = document.querySelector('#v-power .page'), smart = document.createElement('div'); smart.id = 'smart';
  const anchor = [...power.querySelectorAll('h3')].find(h => h.textContent.startsWith('This phone')); power.insertBefore(smart, anchor);
  async function loadSmart() {
    let s = {}; try { s = await (await api('/api/settings')).json(); } catch {}
    const rows = [
      {k: 'autolock', t: 'Lock the PC when this phone disconnects', d: 'About a minute after, if nobody is using the PC', on: s.autolock, set: v => post('/api/settings', {autolock: v})},
      {k: 'dl', t: 'Tell me when downloads finish', d: 'A notification from the PC', on: s.notify_downloads, set: v => post('/api/settings', {notify_downloads: v})},
    ];
    if (native && native.setNotifications) rows.push({k: 'nt', t: 'Show PC notifications on this phone', d: 'Works even when the app is closed', on: native.notificationsEnabled(), set: v => { native.setNotifications(v); return Promise.resolve(); }});
    if (native && native.setAppLock) rows.push({k: 'lk', t: 'Fingerprint to open AOD', d: 'Also hides AOD in the recent-apps view', on: native.appLockEnabled(), set: v => { native.setAppLock(v); return Promise.resolve(); }});
    smart.innerHTML = '<h3>Smart features</h3>' + rows.map(r => `<div class="row2"><span>${esc(r.t)}<small>${esc(r.d)}</small></span><button data-k="${r.k}" class="${r.on ? 'on' : ''}">${r.on ? 'On' : 'Off'}</button></div>`).join('') +
      `<p class="dim" style="font-size:13px">${s.service ? 'PC is running AOD as a service: it works on the lock screen.' : 'Tip: run AOD as a service on the PC (tray menu) to control the lock screen and admin prompts.'}</p>`;
    smart.onclick = async e => { const b = e.target.closest('[data-k]'); if (!b) return; const r = rows.find(x => x.k === b.dataset.k); r.on = !r.on; await r.set(r.on); b.textContent = r.on ? 'On' : 'Off'; b.classList.toggle('on', r.on); };
  }
  document.querySelector('#nav [data-view="power"]').addEventListener('click', loadSmart);

  // ---------- Tasks: "tell me when this closes"
  $('procs').addEventListener('click', async e => { const b = e.target.closest('[data-watch]'); if (!b) return;
    const r = await post('/api/watch', {pid: +b.dataset.watch}); toast(r.ok ? `I'll notify you when ${r.name} closes` : 'That program already closed'); });

  // phone notifications service: make sure it is running if enabled
  if (native && native.notificationsEnabled && native.notificationsEnabled() && native.setNotifications) native.setNotifications(true);

  // ---------- adaptive quality: step resolution / frame rate down on a weak connection, back up when it recovers
  $('bAuto').textContent = 'Auto quality: ' + (autoOn ? 'on' : 'off');
  $('bAuto').onclick = e => { autoOn = !autoOn; store.set('aod_auto', autoOn ? '1' : '0'); autoLvl = 0; sendCfg(); e.target.textContent = 'Auto quality: ' + (autoOn ? 'on' : 'off'); };
  let badN = 0, goodN = 0, prevStats = null, prevPc = null;
  setInterval(async () => {
    if (!autoOn || !ws || ws.readyState !== 1 || document.hidden) return;
    let loss = 0, rtt = 0;
    if (!jpegActive && pc) {
      try {
        if (pc !== prevPc) { prevPc = pc; prevStats = null; }
        let inb, cp;
        (await pc.getStats()).forEach(r => {
          if (r.type === 'inbound-rtp' && r.kind === 'video') inb = r;
          if (r.type === 'candidate-pair' && r.state === 'succeeded' && r.currentRoundTripTime != null) cp = r;
        });
        if (inb) {
          if (prevStats) { const dl = inb.packetsLost - prevStats.l, dr = inb.packetsReceived - prevStats.r; loss = dl > 0 ? dl / (dl + dr) : 0; }
          prevStats = {l: inb.packetsLost, r: inb.packetsReceived};
        }
        if (cp) rtt = cp.currentRoundTripTime * 1000;
      } catch {}
    }
    const target = Math.max(10, $('fps').value * (1 - .08 * autoLvl));
    const bad = loss > .04 || lastFps < target * .6 || rtt > 300;
    const good = loss < .005 && lastFps >= target * .9 && rtt < 100;
    if (bad) { goodN = 0; if (++badN >= 2 && autoLvl < 6) { autoLvl++; badN = 0; sendCfg(); } }
    else if (good) { badN = 0; if (++goodN >= 6 && autoLvl > 0) { autoLvl--; goodN = 0; sendCfg(); } }
    else { badN = 0; }
  }, 2000);

  // ---------- screenshot + recording
  $('bShot').onclick = () => {
    location.href = `/api/screenshot?token=${encodeURIComponent(tok())}&mon=${info.current}&dl=1&save=1`;
    toast('Screenshot saved to this phone and to Pictures\\AOD on the PC');
  };
  const recUi = on => { const b = $('bRec'); b.dataset.ic = on ? 'stop' : 'rec'; b.style.color = on ? 'var(--bad)' : ''; renderIcons(b.parentNode); };
  $('bRec').onclick = async () => {
    const on = $('bRec').dataset.ic === 'rec';
    if (on && jpegActive) return toast('Recording needs WebRTC video (Settings > Video)');
    const r = await post('/api/record', {on});
    recUi(r.on); toast(r.on ? 'Recording on the PC…' : 'Saving recording to Videos\\AOD on the PC');
  };
  api('/api/record').then(r => r.json()).then(r => recUi(r.on)).catch(() => {});

  // ---------- small modal list picker
  const pick = document.createElement('div');
  pick.id = 'pick';
  pick.style.cssText = 'position:fixed;inset:0;z-index:85;background:#000a;display:none;align-items:flex-end;justify-content:center';
  pick.innerHTML = '<div style="background:var(--panel);border:1px solid var(--line);border-radius:16px 16px 0 0;width:100%;max-width:560px;max-height:75vh;display:flex;flex-direction:column"><div id="pickT" style="padding:14px 16px;font-weight:700"></div><div id="pickL" style="overflow-y:auto;padding:0 8px 8px"></div><button id="pickX" style="margin:8px;border-radius:12px">Cancel</button></div>';
  document.body.appendChild(pick);
  const choose = (title, opts) => new Promise(res => {
    $('pickT').textContent = title;
    $('pickL').innerHTML = opts.map((o, i) => `<button data-i="${i}" style="display:block;width:100%;text-align:left;margin:4px 0;white-space:normal;word-break:break-word${o.bad ? ';color:var(--bad)' : ''}">${esc(o.label)}</button>`).join('') || '<p class="dim" style="padding:8px">Nothing here.</p>';
    pick.style.display = 'flex';
    const done = v => { pick.style.display = 'none'; res(v); };
    $('pickX').onclick = () => done(null);
    pick.onclick = e => { if (e.target === pick) done(null); };
    $('pickL').onclick = e => { const b = e.target.closest('[data-i]'); if (b) done(opts[+b.dataset.i]); };
  });

  // ---------- files: thumbnails, actions, search, new folder
  const IMG = /\.(jpe?g|png|gif|bmp|webp)$/i;
  const dl = it => { location.href = '/api/download?token=' + encodeURIComponent(tok()) + '&path=' + encodeURIComponent(it.path); };
  const fsop = async (op, path, name) => {
    const r = await api('/api/fs', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({op, path, name})});
    const j = await r.json(); if (!r.ok) toast(j.error || 'Failed'); return r.ok;
  };
  window.renderFiles = (items, dir, searching) => {
    const box = $('flist');
    box.innerHTML = items.map((it, i) => `<div data-i="${i}">${!it.dir && IMG.test(it.name) ? `<img loading="lazy" width="36" height="36" style="border-radius:6px;object-fit:cover" src="/api/thumb?token=${encodeURIComponent(tok())}&path=${encodeURIComponent(it.path)}">` : `<span style="width:36px;color:var(--soft)">${svg(it.dir ? 'files' : 'doc')}</span>`}<span class="n">${esc(it.name)}${searching ? `<small class="dim" style="display:block;overflow:hidden;text-overflow:ellipsis">${esc(it.path)}</small>` : ''}</span><span class="dim">${it.dir ? '' : fmt(it.size)}</span><button data-m="${i}" style="min-height:34px;padding:2px 10px">⋯</button></div>`).join('') || '<div class="dim">Nothing here</div>';
    box.onclick = async e => {
      const mb = e.target.closest('[data-m]'), row = e.target.closest('[data-i]'); if (!row) return;
      const it = items[(mb || row).dataset[mb ? 'm' : 'i']];
      if (!mb) { if (it.dir) { $('fSearch').value = ''; openDir(it.path); } else dl(it); return; }
      const a = await choose(it.name, [{k: 'dl', label: it.dir ? 'Open' : 'Download to this phone'}, {k: 'rn', label: 'Rename'}, {k: 'rm', label: 'Move to Recycle Bin', bad: true}]);
      if (!a) return;
      if (a.k === 'dl') return it.dir ? openDir(it.path) : dl(it);
      if (a.k === 'rn') { const n = prompt('New name', it.name); if (n && n !== it.name && await fsop('rename', it.path, n)) openDir(curPath); }
      if (a.k === 'rm' && confirm('Move "' + it.name + '" to the Recycle Bin on the PC?') && await fsop('delete', it.path)) { toast('Moved to Recycle Bin'); openDir(curPath); }
    };
  };
  $('fNew').onclick = async () => { const n = prompt('New folder name'); if (n && await fsop('mkdir', curPath, n)) openDir(curPath); };
  let st;
  $('fSearch').oninput = e => {
    clearTimeout(st); const q = e.target.value.trim();
    if (!q) { openDir(curPath); return; }
    st = setTimeout(async () => {
      const r = await api('/api/fs/search?q=' + encodeURIComponent(q) + '&dir=' + encodeURIComponent(curPath));
      window.renderFiles(await r.json(), curPath, true);
    }, 450);
  };

  // ---------- stream a single window
  const bWin = Object.assign(document.createElement('button'), {id: 'bWin'});
  bWin.dataset.ic = 'win'; $('bShot').before(bWin); renderIcons(bWin.parentNode);
  bWin.onclick = async () => {
    const wins = await (await api('/api/windows')).json();
    const c = await choose('Show on screen', [{hwnd: 0, label: '🖥 Whole screen'}, ...wins.map(w => ({hwnd: w.hwnd, label: w.title}))]);
    if (c) { send({t: 'window', hwnd: c.hwnd}); setFollowUi(false); zoom = 1; panX = panY = 0; applyZoom(); toast(c.hwnd ? 'Showing only that window' : 'Showing the whole screen'); }
  };

  // ---------- follow the PC's mouse: show whatever window it's hovering over
  const bFollow = Object.assign(document.createElement('button'), {id: 'bFollow', title: 'Follow the mouse on the PC'});
  bFollow.dataset.ic = 'win'; bWin.before(bFollow); renderIcons(bFollow.parentNode);
  let followOn = false;
  function setFollowUi(on) { followOn = on; bFollow.classList.toggle('on', on); }
  bFollow.onclick = () => { setFollowUi(!followOn); send({t: 'follow', on: followOn}); zoom = 1; panX = panY = 0; applyZoom(); toast(followOn ? 'Following whatever window the PC mouse is over' : 'Follow mouse off'); };
  const prevOnMsg2 = onMsg;
  onMsg = async ev => { if (typeof ev.data === 'string' && ev.data.includes('"t":"info"')) { try { const m = JSON.parse(ev.data); if (m.t === 'info' && m.follow !== followOn) setFollowUi(!!m.follow); } catch {} } return prevOnMsg2(ev); };

  // ---------- clipboard history
  const hb = Object.assign(document.createElement('button'), {textContent: 'History'});
  $('cPaste').after(hb);
  hb.onclick = async () => {
    const h = await (await api('/api/clips')).json();
    const c = await choose('Recent clipboard', h.map(t => ({t, label: t.length > 140 ? t.slice(0, 140) + '…' : t})));
    if (c) { $('cliptext').value = c.t; send({t: 'clip_set', s: c.t}); toast('Copied to the PC clipboard'); }
  };

  // ---------- safety: panic + activity
  const safe = document.createElement('div');
  safe.innerHTML = '<h3>Safety</h3><button class="bad" id="bPanic" style="width:100%;margin-bottom:8px">Panic: disconnect everyone and pause AOD</button><div class="list" id="actl"></div>';
  $('devs').previousElementSibling.before(safe);
  $('bPanic').onclick = async () => { if (confirm('Disconnect every phone and pause AOD? You will need to resume it on the PC.')) { await api('/api/panic', {method: 'POST'}).catch(() => {}); } };
  const loadAct = async () => {
    try {
      const a = await (await api('/api/activity')).json();
      $('actl').innerHTML = a.slice(0, 25).map(x => `<div><span class="n">${esc(x.text)}</span><span class="dim" style="font-size:12px">${new Date(x.ts * 1000).toLocaleString([], {dateStyle: 'short', timeStyle: 'short'})}</span></div>`).join('');
    } catch {}
  };
  document.querySelector('#nav [data-view="power"]').addEventListener('click', loadAct);

  // ---------- wake relay (Android app only)
  if (native && native.setRelay) {
    const w = document.createElement('div');
    w.innerHTML = '<h3>Wake from anywhere</h3><p class="dim" style="font-size:13px;margin:0 0 8px">Optional: address and key of the AOD wake relay running on an always-on device at home (see README).</p><input id="rlUrl" type="text" placeholder="http://100.x.y.z:8767" style="width:100%;margin-bottom:6px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:8px"><input id="rlKey" type="text" placeholder="Relay key" style="width:100%;margin-bottom:6px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:8px"><button id="rlSave">Save relay</button>';
    $('devs').previousElementSibling.before(w);
    $('rlUrl').value = native.relayUrl(); $('rlKey').value = native.relayKey();
    $('rlSave').onclick = () => { native.setRelay($('rlUrl').value.trim(), $('rlKey').value.trim()); toast('Relay saved'); };
  }
})();
