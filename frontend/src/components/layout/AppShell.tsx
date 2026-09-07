import { useCallback } from "react";
import { toast } from "sonner";
import { Sidebar } from "@/components/layout/Sidebar";
import { ChatPane } from "@/components/chat/ChatPane";
import { useSessions } from "@/hooks/useSessions";
import { useDocuments } from "@/hooks/useDocuments";
import { useChatSession } from "@/hooks/useChatSession";

interface AppShellProps {
  username: string;
}

export function AppShell({ username }: AppShellProps) {
  const { sessions, create: createSession } = useSessions(username);
  const { documents, upload, remove: removeDocument } = useDocuments(username);
  const {
    sessionId,
    messages,
    isStreaming,
    selectSession,
    clearSession,
    sendMessage,
  } = useChatSession(username);

  const handleNewChat = useCallback(async () => {
    try {
      clearSession();
      const id = await createSession();
      if (id) selectSession(id);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to create chat");
    }
  }, [createSession, selectSession, clearSession]);

  const handleSend = useCallback(
    (text: string) => {
      try {
        sendMessage(text);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to send message");
      }
    },
    [sendMessage]
  );

  const handleUpload = useCallback(
    async (file: File) => {
      try {
        return await upload(file);
      } catch (err) {
        throw err instanceof Error ? err : new Error(String(err));
      }
    },
    [upload]
  );

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar
        username={username}
        sessions={sessions}
        activeSessionId={sessionId}
        onNewChat={handleNewChat}
        onSelectSession={selectSession}
        documents={documents}
        onUpload={handleUpload}
        onDeleteDocument={removeDocument}
      />
      <main className="flex flex-1 flex-col bg-background">
        <ChatPane
          username={username}
          sessionId={sessionId}
          messages={messages}
          isStreaming={isStreaming}
          onSend={handleSend}
        />
      </main>
    </div>
  );
}
