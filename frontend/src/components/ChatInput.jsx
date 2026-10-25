import { useState, useRef, useEffect } from "react";
import { deleteDocument, uploadDocument } from "../services/documentService";

const ACCEPTED = ".pdf,.txt,.md";

function AttachmentChip({ attachment, onRemove }) {
  const { name, status, error } = attachment;
  const label =
    status === "uploading"
      ? "Uploading…"
      : status === "error"
      ? error || "Upload failed"
      : name;

  return (
    <span
      className={`attachment-chip attachment-${status}`}
      title={status === "error" ? error : name}
    >
      <span className="attachment-icon" aria-hidden="true">
        {status === "uploading" ? (
          <span className="attachment-spinner" />
        ) : status === "error" ? (
          "!"
        ) : (
          "📄"
        )}
      </span>
      <span className="attachment-name">{label}</span>
      {status !== "uploading" && (
        <button
          type="button"
          className="attachment-remove"
          onClick={() => onRemove(attachment)}
          aria-label={`Remove ${name}`}
          title="Remove"
        >
          ×
        </button>
      )}
    </span>
  );
}

function ChatInput({ onSend, loading, disabled }) {
  const [question, setQuestion] = useState("");
  const [attachments, setAttachments] = useState([]);
  const textareaRef = useRef(null);
  const fileRef = useRef(null);
  const blocked = loading || disabled;

  // Block sending while any attachment is still uploading so ids stay valid.
  const uploading = attachments.some((a) => a.status === "uploading");
  const readyAttachments = attachments.filter((a) => a.status === "ready");

  // Adjust height as user types
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [question]);

  // Submit question when form is submitted
  const handleSubmit = (e) => {
    if (e) e.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || blocked || uploading) return;

    onSend(
      trimmed,
      readyAttachments.map((a) => ({
        documentId: a.documentId,
        name: a.name,
      }))
    );
    // Clear the draft and chips now that the question has been handed off.
    setQuestion("");
    setAttachments([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  // Submit on Enter, allow Shift+Enter for new line
  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  async function handleAttach(event) {
    const files = Array.from(event.target.files || []);
    // Reset the input so re-selecting the same file fires change again.
    if (fileRef.current) fileRef.current.value = "";
    if (files.length === 0) return;

    for (const file of files) {
      const localId = `${file.name}-${Date.now()}-${Math.random()}`;
      setAttachments((prev) => [
        ...prev,
        { localId, name: file.name, status: "uploading" },
      ]);
      try {
        const result = await uploadDocument(file);
        setAttachments((prev) =>
          prev.map((a) =>
            a.localId === localId
              ? {
                  ...a,
                  status: "ready",
                  documentId: result.document.document_id,
                  name: result.document.name,
                }
              : a
          )
        );
      } catch (err) {
        setAttachments((prev) =>
          prev.map((a) =>
            a.localId === localId
              ? { ...a, status: "error", error: err.message }
              : a
          )
        );
      }
    }
  }

  function removeAttachment(attachment) {
    // Best-effort server cleanup once the upload succeeded.
    if (attachment.status === "ready" && attachment.documentId) {
      deleteDocument(attachment.documentId).catch(() => {});
    }
    setAttachments((prev) => prev.filter((a) => a.localId !== attachment.localId));
  }

  return (
    <form className="chat-input-area" onSubmit={handleSubmit}>
      <div className="input-wrapper">
        {attachments.length > 0 && (
          <div className="attachment-row">
            {attachments.map((attachment) => (
              <AttachmentChip
                key={attachment.localId}
                attachment={attachment}
                onRemove={removeAttachment}
              />
            ))}
          </div>
        )}

        <textarea
          ref={textareaRef}
          rows={1}
          placeholder="Ask about leave balances, policies, or requests..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={blocked}
          aria-label="Ask a question"
        />
        <div className="input-footer">
          <div className="input-footer-left">
            <input
              ref={fileRef}
              type="file"
              accept={ACCEPTED}
              multiple
              onChange={handleAttach}
              disabled={blocked}
              hidden
            />
            <button
              type="button"
              className="attach-btn"
              onClick={() => fileRef.current?.click()}
              disabled={blocked}
              title="Attach a policy document (.pdf, .txt, .md)"
              aria-label="Attach a document"
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
                <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
              </svg>
            </button>
            <span className="input-hint">
              <span>Enter</span> to send, <span>Shift + Enter</span> for new line
            </span>
          </div>
          <button
            type="submit"
            className={`send-btn ${question.trim() && !blocked && !uploading ? "active" : ""}`}
            disabled={blocked || uploading || !question.trim()}
            title="Send"
          >
            {loading ? (
              <span className="spinner" />
            ) : (
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="19" x2="12" y2="5" />
                <polyline points="5 12 12 5 19 12" />
              </svg>
            )}
          </button>
        </div>
      </div>
      <p className="input-disclaimer">
        Finwallet Assistant verifies deterministic answers directly from company leave records.
      </p>
    </form>
  );
}

export default ChatInput;
