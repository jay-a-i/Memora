/**
 * Document endpoints.
 *
 * Routes mirror backend/app/api/v1/endpoints/documents.py. The list route is
 * declared as "/" upstream, so its path carries a trailing slash.
 */

import { http } from './client';
import type { DocumentDto, DocumentListDto, DocumentUploadDto } from '../types/api';

/** POST /documents/upload -> 202; ingestion continues in the background. */
export function uploadDocument(file: File): Promise<DocumentUploadDto> {
  return http.upload<DocumentUploadDto>('/documents/upload', file);
}

/** GET /documents/ -> newest first. */
export function listDocuments(limit = 100, offset = 0): Promise<DocumentListDto> {
  return http.get<DocumentListDto>('/documents/', { limit, offset });
}

/** GET /documents/{id} -> current processing status. */
export function getDocument(documentId: string): Promise<DocumentDto> {
  return http.get<DocumentDto>(`/documents/${encodeURIComponent(documentId)}`);
}

/** DELETE /documents/{id} -> 204; chunks cascade in the database. */
export function deleteDocument(documentId: string): Promise<void> {
  return http.delete<void>(`/documents/${encodeURIComponent(documentId)}`);
}
