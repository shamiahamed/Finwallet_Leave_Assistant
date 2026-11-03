import { useState } from "react";

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
  onTogglePin,
  busy,
}) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");

  const filtered = conversations.filter((c) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    if (c.title?.toLowerCase().includes(q)) return true;
    return (c.messages || []).some((m) => m.text?.toLowerCase().includes(q));
  });

  const handleSelect = (id) => {
    onSelect(id);
    setSearchOpen(false);
    setQuery("");
  };

  const renderConversation = (conversation) => (
    <div
      key={conversation.id}
      className={`conversation-item ${conversation.id === activeId ? "active" : ""}`}
    >
      <button
        type="button"
        className="conversation-select"
        onClick={() => handleSelect(conversation.id)}
        title={conversation.title}
      >
        <span className="conversation-title">
          {conversation.title}
        </span>
        <span className="conversation-meta">
          {conversation.messages.length} message
          {conversation.messages.length === 1 ? "" : "s"} ·{" "}
          {formatUpdated(conversation.updatedAt)}
        </span>
      </button>
      <button
        type="button"
        className="conversation-pin"
        onClick={() => onTogglePin?.(conversation.id)}
        disabled={busy}
        title={conversation.pinned ? "Unpin" : "Pin"}
        aria-label={`${conversation.pinned ? "Unpin" : "Pin"} conversation: ${conversation.title}`}
        style={{ background: "transparent", border: "none", cursor: "pointer", fontSize: 14, color: "#6B665E", padding: 4 }}
      >
        {conversation.pinned ? "📌" : "📍"}
      </button>
      <button
        type="button"
        className="conversation-delete"
        onClick={() => onDelete(conversation.id)}
        disabled={busy}
        title="Delete conversation"
        aria-label={`Delete conversation: ${conversation.title}`}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          <path d="M10 11v6M14 11v6" />
          <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
        </svg>
      </button>
    </div>
  );

  const recent = [...conversations].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
    return b.updatedAt - a.updatedAt;
  });

  return (
    <aside className={`sidebar ${open ? "open" : "collapsed"}`}>
      <div className="sidebar-inner">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 6px 8px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
            <span className="brand-icon small" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                <path d="M12 2L14.2 8.8L21 9.5L16 14.2L17.5 21L12 17.5L6.5 21L8 14.2L3 9.5L9.8 8.8L12 2Z" fill="#D97757" />
              </svg>
            </span>
            <span className="sidebar-brand-text" style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>Finwallet</span>
          </div>
          <button
            type="button"
            onClick={() => setSearchOpen(true)}
            aria-label="Search conversations"
            title="Search conversations"
            style={{ background: "transparent", border: "none", cursor: "pointer", fontSize: 16, color: "#6B665E", padding: 8, margin: -8, borderRadius: 8, flexShrink: 0 }}
          >
            🔍
          </button>
        </div>

        <button type="button" className="sidebar-new-btn" onClick={onNewChat} disabled={busy}>
          <span aria-hidden="true">+</span> New Chat
        </button>

        <div className="sidebar-section-label">Recent conversations</div>
        <nav className="conversation-list" aria-label="Conversation history">
          {recent.length === 0 ? (
            <p className="sidebar-empty">No conversations found.</p>
          ) : (
            recent.map(renderConversation)
          )}
        </nav>

        <p className="sidebar-note">
          Chats are saved in this browser. Assistant memory resets when the
          backend restarts.
        </p>
      </div>

      {searchOpen && (
        <div
          onClick={() => setSearchOpen(false)}
          style={{
            position: "fixed", inset: 0, background: "rgba(36,34,32,0.28)",
            display: "flex", alignItems: "flex-start", justifyContent: "center",
            paddingTop: "10vh", zIndex: 100,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(560px, 92vw)", background: "#fff", borderRadius: 12,
              border: "1px solid #E8E3DA", boxShadow: "0 10px 30px rgba(36,34,32,0.18)",
              padding: 16,
              margin: "0 12px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search chats"
                aria-label="Search conversations"
                autoFocus
                style={{ flex: 1, padding: "10px 12px", border: "1px solid #DDD7CD", borderRadius: 8, fontSize: 14 }}
              />
              <button type="button" onClick={() => { setSearchOpen(false); setQuery(""); }} aria-label="Close search" style={{ background: "transparent", border: "none", cursor: "pointer", fontSize: 18, color: "#6B665E", padding: 4 }}>
                ✕
              </button>
            </div>
            <div style={{ maxHeight: "60vh", overflowY: "auto" }}>
              {filtered.length === 0 ? (
                <p style={{ color: "#6B665E", fontSize: 14, padding: 8 }}>No results found.</p>
              ) : (
                filtered.map(renderConversation)
              )}
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

export default Sidebar;
