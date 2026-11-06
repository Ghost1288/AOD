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
  #toast{position:fixed;left:50%;bottom:84px;transform:translateX(-50%);background:#151922f0;border:1px solid var(--line);color:var(--fg);padding:10px 16px;border-radius:12px;z-index:90;display:none;max-width:86%;text-align:center}
  #banner{position:fixed;top:10px;left:10px;right:10px;z-index:95;background:#151922;border:1px solid var(--accent);border-radius:14px;padding:12px 14px;display:none;box-shadow:0 6px 24px #000a}
  #banner b{display:block;color:var(--accent)}
  .row2{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}
  .row2 small{color:var(--dim);display:block}`;
  document.head.appendChild(css);

  const toastEl = Object.assign(document.createElement('div'), {id: 'toast'});
  const banner = Object.assign(document.createElement('div'), {id: 'banner'});
  document.body.append(toastEl, banner);
  let tt, bt;
  const toast = m => { toastEl.textContent = m; toastEl.style.display = 'block'; clearTimeout(tt); tt = setTimeout(() => toastEl.style.display = 'none', 3200); };
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
      <div style="display:flex;gap:6px"><button id="scEdit" style="min-height:34px;padding:2px 12px">Edit</button><button id="scNew" class="primary" style="min-height:34px;padding:2px 12px">+ New</button></div></div>
    <div class="grid" id="scGrid"></div><p class="dim" id="scEmpty" style="display:none">No shortcuts yet. Tap <b>+ New</b> to make a button for a key combo, some text, an app, a website or a command.</p>
    <h3>Open an app</h3><input type="search" id="appQ" placeholder="Search apps on your PC…"><div class="list" id="appList" style="margin-top:6px"></div>
    <h3>Run a command</h3><div style="display:flex;gap:8px"><input type="text" id="cmdIn" placeholder="e.g. ipconfig  or  shutdown /a"><button id="cmdRun" class="primary">Run</button></div>
    <pre id="cmdOut"></pre>`;

  let shortcuts = [], editMode = false;
  const KEYALIAS = {windows: 'win', control: 'ctrl', return: 'enter', escape: 'esc', del: 'delete', pgup: 'pageup', pgdn: 'pagedown'};
  async function loadShortcuts() { try { shortcuts = await (await api('/api/shortcuts')).json(); } catch { shortcuts = []; } renderShortcuts(); }
  function renderShortcuts() {
    $('scGrid').innerHTML = shortcuts.map(s => `<button class="sc${editMode ? ' edit' : ''}" data-id="${esc(s.id)}"><span class="ic">${esc(s.icon || '⚡')}</span>${esc(s.label)}</button>`).join('');
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
    <select id="edType"><option value="keys">Press keys</option><option value="text">Type text</option><option value="launch">Open app / file / website</option><option value="run">Run a command (shows output)</option><option value="power">Power action</option></select>
    <input id="edVal"><select id="edPower" style="display:none"><option value="lock">Lock</option><option value="sleep">Sleep</option><option value="restart">Restart</option><option value="shutdown">Shut down</option><option value="logoff">Sign out</option></select>
    <small class="dim" id="edHelp"></small>
    <div style="display:flex;gap:8px"><button id="edDel" class="bad" style="display:none">Delete</button><span style="flex:1"></span><button id="edCancel">Cancel</button><button id="edSave" class="primary">Save</button></div></div>`;
  document.body.appendChild(ed);
  const HELP = {keys: 'Example: ctrl+shift+m   or   win+d   or   alt+f4', text: 'This text is typed on the PC wherever the cursor is.', launch: 'A program path, a website (https://…), a folder, or a command.', run: 'Runs on the PC and shows the result here.', power: ''};
  let editing = null;
  function syncType() { const t = $('edType').value; $('edVal').style.display = t === 'power' ? 'none' : 'block'; $('edPower').style.display = t === 'power' ? 'block' : 'none'; $('edHelp').textContent = HELP[t]; $('edVal').placeholder = HELP[t].split(':')[0]; }
  $('edType').onchange = syncType;
  function openEditor(s) {
    editing = s; $('edT').textContent = s ? 'Edit shortcut' : 'New shortcut';
    $('edIcon').value = s ? s.icon : ''; $('edLabel').value = s ? s.label : ''; $('edType').value = s ? s.type : 'keys';
    $('edVal').value = s && s.type !== 'power' ? s.value : ''; if (s && s.type === 'power') $('edPower').value = s.value;
    $('edDel').style.display = s ? 'block' : 'none'; syncType(); ed.style.display = 'flex';
  }
  $('edCancel').onclick = () => ed.style.display = 'none';
  $('edSave').onclick = async () => {
    const type = $('edType').value, value = type === 'power' ? $('edPower').value : $('edVal').value.trim(), label = $('edLabel').value.trim() || value.slice(0, 14);
    if (!value) { toast('Enter what it should do'); return; }
    const item = {id: editing ? editing.id : Math.random().toString(36).slice(2, 10), label, icon: $('edIcon').value.trim() || '⚡', type, value};
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
  const recUi = on => { $('bRec').textContent = on ? '⏹' : '⏺'; $('bRec').style.color = on ? 'var(--bad)' : ''; $('bRec').classList.toggle('on', on); };
  $('bRec').onclick = async () => {
    const on = $('bRec').textContent === '⏺';
    if (on && jpegActive) return toast('Recording needs WebRTC video (Settings > Video)');
    const r = await post('/api/record', {on});
    recUi(r.on); toast(r.on ? 'Recording on the PC…' : 'Saving recording to Videos\\AOD on the PC');
  };
  api('/api/record').then(r => r.json()).then(r => recUi(r.on)).catch(() => {});
})();
