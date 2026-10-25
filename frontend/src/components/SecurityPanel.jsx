
import { useCallback, useEffect, useState } from "react";
import { getMonitoringStatus } from "../services/securityService";
import "./SecurityPanel.css";

const SEVERITIES = ["high", "medium", "low", "info"];

function formatDate(value) {
  if (!value) return "Not available";

  const date = new Date(value);

  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString();
}

function getSeverityClass(severity) {
  return SEVERITIES.includes(String(severity).toLowerCase())
    ? String(severity).toLowerCase()
    : "info";
}

function countFindings(findings = [], severity) {
  return findings.filter(
    (finding) =>
      getSeverityClass(finding.severity) === severity
  ).length;
}

function SeverityBadge({ severity }) {
  const normalized = getSeverityClass(severity);

  return (
    <span className={`security-badge severity-${normalized}`}>
      <span className="severity-dot" />
      {normalized.toUpperCase()}
    </span>
  );
}

function SummaryCard({ label, count, severity, description }) {
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

export default function SecurityPanel() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const refresh = useCallback(async (manual = false) => {
    if (manual) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      const result = await getMonitoringStatus();
      setData(result);
      setError("");
      setLastUpdated(new Date().toISOString());
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to load monitoring information."
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;

    refresh();

    const intervalId = window.setInterval(() => {
      refresh();
    }, 30000);

    return () => window.clearInterval(intervalId);
  }, [open, refresh]);

  useEffect(() => {
    if (!open) return;

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const findings = data?.current_findings ?? [];
  const history = [...(data?.history ?? [])].reverse().slice(0, 8);
  const events = [...(data?.events ?? [])].reverse().slice(0, 8);

  const highCount = countFindings(findings, "high");
  const mediumCount = countFindings(findings, "medium");
  const lowCount = countFindings(findings, "low");
  const infoCount = countFindings(findings, "info");

  const isRunning = data?.monitoring_enabled === true;
  const scanStatus = data?.last_scan_status ?? "not_started";

  return (
    <>
      <button
        type="button"
        className="security-launch-button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
      >
        <span className="launch-shield">◆</span>
        <span>Security Monitor</span>
        {data && (
          <span
            className={`launch-status ${isRunning ? "is-running" : ""}`}
          />
        )}
      </button>

      {open && (
        <div
          className="security-overlay"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setOpen(false);
            }
          }}
        >
          <section
            className="security-dashboard"
            role="dialog"
            aria-modal="true"
            aria-labelledby="security-dashboard-title"
          >
            <header className="security-header">
              <div className="security-heading">
                <div className="security-logo">◆</div>
                <div>
                  <div className="security-eyebrow">
                    APPLICATION OPERATIONS
                  </div>
                  <h2 id="security-dashboard-title">
                    Security Center
                  </h2>
                  <p>
                    Security findings, background scans, and application
                    events in one place.
                  </p>
                </div>
              </div>

              <div className="security-header-actions">
                <button
                  type="button"
                  className="security-button secondary"
                  onClick={() => refresh(true)}
                  disabled={refreshing || loading}
                >
                  {refreshing ? "Refreshing..." : "↻ Refresh"}
                </button>

                <button
                  type="button"
                  className="security-close-button"
                  onClick={() => setOpen(false)}
                  aria-label="Close security dashboard"
                >
                  ×
                </button>
              </div>
            </header>

            <div className="security-dashboard-body">
              {error && (
                <div className="security-error" role="alert">
                  <strong>Unable to update dashboard</strong>
                  <span>{error}</span>
                  <button
                    type="button"
                    className="security-button secondary"
                    onClick={() => refresh(true)}
                  >
                    Try again
                  </button>
                </div>
              )}

              <div className="security-status-strip">
                <div className="status-main">
                  <span
                    className={`status-pulse ${isRunning ? "active" : ""}`}
                  />
                  <div>
                    <strong>
                      {isRunning ? "Background monitoring active" : "Monitoring stopped"}
                    </strong>
                    <span>
                      {data?.environment ?? "Environment unavailable"}
                    </span>
                  </div>
                </div>

                <div className="status-meta">
                  <span>Last scan</span>
                  <strong>{formatDate(data?.last_scan_at)}</strong>
                </div>

                <div className="status-meta">
                  <span>Scan result</span>
                  <strong
                    className={
                      scanStatus === "ok"
                        ? "status-text-ok"
                        : "status-text-warning"
                    }
                  >
                    {scanStatus.replaceAll("_", " ").toUpperCase()}
                  </strong>
                </div>

                <div className="status-meta">
                  <span>Scan interval</span>
                  <strong>
                    {Math.round((data?.next_scan_in_seconds ?? 300) / 60)} min
                  </strong>
                </div>
              </div>

              {loading && !data ? (
                <div className="security-loading">
                  <span className="security-spinner" />
                  Loading security data...
                </div>
              ) : (
                <>
                  <div className="security-section-heading">
                    <div>
                      <h3>Security overview</h3>
                      <p>
                        {findings.length} active finding
                        {findings.length === 1 ? "" : "s"} detected
                      </p>
                    </div>
                    <span className="security-updated">
                      Updated {formatDate(lastUpdated)}
                    </span>
                  </div>

                  <div className="security-summary-grid">
                    <SummaryCard
                      label="High severity"
                      count={highCount}
                      severity="high"
                      description="Requires priority review"
                    />
                    <SummaryCard
                      label="Medium severity"
                      count={mediumCount}
                      severity="medium"
                      description="Review and assess"
                    />
                    <SummaryCard
                      label="Low severity"
                      count={lowCount}
                      severity="low"
                      description="Improvement suggested"
                    />
                    <SummaryCard
                      label="Informational"
                      count={infoCount}
                      severity="info"
                      description="Awareness and guidance"
                    />
                  </div>

                  <section className="security-content-section">
                    <div className="security-section-heading">
                      <div>
                        <h3>Current findings</h3>
                        <p>Detected by the latest security review</p>
                      </div>
                      <span className="security-count">
                        {findings.length}
                      </span>
                    </div>

                    {findings.length === 0 ? (
                      <div className="security-empty">
                        <span className="empty-check">✓</span>
                        <strong>No current findings</strong>
                        <p>
                          No findings were reported by the latest scan.
                        </p>
                      </div>
                    ) : (
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
                                <SeverityBadge severity={finding.severity} />
                              </div>

                              <h4>{finding.title}</h4>
                              <p className="finding-evidence">
                                {finding.evidence}
                              </p>

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
                    )}
                  </section>

                  <div className="security-lower-grid">
                    <section className="security-content-section">
                      <div className="security-section-heading">
                        <div>
                          <h3>Scan history</h3>
                          <p>Recent background checks</p>
                        </div>
                      </div>

                      {history.length === 0 ? (
                        <p className="security-muted">
                          No scan history available yet.
                        </p>
                      ) : (
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
                      )}
                    </section>

                    <section className="security-content-section">
                      <div className="security-section-heading">
                        <div>
                          <h3>Recent events</h3>
                          <p>Security alerts and application activity</p>
                        </div>
                      </div>

                      {events.length === 0 ? (
                        <p className="security-muted">
                          No monitoring events recorded yet.
                        </p>
                      ) : (
                        <div className="security-events-list">
                          {events.map((event) => (
                            <article
                              className="security-event"
                              key={event.id}
                            >
                              <div className="event-icon">•</div>
                              <div className="event-content">
                                <div className="event-title-row">
                                  <strong>
                                    {(event.type ?? "event")
                                      .replaceAll(".", " ")
                                      .replaceAll("_", " ")}
                                  </strong>
                                  <SeverityBadge severity={event.severity} />
                                </div>
                                <p>{event.message}</p>
                                <time>{formatDate(event.timestamp)}</time>
                              </div>
                            </article>
                          ))}
                        </div>
                      )}
                    </section>
                  </div>
                </>
              )}
            </div>

            <footer className="security-footer">
              <span>
                Automatic refresh every 30 seconds while this panel is open.
              </span>
              <span>Read-only monitoring · No automatic remediation</span>
            </footer>
          </section>
        </div>
      )}
    </>
  );
}
