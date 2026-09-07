# Memora — React Frontend

A Vite + React + TypeScript single-page app that replaces the original Streamlit
frontend (`../app.py`) while talking to the existing FastAPI backend
(`../main.py`).

## Stack

- **Vite 5** + **React 18** + **TypeScript 5**
- **Clerk** for authentication (`@clerk/clerk-react`)
- **Tailwind CSS** + shadcn-style primitives (Button, Input, Textarea, etc.)
- **react-router-dom v6** for routing
- **sonner** for toasts
- Native `fetch` + `ReadableStream` for the streaming chat response

## Project layout

```
src/
├── App.tsx               # Router + Clerk gates
├── main.tsx              # ReactDOM + ClerkProvider
├── index.css             # Tailwind base + shadcn CSS variables
├── lib/
│   ├── api.ts            # typed fetch wrappers for every backend endpoint
│   ├── stream.ts         # streamChat() — ReadableStream consumer
│   ├── username.ts       # resolveBackendUsername() + validation
│   └── utils.ts          # shadcn cn() helper
├── hooks/
│   ├── useUsername.ts    # Clerk → backend username
│   ├── useSessions.ts    # sidebar list of chat sessions
│   ├── useDocuments.ts   # upload + list + delete PDFs
│   └── useChatSession.ts # active session, messages, streaming
├── types/
│   └── api.ts            # Session, Message, Document types
└── components/
    ├── ui/               # Button, Input, Textarea, Label, Separator, ScrollArea
    ├── layout/           # AppShell, Sidebar
    ├── auth/             # SignInForm, SignUpForm, UsernamePrompt
    ├── chat/             # ChatPane, MessageList, MessageBubble, ChatInput, EmptyState
    └── documents/        # DocumentList, DocumentItem, PdfUploader
```

## Local development

1. Copy the env template and fill in your Clerk publishable key + backend URL:
   ```bash
   cp .env.example .env
   ```
   Required values:
   - `VITE_CLERK_PUBLISHABLE_KEY` — from [dashboard.clerk.com](https://dashboard.clerk.com) (API Keys)
   - `VITE_API_URL` — `http://localhost:8000` for local dev, or the deployed
     Render URL (`https://memora-tmek.onrender.com`)

2. Start the FastAPI backend in another terminal (from the repo root):
   ```bash
   uvicorn main:app --reload
   ```

3. Start the frontend:
   ```bash
   npm install
   npm run dev
   ```
   The app opens at `http://localhost:5173`.

## Type-check + build

```bash
npm run typecheck
npm run build       # tsc -b && vite build, output: dist/
npm run preview     # serve dist/ on http://localhost:4173
```

## Clerk setup

1. Create a Clerk application at [dashboard.clerk.com](https://dashboard.clerk.com).
2. In **API Keys**, copy the publishable key into `.env`.
3. The first time a user signs up, they are redirected to `/`. If their
   `publicMetadata.backendUsername` is missing, the `<UsernamePrompt />` modal
   collects a username and writes it to publicMetadata.
4. In the Clerk dashboard, under **Paths**, set:
   - Sign-in URL: `/sign-in`
   - Sign-up URL: `/sign-up`
   - After sign-in URL: `/`
   - After sign-up URL: `/`

## CORS

The backend (`../main.py`) must allow the origin you serve from. The default
allow-list includes:
- `http://localhost:5173` (Vite dev)
- `https://*.vercel.app` (Vercel preview + production wildcard)

If you deploy to a different host, add it to the CORS list in `main.py`.

## Deploy to Vercel

1. Push the repo to GitHub.
2. Import the repo in [vercel.com](https://vercel.com) → **Add New… → Project**.
3. Set **Root Directory** = `frontend`.
4. Set **Framework Preset** = Vite (build command and output directory auto-fill).
5. Under **Settings → Environment Variables**, add:
   - `VITE_CLERK_PUBLISHABLE_KEY`
   - `VITE_API_URL`
6. Deploy.

## Deploy to Netlify

A `netlify.toml` rewrite is recommended for SPA routing:

```toml
[build]
  command = "npm run build"
  publish = "dist"

[[redirects]]
  from = "/*"
  to = "/index.html"
  status = 200
```

## Feature parity with the Streamlit app

| Streamlit (`app.py`)         | React (`frontend/`)                            |
|------------------------------|------------------------------------------------|
| Tabs: Sign In / Create       | `/sign-in`, `/sign-up` (Clerk components)      |
| `+ New Chat` button          | Sidebar → "New Chat"                           |
| Session list                 | Sidebar sessions list                          |
| Click session → load history | `useChatSession.selectSession(id)`             |
| PDF uploader                 | `<PdfUploader />`                              |
| Document list + delete       | `<DocumentList />` + `<DocumentItem />`        |
| `st.chat_message` bubbles    | `<MessageList />` + `<MessageBubble />`        |
| `st.chat_input`              | `<ChatInput />`                                |
| `st.write_stream`            | `streamChat()` in `src/lib/stream.ts`          |
| `bcrypt` + `streamlit-auth`  | Clerk managed auth                             |
| `streamlit.session_state`    | React `useState` + `localStorage` (session id) |
