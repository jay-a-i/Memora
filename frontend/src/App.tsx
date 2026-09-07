import { Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { UsernamePrompt } from "@/components/auth/UsernamePrompt";
import { AppShell } from "@/components/layout/AppShell";
import { useUsername } from "@/hooks/useUsername";

function Root() {
  const { username, setUsername } = useUsername();

  if (username === null) {
    return <UsernamePrompt onSubmit={setUsername} />;
  }

  return <AppShell username={username} />;
}

export default function App() {
  return (
    <>
      <Routes>
        <Route path="/" element={<Root />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toaster richColors position="top-right" />
    </>
  );
}
