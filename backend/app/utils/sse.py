"""Backend Server-Sent Events (SSE) mechanics for chat streaming.

Event formatting, chunk generation, pacing, stream generation, client
disconnection handling, and streaming-error reporting live here so the chat
endpoint file stays focused on HTTP concerns.
"""

import asyncio
import json
import logging
import re
from typing import Callable, Generator

from fastapi import Request

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 24

# Pause between chunks so the typing effect and blinking cursor stay visible.
# Very long answers are capped so the total extra time stays reasonable.
_STREAM_CHUNK_DELAY_SECONDS = 0.05
_STREAM_MAX_TOTAL_SECONDS = 2.0


def iter_text_chunks(text: str, size: int = _CHUNK_SIZE) -> Generator[str, None, None]:
    # Group whole words so chunks stay readable and the combined text is
    # exactly the validated answer.
    buffer = ""
    for token in re.findall(r"\s*\S+\s*", text):
        if buffer and len(buffer) + len(token) > size:
            yield buffer
            buffer = token
        else:
            buffer += token
    if buffer:
        yield buffer


def sse_event(event: str, payload: dict) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    )


def stream_delay(chunk_count: int) -> float:
    # Fixed pause per chunk keeps the typing effect visible; long answers
    # share one time budget so streaming never drags on.
    return min(
        _STREAM_CHUNK_DELAY_SECONDS,
        _STREAM_MAX_TOTAL_SECONDS / max(1, chunk_count),
    )


async def stream_answer(
    request: Request,
    conversation_id: str,
    intent_name: str,
    answer: str,
    build_complete_payload: Callable[[], dict],
    commit: Callable[[], None],
):
    """Yield SSE frames for a prepared answer.

    ``build_complete_payload`` supplies the serialized ``complete`` payload and
    ``commit`` persists the answer as conversation context. Both run in
    ``chat.py`` so their ordering (serialize first, then commit) is preserved
    without importing endpoint internals here.
    """
    try:
        if await request.is_disconnected():
            return

        yield sse_event(
            "start",
            {
                "conversation_id": conversation_id,
                "intent": intent_name,
            },
        )

        chunks = list(iter_text_chunks(answer))
        delay = stream_delay(len(chunks))

        for chunk in chunks:
            if await request.is_disconnected():
                logger.info(
                    "Client disconnected mid-stream (conversation %s).",
                    conversation_id,
                )
                return

            yield sse_event("chunk", {"text": chunk})
            await asyncio.sleep(delay)

        if await request.is_disconnected():
            logger.info(
                "Client disconnected before completion (conversation %s).",
                conversation_id,
            )
            return

        # Serialize the completion first: if that fails, no assistant answer
        # is committed and the client is told the stream failed.
        complete_event = sse_event("complete", build_complete_payload())
        commit()
        yield complete_event
    except Exception:
        logger.exception(
            "Streaming failed for conversation %s.",
            conversation_id,
        )
        yield sse_event(
            "error",
            {
                "code": "stream_failed",
                "message": "The response stream failed before completion.",
                "conversation_id": conversation_id,
            },
        )
