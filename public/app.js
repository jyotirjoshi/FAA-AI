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

// Strip XML/HTML tags and decode entities to get plain readable text
function cleanText(raw) {
  return String(raw || '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function formatIssueDate(raw) {
  const text = cleanText(raw);
  if (!text) return '';
  const dt = new Date(text);
  if (Number.isNaN(dt.getTime())) return text;
  return dt.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
}

function isXmlLikeUrl(raw) {
  const url = cleanText(raw).toLowerCase();
  return Boolean(url) && (url.endsWith('.xml') || url.includes('.xml?') || url.includes('/full/'));
}

function preferredCitationUrl(citation) {
  const candidate = cleanText(citation.url || '');
  const sourceUrl = cleanText(citation.source_url || '');
  const pageUrl = cleanText(citation.page_url || '');

  if (candidate.startsWith('http') && !isXmlLikeUrl(candidate)) return candidate;
  if (sourceUrl.startsWith('http')) return sourceUrl;
  if (pageUrl.startsWith('http') && !isXmlLikeUrl(pageUrl)) return pageUrl;
  return '';
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
      <button class="citation-modal-close" type="button" aria-label="Close">×</button>
      <div class="citation-modal-header">
        <div class="citation-modal-kicker">Source Reference</div>
        <div class="citation-modal-ref-id"></div>
        <h3 id="citationModalTitle"></h3>
      </div>
      <div class="citation-modal-body">
        <div class="citation-modal-meta"></div>
        <div class="citation-excerpt-label">Regulation Text</div>
        <div class="citation-modal-excerpt"></div>
        <div class="citation-modal-actions">
          <a class="citation-modal-source" target="_blank" rel="noopener">Open Source Document</a>
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

  const refIdEl = modal.querySelector('.citation-modal-ref-id');
  refIdEl.textContent = citation.id || '';

  modal.querySelector('#citationModalTitle').textContent = citation.title || 'Section Reference';

  const citationUrl = preferredCitationUrl(citation);
  const issueDate = formatIssueDate(citation.issue_date);
  const metaRows = [
    citation.section_path ? ['Section',    cleanText(citation.section_path)] : null,
    citation.source       ? ['Source',     cleanText(citation.source)]       : null,
    citation.source_host  ? ['Authority',  cleanText(citation.source_host)]  : null,
    issueDate             ? ['Issue Date', issueDate]                        : null,
    typeof citation.score === 'number'
      ? ['Relevance', `${(citation.score * 100).toFixed(0)}% match`]
      : null,
    citationUrl ? ['Document', citationUrl] : null,
  ].filter(Boolean);

  modal.querySelector('.citation-modal-meta').innerHTML = metaRows.map(([label, value]) =>
    `<div class="citation-meta-row">
      <span class="citation-meta-label">${escapeHtml(label)}</span>
      <span class="citation-meta-value">${escapeHtml(value)}</span>
    </div>`
  ).join('');

  modal.querySelector('.citation-modal-excerpt').textContent =
    cleanText(citation.excerpt) || 'No excerpt available.';

  const sourceLink = modal.querySelector('.citation-modal-source');
  sourceLink.href = citationUrl || '#';
  sourceLink.textContent = citationUrl ? 'Open Official Source' : 'Source Not Available';
  sourceLink.style.opacity = citationUrl ? '1' : '0.5';
  sourceLink.style.pointerEvents = citationUrl ? '' : 'none';
  sourceLink.onclick = null;

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

  const citationCards = safeCitations.map((c, idx) => {
    const cleanExcerpt = cleanText(c.excerpt);
    const excerptPreview = cleanExcerpt.slice(0, 420);
    const relevance = typeof c.score === 'number' ? (c.score * 100).toFixed(0) : 'N/A';
    const issueDate = formatIssueDate(c.issue_date);
    const sourceLabel = cleanText(c.source) || 'Regulatory Source';
    return `
    <button class="citation-card-button" type="button">
      <div class="citation-card">
        <div class="citation-card-ref">[${idx + 1}] ${escapeHtml(c.id || 'REF')}</div>
        <div class="citation-card-title">${escapeHtml(cleanText(c.title) || 'Untitled section')}</div>
        ${c.section_path ? `<div class="citation-card-section">${escapeHtml(cleanText(c.section_path))}</div>` : ''}
        <div class="citation-card-meta">${escapeHtml(sourceLabel)}${issueDate ? ` · ${escapeHtml(issueDate)}` : ''}</div>
        <div class="citation-card-excerpt">${escapeHtml(excerptPreview)}${cleanExcerpt.length > 420 ? '…' : ''}</div>
        <div class="citation-score">${relevance}% relevance · click to view full details</div>
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
