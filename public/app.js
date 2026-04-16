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

// ── Session management ──
let currentSessionId = localStorage.getItem('airwise_session_id') || null;

async function ensureSession() {
  if (currentSessionId) return currentSessionId;
  try {
    const res = await fetch('/sessions', { method: 'POST' });
    const data = await res.json();
    currentSessionId = data.session_id;
    localStorage.setItem('airwise_session_id', currentSessionId);
  } catch {
    currentSessionId = null;
  }
  return currentSessionId;
}

function startNewSession() {
  currentSessionId = null;
  localStorage.removeItem('airwise_session_id');
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

let citationModal = null;
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
  startNewSession();
  thread.innerHTML = '';
  emptyState.style.display = '';
  questionInput.value = '';
  questionInput.style.height = 'auto';
  sidebar.classList.remove('open');
  overlay.classList.remove('open');
});

// ── Send on Enter (Shift+Enter = newline) ──
questionInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});

sendBtn.addEventListener('click', send);

// ── Suggestion chips ──
document.querySelectorAll('.suggestion-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    questionInput.value = chip.dataset.q;
    questionInput.style.height = 'auto';
    questionInput.style.height = Math.min(questionInput.scrollHeight, 160) + 'px';
    send();
  });
});

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

function ensureCitationModal() {
  if (citationModal) return citationModal;

  citationModal = document.createElement('div');
  citationModal.className = 'citation-modal';
  citationModal.innerHTML = `
    <div class="citation-modal-backdrop" data-close="true"></div>
    <div class="citation-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="citationModalTitle">
      <button class="citation-modal-close" type="button" aria-label="Close citation card">×</button>
      <div class="citation-modal-body">
        <div class="citation-modal-kicker">Citation Flash Card</div>
        <h3 id="citationModalTitle"></h3>
        <div class="citation-modal-meta"></div>
        <div class="citation-modal-excerpt"></div>
        <div class="citation-modal-actions">
          <a class="citation-modal-source" target="_blank" rel="noopener">Open source</a>
        </div>
      </div>
    </div>`;

  document.body.appendChild(citationModal);

  citationModal.addEventListener('click', event => {
    if (event.target.matches('[data-close="true"], .citation-modal-close')) {
      closeCitationModal();
    }
  });

  return citationModal;
}

function openCitationModal(citation) {
  const modal = ensureCitationModal();
  modal.querySelector('#citationModalTitle').textContent = `${citation.id || 'Citation'} · ${citation.title || 'Section reference'}`;

  const metaParts = [
    citation.section_path ? `<div>📍 <strong>Section:</strong> ${escapeHtml(citation.section_path)}</div>` : '',
    citation.source ? `<div>📄 <strong>Source:</strong> ${escapeHtml(citation.source)}</div>` : '',
    citation.issue_date ? `<div>📅 <strong>Issue Date:</strong> ${escapeHtml(citation.issue_date)}</div>` : '',
    typeof citation.score === 'number' ? `<div>⭐ <strong>Relevance:</strong> ${(citation.score * 100).toFixed(0)}% match</div>` : '',
  ].filter(Boolean);

  modal.querySelector('.citation-modal-meta').innerHTML = metaParts.join('');

  const excerpt = String(citation.excerpt || 'No excerpt available.');
  modal.querySelector('.citation-modal-excerpt').textContent = excerpt;

  const sourceLink = modal.querySelector('.citation-modal-source');
  sourceLink.href = citation.url || '#';
  sourceLink.textContent = citation.url ? '🔗 Open Source Document' : 'Source unavailable';
  sourceLink.toggleAttribute('aria-disabled', !citation.url);
  sourceLink.onclick = event => { if (!citation.url) event.preventDefault(); };

  modal.classList.add('open');
  document.body.classList.add('modal-open');
}

function closeCitationModal() {
  if (!citationModal) return;
  citationModal.classList.remove('open');
  document.body.classList.remove('modal-open');
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
    ? `<button class="citations-toggle">📚 Sources (${safeCitations.length}) ▼</button>`
    : '';

  const citationCards = safeCitations.map((c, idx) => {
    const excerptPreview = (c.excerpt || '').slice(0, 280);
    const relevance = typeof c.score === 'number' ? (c.score * 100).toFixed(0) : 'N/A';
    return `
    <button class="citation-card citation-card-button" type="button" data-citation-id="${escapeHtml(c.id || '')}">
      <div class="citation-card">
        <div class="citation-card-header">
          <strong>[${idx + 1}] ${escapeHtml(c.id || 'REF')}</strong>
          <span>📋 Source</span>
        </div>
        <div class="citation-card-title">${escapeHtml(c.title || 'Untitled section')}</div>
        ${c.section_path ? `<div class="citation-card-section">§ ${escapeHtml(c.section_path)}</div>` : ''}
        <div class="citation-card-excerpt">${escapeHtml(excerptPreview)}${excerptPreview.length >= 280 ? '…' : ''}</div>
        <div class="citation-score">📌 ${relevance}% match · Click to expand</div>
      </div>
    </button>`;
  }).join('');

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

  const toggle = typingEl.querySelector('.citations-toggle');
  const panel  = typingEl.querySelector('.citations-panel');
  if (toggle && panel) {
    toggle.addEventListener('click', () => {
      const open = panel.classList.toggle('open');
      toggle.textContent = `Sources (${safeCitations.length}) ${open ? '▲' : '▼'}`;
    });
  }

  typingEl.querySelectorAll('.citation-card-button').forEach((button, index) => {
    button.addEventListener('click', () => openCitationModal(safeCitations[index]));
  });

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

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeCitationModal();
});

// ── Load previous session on page load ──
async function loadHistory() {
  if (!currentSessionId) return;
  try {
    const res = await fetch(`/sessions/${currentSessionId}/history`);
    if (!res.ok) { startNewSession(); return; }
    const data = await res.json();
    const messages = data.messages || [];
    if (messages.length === 0) return;

    emptyState.style.display = 'none';
    for (let i = 0; i < messages.length; i++) {
      const m = messages[i];
      if (m.role === 'user') {
        appendUserMessage(m.content);
      } else if (m.role === 'assistant') {
        const el = document.createElement('div');
        el.className = 'msg msg-assistant';
        thread.appendChild(el);
        replaceTypingWithAnswer(el, {
          answer: m.content,
          citations: m.citations || [],
          confidence: m.confidence || 0,
          grounded: true,
          error: null,
        });
      }
    }
    scrollToBottom();
  } catch {
    startNewSession();
  }
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
  const sessionId = await ensureSession();

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 55000);

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: sessionId }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    let data;
    try {
      data = await res.json();
    } catch {
      data = { answer: 'Server returned a non-JSON response.', citations: [], confidence: 0, grounded: false };
    }

    // Update session id from server response (in case server created a new one)
    if (data.session_id) {
      currentSessionId = data.session_id;
      localStorage.setItem('airwise_session_id', currentSessionId);
    }

    if (!res.ok) {
      typingEl.remove();
      appendErrorMessage(`HTTP ${res.status}: ${data.answer || 'Server error.'}`);
    } else {
      replaceTypingWithAnswer(typingEl, data);
    }
  } catch (err) {
    clearTimeout(timeoutId);
    typingEl.remove();
    if (err.name === 'AbortError') {
      appendErrorMessage('The request timed out — the model is taking too long. Please try again.');
    } else {
      appendErrorMessage('Request failed. Please try again.');
    }
  } finally {
    setLoading(false);
  }
}

// Load history on startup
loadHistory();
