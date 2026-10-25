// Document upload, listing, and removal API calls for retrieval (RAG).
const API_BASE = "/api/v1";

async function errorMessage(response) {
  let data = null;
  try {
    data = await response.json();
  } catch {
    // Non-JSON error body: fall back to the generic message.
  }
  return data?.error?.message || data?.detail || "Request failed";
}

export async function listDocuments() {
  const response = await fetch(`${API_BASE}/documents`);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function uploadDocument(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/documents/upload`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function deleteDocument(documentId) {
  const response = await fetch(
    `${API_BASE}/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}
