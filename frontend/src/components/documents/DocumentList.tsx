import { DocumentItem } from "@/components/documents/DocumentItem";
import type { DocumentRecord } from "@/types/api";

interface DocumentListProps {
  documents: DocumentRecord[];
  onDelete: (id: number) => void;
}

export function DocumentList({ documents, onDelete }: DocumentListProps) {
  if (documents.length === 0) {
    return (
      <p className="px-1 text-xs text-muted-foreground">
        No documents uploaded yet.
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-1">
      {documents.map((doc) => (
        <DocumentItem key={doc.id} document={doc} onDelete={onDelete} />
      ))}
    </div>
  );
}
