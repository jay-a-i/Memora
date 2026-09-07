import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { DocumentRecord } from "@/types/api";

interface DocumentItemProps {
  document: DocumentRecord;
  onDelete: (id: number) => void;
}

export function DocumentItem({ document, onDelete }: DocumentItemProps) {
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-border bg-card px-2 py-1.5 text-sm">
      <span className="truncate" title={document.filename}>
        {document.filename}
      </span>
      <Button
        size="icon"
        variant="ghost"
        className="h-7 w-7"
        onClick={() => onDelete(document.id)}
        aria-label={`Delete ${document.filename}`}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  );
}
