// Dataset upload, listing, preview, and removal API calls.
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

export async function listDatasets() {
  const response = await fetch(`${API_BASE}/datasets`);
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function uploadDataset(file) {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${API_BASE}/datasets/upload`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function previewDataset(datasetId) {
  const response = await fetch(
    `${API_BASE}/datasets/${encodeURIComponent(datasetId)}/preview`
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}

export async function deleteDataset(datasetId) {
  const response = await fetch(
    `${API_BASE}/datasets/${encodeURIComponent(datasetId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json();
}
