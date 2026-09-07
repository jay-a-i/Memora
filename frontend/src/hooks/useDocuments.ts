// Document library: list, upload, delete.

import { useCallback, useEffect, useState } from "react";
import { deleteDocument, getDocuments, uploadDocument } from "@/lib/api";
import type { DocumentRecord } from "@/types/api";

export function useDocuments(username: string | null) {
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!username) return;
    setLoading(true);
    try {
      const data = await getDocuments(username);
      setDocuments(data);
    } finally {
      setLoading(false);
    }
  }, [username]);

  const upload = useCallback(
    async (file: File) => {
      if (!username) throw new Error("Not signed in");
      const result = await uploadDocument(username, file);
      await refresh();
      return result;
    },
    [username, refresh]
  );

  const remove = useCallback(
    async (documentId: number) => {
      await deleteDocument(documentId);
      await refresh();
    },
    [refresh]
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { documents, loading, refresh, upload, remove };
}
