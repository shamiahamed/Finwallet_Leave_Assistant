import { useEffect, useRef, useState } from "react";
import { createId, loadChats, saveChats } from "../services/chatStorage";
import { streamQuestion } from "../services/chatService";

function titleFromQuestion(question) {
  const clean = question.replace(/\s+/g, " ").trim();
  return clean.length > 48 ? `${clean.slice(0, 48)}…` : clean;
}

export function useChat() {
  const [chatState, setChatState] = useState(() => {
    const saved = loadChats();
    if (saved) return saved;
    const conversation = createConversation();
    return { conversations: [conversation], activeId: conversation.id };
  });
  const [loadingId, setLoadingId] = useState(null);
  const [datasetId, setDatasetId] = useState(null);
  const abortRef = useRef(null);

  const { conversations, activeId } = chatState;
  const activeConversation =
    conversations.find((c) => c.id === activeId) ?? conversations[0];
  const messages = activeConversation?.messages ?? [];
  const sending = loadingId !== null;

  useEffect(() => {
    const streaming = chatState.conversations.some((c) =>
      c.messages.some((m) => m.streaming)
    );
    if (!streaming) saveChats(chatState);
  }, [chatState]);

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
      if (error.name === "AbortError") return;

      const isRateLimited = error.status === 429 || error.code === "rate_limit";
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

  return {
    chatState,
    setChatState,
    conversations,
    activeId,
    activeConversation,
    messages,
    sending,
    loadingId,
    datasetId,
    setDatasetId,
    handleSend,
    handleRetry,
    handleNewChat,
    handleSelectConversation,
    handleDeleteConversation,
    updateConversation,
    sendQuestion,
  };
}