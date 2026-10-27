import { formatDate, getSeverityClass } from "../utils/securityUtils";

export function FindingsList({ findings }) {
  if (findings.length === 0) {
    return (
      <div className="security-empty">
        <span className="empty-check">✓</span>
        <strong>No current findings</strong>
        <p>No findings were reported by the latest scan.</p>
      </div>
    );
  }

  return (
    <div className="security-findings-list">
      {findings.map((finding, index) => (
        <article
          className={`security-finding finding-${getSeverityClass(finding.severity)}`}
          key={finding.id ?? `${finding.title}-${index}`}
        >
          <div className="finding-severity-rail" />

          <div className="finding-body">
            <div className="finding-topline">
              <span className="finding-category">
                {(finding.category ?? "general")
                  .replaceAll("_", " ")
                  .toUpperCase()}
              </span>
            </div>

            <h4>{finding.title}</h4>
            <p className="finding-evidence">{finding.evidence}</p>

            <div className="finding-recommendation">
              <span className="recommendation-icon">↗</span>
              <div>
                <strong>Recommended action</strong>
                <p>{finding.recommendation}</p>
              </div>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

export function ScanHistory({ history }) {
  if (history.length === 0) {
    return (
      <p className="security-muted">No scan history available yet.</p>
    );
  }

  return (
    <div className="security-timeline">
      {history.map((scan, index) => (
        <div
          className="timeline-item"
          key={`${scan.timestamp}-${index}`}
        >
          <span
            className={`timeline-dot ${
              scan.status === "ok" ? "success" : "warning"
            }`}
          />
          <div className="timeline-content">
            <div className="timeline-title">
              <strong>
                {scan.status === "ok"
                  ? "Security scan completed"
                  : "Security scan issue"}
              </strong>
              <span
                className={`history-status ${
                  scan.status === "ok" ? "success" : "warning"
                }`}
              >
                {scan.status}
              </span>
            </div>
            <p>
              {scan.finding_count ?? 0} findings ·{" "}
              {scan.checks_run ?? 0} checks
            </p>
            <time>{formatDate(scan.timestamp)}</time>
          </div>
        </div>
      ))}
    </div>
  );
}

export function RecentEvents({ events }) {
  if (events.length === 0) {
    return (
      <p className="security-muted">
        No monitoring events recorded yet.
      </p>
    );
  }

  return (
    <div className="security-events-list">
      {events.map((event) => (
        <article className="security-event" key={event.id}>
          <div className="event-icon">•</div>
          <div className="event-content">
            <div className="event-title-row">
              <strong>
                {(event.type ?? "event")
                  .replaceAll(".", " ")
                  .replaceAll("_", " ")}
              </strong>
            </div>
            <p>{event.message}</p>
            <time>{formatDate(event.timestamp)}</time>
          </div>
        </article>
      ))}
    </div>
  );
}