/**
 * Chat and session endpoints.
 *
 * Routes mirror backend/app/api/v1/endpoints/chat.py, mounted under /api/v1.
 * Note that POST /chat/sessions creates the session, while GET /chat/sessions
 * lists them and DELETE /chat/sessions/{id} removes one.
 */

import { http } from './client';
import type {
  ChatHistoryDto,
  ChatSessionCreateDto,
  ChatSessionDto,
} from '../types/api';

/** POST /chat/sessions -> 201 with the created session. */
export function createSession(title?: string): Promise<ChatSessionDto> {
  const payload: ChatSessionCreateDto = title ? { title } : {};
  return http.post<ChatSessionDto>('/chat/sessions', payload);
}

/** GET /chat/sessions, most recently active first. */
export function listSessions(limit = 100, offset = 0): Promise<ChatSessionDto[]> {
  return http.get<ChatSessionDto[]>('/chat/sessions', { limit, offset });
}

/** GET /chat/sessions/{id} -> the stored transcript, oldest first. */
export function getSessionHistory(sessionId: string): Promise<ChatHistoryDto> {
  return http.get<ChatHistoryDto>(`/chat/sessions/${encodeURIComponent(sessionId)}`);
}

/** DELETE /chat/sessions/{id} -> 204; messages cascade. */
export function deleteSession(sessionId: string): Promise<void> {
  return http.delete<void>(`/chat/sessions/${encodeURIComponent(sessionId)}`);
}
