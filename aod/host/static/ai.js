/* AOD assistant tab: ask the PC for things in plain language. Loaded after extras.js. */
(() => {
  const v = $('v-ai');
  v.innerHTML = `<div class="vh" style="justify-content:space-between"><span style="display:flex;align-items:center;gap:10px"><img src="/logo.png" alt="">Assistant</span><button id="aiNew" style="min-height:34px;padding:2px 12px;font-size:13px">New chat</button></div>
    <div id="aiLog" style="flex:1;min-height:0;overflow-y:auto;padding:8px 14px;display:flex;flex-direction:column;gap:8px"></div>
    <div id="aiBar" style="display:flex;gap:8px;padding:8px 10px;border-top:1px solid var(--line);background:#0e0b16cc;align-items:center">
      <button id="aiMic" style="display:none;flex:none"></button>
      <input id="aiIn" type="text" placeholder="Ask your PC to do something…" enterkeyhint="send" autocomplete="off" style="flex:1;min-width:0;background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:12px;padding:11px 12px;font:inherit">
      <button id="aiGo" class="primary" style="flex:none"></button>
    </div>`;
  const log = $('aiLog'), inp = $('aiIn');
  let running = false;

  const setGo = () => { const b = $('aiGo'); b.dataset.ic = running ? 'stop' : 'send'; renderIcons(b.parentNode); b.style.background = running ? 'var(--bad)' : ''; };
  const mic = $('aiMic'); mic.dataset.ic = 'mic';
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if ((native && native.startVoice) || SR) mic.style.display = '';
  renderIcons(v); setGo();

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
    ['What’s on my screen?', 'Open Spotify', 'Find my latest download', 'Turn the volume down'].forEach(t => {
      const c = document.createElement('button'); c.textContent = t; c.style.cssText = 'min-height:36px;padding:4px 12px;font-size:13px';
      c.onclick = () => ask(t); chips.appendChild(c);
    });
    log.appendChild(chips);
  };
  const ask = t => {
    t = (t || inp.value).trim(); if (!t || running) return;
    if (!info || !info.ai) return welcome();
    inp.value = ''; if (log.querySelector('button')) log.innerHTML = '';
    bubble('me', text(t)); running = true; setGo(); send({t: 'ai', text: t});
  };
  $('aiGo').onclick = () => { if (running) { send({t: 'ai_stop'}); } else ask(); };
  inp.onkeydown = e => { if (e.key === 'Enter') ask(); };
  $('aiNew').onclick = () => { send({t: 'ai_reset'}); welcome(); };
  new MutationObserver(() => { if (v.classList.contains('active') && !log.children.length) welcome(); }).observe(v, {attributes: true, attributeFilter: ['class']});

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
          if (m.kind === 'text') bubble('ai', text(m.text));
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
