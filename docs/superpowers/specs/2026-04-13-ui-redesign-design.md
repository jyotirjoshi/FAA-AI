# UI Redesign + Railway Deploy — Design Spec
Date: 2026-04-13

## Overview

Rebuild the FAA/TC Regulation chatbot frontend into a clean, modern SaaS-style chat UI (Perplexity/ChatGPT aesthetic). No backend changes. Deploy to Railway.

---

## Scope

- Complete rewrite of `src/api/templates/index.html`, `src/api/static/styles.css`, `src/api/static/app.js`
- Add `marked.js` via CDN for markdown rendering
- Add Railway deployment files (`railway.json`, `Procfile` or `nixpacks.toml`)
- No changes to Python API, RAG pipeline, or vector store

---

## Layout

Full-height two-column layout:

### Left Sidebar (260px, collapsible on mobile)
- App logo / name: "RegChat" (or similar)
- Model/source badge: "FAA Part 25 · CAR 525 · ACs"
- "New Chat" button — clears the conversation thread
- Footer: version or subtle branding

### Main Chat Column (flex-grow)
- **Message thread** — scrollable, grows upward as messages are added
- **Input bar** — pinned to bottom of the page

---

## Message Thread

Each exchange produces two bubbles:

**User bubble (right-aligned)**
- Light gray background pill/card
- User's question text

**Assistant bubble (left-aligned)**
- White card with subtle shadow
- Small avatar/icon (regulation book or similar)
- Answer rendered via `marked.js` as HTML (headings, bullets, bold, code blocks)
- Confidence + grounded shown as small inline badges below the answer text (e.g. `✓ Grounded  · 87% confidence`)
- "Sources (N)" toggle button below the badges — clicking expands/collapses citation cards
- Citation cards (when expanded): source ID, section path, relevance score, clickable URL

**Empty state** (no messages yet)
- Centered prompt suggestions: 3 example questions as clickable chips

---

## Input Bar

- Pinned to bottom, full-width of the chat column
- Auto-expanding textarea (min 1 line, max ~5 lines)
- Send button (arrow icon) to the right
- Send on `Enter` (new line on `Shift+Enter`)
- Input + button disabled while a response is loading
- Animated typing indicator (3 dots) appears in a ghost assistant bubble while waiting

---

## Styling

- **Font**: Inter (Google Fonts CDN) or system-ui fallback
- **Colors**:
  - Background: `#f9fafb` (very light gray)
  - Sidebar: `#ffffff` with right border `#e5e7eb`
  - User bubble: `#f3f4f6`
  - Assistant card: `#ffffff` with `box-shadow: 0 1px 4px rgba(0,0,0,0.08)`
  - Accent: `#2563eb` (blue-600, for send button, links, badges)
  - Grounded badge: green `#16a34a`
  - Confidence badge: gray `#6b7280`
- **Border radius**: 12px cards, 20px user bubbles
- **Transitions**: smooth expand/collapse for citations (max-height transition)
- **Mobile**: sidebar hidden by default, hamburger button to toggle

---

## Markdown Rendering

- Load `marked.js` from jsDelivr CDN
- Configure with `{ breaks: true, gfm: true }`
- Sanitize output — strip `<script>` tags (simple regex on rendered HTML before inserting)
- Style rendered markdown: `h1–h3` get smaller sizes within chat context, `code` gets monospace with light background, `a` tags open in new tab

---

## Error Handling

- If the API returns `error` field: show a red inline banner inside the assistant bubble, still show partial answer if present
- Network failure: show a dismissible error card in the thread
- Empty question: shake animation on the input bar, no request sent

---

## Railway Deployment

- `Procfile`: `web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
- `railway.json`: sets builder to Nixpacks, start command
- `nixpacks.toml`: pins Python 3.12, installs from `requirements.txt`
- Environment variables set in Railway dashboard (not in files): `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`
- **Vector index**: the pre-built `data/index/` directory must be committed to the repo (or mounted as a Railway volume). Spec assumes committed to repo for simplicity. If too large for git, use Railway volume — flagged as a decision point.
- Health check: Railway uses `/health` endpoint (already exists)

---

## Files Changed

| File | Action |
|------|--------|
| `src/api/templates/index.html` | Rewrite |
| `src/api/static/styles.css` | Rewrite |
| `src/api/static/app.js` | Rewrite |
| `Procfile` | Create |
| `railway.json` | Create |
| `nixpacks.toml` | Create |

---

## Out of Scope

- Conversation history sent to backend (each question is independent — history is UI-only)
- Compliance Plan UI
- Authentication
- Streaming responses
