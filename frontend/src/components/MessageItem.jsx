import { useState } from "react";
import { BotAvatar } from "./Avatar";
import { suggestedFollowUps } from "../services/suggestions";

function formatClock(timestamp) {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function MessageItem({ message, isLast, onRetry, onSelectPrompt }) {
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
        {!isUser && <BotAvatar />}
      </div>
    </div>
  );
}