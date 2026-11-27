# Memora — Frontend

A minimal, monochrome workspace for chatting with the Memora knowledge base.

## Stack

React 19 · TypeScript (strict) · Vite 6 · Tailwind CSS 4 · React Router 7

Only two additional runtime dependencies were added beyond the stack above:

- `react-markdown` + `remark-gfm` — assistant answers need real Markdown
  (tables, fenced code, lists). Hand-rolling a parser would be far more code
  and less correct. **No syntax highlighter** is installed, because every
  highlighter introduces colour and this UI is restricted to grey.

## Running

```bash
cd frontend
cp .env.example .env      # then fill in VITE_APP_SECURITY_KEY
npm install
npm run dev               # http://localhost:3000
```

The dev server is pinned to **port 3000** because the backend's default
`CORS_ORIGINS` is `["http://localhost:3000"]` (`backend/core/config.py`).
Vite's default 5173 is not on that list and every `/api/v1` request would be
blocked by preflight.

| Script | Purpose |
| --- | --- |
| `npm run dev` | Dev server with HMR |
| `npm run build` | Typecheck, then production build |
| `npm run preview` | Serve the built output |
| `npm run typecheck` | Types only |

## Configuration

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | API root, including the `/api/v1` prefix |
| `VITE_APP_SECURITY_KEY` | Sent as the `APP_SECURITY_KEY` request header |

`VITE_APP_SECURITY_KEY` must match `APP_API_KEY` in the backend's `app.env`.

**On the key:** the backend authenticates with a custom `APP_SECURITY_KEY`
header (not `Authorization: Bearer`). Anything shipped to a browser is readable
by the user, so this is a local/demo convenience, not a secret. All of it lives
behind `src/config.ts` and the `authHeaders()` helper in `src/api/client.ts`,
so swapping in real user auth means replacing one function — no call sites
change. A key can also be supplied at runtime via localStorage (see
`config.setSecurityKey`), which overrides the build-time value.

## Backend contract

Everything the app knows about the API lives in `src/api/` and `src/types/api.ts`,
both derived from the backend Pydantic schemas. No component calls `fetch`.

| Route | Notes |
| --- | --- |
| `POST /chat/stream` | SSE over **POST** — see below |
| `POST /chat/sessions` | 201 with the new session |
| `GET /chat/sessions` | Most recently active first |
| `GET /chat/sessions/{id}` | One history page, oldest first; accepts `limit` and `before_seq` and returns `next_before_seq` |
| `DELETE /chat/sessions/{id}` | 204; messages cascade |
| `POST /documents/upload` | 202; ingestion continues in the background |
| `GET /documents/` | Note the trailing slash |
| `GET /documents/{id}` | Current ingestion status |
| `GET /documents/{id}/chunks` | `chunk_index`, `content`, `metadata` |
| `DELETE /documents/{id}` | 204; chunks cascade |

Four contract details that drove real implementation decisions:

1. **`EventSource` cannot be used.** `POST /chat/stream` is a POST and needs a
   custom header, neither of which `EventSource` supports. The stream is read
   from a `fetch()` `ReadableStream` and parsed in `src/utils/sse.ts`.

2. **The server discards text emitted before a tool boundary.** `chat.py`
   resets `current_parts` on both `tool_start` and `tool_end` and persists only
   the final segment. The client mirrors this, so what is on screen matches
   what is stored and re-read on reload. See the `tool_start`/`tool_end` cases
   in `src/hooks/useChat.ts`.

3. **Sessions are created lazily.** An abandoned empty conversation would
   otherwise litter the sidebar, so the first send creates the session and
   navigates to `/c/{id}`.

4. **Every turn carries a stable `turn_id`.** The ID is generated once per new
   question, sent at the top level of the `/chat/stream` body, and reused when
   the same turn is retried or resumed. Stopping a stream or reloading the page
   leaves the turn recoverable: history messages expose `turn_id`, so a user
   message without a matching assistant answer is shown with a Resume action.
   The frontend never submits a new question while an earlier turn is
   unfinished; the backend rejects that with HTTP 409.

### History pagination

`getSessionHistory()` accepts `limit` and `before_seq`. The first page stores
`next_before_seq`; "Load older messages" requests that cursor, prepends the
result without duplicates, and `MessageList` compensates for the added height
so the reader's position does not jump.

### Citations

`Sources.tsx` renders the `sources` events the backend emits from
`hybrid_search` results (filename, document id, chunk index, score and a text
snippet). Values are displayed as received; nothing is fabricated when an
answer has no sources.

## Layout

```
src/
  api/         transport + one module per resource (client, chat, documents)
  components/
    ui/        Button, Icon, Modal, Notice, Skeleton, ErrorBoundary
    chat/      MessageList, MessageItem, MessageComposer, ToolActivity, Sources
  sidebar/     Sidebar, SessionList, SessionItem
  documents/   UploadDocument, DocumentItem, DocumentStatusBadge
  hooks/       useChat, useSessions, useDocuments
  types/       mirrors of the backend schemas
  pages/       ChatPage
  utils/       sse.ts
  config.ts    env + auth resolution
```

State is React state and hooks only — no Redux or global store. The backend
stays the source of truth for chat, sessions and documents; localStorage holds
just the last active session id (and, optionally, a runtime API-key override).

## Design system

A single neutral grey hue. Every surface, border and text colour is the same
grey at a different lightness or opacity — there is no second hue anywhere in
`src/index.css`. Document states are separated by icon, border weight,
letter-spacing and opacity rather than colour:

- **PROCESSING** — spinner icon, muted text
- **COMPLETED** — check icon, muted text
- **FAILED** — warning icon, heavier border, heavier text, error detail shown

There are no emojis in the interface. Icons are inline SVG drawn with
`currentColor`, so they inherit the text colour by construction.
