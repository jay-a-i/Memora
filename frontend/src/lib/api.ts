// Thin typed fetch wrappers for every backend endpoint we use.
// All endpoints pre-pend VITE_API_URL; failures throw Error with a useful message.

import type {
  CreateSessionRequest,
  DocumentRecord,
  DocumentUploadResponse,
  Message,
  Session,
} from "@/types/api";

const API_BASE: string = import.meta.env.VITE_API_URL;

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      if (data && typeof data === "object" && "detail" in data) {
        detail = String(data.detail);
      }
    } catch {
      // body wasn't JSON; fall through with statusText
    }
    throw new ApiError(detail || `Request failed: ${res.status}`, res.status);
  }
  return res.json() as Promise<T>;
}

export async function createSession(
  username: string,
  title?: string
): Promise<{ session_id: number }> {
  const body: CreateSessionRequest = { username, ...(title ? { title } : {}) };
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return handle<{ session_id: number }>(res);
}

export async function getSessions(username: string): Promise<Session[]> {
  const res = await fetch(`${API_BASE}/users/${encodeURIComponent(username)}/sessions`);
  return handle<Session[]>(res);
}

export async function getMessages(sessionId: number): Promise<Message[]> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/messages`);
  return handle<Message[]>(res);
}

export async function getDocuments(username: string): Promise<DocumentRecord[]> {
  const res = await fetch(`${API_BASE}/documents/${encodeURIComponent(username)}`);
  return handle<DocumentRecord[]>(res);
}

export async function uploadDocument(
  username: string,
  file: File
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("username", username);
  form.append("file", file, file.name);
  const res = await fetch(`${API_BASE}/documents/upload`, {
    method: "POST",
    body: form,
  });
  return handle<DocumentUploadResponse>(res);
}

export async function deleteDocument(
  documentId: number
): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/documents/${documentId}`, {
    method: "DELETE",
  });
  return handle<{ message: string }>(res);
}

export { ApiError };
