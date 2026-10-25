// Minimal SSE parser for fetch-based POST streams. EventSource cannot send
// POST bodies, so the response stream is decoded manually.
export function parseSSEFrame(frame) {
  let event = "message";
  const dataLines = [];

  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(":")) continue;

    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? "" : line.slice(separator + 1);
    if (value.startsWith(" ")) value = value.slice(1);

    if (field === "event") event = value;
    else if (field === "data") dataLines.push(value);
  }

  if (dataLines.length === 0) return null;

  const raw = dataLines.join("\n");
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error("Malformed stream event.");
  }

  return { event, data };
}

export async function consumeSSE(body, handlers = {}) {
  const { onStart, onChunk, onComplete } = handlers;
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let completed = false;

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.search(/\r?\n\r?\n/);
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/);
        buffer = buffer.slice(boundary + separator[0].length);

        const parsed = parseSSEFrame(frame);
        if (parsed) {
          if (parsed.event === "start") {
            onStart?.(parsed.data);
          } else if (parsed.event === "chunk") {
            onChunk?.(parsed.data?.text ?? "");
          } else if (parsed.event === "complete") {
            completed = true;
            onComplete?.(parsed.data);
          } else if (parsed.event === "error") {
            throw new Error(
              parsed.data?.message || "The response stream failed."
            );
          }
        }

        boundary = buffer.search(/\r?\n\r?\n/);
      }
    }

    if (!completed) {
      throw new Error("The response was interrupted before completion.");
    }
  } finally {
    reader.releaseLock();
  }
}
