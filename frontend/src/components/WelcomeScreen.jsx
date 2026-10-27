export default function WelcomeScreen({ onSelectPrompt }) {
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
  );
}