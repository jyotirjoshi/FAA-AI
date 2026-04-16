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
    citation.section_path ? citation.section_path : '',
    citation.source ? `Source: ${citation.source}` : '',
    citation.issue_date ? `Issue date: ${citation.issue_date}` : '',
    typeof citation.score === 'number' ? `Relevance: ${citation.score.toFixed(3)}` : '',
  ].filter(Boolean);

  modal.querySelector('.citation-modal-meta').textContent = metaParts.join(' • ');

  const excerpt = String(citation.excerpt || 'No excerpt available.');
  modal.querySelector('.citation-modal-excerpt').textContent = excerpt;

  const sourceLink = modal.querySelector('.citation-modal-source');
  sourceLink.href = citation.url || '#';
  sourceLink.textContent = citation.url ? 'Open source' : 'Source unavailable';
  sourceLink.toggleAttribute('aria-disabled', !citation.url);
  sourceLink.onclick = event => {
    if (!citation.url) {
      event.preventDefault();
    }
  };

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
    ? `<button class="citations-toggle">Sources (${safeCitations.length}) ▼</button>`
    : '';

  const citationCards = safeCitations.map(c => `
    <button class="citation-card citation-card-button" type="button" data-citation-id="${escapeHtml(c.id || '')}">
      <div class="citation-card-header">
        <strong>${escapeHtml(c.id || '')}</strong>
        <span>Flash card</span>
      </div>
      <div class="citation-card-title">${escapeHtml(c.title || '')}</div>
      <div class="citation-card-section">${escapeHtml(c.section_path || '')}</div>
      <div class="citation-card-excerpt">${escapeHtml((c.excerpt || '').slice(0, 240))}${(c.excerpt || '').length > 240 ? '…' : ''}</div>
      <div class="citation-score">Tap to view section card</div>
    </button>`).join('');

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

  const citationButtons = typingEl.querySelectorAll('.citation-card-button');
  citationButtons.forEach((button, index) => {
    button.addEventListener('click', () => {
      openCitationModal(safeCitations[index]);
    });
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
  if (event.key === 'Escape') {
    closeCitationModal();
  }
});

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

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 55000);

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

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
