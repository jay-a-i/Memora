/**
 * Types mirroring the backend contract.
 *
 * Sourced from backend/schemas/*.py. Keep these in sync with the Pydantic
 * models rather than loosening them, so a contract change surfaces as a
 * type error instead of a runtime surprise.
 */

/** backend/schemas/chat_schemas.py: MessageRole */
export type MessageRole = 'user' | 'assistant' | 'system' | 'tool';

/**
 * backend/schemas/chat_schemas.py: ChatMessageInputSchema
 *
 * The request body only carries a role and content per message. `turn_id`
 * belongs to the request as a whole, not to each message.
 */
export interface ChatMessageInputDto {
  role: MessageRole;
  content: string;
}

/**
 * backend/schemas/chat_schemas.py: ChatMessageSchema
 *
 * Stored/historical messages additionally carry the turn they belong to, so
 * the client can pair a user turn with its assistant answer.
 */
export interface ChatMessageDto {
  role: MessageRole;
  content: string;
  turn_id: string;
}

/** backend/schemas/chat_schemas.py: ChatRequestSchema */
export interface ChatRequestDto {
  session_id: string;
  /** At least one message; the final one must have the user role. */
  messages: ChatMessageInputDto[];
  /**
   * Stable identifier for one logical user turn. Reused verbatim when the
   * same turn is retried or resumed; 1-64 characters.
   */
  turn_id: string;
}

/** backend/schemas/chat_schemas.py: ChatSessionCreateSchema */
export interface ChatSessionCreateDto {
  title?: string | null;
}

/** backend/schemas/chat_schemas.py: ChatSessionResponseSchema */
export interface ChatSessionDto {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

/** backend/schemas/chat_schemas.py: ChatHistoryResponseSchema */
export interface ChatHistoryDto {
  session_id: string;
  messages: ChatMessageDto[];
  /** Cursor for the next older page; null when there is nothing older. */
  next_before_seq: number | null;
}

/** backend/schemas/document_schemas.py: DocumentStatus */
export type DocumentStatus = 'PROCESSING' | 'COMPLETED' | 'FAILED';

/** backend/schemas/document_schemas.py: DocumentResponse */
export interface DocumentDto {
  id: string;
  filename: string;
  file_type: string;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
}

/** backend/schemas/document_schemas.py: DocumentListResponse */
export interface DocumentListDto {
  documents: DocumentDto[];
  total: number;
}

/** backend/schemas/document_schemas.py: DocumentUploadResponse */
export interface DocumentUploadDto {
  document_id: string;
  filename: string;
  status: DocumentStatus;
  message: string;
}

/** backend/schemas/common_schemas.py: HealthCheckResponse */
export interface HealthDto {
  status: 'healthy' | 'unhealthy';
  database: Record<string, string>;
  version: string;
}

/**
 * Events emitted by POST /chat/stream.
 *
 * Produced by chat.py's `_sse()` calls: chunk, tool_start, tool_end, sources,
 * done and error. The stream also terminates with a bare `data: [DONE]`
 * sentinel, handled separately in the SSE parser.
 */
export type StreamEvent =
  | { type: 'chunk'; content: string }
  | { type: 'tool_start'; name: string; status: string }
  | { type: 'tool_end'; name: string }
  | { type: 'done'; session_id: string }
  | { type: 'error'; message: string }
  | { type: 'sources'; sources: RetrievalSource[] };

/**
 * A retrieval source from a hybrid_search result.
 *
 * The backend emits `label`, `filename`, `document_id`, `chunk`, `score` and
 * `snippet`. Only `label` is required so a partial payload still renders;
 * nothing is filled in client-side when a field is absent.
 */
export interface RetrievalSource {
  label: string;
  filename?: string;
  document_id?: string;
  chunk?: number | string;
  score?: number;
  snippet?: string;
}
