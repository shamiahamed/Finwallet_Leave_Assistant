import { useEffect, useRef, useState } from "react";
import { BotAvatar } from "./Avatar";
import MessageItem from "./MessageItem";
import WelcomeScreen from "./WelcomeScreen";

export default function ChatWindow({ messages, loading, onSelectPrompt, onRetry }) {
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

  return (
    <div className="chat-window">
      {messages.length === 0 ? (
        <WelcomeScreen onSelectPrompt={onSelectPrompt} />
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