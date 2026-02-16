import { createSession, getSession } from "./api";

const LS_KEY = "almready_session_id";

async function createAndStoreSessionId(): Promise<string> {
  const meta = await createSession();
  localStorage.setItem(LS_KEY, meta.session_id);
  return meta.session_id;
}

export async function getOrCreateSessionId(): Promise<string> {
  const existing = localStorage.getItem(LS_KEY);

  if (existing) {
    try {
      await getSession(existing);
      return existing;
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      const isSessionMissing = msg.includes("HTTP 404") || msg.includes("Session not found");

      // If backend restarted and forgot in-memory sessions, rotate to a fresh one.
      if (!isSessionMissing) throw error;

      localStorage.removeItem(LS_KEY);
    }
  }

  const sessionId = await createAndStoreSessionId();
  return sessionId;
}

export function clearSessionId() {
  localStorage.removeItem(LS_KEY);
}
