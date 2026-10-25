import { consumeSSE } from "./sse";

// API endpoints for chat queries
const API_BASE = "/api/v1";
const API_URL = `${API_BASE}/chat`;
const STREAM_URL = `${API_BASE}/chat/stream`;

async function readError(response) {
  let data = null;
  try {
    data = await response.json();
  } catch {
    // Non-JSON error body: fall back to the generic message.
  }

  let message = data?.error?.message;
  if (!message && data?.error?.details?.errors) {
    message = data.error.details.errors
      .map((e) => (e.field ? `${e.field}: ${e.message}` : e.message))
      .join("; ");
  }
  if (!message && data?.detail) {
    if (typeof data.detail === "string") {
      message = data.detail;
    } else if (Array.isArray(data.detail)) {
      message = data.detail
        .map((e) => e.msg || e.message || (typeof e === "string" ? e : JSON.stringify(e)))
        .join("; ");
    } else if (typeof data.detail === "object") {
      message = data.detail.message || data.detail.msg || JSON.stringify(data.detail);
    }
  }
  if (!message) {
    message = response.statusText || "Failed to get answer";
  }

  return { message, code: data?.error?.code || null };
}

// Build an Error carrying the HTTP status, backend error code, and the
// provider's Retry-After hint so the UI can treat a rate limit differently.
function httpError(response, { message, code }) {
  const error = new Error(message);
  error.status = response.status;
  error.code = code;

  // The rate limit may arrive as HTTP 429 or as a provider message.
  if (
    response.status === 429 ||
    code === "rate_limit" ||
    /rate limit/i.test(message)
  ) {
    error.code = "rate_limit";
  }

  const retryAfter = response.headers.get("Retry-After");
  if (retryAfter) {
    const seconds = Number(retryAfter);
    error.retryAfterSeconds = Number.isFinite(seconds) ? seconds : null;
  }
  return error;
}

export async function askQuestion(question, conversationId = null, datasetId = null) {
  // Send user question and optional conversation ID to the backend
  const payload = { question };
  if (conversationId) {
    payload.conversation_id = conversationId;
  }

  const headers = { "Content-Type": "application/json" };
  if (datasetId) {
    headers["X-Dataset-Id"] = datasetId;
  }

  const response = await fetch(API_URL, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw httpError(response, await readError(response));
  }

  return response.json();
}

export async function streamQuestion(
  question,
  conversationId = null,
  { signal, onStart, onChunk, onComplete, datasetId } = {}
) {
  const payload = { question };
  if (conversationId) {
    payload.conversation_id = conversationId;
  }

  const headers = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (datasetId) {
    headers["X-Dataset-Id"] = datasetId;
  }

  const response = await fetch(STREAM_URL, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) {
    throw httpError(response, await readError(response));
  }

  if (!response.body) {
    throw new Error("Streaming is not supported by this browser.");
  }

  await consumeSSE(response.body, { onStart, onChunk, onComplete });
}
