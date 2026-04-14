# UI Redesign + Railway Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the basic single-page chat UI with a modern Perplexity/ChatGPT-style conversation interface and add Railway deployment config.

**Architecture:** Pure frontend rewrite (HTML/CSS/JS) with no backend changes. The JS maintains a visual conversation thread in the DOM; each question is sent independently to the existing `/chat` endpoint. `marked.js` renders answers as markdown. Railway deployment uses Nixpacks with a `Procfile` start command.

**Tech Stack:** Vanilla JS, marked.js 9 (CDN), Inter font (Google Fonts CDN), FastAPI (unchanged), Railway + Nixpacks

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/api/templates/index.html` | Rewrite | Page shell, sidebar, chat area, input bar, empty state |
| `src/api/static/styles.css` | Rewrite | All visual styling — layout, bubbles, badges, citations, animations |
| `src/api/static/app.js` | Rewrite | Conversation state, send/receive logic, markdown render, citation toggle |
| `Procfile` | Create | Railway start command |
| `railway.json` | Create | Railway build + deploy config, health check |
| `nixpacks.toml` | Create | Python 3.12 + pip install |

---

## Task 1: Railway Deployment Files

**Files:**
- Create: `Procfile`
- Create: `railway.json`
- Create: `nixpacks.toml`

- [ ] **Step 1: Create Procfile**

```
web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
```

Save to `Procfile` (no extension) at project root.

- [ ] **Step 2: Create railway.json**

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "uvicorn src.api.main:app --host 0.0.0.0 --port $PORT",
    "healthcheckPath": "/health",
    "healthcheckTimeout": 300,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

- [ ] **Step 3: Create nixpacks.toml**

```toml
[phases.setup]
nixPkgs = ["python312"]

[phases.install]
cmds = ["pip install -r requirements.txt"]

[start]
cmd = "uvicorn src.api.main:app --host 0.0.0.0 --port $PORT"
```

- [ ] **Step 4: Verify Procfile syntax**

Run:
```bash
cat Procfile
```
Expected output: `web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`

- [ ] **Step 5: Commit**

```bash
git add Procfile railway.json nixpacks.toml
git commit -m "feat: add Railway deployment config"
```

---

## Task 2: Rewrite index.html

**Files:**
- Modify: `src/api/templates/index.html`

- [ ] **Step 1: Replace index.html entirely**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>RegChat — FAA/TC Regulations</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />
  <script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
  <link rel="stylesheet" href="/static/styles.css" />
</head>
<body>
  <div class="layout">

    <aside class="sidebar" id="sidebar">
      <div class="sidebar-top">
        <div class="brand">
          <div class="brand-icon">✈</div>
          <span class="brand-name">RegChat</span>
        </div>
        <button class="new-chat-btn" id="newChatBtn">+ New Chat</button>
      </div>
      <div class="sidebar-bottom">
        <div class="source-badge">FAA Part 25 · CAR 525 · ACs</div>
      </div>
    </aside>

    <div class="overlay" id="overlay"></div>

    <div class="main">
      <header class="mobile-header">
        <button class="hamburger" id="hamburger" aria-label="Menu">&#9776;</button>
        <span class="brand-name">RegChat</span>
      </header>

      <div class="chat-area" id="chatArea">
        <div class="empty-state" id="emptyState">
          <div class="empty-icon">✈</div>
          <h2>Ask a regulation question</h2>
          <p>Answers grounded in FAA Part 25, CAR 525, and Advisory Circulars.</p>
          <div class="suggestions">
            <button class="suggestion-chip" data-q="What are the structural requirements for passenger seats under FAR Part 25?">Passenger seat structural requirements</button>
            <button class="suggestion-chip" data-q="What does CAR 525 say about emergency exit lighting?">Emergency exit lighting in CAR 525</button>
            <button class="suggestion-chip" data-q="What Advisory Circulars cover cabin interior flammability requirements?">Cabin interior flammability ACs</button>
          </div>
        </div>
        <div class="thread" id="thread"></div>
      </div>

      <div class="input-bar">
        <div class="input-wrap">
          <textarea id="questionInput" placeholder="Ask a regulation question…" rows="1"></textarea>
          <button class="send-btn" id="sendBtn" aria-label="Send">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
        <p class="input-hint">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>

  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add src/api/templates/index.html
git commit -m "feat: rewrite HTML for chat UI shell"
```

---

## Task 3: Rewrite styles.css

**Files:**
- Modify: `src/api/static/styles.css`

- [ ] **Step 1: Replace styles.css entirely**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #f9fafb;
  --sidebar-bg: #ffffff;
  --sidebar-border: #e5e7eb;
  --card-bg: #ffffff;
  --user-bubble: #f3f4f6;
  --ink: #111827;
  --ink-muted: #6b7280;
  --accent: #2563eb;
  --accent-hover: #1d4ed8;
  --green: #16a34a;
  --red: #dc2626;
  --border: #e5e7eb;
  --shadow-sm: 0 1px 4px rgba(0,0,0,0.08);
  --radius-bubble: 20px;
}

html, body { height: 100%; }

body {
  font-family: 'Inter', system-ui, sans-serif;
  font-size: 15px;
  color: var(--ink);
  background: var(--bg);
}

/* ── Layout ── */
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ── Sidebar ── */
.sidebar {
  width: 260px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--sidebar-border);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 20px 16px;
  z-index: 100;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 20px;
}

.brand-icon { font-size: 1.4rem; line-height: 1; }

.brand-name {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--ink);
}

.new-chat-btn {
  width: 100%;
  padding: 9px 14px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
  text-align: left;
}

.new-chat-btn:hover { background: var(--accent-hover); }

.source-badge {
  font-size: 0.75rem;
  color: var(--ink-muted);
  padding: 8px 10px;
  background: var(--bg);
  border-radius: 8px;
  line-height: 1.5;
}

/* ── Main column ── */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.mobile-header {
  display: none;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--card-bg);
}

.hamburger {
  background: none;
  border: none;
  font-size: 1.3rem;
  cursor: pointer;
  color: var(--ink);
  padding: 4px;
}

/* ── Chat area ── */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0 8px;
  display: flex;
  flex-direction: column;
}

/* ── Empty state ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 40px 24px;
  text-align: center;
  gap: 12px;
}

.empty-icon { font-size: 3rem; line-height: 1; }

.empty-state h2 {
  font-size: 1.4rem;
  font-weight: 600;
}

.empty-state p {
  color: var(--ink-muted);
  max-width: 400px;
  line-height: 1.6;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}

.suggestion-chip {
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--card-bg);
  color: var(--ink);
  font-size: 0.85rem;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s, color 0.15s;
}

.suggestion-chip:hover {
  border-color: var(--accent);
  background: #eff6ff;
  color: var(--accent);
}

/* ── Thread ── */
.thread {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding: 0 max(24px, calc(50% - 380px));
  padding-bottom: 16px;
}

/* ── Messages ── */
.msg { display: flex; flex-direction: column; max-width: 100%; }
.msg-user  { align-items: flex-end; }
.msg-assistant { align-items: flex-start; }

.bubble-user {
  background: var(--user-bubble);
  border-radius: var(--radius-bubble) var(--radius-bubble) 4px var(--radius-bubble);
  padding: 12px 16px;
  max-width: 72%;
  line-height: 1.6;
  white-space: pre-wrap;
}

.bubble-assistant {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 4px var(--radius-bubble) var(--radius-bubble) var(--radius-bubble);
  padding: 16px 18px;
  width: 100%;
  box-shadow: var(--shadow-sm);
  line-height: 1.7;
}

/* Markdown inside assistant bubble */
.bubble-assistant h1,
.bubble-assistant h2,
.bubble-assistant h3 {
  font-size: 1rem;
  font-weight: 600;
  margin: 12px 0 6px;
}

.bubble-assistant h1:first-child,
.bubble-assistant h2:first-child,
.bubble-assistant h3:first-child { margin-top: 0; }

.bubble-assistant p { margin: 0 0 8px; }
.bubble-assistant p:last-child { margin-bottom: 0; }
.bubble-assistant ul,
.bubble-assistant ol { padding-left: 20px; margin: 6px 0; }
.bubble-assistant li { margin: 3px 0; }

.bubble-assistant code {
  font-family: 'Menlo', 'Consolas', monospace;
  font-size: 0.875em;
  background: #f3f4f6;
  padding: 2px 5px;
  border-radius: 4px;
}

.bubble-assistant pre {
  background: #f3f4f6;
  border-radius: 8px;
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}

.bubble-assistant pre code { background: none; padding: 0; }

.bubble-assistant a { color: var(--accent); text-decoration: none; }
.bubble-assistant a:hover { text-decoration: underline; }

/* ── Meta row ── */
.msg-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.badge {
  font-size: 0.75rem;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 20px;
}

.badge-grounded    { background: #dcfce7; color: var(--green); }
.badge-ungrounded  { background: #f3f4f6; color: var(--ink-muted); }
.badge-confidence  { background: #f3f4f6; color: var(--ink-muted); }

.citations-toggle {
  background: none;
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 2px 10px;
  font-size: 0.75rem;
  color: var(--ink-muted);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.citations-toggle:hover { border-color: var(--accent); color: var(--accent); }

/* ── Citations panel ── */
.citations-panel {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: hidden;
  max-height: 0;
  transition: max-height 0.3s ease;
}

.citations-panel.open { max-height: 2000px; }

.citation-card {
  background: #f9fafb;
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 0.82rem;
  line-height: 1.5;
}

.citation-card strong { color: var(--ink); }

.citation-card a {
  color: var(--accent);
  text-decoration: none;
  word-break: break-all;
}

.citation-card a:hover { text-decoration: underline; }

.citation-score {
  color: var(--ink-muted);
  font-size: 0.75rem;
  margin-top: 2px;
}

/* ── Error banner ── */
.error-banner {
  background: #fee2e2;
  color: var(--red);
  border-radius: 8px;
  padding: 10px 14px;
  font-size: 0.875rem;
  margin-top: 8px;
}

/* ── Typing indicator ── */
.typing-indicator {
  display: flex;
  gap: 5px;
  align-items: center;
  padding: 4px 0;
}

.typing-indicator span {
  width: 7px;
  height: 7px;
  background: var(--ink-muted);
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}

.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-6px); }
}

/* ── Input bar ── */
.input-bar {
  padding: 12px max(24px, calc(50% - 380px)) 10px;
  background: var(--bg);
  border-top: 1px solid var(--border);
}

.input-wrap {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 10px 12px;
  box-shadow: var(--shadow-sm);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.input-wrap:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(37,99,235,0.1);
}

.input-wrap textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  font-family: inherit;
  font-size: 0.95rem;
  line-height: 1.5;
  color: var(--ink);
  background: transparent;
  max-height: 160px;
  overflow-y: auto;
}

.input-wrap textarea::placeholder { color: var(--ink-muted); }

.send-btn {
  flex-shrink: 0;
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.15s;
}

.send-btn:hover:not(:disabled) { background: var(--accent-hover); }
.send-btn:disabled { background: var(--border); cursor: not-allowed; }

.input-hint {
  font-size: 0.72rem;
  color: var(--ink-muted);
  margin-top: 6px;
  text-align: center;
}

/* ── Shake animation ── */
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-6px); }
  40% { transform: translateX(6px); }
  60% { transform: translateX(-4px); }
  80% { transform: translateX(4px); }
}

.shake { animation: shake 0.35s ease; }

/* ── Mobile overlay ── */
.overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.4);
  z-index: 50;
}

/* ── Responsive ── */
@media (max-width: 768px) {
  .sidebar {
    position: fixed;
    top: 0; left: 0; height: 100%;
    transform: translateX(-100%);
    transition: transform 0.25s ease;
  }

  .sidebar.open { transform: translateX(0); }
  .overlay.open { display: block; }
  .mobile-header { display: flex; }

  .thread { padding: 0 16px 16px; }
  .input-bar { padding: 10px 16px 8px; }
  .bubble-user { max-width: 85%; }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/api/static/styles.css
git commit -m "feat: rewrite CSS for modern chat UI"
```

---

## Task 4: Rewrite app.js

**Files:**
- Modify: `src/api/static/app.js`

- [ ] **Step 1: Replace app.js entirely**

```javascript
// Configure marked
marked.use({ breaks: true, gfm: true });

// Sanitize rendered HTML — strip script tags
function sanitizeHtml(html) {
  return html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');
}

// Escape user-provided strings before inserting as HTML
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
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
    ? `<button class="citations-toggle">Sources (${safeCitations.length})</button>`
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

  const renderedAnswer = sanitizeHtml(marked.parse(answer || ''));

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
    wrap.classList.add('shake');
    wrap.addEventListener('animationend', () => wrap.classList.remove('shake'), { once: true });
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
```

- [ ] **Step 2: Commit**

```bash
git add src/api/static/app.js
git commit -m "feat: rewrite JS for persistent chat UI with markdown and citations"
```

---

## Task 5: Verify Locally

**Files:** (none changed)

- [ ] **Step 1: Start the dev server**

From the project root with the venv active:
```bash
uvicorn src.api.main:app --reload --port 8000
```

Expected: `INFO: Application startup complete.`

- [ ] **Step 2: Open browser**

Navigate to `http://localhost:8000`

Expected:
- Two-column layout: white sidebar on left, chat area on right
- Empty state visible with ✈ icon, heading, and 3 suggestion chips
- No console errors in DevTools

- [ ] **Step 3: Test suggestion chip**

Click "Passenger seat structural requirements" chip.

Expected:
- Empty state disappears
- User bubble appears on the right
- Animated typing indicator (3 bouncing dots) appears on the left
- After a few seconds, typing indicator is replaced with a markdown-rendered answer
- "✓ Grounded" or "Ungrounded" badge + confidence % badge appear below the answer
- If there are citations: "Sources (N)" toggle button appears

- [ ] **Step 4: Test citations toggle**

Click "Sources (N)" button.

Expected:
- Citation cards slide open (smooth max-height transition)
- Each card shows source ID, section path, relevance score, and a clickable URL
- Button text updates to "Sources (N) ▲"
- Clicking again collapses the panel

- [ ] **Step 5: Test New Chat button**

Click "+ New Chat" in sidebar.

Expected:
- Thread clears
- Empty state reappears

- [ ] **Step 6: Test mobile layout**

Resize browser to < 768px width (or use DevTools device emulation).

Expected:
- Sidebar is hidden
- Hamburger menu (☰) appears in top header
- Clicking hamburger opens sidebar with dark overlay
- Clicking overlay closes sidebar

- [ ] **Step 7: Commit verification note (no code change needed)**

```bash
git commit --allow-empty -m "chore: verified UI locally"
```

---

## Task 6: Deploy to Railway

**Files:** (none changed — all Railway config committed in Task 1)

- [ ] **Step 1: Push to GitHub**

Make sure the repo is pushed to GitHub (Railway deploys from GitHub):
```bash
git push origin main
```

- [ ] **Step 2: Create Railway project**

1. Go to [railway.app](https://railway.app) and sign in
2. Click **New Project → Deploy from GitHub repo**
3. Select this repository
4. Railway will detect `nixpacks.toml` and start building automatically

- [ ] **Step 3: Set environment variables in Railway dashboard**

In Railway project → **Variables** tab, add:
```
LLM_API_KEY=<your key>
LLM_BASE_URL=<your base url>
LLM_MODEL=<your model name>
```

(These match the field names in `src/config.py`)

- [ ] **Step 4: Check build logs**

In Railway → **Deployments** tab, watch the build log.

Expected final lines:
```
✓ nixpacks build succeeded
✓ Application started
```

- [ ] **Step 5: Verify health check**

Railway will call `GET /health` automatically. In the deployment details, status should show **Active**.

You can also open the Railway-provided URL + `/health`:
Expected response: `{"status":"ok"}`

- [ ] **Step 6: Open the app**

Click the Railway-provided domain (e.g. `your-app.up.railway.app`).

Expected: Full chat UI loads, same as local verification in Task 5.

> **Note on vector index:** If `data/index/` is not committed to git (too large), Railway will start but `/chat` will return an error about missing index. In that case, use a Railway Volume: attach a volume at `/app/data/index` and upload the index files via Railway CLI (`railway volume upload`).

---

## Decision Point: Vector Index Size

Before pushing to GitHub, check if the index files will fit in git:

```bash
du -sh data/index/
```

- **Under ~50 MB**: commit to git — `git add data/index/ && git commit -m "feat: add pre-built vector index"`
- **Over 50 MB**: add `data/index/` to `.gitignore`, use Railway Volume (instructions in Task 6 note above)
