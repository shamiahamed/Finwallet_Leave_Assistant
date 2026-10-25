
/**
 * Security and monitoring API services.
 *
 * These endpoints provide read-only security findings,
 * background monitoring status, scan history, and events.
 */

const API_BASE = "/api/v1";

/**
 * Shared helper for handling API responses.
 */
async function fetchMonitoringData(endpoint, errorMessage) {
  let response;

  try {
    response = await fetch(`${API_BASE}${endpoint}`);
  } catch {
    throw new Error(
      "Cannot connect to the backend. Make sure FastAPI is running."
    );
  }

  if (!response.ok) {
    throw new Error(
      `${errorMessage} (HTTP ${response.status})`
    );
  }

  try {
    return await response.json();
  } catch {
    throw new Error("The backend returned an invalid response.");
  }
}

/**
 * Run an on-demand security review.
 * GET /api/v1/security/review
 */
export async function getSecurityReview() {
  return fetchMonitoringData(
    "/security/review",
    "Security review unavailable"
  );
}

/**
 * Retrieve the background monitoring status and current findings.
 * GET /api/v1/security/monitoring
 */
export async function getMonitoringStatus() {
  return fetchMonitoringData(
    "/security/monitoring",
    "Could not load monitoring status"
  );
}

/**
 * Retrieve the background scan history.
 * GET /api/v1/security/history
 */
export async function getMonitoringHistory() {
  return fetchMonitoringData(
    "/security/history",
    "Could not load scan history"
  );
}

/**
 * Retrieve recent monitoring events and event counts.
 * GET /api/v1/security/events
 */
export async function getMonitoringEvents() {
  return fetchMonitoringData(
    "/security/events",
    "Could not load monitoring events"
  );
}
