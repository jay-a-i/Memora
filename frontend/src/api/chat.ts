/**
 * Chat and session endpoints.
 *
 * Routes mirror backend/api/v1/endpoints/chat.py, mounted under /api/v1.
 * POST /chat/sessions creates a session, GET /chat/sessions lists them and
 * DELETE /chat/sessions/{id} removes one.
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

export interface HistoryPageParams {
  limit?: number;
  /** Return messages with `seq < before_seq`. Omit for the newest page. */
  before_seq?: number | null;
}

/**
 * GET /chat/sessions/{id} -> one page of stored transcript, oldest first.
 *
 * Pages are cursor-based: pass the previous response's `next_before_seq` as
 * `before_seq` to load older messages.
 */
export function getSessionHistory(
  sessionId: string,
  params: HistoryPageParams = {},
): Promise<ChatHistoryDto> {
  return http.get<ChatHistoryDto>(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    limit: params.limit,
    before_seq: params.before_seq ?? undefined,
  });
}

/** DELETE /chat/sessions/{id} -> 204; messages cascade. */
export function deleteSession(sessionId: string): Promise<void> {
  return http.delete<void>(`/chat/sessions/${encodeURIComponent(sessionId)}`);
}
