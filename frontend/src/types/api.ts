// Type definitions for the Memora backend API.
// Mirrors the response shapes from main.py (see plan §2.8).

export type Role = "user" | "assistant";

export interface Session {
  id: number;
  title: string;
}

export interface Message {
  role: Role;
  content: string;
}

export interface DocumentRecord {
  id: number;
  filename: string;
  uploaded_at: string;
}

export interface DocumentUploadResponse {
  document_id: number;
  filename: string;
  chunks_count: number;
}

export interface CreateSessionRequest {
  username: string;
  title?: string;
}
