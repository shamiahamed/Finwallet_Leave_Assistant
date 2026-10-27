import { useState } from "react";
import ChatInput from "./components/ChatInput";
import ChatWindow from "./components/ChatWindow";
import DatasetPanel from "./components/DatasetPanel";
import SecurityPanel from "./components/SecurityPanel";
import Sidebar from "./components/Sidebar";
import { useChat } from "./hooks/useChat";
import "./index.css";

function App() {
  const {
    conversations,
    activeId,
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
  } = useChat();

  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 768);

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