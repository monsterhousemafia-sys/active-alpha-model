"""R3 KI Chat — Apple-inspirierte Mensch-Maschine-Schnittstelle (CSS + JS)."""

KI_CHAT_CSS = """
.ki-chat {{
  margin-bottom: 22px; border-radius: 22px; overflow: hidden;
  border: 1px solid rgba(94,92,230,.22);
  background: var(--card);
  box-shadow: 0 8px 32px rgba(0,0,0,.06), 0 1px 0 rgba(255,255,255,.6) inset;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}}
.ki-chat-header {{
  display: flex; justify-content: space-between; align-items: flex-start; gap: 14px;
  flex-wrap: wrap; padding: 18px 20px 12px;
  background: linear-gradient(180deg, rgba(94,92,230,.08) 0%, transparent 100%);
  border-bottom: 1px solid var(--line);
}}
.ki-chat-brand {{ display: flex; align-items: center; gap: 12px; }}
.ki-chat-avatar {{
  width: 42px; height: 42px; border-radius: 12px;
  background: linear-gradient(135deg, var(--accent), #30d5c8);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 14px; color: #fff; letter-spacing: -.02em;
  box-shadow: 0 4px 14px rgba(94,92,230,.35);
}}
.ki-chat-eyebrow {{ font-size: 11px; letter-spacing: .07em; text-transform: uppercase; color: var(--muted); }}
.ki-chat-title {{
  margin: 2px 0 4px; font-size: clamp(18px, 2.5vw, 22px); font-weight: 700;
  background: linear-gradient(90deg, var(--accent), var(--ok));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}}
.ki-chat-meta {{ margin: 0; font-size: 12px; color: var(--muted); display: flex; flex-wrap: wrap; gap: 6px; }}
.ki-chat-meta span {{ padding: 2px 8px; border-radius: 999px; background: rgba(127,127,127,.08); }}
.ki-chat-hint {{
  margin: 0; max-width: 300px; font-size: 12px; color: var(--muted); line-height: 1.45;
  padding: 10px 12px; border-radius: 14px; background: rgba(94,92,230,.07);
}}
.ki-chat-layout {{
  display: grid; grid-template-columns: 58px minmax(0, 1fr); min-height: 360px;
  border-top: 1px solid var(--line);
}}
.ki-rail {{
  display: flex; flex-direction: column; gap: 6px; padding: 10px 6px;
  border-right: 1px solid var(--line);
  background: rgba(127,127,127,.04);
}}
.ki-rail-btn {{
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  border: 1px solid transparent; background: transparent; border-radius: 12px;
  padding: 8px 4px; cursor: pointer; color: var(--muted); font-family: inherit;
  transition: background .15s, border-color .15s, color .15s;
}}
.ki-rail-btn:hover, .ki-rail-btn:focus-visible {{
  background: rgba(94,92,230,.08); border-color: rgba(94,92,230,.25); color: var(--accent);
  outline: none;
}}
.ki-rail-icon {{ font-size: 15px; line-height: 1; }}
.ki-rail-label {{ font-size: 9px; letter-spacing: .04em; text-transform: uppercase; }}
.ki-chat-main {{ display: flex; flex-direction: column; min-width: 0; }}
.ki-chat-toolbar {{ padding: 0 16px 10px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }}
.ki-power-bar {{ display: flex; flex-wrap: wrap; gap: 5px; }}
.ki-pmod {{
  font-size: 10px; padding: 4px 9px; border-radius: 999px; border: 1px solid var(--line);
  color: var(--muted); cursor: pointer; font-family: inherit;
  transition: border-color .15s, color .15s, background .15s;
}}
.ki-pmod:hover {{ border-color: var(--accent); color: var(--accent); }}
.ki-pmod.ok {{ border-color: rgba(52,199,89,.45); color: var(--ok); background: rgba(52,199,89,.06); }}
.ki-pmod.ok:hover {{ border-color: var(--accent); color: var(--accent); }}
.ki-quick {{ display: flex; flex-wrap: wrap; gap: 6px; margin-left: auto; }}
.ki-chip {{
  border: 1px solid var(--line); background: rgba(255,255,255,.5); border-radius: 999px;
  padding: 6px 12px; font-size: 11px; cursor: pointer; color: var(--muted); font-family: inherit;
  transition: border-color .15s, color .15s, transform .1s;
}}
.ki-chip:hover {{ border-color: var(--accent); color: var(--accent); transform: translateY(-1px); }}
.ki-chat-body {{
  display: flex; flex-direction: column; min-height: 320px; max-height: min(58vh, 520px);
  background: rgba(0,0,0,.02);
}}
@media (prefers-color-scheme: dark) {{ .ki-chat-body {{ background: rgba(255,255,255,.02); }} }}
.ki-transcript {{
  flex: 1; overflow-y: auto; overflow-x: hidden; padding: 16px 16px 8px;
  scroll-behavior: smooth;
}}
.ki-transcript:empty::before {{
  content: ''; display: block;
}}
.ki-welcome {{
  text-align: center; padding: 28px 20px 16px; color: var(--muted);
}}
.ki-welcome h3 {{ margin: 0 0 8px; font-size: 17px; color: var(--text); font-weight: 600; }}
.ki-welcome p {{ margin: 0; font-size: 13px; line-height: 1.5; max-width: 420px; margin-inline: auto; }}
.ki-row {{ display: flex; gap: 10px; margin-bottom: 14px; align-items: flex-end; animation: kiFadeIn .25s ease; }}
@keyframes kiFadeIn {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
.ki-row.user {{ flex-direction: row-reverse; }}
.ki-bubble-avatar {{
  width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 10px; font-weight: 700; color: #fff;
}}
.ki-row.user .ki-bubble-avatar {{ background: linear-gradient(135deg, #5e5ce6, #7d7aff); }}
.ki-row.bot .ki-bubble-avatar {{ background: linear-gradient(135deg, #30d5c8, #34c759); }}
.ki-bubble {{
  max-width: min(88%, 560px); padding: 11px 14px; border-radius: 18px;
  font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
}}
.ki-row.user .ki-bubble {{
  background: linear-gradient(135deg, var(--accent), #7d7aff);
  color: #fff; border-bottom-right-radius: 6px;
  box-shadow: 0 2px 12px rgba(94,92,230,.25);
}}
.ki-row.bot .ki-bubble {{
  background: var(--card); color: var(--text);
  border: 1px solid var(--line); border-bottom-left-radius: 6px;
  box-shadow: 0 1px 4px rgba(0,0,0,.04);
}}
.ki-bubble-meta {{ font-size: 10px; opacity: .65; margin-top: 6px; }}
.ki-bubble-att {{
  display: inline-flex; align-items: center; gap: 4px; margin-top: 6px; margin-right: 6px;
  font-size: 11px; padding: 3px 8px; border-radius: 999px;
  background: rgba(255,255,255,.18); color: inherit;
}}
.ki-row.bot .ki-bubble-att {{ background: rgba(94,92,230,.1); color: var(--accent); }}
.ki-route-tag {{
  display: inline-block; margin-top: 8px; font-size: 10px; padding: 3px 8px;
  border-radius: 999px; background: rgba(94,92,230,.1); color: var(--accent);
}}
.ki-typing {{ display: flex; gap: 5px; padding: 14px 16px; align-items: center; }}
.ki-typing-dots {{ display: flex; gap: 4px; padding: 10px 14px; border-radius: 18px; background: var(--card); border: 1px solid var(--line); }}
.ki-typing-dots span {{
  width: 7px; height: 7px; border-radius: 50%; background: var(--muted);
  animation: kiDot 1.2s infinite ease-in-out;
}}
.ki-typing-dots span:nth-child(2) {{ animation-delay: .15s; }}
.ki-typing-dots span:nth-child(3) {{ animation-delay: .3s; }}
@keyframes kiDot {{ 0%,80%,100% {{ transform: scale(.7); opacity: .4; }} 40% {{ transform: scale(1); opacity: 1; }} }}
.ki-attach-bar {{
  display: flex; flex-wrap: wrap; gap: 8px; padding: 0 16px 8px; min-height: 0;
}}
.ki-att-tag {{
  display: inline-flex; align-items: center; gap: 6px; font-size: 12px;
  padding: 6px 10px; border-radius: 12px;
  background: rgba(94,92,230,.1); color: var(--accent); border: 1px solid rgba(94,92,230,.2);
}}
.ki-att-tag button {{
  border: 0; background: transparent; cursor: pointer; font-size: 14px;
  line-height: 1; color: var(--muted); padding: 0 2px;
}}
.ki-att-tag.uploading {{ opacity: .6; }}
.ki-composer-wrap {{
  padding: 12px 14px 14px; border-top: 1px solid var(--line);
  background: rgba(255,255,255,.72);
  backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
}}
@media (prefers-color-scheme: dark) {{ .ki-composer-wrap {{ background: rgba(30,30,32,.85); }} }}
.ki-form {{ margin: 0; }}
.ki-composer {{
  display: flex; align-items: flex-end; gap: 8px;
  padding: 8px 10px 8px 12px; border-radius: 22px;
  border: 1px solid var(--line); background: var(--card);
  box-shadow: 0 2px 16px rgba(0,0,0,.05);
  transition: border-color .2s, box-shadow .2s;
}}
.ki-composer:focus-within {{
  border-color: rgba(94,92,230,.5);
  box-shadow: 0 0 0 3px rgba(94,92,230,.12), 0 2px 16px rgba(0,0,0,.05);
}}
.ki-composer.ki-dragover {{ border-color: var(--accent); background: rgba(94,92,230,.04); }}
.ki-composer textarea {{
  flex: 1; border: 0; background: transparent; resize: none; min-height: 24px; max-height: 120px;
  padding: 6px 0; font-family: inherit; font-size: 15px; line-height: 1.4; color: var(--text);
  outline: none;
}}
.ki-icon-btn {{
  width: 36px; height: 36px; border-radius: 50%; border: 0; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  background: transparent; color: var(--muted); font-size: 18px; flex-shrink: 0;
  transition: background .15s, color .15s, transform .1s;
}}
.ki-icon-btn:hover {{ background: rgba(127,127,127,.1); color: var(--text); }}
.ki-icon-btn:disabled {{ opacity: .4; cursor: not-allowed; }}
.ki-icon-btn.ki-mic-active {{
  background: rgba(255,59,48,.12); color: #ff3b30;
  animation: kiPulse 1.2s infinite;
}}
@keyframes kiPulse {{ 0%,100% {{ box-shadow: 0 0 0 0 rgba(255,59,48,.3); }} 50% {{ box-shadow: 0 0 0 8px rgba(255,59,48,0); }} }}
.ki-send-btn {{
  width: 36px; height: 36px; border-radius: 50%; border: 0; cursor: pointer;
  background: linear-gradient(135deg, var(--accent), #7d7aff); color: #fff;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  transition: transform .1s, opacity .15s;
}}
.ki-send-btn:hover:not(:disabled) {{ transform: scale(1.05); }}
.ki-send-btn:disabled {{ opacity: .45; cursor: wait; }}
.ki-file {{ display: none; }}
.ki-starters {{
  display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; justify-content: center;
}}
.ki-starter {{
  border: 1px solid var(--line); background: var(--card); border-radius: 999px;
  padding: 8px 14px; font-size: 12px; cursor: pointer; color: var(--text); font-family: inherit;
  transition: border-color .15s, background .15s;
}}
.ki-starter:hover {{ border-color: var(--accent); background: rgba(94,92,230,.06); }}
.ki-composer-hint {{ margin: 8px 4px 0; font-size: 11px; color: var(--muted); text-align: center; }}
"""

from analytics.r3_icons import R3_ICON_CSS as _KI_ICON_CSS, render_icons_js as _ki_icons_js  # noqa: E402

KI_CHAT_CSS = KI_CHAT_CSS + _KI_ICON_CSS

KI_CHAT_JS = r"""
(function initKiConsole() {
  const form = document.getElementById('ki-form');
  const input = document.getElementById('ki-input');
  const transcript = document.getElementById('ki-transcript');
  const sendBtn = document.getElementById('ki-send');
  const attachBar = document.getElementById('ki-attach-bar');
  const fileInput = document.getElementById('ki-file');
  const attachBtn = document.getElementById('ki-attach-btn');
  const micBtn = document.getElementById('ki-mic-btn');
  const composer = document.getElementById('ki-composer');
  const startersEl = document.getElementById('ki-starters');
  const routeHint = document.getElementById('ki-route-hint');
  const powerBar = document.getElementById('ki-power-bar');
  if (!form || !input || !transcript) return;

  let pendingAtt = [];
  let sending = false;
  let recognition = null;
  let micActive = false;

  function routeLabel(intent) {
    const m = {
      growth_refusal: 'Mandat', status: 'Status', help: 'Hilfe', trading: 'ML',
      prognose_slash: 'Prognose', web: 'Internet', advisor: 'Berater',
      pilot: 'Pilot', kernel: 'Kernel', chat: 'Chat', build: 'Bau'
    };
    return m[intent] || intent || '';
  }

  function setRoute(route) {
    if (routeHint && route) routeHint.textContent = route;
  }

  function moduleCmdMap() {
    if (!powerBar) return {};
    try {
      const raw = powerBar.getAttribute('data-module-cmds') || '{}';
      return JSON.parse(raw) || {};
    } catch (e) { return {}; }
  }

  function bindPowerModules() {
    if (!powerBar) return;
    const cmds = moduleCmdMap();
    powerBar.querySelectorAll('.ki-pmod[data-mod]').forEach(btn => {
      if (btn._kiBound) return;
      btn._kiBound = true;
      btn.addEventListener('click', () => {
        const cmd = btn.getAttribute('data-cmd') || '';
        if (!cmd) return;
        submitText(cmd, { autoSend: !cmd.endsWith(' ') });
      });
    });
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }

  function formatSize(n) {
    if (!n) return '';
    if (n < 1024) return n + ' B';
    return (n / 1024).toFixed(1) + ' KB';
  }

  function hideWelcome() {
    const w = transcript.querySelector('.ki-welcome');
    if (w) w.remove();
  }

  function appendBubble(role, text, opts) {
    opts = opts || {};
    hideWelcome();
    const row = document.createElement('div');
    row.className = 'ki-row ' + (role === 'user' ? 'user' : 'bot');
    const av = document.createElement('div');
    av.className = 'ki-bubble-avatar';
    av.textContent = role === 'user' ? 'Du' : 'R3';
    const bubble = document.createElement('div');
    bubble.className = 'ki-bubble';
    let html = esc(text || '');
    if (opts.attachments && opts.attachments.length) {
      html += opts.attachments.map(a => {
        const name = typeof a === 'string' ? a : (a.filename || a.id || a);
        return '<span class="ki-bubble-att">' + (typeof r3IconHtml === 'function' ? r3IconHtml('paperclip', 'r3-ico r3-ico--sm') : '') + esc(name) + '</span>';
      }).join('');
    }
    bubble.innerHTML = html;
    if (opts.route) {
      const tag = document.createElement('span');
      tag.className = 'ki-route-tag';
      tag.textContent = opts.route;
      bubble.appendChild(tag);
    }
    row.appendChild(av);
    row.appendChild(bubble);
    transcript.appendChild(row);
    transcript.scrollTop = transcript.scrollHeight;
  }

  function showTyping() {
    hideWelcome();
    const existing = document.getElementById('ki-typing-row');
    if (existing) return;
    const row = document.createElement('div');
    row.className = 'ki-typing';
    row.id = 'ki-typing-row';
    row.innerHTML = '<div class="ki-bubble-avatar">R3</div><div class="ki-typing-dots"><span></span><span></span><span></span></div>';
    transcript.appendChild(row);
    transcript.scrollTop = transcript.scrollHeight;
  }

  function hideTyping() {
    const el = document.getElementById('ki-typing-row');
    if (el) el.remove();
  }

  function renderAttBar() {
    if (!attachBar) return;
    attachBar.innerHTML = '';
    pendingAtt.forEach((a, idx) => {
      const span = document.createElement('span');
      span.className = 'ki-att-tag' + (a.uploading ? ' uploading' : '');
      const size = a.size_bytes ? ' · ' + formatSize(a.size_bytes) : '';
      span.innerHTML = (typeof r3IconHtml === 'function' ? r3IconHtml('paperclip', 'r3-ico r3-ico--sm') : '') + esc(a.filename || a.id) + size +
        ' <button type="button" aria-label="Entfernen" data-idx="' + idx + '">' + (typeof r3IconHtml === 'function' ? r3IconHtml('close', 'r3-ico r3-ico--sm') : '') + '</button>';
      attachBar.appendChild(span);
    });
    attachBar.querySelectorAll('button').forEach(btn => {
      btn.addEventListener('click', () => {
        pendingAtt.splice(parseInt(btn.getAttribute('data-idx'), 10), 1);
        renderAttBar();
      });
    });
  }

  async function uploadFile(file) {
    const placeholder = { id: 'tmp-' + Date.now(), filename: file.name, uploading: true };
    pendingAtt.push(placeholder);
    renderAttBar();
    try {
      const buf = await file.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let bin = '';
      const chunk = 8192;
      for (let i = 0; i < bytes.length; i += chunk) {
        bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
      }
      const b64 = btoa(bin);
      const r = await fetch('/api/ki/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, content_b64: b64, mime: file.type || 'text/plain' })
      });
      const d = await r.json();
      const idx = pendingAtt.indexOf(placeholder);
      if (idx >= 0) pendingAtt.splice(idx, 1);
      if (d.ok && d.id) {
        pendingAtt.push({ id: d.id, filename: d.filename || file.name, size_bytes: d.size_bytes });
      } else {
        appendBubble('bot', d.message_de || 'Upload fehlgeschlagen: ' + (file.name || ''));
      }
    } catch (e) {
      const idx = pendingAtt.indexOf(placeholder);
      if (idx >= 0) pendingAtt.splice(idx, 1);
      appendBubble('bot', 'Upload fehlgeschlagen — Verbindung prüfen.');
    }
    renderAttBar();
  }

  async function loadHistory() {
    try {
      const r = await fetch('/api/ki/history', { cache: 'no-store' });
      const d = await r.json();
      const msgs = Array.isArray(d.messages) ? d.messages : [];
      transcript.innerHTML = '';
      if (!msgs.length) showWelcome();
      msgs.forEach(m => {
        const atts = (m.attachment_names || m.attachments || []).map(a =>
          typeof a === 'string' ? { filename: a } : a
        );
        appendBubble(m.role === 'user' ? 'user' : 'bot', m.content || '', { attachments: atts });
      });
    } catch (e) {
      showWelcome();
    }
  }

  function showWelcome() {
    if (transcript.querySelector('.ki-welcome')) return;
    const div = document.createElement('div');
    div.className = 'ki-welcome';
    div.innerHTML = '<h3>R3 KI — lokaler Chat</h3><p>Hauptkanal: active-alpha-chat und dieses Cockpit. Slash-Befehle: /status, /geheimnis, /desktop. Kein Cursor-Konto nötig.</p>';
    transcript.appendChild(div);
  }

  async function loadStarters() {
    if (!startersEl) return;
    try {
      const r = await fetch('/api/ki/guidance', { cache: 'no-store' });
      const d = await r.json();
      const items = d.starters || [];
      startersEl.innerHTML = '';
      items.forEach(s => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'ki-starter';
        btn.textContent = s.label || s.message || '';
        btn.addEventListener('click', () => {
          const msg = s.message || '';
          input.value = msg;
          input.focus();
          autoGrow();
          if (msg.trim() && !msg.endsWith(' ')) submitText(msg, { voice: false });
        });
        startersEl.appendChild(btn);
      });
    } catch (e) {}
  }

  async function postChat(body) {
    const r = await fetch('/api/ki/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    return r.json();
  }

  async function submitText(text, opts) {
    opts = opts || {};
    const raw = String(text || '').trim();
    if (!raw && !pendingAtt.length && !opts.reset && !opts.import) return;
    if (sending) return;
    sending = true;
    const attIds = pendingAtt.filter(a => a.id && !String(a.id).startsWith('tmp-')).map(a => a.id);
    const attDisplay = pendingAtt.map(a => ({ filename: a.filename || a.id }));
    if (!opts.silentUser && (raw || pendingAtt.length)) {
      appendBubble('user', raw || '(Anhang)', { attachments: attDisplay });
    }
    input.value = '';
    input.style.height = 'auto';
    if (sendBtn) sendBtn.disabled = true;
    showTyping();
    try {
      let d;
      if (opts.import) {
        const ir = await fetch('/api/ki/import', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        d = await ir.json();
        hideTyping();
        appendBubble('bot', d.reply_de || d.headline_de || 'Archiv geladen.', { route: 'Archiv' });
        setRoute('Archiv');
        await loadHistory();
      } else if (opts.reset) {
        d = await postChat({ reset: true, message: '' });
        hideTyping();
        transcript.innerHTML = '';
        showWelcome();
        appendBubble('bot', d.reply_de || 'Neue Sitzung.', { route: 'Neu' });
        setRoute('Neu');
        pendingAtt = [];
        renderAttBar();
      } else if (opts.desktop) {
        hideTyping();
        window.location.hash = 'r3-desktop-shell';
        const target = document.getElementById('r3-desktop-shell');
        if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        appendBubble('bot', 'R3 System Desktop geöffnet — Spotlight: Ctrl+K', { route: 'Desktop' });
        setRoute('Desktop');
      } else {
        d = await postChat({ message: raw, attachment_ids: attIds, voice: !!opts.voice });
        hideTyping();
        const body = d.reply_de || d.message_de || '—';
        const route = d.route_de || routeLabel(d.intent) || '';
        appendBubble('bot', body, { route: route });
        setRoute(route || 'Auto-Route');
        pendingAtt = [];
        renderAttBar();
        if (d.reset) {
          transcript.innerHTML = '';
          showWelcome();
        }
        if (d.next_step_de) {
          const hint = document.getElementById('ki-next-hint');
          if (hint) hint.textContent = d.next_step_de;
        }
      }
      if (typeof refreshSystemStatus === 'function') refreshSystemStatus();
    } catch (err) {
      hideTyping();
      appendBubble('bot', 'Verbindung fehlgeschlagen — Hub auf :17890 prüfen.');
    } finally {
      sending = false;
      if (sendBtn) sendBtn.disabled = false;
      input.focus();
    }
  }

  async function sendMessage(voice) {
    const text = (input.value || '').trim();
    await submitText(text, { voice: !!voice, autoSend: true });
  }

  window.kiSubmit = submitText;

  function setupMic() {
    if (!micBtn) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      micBtn.title = 'Spracheingabe nicht unterstützt (Chrome/Edge)';
      micBtn.disabled = true;
      return;
    }
    recognition = new SR();
    recognition.lang = 'de-DE';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onstart = () => {
      micActive = true;
      micBtn.classList.add('ki-mic-active');
      micBtn.setAttribute('aria-pressed', 'true');
    };
    recognition.onend = () => {
      micActive = false;
      micBtn.classList.remove('ki-mic-active');
      micBtn.setAttribute('aria-pressed', 'false');
    };
    recognition.onerror = () => {
      micActive = false;
      micBtn.classList.remove('ki-mic-active');
    };
    recognition.onresult = (ev) => {
      const t = ev.results[0] && ev.results[0][0] ? ev.results[0][0].transcript : '';
      if (t) {
        input.value = (input.value ? input.value + ' ' : '') + t.trim();
        input.dispatchEvent(new Event('input'));
        sendMessage(true);
      }
    };
    micBtn.addEventListener('click', async () => {
      if (micActive) {
        recognition.stop();
        return;
      }
      try {
        const gr = await fetch('/api/ki/guidance?voice=1', { cache: 'no-store' });
        const gd = await gr.json();
        if (gd.reply_de && !transcript.querySelector('.ki-row')) {
          appendBubble('bot', gd.reply_de);
        }
      } catch (e) {}
      try { recognition.start(); } catch (e) {}
    });
  }

  function autoGrow() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  }

  function bindChips() {
    document.querySelectorAll('.ki-chip').forEach(chip => {
      if (chip._kiBound) return;
      chip._kiBound = true;
      chip.addEventListener('click', () => {
        const cmd = chip.getAttribute('data-cmd') || '';
        input.value = cmd;
        input.focus();
        autoGrow();
        const auto = chip.getAttribute('data-auto-send') !== 'false';
        if (auto && cmd.trim() && !cmd.endsWith(' ')) submitText(cmd, {});
      });
    });
  }

  function bindRail() {
    document.querySelectorAll('.ki-rail-btn').forEach(btn => {
      if (btn._kiBound) return;
      btn._kiBound = true;
      btn.addEventListener('click', () => {
        const action = btn.getAttribute('data-rail-action') || '';
        const cmd = btn.getAttribute('data-rail-cmd') || '';
        if (action === 'reset') submitText('', { reset: true });
        else if (action === 'import') submitText('', { import: true, silentUser: true });
        else if (action === 'desktop') submitText('', { desktop: true, silentUser: true });
        else if (cmd) submitText(cmd, {});
      });
    });
  }

  bindChips();
  bindRail();

  if (attachBtn && fileInput) {
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', async () => {
      const files = Array.from(fileInput.files || []);
      for (const f of files.slice(0, 4 - pendingAtt.length)) await uploadFile(f);
      fileInput.value = '';
    });
  }

  if (composer) {
    ['dragenter', 'dragover'].forEach(ev => {
      composer.addEventListener(ev, e => { e.preventDefault(); composer.classList.add('ki-dragover'); });
    });
    ['dragleave', 'drop'].forEach(ev => {
      composer.addEventListener(ev, e => { e.preventDefault(); composer.classList.remove('ki-dragover'); });
    });
    composer.addEventListener('drop', async e => {
      const files = Array.from(e.dataTransfer?.files || []);
      for (const f of files.slice(0, 4 - pendingAtt.length)) await uploadFile(f);
    });
  }

  form.addEventListener('submit', e => { e.preventDefault(); sendMessage(false); });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); }
  });
  input.addEventListener('input', autoGrow);

  window.kiBindPowerModules = bindPowerModules;
  loadHistory();
  loadStarters();
  setupMic();
  bindPowerModules();
})();
""" + _ki_icons_js()
