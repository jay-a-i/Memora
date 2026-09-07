import { LogOut, Plus, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { DocumentList } from "@/components/documents/DocumentList";
import { PdfUploader } from "@/components/documents/PdfUploader";
import { useUsername } from "@/hooks/useUsername";
import { cn } from "@/lib/utils";
import type { DocumentRecord, Session } from "@/types/api";

interface SidebarProps {
  username: string;
  sessions: Session[];
  activeSessionId: number | null;
  onNewChat: () => void;
  onSelectSession: (id: number) => void;
  documents: DocumentRecord[];
  onUpload: (file: File) => Promise<{ chunks_count: number }>;
  onDeleteDocument: (id: number) => void;
}

export function Sidebar({
  username,
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  documents,
  onUpload,
  onDeleteDocument,
}: SidebarProps) {
  const { clearUsername } = useUsername();

  return (
    <aside className="flex h-full w-72 flex-col border-r border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-xl">🧠</span>
          <span className="font-semibold">Memora</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={clearUsername}
          aria-label="Sign out"
          title="Sign out"
        >
          <LogOut className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="flex-1 px-3 py-3">
        <Button
          variant="default"
          className="mb-3 w-full justify-start"
          onClick={onNewChat}
        >
          <Plus className="h-4 w-4" /> New Chat
        </Button>

        {sessions.length > 0 && (
          <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">
            Sessions
          </div>
        )}
        <div className="flex flex-col gap-1">
          {sessions.map((s) => (
            <Button
              key={s.id}
              variant="ghost"
              size="sm"
              className={cn(
                "w-full justify-start truncate",
                activeSessionId === s.id && "bg-accent text-accent-foreground"
              )}
              onClick={() => onSelectSession(s.id)}
              title={s.title}
            >
              <MessageSquare className="h-4 w-4 shrink-0" />
              <span className="truncate">{s.title}</span>
            </Button>
          ))}
        </div>

        <Separator className="my-4" />

        <div className="mb-2 text-xs font-medium uppercase text-muted-foreground">
          Documents
        </div>
        <PdfUploader onUpload={onUpload} />
        <div className="mt-3">
          <DocumentList documents={documents} onDelete={onDeleteDocument} />
        </div>
      </ScrollArea>

      <div className="border-t border-border px-4 py-2 text-xs text-muted-foreground">
        Signed in as <span className="font-medium text-foreground">{username}</span>
      </div>
    </aside>
  );
}
