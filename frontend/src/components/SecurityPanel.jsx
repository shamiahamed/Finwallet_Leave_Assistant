import { useCallback, useEffect, useState } from "react";
import { getMonitoringStatus } from "../services/securityService";
import SecurityDashboard from "./SecurityDashboard";
import "./SecurityPanel.css";

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

  const isRunning = data?.monitoring_enabled === true;

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
          <SecurityDashboard
            data={data}
            error={error}
            loading={loading}
            refreshing={refreshing}
            lastUpdated={lastUpdated}
            onRefresh={refresh}
            onClose={() => setOpen(false)}
          />
        </div>
      )}
    </>
  );
}