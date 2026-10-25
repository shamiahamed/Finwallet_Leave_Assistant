function formatUpdated(timestamp) {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function Sidebar({
  open,
  conversations,
  activeId,
  onNewChat,
  onSelect,
  onDelete,
  busy,
}) {
  const recent = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);

  return (
    <aside className={`sidebar ${open ? "open" : "collapsed"}`}>
      <div className="sidebar-inner">
        <div className="sidebar-brand">
          <span className="brand-icon small" aria-hidden="true">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L14.2 8.8L21 9.5L16 14.2L17.5 21L12 17.5L6.5 21L8 14.2L3 9.5L9.8 8.8L12 2Z"
                fill="#D97757"
              />
            </svg>
          </span>
          <span className="sidebar-brand-text">Finwallet</span>
        </div>

        <button
          type="button"
          className="sidebar-new-btn"
          onClick={onNewChat}
          disabled={busy}
        >
          <span aria-hidden="true">+</span> New Chat
        </button>

        <div className="sidebar-section-label">Recent conversations</div>
        <nav className="conversation-list" aria-label="Conversation history">
          {recent.map((conversation) => (
            <div
              key={conversation.id}
              className={`conversation-item ${
                conversation.id === activeId ? "active" : ""
              }`}
            >
              <button
                type="button"
                className="conversation-select"
                onClick={() => onSelect(conversation.id)}
                title={conversation.title}
              >
                <span className="conversation-title">{conversation.title}</span>
                <span className="conversation-meta">
                  {conversation.messages.length} message
                  {conversation.messages.length === 1 ? "" : "s"} ·{" "}
                  {formatUpdated(conversation.updatedAt)}
                </span>
              </button>
              <button
                type="button"
                className="conversation-delete"
                onClick={() => onDelete(conversation.id)}
                disabled={busy}
                title="Delete conversation"
                aria-label={`Delete conversation: ${conversation.title}`}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                  <path d="M10 11v6M14 11v6" />
                  <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                </svg>
              </button>
            </div>
          ))}
        </nav>

        <p className="sidebar-note">
          Chats are saved in this browser. Assistant memory resets when the
          backend restarts.
        </p>
      </div>
    </aside>
  );
}

export default Sidebar;
