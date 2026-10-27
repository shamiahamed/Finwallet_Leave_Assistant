export function BotAvatar() {
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

export function UserAvatar() {
  return (
    <div className="user-avatar" aria-hidden="true">
      <span>You</span>
    </div>
  );
}