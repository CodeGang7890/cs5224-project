// mock_whatsapp's page, in plain JavaScript: renders the chat like WhatsApp Web (bubbles grouped
// by sender, date chips, ticks), sends messages, photos and documents (the server calls the webhook,
// like Meta; for a file, only its name, type and size are sent and shown as a placeholder) and polls
// for the replies the fake Graph API receives.
(() => {
  const app = document.querySelector('.app');
  const waId = app.dataset.waId;
  const phoneNumberId = app.dataset.phoneNumberId;
  const pane = document.getElementById('messages');
  const status = document.getElementById('chat-status');
  const input = document.getElementById('message-input');

  // --- The messages --------------------------------------------------------------------------
  // From the server's rows (the page) and then the poll: {id, text, from_customer, status, error,
  // created_time, media}. media: a photo / document's {kind, filename, mime_type, size}, or null.
  const messages = [...pane.querySelectorAll('.row')].map((row) => ({
    id: Number(row.dataset.id),
    text: row.querySelector('.text').textContent,
    from_customer: row.dataset.out === '1',
    status: row.dataset.status,
    error: row.dataset.error,
    created_time: row.dataset.time,
    media: JSON.parse(row.dataset.media || 'null'),
  }));
  pane.querySelectorAll('.row').forEach((row) => row.remove());
  let waiting = 0; // messages sent that the business hasn't answered yet

  const SVG = 'http://www.w3.org/2000/svg';
  const TICKS = {
    sending: '<svg class="tick" viewBox="0 0 16 15"><circle cx="8" cy="7.5" r="5.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 4.6v3.2l2 1.3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    sent: '<svg class="tick" viewBox="0 0 16 11"><path d="M11.07.65l-6.4 7.9-2.3-2.4-.9.9 3.3 3.4 7.3-9z" fill="currentColor"/><path d="M15.07.65l-6.4 7.9-1-1-.9.9 2 2 7.3-9z" fill="currentColor"/></svg>',
    failed: '<svg class="tick failed" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M12 6.5v7M12 16.8v.2" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/></svg>',
  };

  const ICONS = {
    image: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="8.5" cy="9.5" r="1.8" fill="currentColor"/><path d="M4 18l5-5 3.5 3.5L15 14l5 4.5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
    document: '<svg viewBox="0 0 24 24"><path d="M6 3h8l5 5v13H6z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M14 3v5h5" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>',
  };

  function fileSize(bytes) {
    if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
    if (bytes >= 1024) return `${Math.round(bytes / 1024)} kB`;
    return `${bytes} B`;
  }
  // "PDF · 120 kB" (the file's extension, else its type).
  const fileInfo = (media) => [
    (media.filename.includes('.') ? media.filename.split('.').pop() : media.mime_type.split('/').pop()).toUpperCase(),
    fileSize(media.size),
  ].join(' · ');

  // The placeholder for a photo / document (no file is kept). An empty text without media is an
  // attachment whose details went with a restart of the mock.
  function attachment(media) {
    const el = document.createElement('div');
    const kind = media ? media.kind : 'document';
    el.className = `attachment ${kind}`;
    el.innerHTML = ICONS[kind];
    const label = document.createElement('span');
    label.className = 'attachment-text';
    const name = document.createElement('span');
    name.className = 'attachment-name';
    name.textContent = media ? media.filename : 'Attachment';
    const info = document.createElement('span');
    info.className = 'attachment-info';
    info.textContent = media ? `${kind === 'image' ? 'Photo' : 'Document'} · ${fileInfo(media)}` : 'details not kept after a restart';
    label.append(name, info);
    el.append(label);
    return el;
  }

  const clock = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }).toLowerCase() : '');
  const dayKey = (iso) => new Date(iso).toDateString();
  function dayLabel(iso) {
    const day = new Date(iso);
    const today = new Date();
    const yesterday = new Date(today.getTime() - 86400000);
    if (day.toDateString() === today.toDateString()) return 'Today';
    if (day.toDateString() === yesterday.toDateString()) return 'Yesterday';
    return day.toLocaleDateString([], { day: 'numeric', month: 'long', year: 'numeric' });
  }

  function chip(text, extra) {
    const el = document.createElement('div');
    el.className = `system-chip ${extra}`;
    el.textContent = text;
    return el;
  }

  function bubble(message, first, read) {
    const row = document.createElement('div');
    row.className = `msg ${message.from_customer ? 'out' : 'in'}${first ? ' first' : ''}`;
    row.dataset.id = message.id;
    const inner = document.createElement('div');
    inner.className = 'msg-inner';
    const box = document.createElement('div');
    box.className = 'bubble';
    const text = document.createElement('span');
    text.className = 'text';
    text.textContent = message.text;
    const spacer = document.createElement('span');
    spacer.className = 'spacer';
    const meta = document.createElement('span');
    meta.className = 'meta';
    meta.textContent = clock(message.created_time);
    if (message.from_customer) {
      meta.insertAdjacentHTML('beforeend', TICKS[message.status] || TICKS.sent);
      if (message.status === 'sent' && read) meta.querySelector('.tick').classList.add('read');
    }
    if (message.media || !message.text) box.append(attachment(message.media));
    box.append(text, spacer, meta);
    inner.append(box);
    if (message.status === 'failed') {
      const error = document.createElement('div');
      error.className = 'send-error';
      error.textContent = `Not sent: ${message.error || 'the webhook call failed'}`;
      inner.append(error);
    }
    row.append(inner);
    return row;
  }

  function render() {
    const atBottom = pane.scrollHeight - pane.scrollTop - pane.clientHeight < 80;
    pane.querySelectorAll('.msg, .date-chip').forEach((el) => el.remove());
    // A message you sent counts as "read" (blue ticks) once the business has replied after it.
    const lastReply = Math.max(0, ...messages.filter((m) => !m.from_customer).map((m) => m.id));
    let previous = null;
    for (const message of messages) {
      if (!previous || dayKey(previous.created_time) !== dayKey(message.created_time)) {
        pane.append(chip(dayLabel(message.created_time), 'date-chip'));
        previous = null;
      }
      const first = !previous || previous.from_customer !== message.from_customer;
      pane.append(bubble(message, first, message.id < lastReply));
      previous = message;
    }
    if (atBottom) pane.scrollTop = pane.scrollHeight;
  }

  function upsert(message) {
    const index = messages.findIndex((m) => m.id === message.id);
    if (index >= 0) messages[index] = message;
    else messages.push(message);
    messages.sort((a, b) => a.id - b.id);
    if (!message.from_customer) waiting = 0;
  }

  function showStatus() {
    status.textContent = waiting > 0 ? 'typing…' : status.dataset.idle;
    status.classList.toggle('typing', waiting > 0);
  }

  async function poll() {
    const after = Math.max(0, ...messages.map((m) => m.id));
    try {
      const response = await fetch(`/api/messages?${new URLSearchParams({ as: waId, chat: phoneNumberId, after })}`);
      if (!response.ok) return;
      const fresh = await response.json();
      if (!fresh.length) return;
      fresh.forEach(upsert);
      render();
      showStatus();
      refreshChats();
    } catch { /* the server restarting: try again next time */ }
  }

  // --- The chat list ---------------------------------------------------------------------------
  function showChatTimes() {
    document.querySelectorAll('.chat-time').forEach((el) => {
      const iso = el.dataset.time;
      if (!iso) { el.textContent = ''; return; }
      el.textContent = dayKey(iso) === new Date().toDateString() ? clock(iso) : new Date(iso).toLocaleDateString();
    });
  }

  async function refreshChats() {
    try {
      const response = await fetch(`/api/chats?${new URLSearchParams({ as: waId })}`);
      if (!response.ok) return;
      for (const chat of await response.json()) {
        const item = document.querySelector(`.chat-item[data-phone-number-id="${chat.phone_number_id}"]`);
        if (!item || !chat.last) continue;
        const preview = item.querySelector('.chat-preview');
        preview.innerHTML = '';
        if (chat.last.from_customer) {
          const tick = document.createElement('span');
          tick.className = `tick-mini ${chat.last.status}`;
          preview.append(tick);
        }
        const text = document.createElement('span');
        text.className = 'preview-text';
        text.textContent = chat.last.preview;
        preview.append(text);
        item.querySelector('.chat-time').dataset.time = chat.last.created_time;
      }
      showChatTimes();
    } catch { /* ignore */ }
  }

  document.getElementById('chat-search').addEventListener('input', (event) => {
    const query = event.target.value.trim().toLowerCase();
    document.querySelectorAll('.chat-item').forEach((item) => {
      item.classList.toggle('hidden', query !== '' && !item.dataset.search.includes(query));
    });
  });

  // --- Sending ---------------------------------------------------------------------------------
  const grow = () => { input.style.height = 'auto'; input.style.height = `${Math.min(input.scrollHeight, 120)}px`; };
  input.addEventListener('input', grow);
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      document.getElementById('composer').requestSubmit();
    }
  });

  // A photo / document to send with the next message (its text is the caption): only the metadata.
  // ＋ opens a menu: Photo (images) or Document (any file, sent as a document, as WhatsApp does).
  let pending = null;
  const attachButton = document.getElementById('attach-button');
  const attachMenu = document.getElementById('attach-menu');
  const attachmentBar = document.getElementById('attachment-bar');
  function setPending(file, kind) {
    pending = file ? {
      kind,
      filename: file.name,
      mime_type: file.type || 'application/octet-stream',
      size: file.size,
    } : null;
    attachmentBar.hidden = !pending;
    input.placeholder = pending ? 'Add a caption' : 'Type a message';
    if (pending) {
      document.getElementById('attachment-icon').innerHTML = ICONS[pending.kind];
      document.getElementById('attachment-name').textContent = pending.filename;
      document.getElementById('attachment-info').textContent = `${pending.kind === 'image' ? 'Photo' : 'Document'} · ${fileInfo(pending)}`;
    }
    input.focus();
  }
  function showMenu(open) {
    attachMenu.hidden = !open;
    attachButton.classList.toggle('open', open);
    attachButton.setAttribute('aria-expanded', String(open));
  }
  attachButton.addEventListener('click', () => showMenu(attachMenu.hidden));
  attachMenu.querySelectorAll('[data-input]').forEach((item) => item.addEventListener('click', () => {
    showMenu(false);
    document.getElementById(item.dataset.input).click();
  }));
  document.querySelectorAll('#photo-input, #document-input').forEach((picker) => picker.addEventListener('change', () => {
    if (picker.files[0]) setPending(picker.files[0], picker.dataset.kind);
    picker.value = ''; // picking the same file again still fires "change"
  }));
  document.addEventListener('click', (event) => { if (!event.target.closest('.attach')) showMenu(false); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') showMenu(false); });
  document.getElementById('attachment-remove').addEventListener('click', () => setPending(null));

  document.getElementById('composer').addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    const media = pending;
    if (!text && !media) return;
    input.value = '';
    grow();
    setPending(null);
    waiting += 1;
    showStatus();
    pane.scrollTop = pane.scrollHeight;
    try {
      const response = await fetch('/api/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wa_id: waId, phone_number_id: phoneNumberId, text, attachment: media }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || response.statusText);
      if (body.status === 'failed') waiting = Math.max(0, waiting - 1);
      upsert(body);
    } catch (error) {
      waiting = Math.max(0, waiting - 1);
      upsert({ id: Date.now(), text, from_customer: true, status: 'failed', error: error.message, created_time: new Date().toISOString(), media });
    }
    render();
    pane.scrollTop = pane.scrollHeight;
    showStatus();
    refreshChats();
    input.focus();
  });

  // --- Who you are -----------------------------------------------------------------------------
  document.getElementById('customer-select').addEventListener('change', (event) => {
    window.location.search = new URLSearchParams({ as: event.target.value, chat: phoneNumberId });
  });

  const customerDialog = document.getElementById('new-customer-dialog');
  const customerForm = document.getElementById('new-customer-form');
  const customerError = document.getElementById('new-customer-error');
  document.getElementById('new-customer').addEventListener('click', () => {
    customerForm.reset();
    customerError.textContent = '';
    customerDialog.showModal();
  });
  customerDialog.querySelector('[data-close]').addEventListener('click', () => customerDialog.close());
  customerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const data = new FormData(customerForm);
    const response = await fetch('/api/customers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: data.get('name').trim(), wa_id: data.get('wa_id').trim() || null }),
    });
    const body = await response.json();
    if (!response.ok) {
      customerError.textContent = typeof body.detail === 'string' ? body.detail : 'Check the name and number.';
      return;
    }
    window.location.search = new URLSearchParams({ as: body.wa_id, chat: phoneNumberId });
  });

  // --- About this mock -------------------------------------------------------------------------
  const infoDialog = document.getElementById('info-dialog');
  document.getElementById('info-button').addEventListener('click', () => infoDialog.showModal());
  document.getElementById('reset').addEventListener('click', async () => {
    if (!confirm('Delete every message in mock_whatsapp? (Chats in the project database stay.)')) return;
    await fetch('/api/reset', { method: 'POST' });
    window.location.reload();
  });

  render();
  pane.scrollTop = pane.scrollHeight;
  showChatTimes();
  setInterval(poll, 1500);
  setInterval(refreshChats, 4000);
})();
