import { useEffect, useRef, useState } from "react";

function BotAvatar() {
  return (
    <div className="bot-avatar" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
        <path
          d="M12 2L14.2 8.8L21 9.5L16 14.2L17.5 21L12 17.5L6.5 21L8 14.2L3 9.5L9.8 8.8L12 2Z"
          fill="currentColor"
        />
      </svg>
    </div>
  );
}

function UserAvatar() {
  return (
    <div className="user-avatar" aria-hidden="true">
      <span>You</span>
    </div>
  );
}

function formatClock(timestamp) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Suggestions are deterministic per intent and use only employee IDs that the
// backend already verified in this answer, so every chip is answerable.
import { suggestedFollowUps } from "../services/suggestions";

function MessageItem({ message, isLast, onRetry, onSelectPrompt }) {
  const [copied, setCopied] = useState(false);
  const [showSources, setShowSources] = useState(false);

  const handleCopy = () => {
    if (message.text) {
      navigator.clipboard.writeText(message.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const isUser = message.role === "user";
  const isError = message.isError;
  const isStreaming = message.streaming;
  const hasSources = message.evidence || message.intent || message.metrics;

  return (
    <div className={`message-row ${isUser ? "user-row" : "bot-row"}`}>
      <div className="message-container">
        {!isUser && <BotAvatar />}
        <div
          className={`message-bubble ${isUser ? "user-bubble" : "bot-bubble"
            } ${isError ? "error-bubble" : ""}`}
          aria-busy={isStreaming || undefined}
        >
          <div className="message-content">
            {message.text}
            {isStreaming && (
              <span className="streaming-caret" aria-hidden="true" />
            )}
          </div>

          {isUser && message.attachments?.length > 0 && (
            <div className="message-attachments">
              {message.attachments.map((attachment) => (
                <span
                  key={attachment.documentId}
                  className="message-attachment-chip"
                  title={attachment.name}
                >
                  <span aria-hidden="true">📄</span> {attachment.name}
                </span>
              ))}
            </div>
          )}

          {message.timestamp && (
            <div className="message-time">{formatClock(message.timestamp)}</div>
          )}

          {!isUser && !isStreaming && (
            <div className="message-actions">
              {!isError && (
                <button
                  type="button"
                  className="action-btn"
                  onClick={handleCopy}
                  title="Copy text"
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              )}

              {!isError && hasSources && (
                <button
                  type="button"
                  className="action-btn"
                  onClick={() => setShowSources(!showSources)}
                >
                  {showSources ? "Hide Details" : "View Details"}
                </button>
              )}

              {!isError && message.metrics && (
                <span
                  className="metrics-badge"
                  title="LLM request latency and token usage"
                >
                  ⚡ {Math.round(message.metrics.latency_ms)}ms
                  {message.metrics.total_tokens != null &&
                    ` · ${message.metrics.total_tokens} tokens`}
                </span>
              )}

              {isError && isLast && message.retryQuestion && (
                <>
                  <button
                    type="button"
                    className="action-btn retry-btn"
                    onClick={() => onRetry(message)}
                  >
                    Retry
                  </button>
                  {message.rateLimited && (
                    <span className="retry-hint">
                      Provider is busy
                      {message.retryAfterSeconds
                        ? ` — wait about ${message.retryAfterSeconds}s`
                        : " — wait a few seconds"}
                    </span>
                  )}
                </>
              )}
            </div>
          )}

          {!isUser &&
            isLast &&
            !isError &&
            !isStreaming &&
            suggestedFollowUps(message).length > 0 && (
              <div className="suggestions">
                {suggestedFollowUps(message).map((question) => (
                  <button
                    key={question}
                    type="button"
                    className="suggestion-chip"
                    onClick={() => onSelectPrompt(question)}
                  >
                    {question}
                  </button>
                ))}
              </div>
            )}

          {!isUser && hasSources && showSources && (
            <div className="sources-panel">
              <div className="source-row">
                <span className="source-label">Intent:</span>
                <code className="source-tag">{message.intent}</code>
              </div>

              {message.metrics && (
                <>
                  <div className="source-row">
                    <span className="source-label">Latency:</span>
                    <span className="source-text">
                      {message.metrics.latency_ms} ms
                    </span>
                  </div>
                  <div className="source-row">
                    <span className="source-label">Tokens:</span>
                    <div className="source-chips">
                      <span className="source-chip" title="Prompt Tokens">
                        Prompt: {message.metrics.prompt_tokens ?? "N/A"}
                      </span>
                      <span className="source-chip" title="Completion Tokens">
                        Completion: {message.metrics.completion_tokens ?? "N/A"}
                      </span>
                      <span className="source-chip" title="Total Tokens">
                        Total: {message.metrics.total_tokens ?? "N/A"}
                      </span>
                    </div>
                  </div>
                </>
              )}

              {message.evidence?.worksheets?.length > 0 && (
                <div className="source-row">
                  <span className="source-label">Worksheets:</span>
                  <div className="source-chips">
                    {message.evidence.worksheets.map((sheet, idx) => (
                      <span key={idx} className="source-chip">
                        {sheet}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {message.evidence?.employee_ids?.length > 0 && (
                <div className="source-row">
                  <span className="source-label">Employees:</span>
                  <span className="source-text">
                    {message.evidence.employee_ids.join(", ")}
                  </span>
                </div>
              )}
              {message.evidence?.request_ids?.length > 0 && (
                <div className="source-row">
                  <span className="source-label">Requests:</span>
                  <span className="source-text">
                    {message.evidence.request_ids.slice(0, 10).join(", ")}
                    {message.evidence.request_ids.length > 10 &&
                      ` +${message.evidence.request_ids.length - 10} more`}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
        {isUser && <UserAvatar />}
      </div>
    </div>
  );
}

function ChatWindow({ messages, loading, onSelectPrompt, onRetry }) {
  const bottomRef = useRef(null);
  const [showScrollBottom, setShowScrollBottom] = useState(false);

  useEffect(() => {
    const container = document.querySelector(".main-content");
    if (!container) return;

    const handleScroll = () => {
      const isScrolledUp =
        container.scrollHeight - container.scrollTop - container.clientHeight >
        100;
      setShowScrollBottom(isScrolledUp);
    };

    container.addEventListener("scroll", handleScroll);
    return () => container.removeEventListener("scroll", handleScroll);
  }, []);

  useEffect(() => {
    const container = document.querySelector(".main-content");
    const isUserMsg = messages[messages.length - 1]?.role === "user";
    const isNearBottom =
      !container ||
      container.scrollHeight - container.scrollTop - container.clientHeight <
      150;

    if (isUserMsg || isNearBottom || loading) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, loading]);

  const lastMessage = messages[messages.length - 1];
  const streamingMessage =
    lastMessage?.role === "assistant" && lastMessage.streaming;

  const samplePrompts = [
    {
      icon: "💳",
      title: "Check Leave Balance",
      prompt: "What is Arun Kumar's leave balance?",
    },
    {
      icon: "👥",
      title: "Active Employees",
      prompt: "How many total employees are there in the company?",
    },
    {
      icon: "🌴",
      title: "Current Leaves",
      prompt: "Who is currently on leave in the Engineering department?",
    },
    {
      icon: "📜",
      title: "Leave Policy",
      prompt: "What is the policy for Sick Leave and Casual Leave?",
    },
  ];

  return (
    <div className="chat-window">
      {messages.length === 0 ? (
        <div className="welcome-screen">
          <div className="welcome-icon">
            <svg width="34" height="34" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L14.2 8.8L21 9.5L16 14.2L17.5 21L12 17.5L6.5 21L8 14.2L3 9.5L9.8 8.8L12 2Z"
                fill="#D97757"
              />
            </svg>
          </div>
          <h2>How can I help with leave management today?</h2>
          <p className="welcome-desc">
            Ask natural language questions about balances, leave requests,
            employee records, or policies.
          </p>

          <div className="prompts-grid">
            {samplePrompts.map((item, idx) => (
              <button
                key={idx}
                type="button"
                className="prompt-card"
                onClick={() => onSelectPrompt(item.prompt)}
              >
                <span className="prompt-icon">{item.icon}</span>
                <div className="prompt-info">
                  <div className="prompt-title">{item.title}</div>
                  <div className="prompt-desc">{item.prompt}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="messages-list">
          {messages.map((msg, idx) => (
            <MessageItem
              key={msg.id ?? idx}
              message={msg}
              isLast={idx === messages.length - 1}
              onRetry={onRetry}
              onSelectPrompt={onSelectPrompt}
            />
          ))}

          {loading && !streamingMessage && (
            <div className="message-row bot-row">
              <div className="message-container">
                <BotAvatar />
                <div className="message-bubble bot-bubble thinking-bubble">
                  <div className="thinking-dots">
                    <span className="dot" />
                    <span className="dot" />
                    <span className="dot" />
                  </div>
                  <span className="thinking-text">Thinking...</span>
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {showScrollBottom && (
        <button
          type="button"
          className="scroll-bottom-btn"
          onClick={() =>
            bottomRef.current?.scrollIntoView({ behavior: "smooth" })
          }
          title="Scroll to latest query"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <polyline points="19 12 12 19 5 12" />
          </svg>
        </button>
      )}
    </div>
  );
}

export default ChatWindow;
