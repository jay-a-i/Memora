// First-visit modal: collects a backend username and stores it in localStorage.
// The backend auto-creates a user row on first use of /sessions, so the
// frontend just needs any 3-32 char [a-z0-9_] string.

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { isValidBackendUsername } from "@/lib/username";

interface UsernamePromptProps {
  onSubmit: (value: string) => boolean;
}

export function UsernamePrompt({ onSubmit }: UsernamePromptProps) {
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const normalized = value.toLowerCase().trim();
    if (!isValidBackendUsername(normalized)) {
      setError("Use 3-32 lowercase letters, digits, or underscores.");
      return;
    }
    const ok = onSubmit(normalized);
    if (!ok) {
      setError("Couldn't save username. Try a different value.");
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border border-border bg-card p-6 shadow-lg"
      >
        <div>
          <h2 className="text-lg font-semibold">Choose a username</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            This identifies you to the Memora backend and is how your chats
            and documents are stored.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="backend-username">Username</Label>
          <Input
            id="backend-username"
            autoFocus
            autoComplete="off"
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              if (error) setError(null);
            }}
            placeholder="alice"
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <Button type="submit" className="w-full">
          Continue
        </Button>
      </form>
    </div>
  );
}
