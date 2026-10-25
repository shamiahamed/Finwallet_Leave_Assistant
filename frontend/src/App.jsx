import { useEffect, useRef, useState } from "react";
import ChatInput from "./components/ChatInput";
import ChatWindow from "./components/ChatWindow";
import DatasetPanel from "./components/DatasetPanel";
import SecurityPanel from "./components/SecurityPanel";
import Sidebar from "./components/Sidebar";
import {
  createConversation,
  createId,
  loadChats,
  saveChats,
} from "./services/chatStorage";
import { streamQuestion } from "./services/chatService";
import "./index.css";

function titleFromQuestion(question) {
  const clean = question.replace(/\s+/g, " ").trim();
  return clean.length > 48 ? `${clean.slice(0, 48)}…` : clean;
}

function App() {
  const [chatState, setChatState] = useState(() => {
    const saved = loadChats();
    if (saved) return saved;
    const conversation = createConversation();
    return { conversations: [conversation], activeId: conversation.id };
  });
  const [loadingId, setLoadingId] = useState(null);
  const [datasetId, setDatasetId] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(
    () => window.innerWidth > 768
  );
  const abortRef = useRef(null);

  const { conversations, activeId } = chatState;
  const activeConversation =
    conversations.find((c) => c.id === activeId) ?? conversations[0];
  const messages = activeConversation?.messages ?? [];
  const sending = loadingId !== null;

  // Persist visible history when no answer is streaming; saving every chunk
  // would rewrite storage dozens of times per response.
  useEffect(() => {
    const streaming = chatState.conversations.some((c) =>
      c.messages.some((m) => m.streaming)
    );
    if (!streaming) saveChats(chatState);
  }, [chatState]);

  // Closing the page mid-stream cancels the request and tells the backend
  // not to store an incomplete answer.
  useEffect(() => () => abortRef.current?.abort(), []);

  function updateConversation(id, updater) {
    setChatState((prev) => ({
      ...prev,
      conversations: prev.conversations.map((c) =>
        c.id === id ? updater(c) : c
      ),
    }));
  }

  async function sendQuestion(
    question,
    conversationId,
    { retry = false, attachments = [], datasetId: datasetOverride } = {}
  ) {
    const trimmed = question.trim();
    if (!trimmed || loadingId) return;

    const datasetForRequest = datasetOverride ?? datasetId;

    const target = conversations.find((c) => c.id === conversationId);
    if (!target) return;

    if (retry) {
      // The user question is already stored; drop only the failed answer.
      updateConversation(conversationId, (c) => ({
        ...c,
        messages: c.messages.filter((m) => !m.isError && !m.streaming),
        updatedAt: Date.now(),
      }));
    } else {
      updateConversation(conversationId, (c) => ({
        ...c,
        title: c.messages.some((m) => m.role === "user")
          ? c.title
          : titleFromQuestion(trimmed),
        messages: [
          ...c.messages,
          {
            id: createId(),
            role: "user",
            text: trimmed,
            attachments,
            timestamp: new Date().toISOString(),
          },
        ],
        updatedAt: Date.now(),
      }));
    }

    setLoadingId(conversationId);
    const controller = new AbortController();
    abortRef.current = controller;
    let assistantId = null;

    try {
      await streamQuestion(trimmed, target.serverConversationId, {
        signal: controller.signal,
        datasetId: datasetForRequest,
        onStart: (data) => {
          assistantId = createId();
          updateConversation(conversationId, (c) => ({
            ...c,
            serverConversationId:
              data?.conversation_id ?? c.serverConversationId,
            messages: [
              ...c.messages.filter((m) => !m.isError && !m.streaming),
              {
                id: assistantId,
                role: "assistant",
                text: "",
                streaming: true,
                timestamp: new Date().toISOString(),
              },
            ],
            updatedAt: Date.now(),
          }));
        },
        onChunk: (text) => {
          if (!assistantId) return;
          updateConversation(conversationId, (c) => ({
            ...c,
            messages: c.messages.map((m) =>
              m.id === assistantId ? { ...m, text: m.text + text } : m
            ),
          }));
        },
        onComplete: (data) => {
          const targetId = assistantId ?? createId();
          assistantId = targetId;
          updateConversation(conversationId, (c) => {
            const finalized = {
              id: targetId,
              role: "assistant",
              text: data?.answer || "No response received.",
              streaming: false,
              intent: data?.intent,
              data: data?.data,
              evidence: data?.evidence,
              metrics: data?.metrics,
              timestamp: new Date().toISOString(),
            };
            const exists = c.messages.some((m) => m.id === targetId);

            return {
              ...c,
              serverConversationId:
                data?.conversation_id ?? c.serverConversationId,
              messages: exists
                ? c.messages.map((m) =>
                    m.id === targetId ? finalized : m
                  )
                : [...c.messages.filter((m) => !m.isError), finalized],
              updatedAt: Date.now(),
            };
          });
        },
      });
    } catch (error) {
      // An abort only happens on unmount; the UI is already gone.
      if (error.name === "AbortError") return;

      const isRateLimited = error.status === 429 || error.code === "rate_limit";
      // Store everything a retry needs so it can re-send the exact request.
      updateConversation(conversationId, (c) => ({
        ...c,
        messages: [
          ...c.messages.filter((m) => !m.isError && m.id !== assistantId),
          {
            id: createId(),
            role: "assistant",
            text: error.message || "Failed to reach the backend.",
            isError: true,
            rateLimited: isRateLimited,
            retryAfterSeconds: error.retryAfterSeconds ?? null,
            retryQuestion: trimmed,
            retryAttachments: attachments,
            retryDatasetId: datasetForRequest,
            timestamp: new Date().toISOString(),
          },
        ],
        updatedAt: Date.now(),
      }));
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setLoadingId(null);
    }
  }

  function handleSend(question, attachments = []) {
    if (!activeConversation) return;
    sendQuestion(question, activeConversation.id, { attachments });
  }

  function handleRetry(message) {
    // Ignore clicks while a request is already in flight so retries cannot stack.
    if (!activeConversation || !message.retryQuestion || sending) return;
    sendQuestion(message.retryQuestion, activeConversation.id, {
      retry: true,
      attachments: message.retryAttachments ?? [],
      datasetId: message.retryDatasetId ?? null,
    });
  }

  function handleNewChat() {
    if (sending) return;
    const conversation = createConversation();
    setChatState((prev) => ({
      conversations: [
        conversation,
        ...prev.conversations.filter((c) => c.messages.length > 0),
      ],
      activeId: conversation.id,
    }));
  }

  function handleSelectConversation(id) {
    setChatState((prev) => ({ ...prev, activeId: id }));
    if (window.innerWidth <= 768) setSidebarOpen(false);
  }

  function handleDeleteConversation(id) {
    if (loadingId === id) return;

    setChatState((prev) => {
      const remaining = prev.conversations.filter((c) => c.id !== id);
      if (remaining.length === 0) {
        const conversation = createConversation();
        return { conversations: [conversation], activeId: conversation.id };
      }
      return {
        conversations: remaining,
        activeId: prev.activeId === id ? remaining[0].id : prev.activeId,
      };
    });
  }

  return (
    <div className="app-layout">
      <Sidebar
        open={sidebarOpen}
        conversations={conversations}
        activeId={activeId}
        onNewChat={handleNewChat}
        onSelect={handleSelectConversation}
        onDelete={handleDeleteConversation}
        busy={sending}
      />

      <div className="app-container">
        <header className="app-header">
          <div className="header-left">
            <button
              type="button"
              className="icon-btn"
              onClick={() => setSidebarOpen((open) => !open)}
              title="Toggle sidebar"
              aria-label="Toggle sidebar"
            >
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>

            <div className="header-brand">
              <div className="brand-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M12 2L14.2 8.8L21 9.5L16 14.2L17.5 21L12 17.5L6.5 21L8 14.2L3 9.5L9.8 8.8L12 2Z"
                    fill="#D97757"
                  />
                </svg>
              </div>
              <div>
                <h1 className="brand-title">Finwallet Leave Assistant</h1>
                <p className="brand-subtitle">
                  Internal Leave &amp; Workforce Intelligence
                </p>
              </div>
            </div>
          </div>

          <div className="header-actions">
            <DatasetPanel
              selectedDatasetId={datasetId}
              onSelectDataset={setDatasetId}
            />
            <SecurityPanel />
            <div className="status-badge">
              <span className="status-dot" />
              <span>Connected</span>
            </div>
            <button
              type="button"
              className="new-chat-btn"
              onClick={handleNewChat}
              disabled={sending}
            >
              + New Chat
            </button>
          </div>
        </header>

        <main className="main-content">
          <ChatWindow
            messages={messages}
            loading={loadingId === activeId}
            onSelectPrompt={handleSend}
            onRetry={handleRetry}
          />
        </main>

        <footer className="footer-area">
          <ChatInput
            onSend={handleSend}
            loading={loadingId === activeId}
            disabled={sending}
          />
        </footer>
      </div>

      {sidebarOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}
    </div>
  );
}

export default App;
