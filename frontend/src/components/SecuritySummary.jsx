import { getSeverityClass } from "../utils/securityUtils";

export function SeverityBadge({ severity }) {
  const normalized = getSeverityClass(severity);

  return (
    <span className={`security-badge severity-${normalized}`}>
      <span className="severity-dot" />
      {normalized.toUpperCase()}
    </span>
  );
}

export function SummaryCard({ label, count, severity, description }) {
  return (
    <div className={`security-summary-card card-${severity}`}>
      <div className="summary-card-top">
        <span>{label}</span>
        <span className={`summary-indicator ${severity}`} />
      </div>

      <div className="summary-count">{count}</div>
      <div className="summary-description">{description}</div>
    </div>
  );
}