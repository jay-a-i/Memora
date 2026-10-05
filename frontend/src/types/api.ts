/**
 * Types mirroring the backend contract.
 *
 * Sourced from backend/schemas/*.py. Keep these in sync with the Pydantic
 * models rather than loosening them, so a contract change surfaces as a
 * type error instead of a runtime surprise.
 */

/** backend/schemas/chat_schemas.py: MessageRole */
export type MessageRole = 'user' | 'assistant' | 'system' | 'tool';

/** backend/schemas/chat_schemas.py: ChatMessageSchema */
export interface ChatMessageDto {
  role: MessageRole;
  content: string;
}

/** backend/schemas/chat_schemas.py: ChatRequestSchema */
export interface ChatRequestDto {
  /** UUID string. The backend creates the session on demand if unknown. */
  session_id: string;
  /** Only the final message is treated as the new question. */
  messages: ChatMessageDto[];
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
  updated_at: string | null;
}

/** backend/schemas/chat_schemas.py: ChatHistoryResponseSchema */
export interface ChatHistoryDto {
  session_id: string;
  messages: ChatMessageDto[];
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
 * Produced by chat.py's `_sse()` calls: chunk, tool_start, tool_end, done,
 * error. The stream also terminates with a bare `data: [DONE]` sentinel,
 * handled separately in the SSE parser.
 *
 * `sources` is not currently emitted by the backend. It is declared here so
 * the source-rendering path stays typed and inert rather than fabricating data.
 */
export type StreamEvent =
  | { type: 'chunk'; content: string }
  | { type: 'tool_start'; name: string; status: string }
  | { type: 'tool_end'; name: string }
  | { type: 'done'; session_id: string }
  | { type: 'error'; message: string }
  | { type: 'sources'; sources: RetrievalSource[] };

/**
 * A retrieval source, if the backend ever provides them.
 *
 * Every field except `label` is optional so that partial payloads from
 * different backends degrade to "show the label" instead of throwing.
 */
export interface RetrievalSource {
  label: string;
  document_id?: string;
  filename?: string;
  chunk?: number | string;
  url?: string;
  score?: number;
  snippet?: string;
  metadata?: Record<string, unknown>;
}
