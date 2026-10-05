import { Navigate, Route, Routes } from 'react-router-dom';
import { ChatPage } from './pages/ChatPage';

/**
 * Routing.
 *
 * `<Routes>` renders exactly one matched element, so switching between "/" and
 * "/c/:id" swaps the parameter without changing the element type or its
 * position in the tree. ChatPage therefore stays mounted and an in-flight
 * stream is not torn down by navigating.
 */
export function App() {
  return (
    <Routes>
      <Route path="/c/:sessionId" element={<ChatPage />} />
      <Route path="/" element={<ChatPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
