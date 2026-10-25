// Browser-side persistence for visible chats. Server-side conversation
// context is separate and still disappears when the backend restarts.
const STORAGE_KEY = "finwallet.chats.v1";

export function createId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function createConversation() {
  const now = Date.now();
  return {
    id: createId(),
    serverConversationId: null,
    title: "New chat",
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

function isMessage(value) {
  return (
    value &&
    (value.role === "user" || value.role === "assistant") &&
    typeof value.text === "string"
  );
}

function normalizeConversation(value) {
  if (!value || typeof value.id !== "string" || !Array.isArray(value.messages)) {
    return null;
  }
  return {
    id: value.id,
    serverConversationId:
      typeof value.serverConversationId === "string"
        ? value.serverConversationId
        : null,
    title:
      typeof value.title === "string" && value.title.trim()
        ? value.title
        : "New chat",
    messages: value.messages.filter(isMessage),
    createdAt: Number(value.createdAt) || Date.now(),
    updatedAt: Number(value.updatedAt) || Date.now(),
  };
}

export function loadChats() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;

    const parsed = JSON.parse(raw);
    if (!parsed || !Array.isArray(parsed.conversations)) return null;

    const conversations = parsed.conversations
      .map(normalizeConversation)
      .filter(Boolean);
    if (conversations.length === 0) return null;

    const activeId = conversations.some((c) => c.id === parsed.activeId)
      ? parsed.activeId
      : conversations[0].id;
    return { conversations, activeId };
  } catch {
    // Corrupt or unreadable storage must never break the app.
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore: storage may be disabled entirely.
    }
    return null;
  }
}

export function saveChats(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // Quota or privacy mode: keep working with in-memory state only.
  }
}
