import { formatDate, countFindings } from "../utils/securityUtils";
import { SummaryCard } from "./SecuritySummary";
import { FindingsList, ScanHistory, RecentEvents } from "./SecurityFindings";

export default function SecurityDashboard({
  data,
  error,
  loading,
  refreshing,
  lastUpdated,
  onRefresh,
  onClose,
}) {
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
            onClick={() => onRefresh(true)}
            disabled={refreshing || loading}
          >
            {refreshing ? "Refreshing..." : "↻ Refresh"}
          </button>

          <button
            type="button"
            className="security-close-button"
            onClick={onClose}
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
              onClick={() => onRefresh(true)}
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
              <FindingsList findings={findings} />
            </section>

            <div className="security-lower-grid">
              <section className="security-content-section">
                <div className="security-section-heading">
                  <div>
                    <h3>Scan history</h3>
                    <p>Recent background checks</p>
                  </div>
                </div>
                <ScanHistory history={history} />
              </section>

              <section className="security-content-section">
                <div className="security-section-heading">
                  <div>
                    <h3>Recent events</h3>
                    <p>Security alerts and application activity</p>
                  </div>
                </div>
                <RecentEvents events={events} />
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
  );
}