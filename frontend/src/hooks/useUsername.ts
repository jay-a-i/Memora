// Local-only "current user" hook. The backend has its own plain-username
// model (see /sessions in main.py), so the frontend just needs to remember
// a username string in localStorage and surface setters for the prompt UI.
//
// Returns null while no username is set; Root renders <UsernamePrompt />
// in that case. Validates with the same 3-32 / [a-z0-9_] rule the backend
// expects (enforced on the server too, but we fail fast on the client).

import { useCallback, useEffect, useState } from "react";
import { isValidBackendUsername } from "@/lib/username";

const STORAGE_KEY = "memora.username";

function readStoredUsername(): string | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return isValidBackendUsername(raw) ? raw : null;
  } catch {
    return null;
  }
}

export interface UseUsernameResult {
  username: string | null;
  setUsername: (value: string) => boolean;
  clearUsername: () => void;
}

export function useUsername(): UseUsernameResult {
  const [username, setUsernameState] = useState<string | null>(null);

  // Initial load + cross-tab sync.
  useEffect(() => {
    setUsernameState(readStoredUsername());

    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return;
      setUsernameState(readStoredUsername());
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setUsername = useCallback((value: string): boolean => {
    const normalized = value.toLowerCase().trim();
    if (!isValidBackendUsername(normalized)) return false;
    try {
      localStorage.setItem(STORAGE_KEY, normalized);
    } catch {
      // Storage may be unavailable (private mode, quota); treat as success
      // so the UI still works in-memory for this session.
    }
    setUsernameState(normalized);
    return true;
  }, []);

  const clearUsername = useCallback(() => {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // ignore
    }
    setUsernameState(null);
  }, []);

  return { username, setUsername, clearUsername };
}
