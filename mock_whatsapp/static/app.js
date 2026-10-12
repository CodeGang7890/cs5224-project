// mock_whatsapp's page, in plain JavaScript: renders the chat like WhatsApp Web (bubbles grouped
// by sender, date chips, ticks), sends messages (the server calls the webhook, like Meta) and
// polls for the replies the fake Graph API receives.
(() => {
  const app = document.querySelector('.app');
  const waId = app.dataset.waId;
  const phoneNumberId = app.dataset.phoneNumberId;
  const pane = document.getElementById('messages');
  const status = document.getElementById('chat-status');
  const input = document.getElementById('message-input');

  // --- The messages --------------------------------------------------------------------------
  // From the server's rows (the page) and then the poll: {id, text, from_customer, status, error, created_time}.
  const messages = [...pane.querySelectorAll('.row')].map((row) => ({
    id: Number(row.dataset.id),
    text: row.querySelector('.text').textContent,
    from_customer: row.dataset.out === '1',
    status: row.dataset.status,
    error: row.dataset.error,
    created_time: row.dataset.time,
  }));
  pane.querySelectorAll('.row').forEach((row) => row.remove());
  let waiting = 0; // messages sent that the business hasn't answered yet

  const SVG = 'http://www.w3.org/2000/svg';
  const TICKS = {
    sending: '<svg class="tick" viewBox="0 0 16 15"><circle cx="8" cy="7.5" r="5.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 4.6v3.2l2 1.3" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    sent: '<svg class="tick" viewBox="0 0 16 11"><path d="M11.07.65l-6.4 7.9-2.3-2.4-.9.9 3.3 3.4 7.3-9z" fill="currentColor"/><path d="M15.07.65l-6.4 7.9-1-1-.9.9 2 2 7.3-9z" fill="currentColor"/></svg>',
    failed: '<svg class="tick failed" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10" fill="currentColor"/><path d="M12 6.5v7M12 16.8v.2" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/></svg>',
  };

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
        text.textContent = chat.last.text;
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

  document.getElementById('composer').addEventListener('submit', async (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    grow();
    waiting += 1;
    showStatus();
    pane.scrollTop = pane.scrollHeight;
    try {
      const response = await fetch('/api/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ wa_id: waId, phone_number_id: phoneNumberId, text }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || response.statusText);
      if (body.status === 'failed') waiting = Math.max(0, waiting - 1);
      upsert(body);
    } catch (error) {
      waiting = Math.max(0, waiting - 1);
      upsert({ id: Date.now(), text, from_customer: true, status: 'failed', error: error.message, created_time: new Date().toISOString() });
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
