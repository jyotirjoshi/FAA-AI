// Configure marked
marked.use({ breaks: true, gfm: true });

// Escape user-provided strings before inserting as HTML
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// DOM refs
const thread        = document.getElementById('thread');
const chatArea      = document.getElementById('chatArea');
const emptyState    = document.getElementById('emptyState');
const questionInput = document.getElementById('questionInput');
const sendBtn       = document.getElementById('sendBtn');
const newChatBtn    = document.getElementById('newChatBtn');
const hamburger     = document.getElementById('hamburger');
const sidebar       = document.getElementById('sidebar');
const overlay       = document.getElementById('overlay');

let isLoading = false;

// ── Auto-resize textarea ──
questionInput.addEventListener('input', () => {
  questionInput.style.height = 'auto';
  questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + 'px';
});

// ── Mobile sidebar ──
hamburger.addEventListener('click', () => {
  sidebar.classList.toggle('open');
  overlay.classList.toggle('open');
});

overlay.addEventListener('click', () => {
  sidebar.classList.remove('open');
  overlay.classList.remove('open');
});

// ── New Chat ──
newChatBtn.addEventListener('click', () => {
  thread.innerHTML = '';
  emptyState.style.display = '';
  questionInput.value = '';
  questionInput.style.height = 'auto';
  sidebar.classList.remove('open');
  overlay.classList.remove('open');
});

// ── Suggestion chips ──
document.querySelectorAll('.suggestion-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    questionInput.value = chip.dataset.q;
    questionInput.style.height = 'auto';
    questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + 'px';
    send();
  });
});

// ── Send on Enter (Shift+Enter = newline) ──
questionInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

sendBtn.addEventListener('click', send);

// ── Helpers ──
function setLoading(loading) {
  isLoading = loading;
  sendBtn.disabled = loading;
  questionInput.disabled = loading;
}

function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

function appendUserMessage(text) {
  emptyState.style.display = 'none';
  const msg = document.createElement('div');
  msg.className = 'msg msg-user';
  msg.innerHTML = `<div class="bubble-user">${escapeHtml(text)}</div>`;
  thread.appendChild(msg);
  scrollToBottom();
}

function appendTypingIndicator() {
  const msg = document.createElement('div');
  msg.className = 'msg msg-assistant';
  msg.innerHTML = `
    <div class="bubble-assistant">
      <div class="typing-indicator">
        <span></span><span></span><span></span>
      </div>
    </div>`;
  thread.appendChild(msg);
  scrollToBottom();
  return msg;
}

function replaceTypingWithAnswer(typingEl, data) {
  const { answer, citations, confidence, grounded, error } = data;
  const pct = Math.round((confidence || 0) * 100);
  const safeCitations = Array.isArray(citations) ? citations : [];

  const groundedBadge = grounded
    ? `<span class="badge badge-grounded">✓ Grounded</span>`
    : `<span class="badge badge-ungrounded">Ungrounded</span>`;

  const confidenceBadge = `<span class="badge badge-confidence">${pct}% confidence</span>`;

  const citationsToggle = safeCitations.length > 0
    ? `<button class="citations-toggle">Sources (${safeCitations.length}) ▼</button>`
    : '';

  const citationCards = safeCitations.map(c => `
    <div class="citation-card">
      <strong>${escapeHtml(c.id || '')}</strong> ${escapeHtml(c.section_path || '')}<br>
      <a href="${escapeHtml(c.url || '#')}" target="_blank" rel="noopener">${escapeHtml(c.url || '')}</a>
      <div class="citation-score">Relevance: ${(c.score || 0).toFixed(3)}</div>
    </div>`).join('');

  const errorBanner = error
    ? `<div class="error-banner">⚠ ${escapeHtml(String(error))}</div>`
    : '';

  const renderedAnswer = DOMPurify.sanitize(marked.parse(answer || ''));

  typingEl.innerHTML = `
    <div class="bubble-assistant">
      ${renderedAnswer}
      ${errorBanner}
    </div>
    <div class="msg-meta">
      ${groundedBadge}
      ${confidenceBadge}
      ${citationsToggle}
    </div>
    ${safeCitations.length > 0 ? `<div class="citations-panel">${citationCards}</div>` : ''}
  `;

  // Wire up citations toggle
  const toggle = typingEl.querySelector('.citations-toggle');
  const panel  = typingEl.querySelector('.citations-panel');
  if (toggle && panel) {
    toggle.addEventListener('click', () => {
      const open = panel.classList.toggle('open');
      toggle.textContent = `Sources (${safeCitations.length}) ${open ? '▲' : '▼'}`;
    });
  }

  scrollToBottom();
}

function appendErrorMessage(text) {
  const msg = document.createElement('div');
  msg.className = 'msg msg-assistant';
  msg.innerHTML = `
    <div class="bubble-assistant">
      <div class="error-banner">⚠ ${escapeHtml(text)}</div>
    </div>`;
  thread.appendChild(msg);
  scrollToBottom();
}

// ── Main send function ──
async function send() {
  if (isLoading) return;

  const question = questionInput.value.trim();
  if (!question) {
    const wrap = questionInput.closest('.input-wrap');
    if (wrap) {
      wrap.classList.add('shake');
      wrap.addEventListener('animationend', () => wrap.classList.remove('shake'), { once: true });
    }
    return;
  }

  appendUserMessage(question);
  questionInput.value = '';
  questionInput.style.height = 'auto';
  setLoading(true);

  const typingEl = appendTypingIndicator();

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });

    let data;
    try {
      data = await res.json();
    } catch {
      data = { answer: 'Server returned a non-JSON response.', citations: [], confidence: 0, grounded: false };
    }

    if (!res.ok) {
      typingEl.remove();
      appendErrorMessage(`HTTP ${res.status}: ${data.answer || 'Server error.'}`);
    } else {
      replaceTypingWithAnswer(typingEl, data);
    }
  } catch {
    typingEl.remove();
    appendErrorMessage('Request failed. Check server logs.');
  } finally {
    setLoading(false);
  }
}
