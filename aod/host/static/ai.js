/* AOD assistant tab: ask the PC for things in plain language. Loaded after extras.js. */
(() => {
  const v = $('v-ai');
  v.innerHTML = `<div class="vh" style="justify-content:space-between"><span style="display:flex;align-items:center;gap:10px"><img src="/logo.png" alt="">Assistant</span><span style="display:flex;gap:6px"><button id="aiSpk" style="min-height:34px;padding:2px 10px"></button><button id="aiWatchB" style="min-height:34px;padding:2px 12px;font-size:13px">Watching</button><button id="aiNew" style="min-height:34px;padding:2px 12px;font-size:13px">New</button></span></div>
    <div id="aiLog" style="flex:1;min-height:0;overflow-y:auto;padding:8px 14px;display:flex;flex-direction:column;gap:8px"></div>
    <div id="aiBar" style="display:flex;gap:8px;padding:8px 10px;border-top:1px solid var(--line);background:#0e0b16cc;align-items:center">
      <button id="aiLook" title="Ask about what is on the screen" style="flex:none"></button>
      <button id="aiMic" style="display:none;flex:none"></button>
      <input id="aiIn" type="text" placeholder="Ask your PC to do something…" enterkeyhint="send" autocomplete="off" style="flex:1;min-width:0;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:12px;padding:11px 12px;font:inherit">
      <button id="aiGo" class="primary" style="flex:none"></button>
    </div>
    <div id="aiWatch" style="display:none;position:absolute;inset:0;background:var(--bg);z-index:5;flex-direction:column"></div>`;
  v.style.position = 'relative';
  const log = $('aiLog'), inp = $('aiIn');
  let running = false, look = false, speakOn = store.get('aod_speak') === '1';
  const speakTxt = t => {
    t = t.replace(/https?:\/\/\S+/g, 'link').replace(/[*_`#>]/g, '');
    if (native && native.speak) return native.speak(t);
    if (window.speechSynthesis) { speechSynthesis.cancel(); speechSynthesis.speak(new SpeechSynthesisUtterance(t)); }
  };
  const stopSpeak = () => { try { native && native.stopSpeak && native.stopSpeak(); window.speechSynthesis && speechSynthesis.cancel(); } catch {} };
  const setSpk = () => { const b = $('aiSpk'); b.dataset.ic = speakOn ? 'snd' : 'muted'; b.classList.toggle('on', speakOn); renderIcons(b.parentNode); };
  const setLook = () => { const b = $('aiLook'); b.dataset.ic = 'screen'; b.classList.toggle('on', look); renderIcons(b.parentNode); };

  const setGo = () => { const b = $('aiGo'); b.dataset.ic = running ? 'stop' : 'send'; renderIcons(b.parentNode); b.style.background = running ? 'var(--bad)' : ''; };
  const mic = $('aiMic'); mic.dataset.ic = 'mic';
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if ((native && native.startVoice) || SR) mic.style.display = '';
  renderIcons(v); setGo(); setSpk(); setLook();
  $('aiSpk').onclick = () => { speakOn = !speakOn; store.set('aod_speak', speakOn ? '1' : '0'); if (!speakOn) stopSpeak(); setSpk(); toast(speakOn ? 'Replies will be read aloud' : 'Spoken replies off'); };
  $('aiLook').onclick = () => { look = !look; setLook(); toast(look ? 'Screen mode: I\'ll look at your screen and answer, without touching anything' : 'Screen mode off'); };

  const bubble = (cls, html) => {
    const d = document.createElement('div'); d.innerHTML = html;
    d.style.cssText = {
      me: 'align-self:flex-end;background:linear-gradient(135deg,#9d4edd,#6d28d9);color:#fff;border-radius:16px 16px 4px 16px;padding:9px 13px;max-width:85%',
      ai: 'align-self:flex-start;background:#16111f;border:1px solid var(--line);border-radius:16px 16px 16px 4px;padding:9px 13px;max-width:90%',
      tool: 'align-self:flex-start;color:var(--dim);font-size:13px;padding:0 6px',
      err: 'align-self:flex-start;background:#f8717122;border:1px solid var(--bad);color:var(--bad);border-radius:12px;padding:9px 13px;max-width:90%',
    }[cls] + ';word-break:break-word';
    log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
  };
  const text = s => esc(s).replace(/\n/g, '<br>');
  const welcome = () => {
    log.innerHTML = '';
    if (!info || !info.ai) {
      bubble('ai', 'The assistant needs an API key. Open the AOD dashboard on your PC, find <b>AI assistant</b>, paste your Anthropic key and press Save.'); return;
    }
    bubble('ai', 'Hi! Tell me what to do on your PC, by typing or tapping the mic.');
    const chips = document.createElement('div'); chips.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin-top:4px';
    ['What’s on my screen?', 'Open Spotify', 'Find the best-reviewed pizza near me', 'Keep an eye on a page for me', 'Turn the volume down'].forEach(t => {
      const c = document.createElement('button'); c.textContent = t; c.style.cssText = 'min-height:36px;padding:4px 12px;font-size:13px';
      c.onclick = () => ask(t); chips.appendChild(c);
    });
    log.appendChild(chips);
  };
  const ask = t => {
    t = (t || inp.value).trim(); if (!t || running) return;
    if (!info || !info.ai) return welcome();
    inp.value = ''; if (log.querySelector('button')) log.innerHTML = '';
    bubble('me', text(t)); running = true; setGo(); stopSpeak(); send({t: 'ai', text: t, mode: look ? 'look' : undefined, speak: speakOn});
  };
  $('aiGo').onclick = () => { if (running) { send({t: 'ai_stop'}); } else ask(); };
  inp.onkeydown = e => { if (e.key === 'Enter') ask(); };
  $('aiNew').onclick = () => { send({t: 'ai_reset'}); stopSpeak(); welcome(); };
  new MutationObserver(() => { if (v.classList.contains('active') && !log.children.length) welcome(); }).observe(v, {attributes: true, attributeFilter: ['class']});

  // ---- watched pages
  const wp = $('aiWatch');
  const ago = s => { if (!s) return 'never'; const m = Math.round((Date.now() / 1000 - s) / 60); return m < 1 ? 'just now' : m < 90 ? m + ' min ago' : Math.round(m / 60) + ' h ago'; };
  async function loadWatch() {
    let list = []; try { list = await (await api('/api/watches')).json(); } catch {}
    wp.innerHTML = `<div class="vh" style="justify-content:space-between"><span>Watching</span><button id="wBack" style="min-height:34px;padding:2px 12px">Back</button></div>
      <div style="flex:1;overflow-y:auto;padding:4px 14px 10px">${list.length ? list.map(w => `<div style="background:#16111f;border:1px solid var(--line);border-radius:14px;padding:10px 12px;margin-bottom:8px">
        <b>${esc(w.label)}</b><div class="dim" style="font-size:12px;word-break:break-all">${esc(w.url)}</div>
        ${w.question ? `<div style="font-size:13px;margin-top:4px">Looking for: ${esc(w.question)}</div>` : ''}
        <div class="dim" style="font-size:12px;margin:4px 0">Every ${w.every} min · checked ${ago(w.last_check)} · ${esc(w.status || '')}</div>
        <div style="display:flex;gap:8px"><button data-chk="${w.id}" style="min-height:34px;padding:2px 12px">Check now</button><button class="bad" data-del="${w.id}" style="min-height:34px;padding:2px 12px">Stop</button></div></div>`).join('') : '<p class="dim">Not watching anything yet. Add a page below, or ask the assistant: “keep an eye on this page and tell me if the price drops under £50”.</p>'}
        <h3 style="margin:16px 0 6px">Add a page</h3>
        <input id="wUrl" type="url" placeholder="https://…" style="width:100%;margin-bottom:6px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:10px">
        <input id="wQ" type="text" placeholder="Only tell me if… (optional, e.g. price under £50)" style="width:100%;margin-bottom:6px;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:10px">
        <div style="display:flex;gap:8px;align-items:center"><select id="wEvery" style="background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:10px"><option value="15">every 15 min</option><option value="60" selected>every hour</option><option value="360">every 6 hours</option><option value="1440">every day</option></select><button class="primary" id="wAdd" style="flex:1">Watch it</button></div>
        <p class="dim" style="font-size:12px">Works for pages that show their content without logging in. Alerts arrive as phone notifications.</p></div>`;
    $('wBack').onclick = () => { wp.style.display = 'none'; };
    wp.onclick = async e => {
      const c = e.target.closest('[data-chk]'), d = e.target.closest('[data-del]');
      if (c) { c.textContent = 'Checking…'; const r = await (await api('/api/watches/check', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({id: c.dataset.chk})})).json(); toast(r.status); loadWatch(); }
      if (d && confirm('Stop watching this page?')) { await api('/api/watches/delete', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({id: d.dataset.del})}); loadWatch(); }
    };
    $('wAdd').onclick = async () => {
      const url = $('wUrl').value.trim(); if (!url) return;
      $('wAdd').textContent = 'Adding…';
      const r = await api('/api/watches', {method: 'POST', headers: {'content-type': 'application/json'}, body: JSON.stringify({url, question: $('wQ').value.trim(), every: +$('wEvery').value})});
      const j = await r.json(); if (!r.ok) toast(j.error || 'Could not add that page'); else toast('Watching ' + j.label);
      loadWatch();
    };
  }
  $('aiWatchB').onclick = () => { wp.style.display = 'flex'; loadWatch(); };

  // voice: Android's recognizer through the app, or the browser's own
  window.onVoice = t => { if (t) { inp.value = t; ask(); } };
  mic.onclick = () => {
    if (native && native.startVoice) return native.startVoice();
    const r = new SR(); r.lang = navigator.language || 'en-GB'; r.onresult = e => window.onVoice(e.results[0][0].transcript); r.start();
  };

  const prev = onMsg;
  onMsg = async ev => {
    if (typeof ev.data === 'string' && ev.data.includes('"t":"ai"')) {
      try {
        const m = JSON.parse(ev.data);
        if (m.t === 'ai') {
          if (m.kind === 'text') { bubble('ai', text(m.text)); if (speakOn) speakTxt(m.text); }
          else if (m.kind === 'tool') bubble('tool', '• ' + esc(m.text));
          else if (m.kind === 'error') bubble('err', text(m.text));
          else if (m.kind === 'done') { running = false; setGo(); if (tab !== 'ai') toast('Assistant finished'); }
          else if (m.kind === 'confirm') {
            if (tab !== 'ai') document.querySelector('#nav [data-view="ai"]').click();
            try { navigator.vibrate && navigator.vibrate([60, 40, 60]); } catch {}
            const d = bubble('ai', `<b>Allow this?</b><div style="margin:6px 0;word-break:break-all;font-family:monospace;font-size:13px">${esc(m.text)}</div><div style="display:flex;gap:8px"><button class="primary" data-a="1" style="flex:1">Allow</button><button data-a="0" style="flex:1">Deny</button></div>`);
            d.style.border = '1px solid var(--accent)';
            d.onclick = e => { const b = e.target.closest('[data-a]'); if (!b) return; send({t: 'ai_ok', id: m.id, ok: b.dataset.a === '1'}); d.querySelector('div:last-child').outerHTML = `<div class="dim">${b.dataset.a === '1' ? 'Allowed' : 'Denied'}</div>`; };
          }
          return;
        }
      } catch {}
    }
    return prev(ev);
  };
})();
