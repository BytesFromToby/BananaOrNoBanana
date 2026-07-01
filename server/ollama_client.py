"""Ollama chat proxy with reasoning disabled and defensively stripped.

The one true landmine: the Box Holder's hidden reasoning must never reach the Guesser.
We both request `think:false` AND strip any `<think>...</think>` from returned content.
"""
import json
import re
from typing import AsyncIterator

import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    """Remove every <think>...</think> span (incl. multi-line); leave all other text verbatim.

    Must NOT trim surrounding whitespace: this runs per streamed chunk, and Ollama emits
    inter-token spaces as their own leading-space chunks — trimming them jams words together.
    """
    if not text:
        return text
    return _THINK_RE.sub("", text)


async def list_models(url: str) -> list:
    """Return the names of models installed in Ollama (GET /api/tags)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{url}/api/tags")
        resp.raise_for_status()
        data = resp.json()
    return [m["name"] for m in data.get("models", [])]


def build_chat_request(messages: list, model: str, temperature: float) -> dict:
    """The Ollama /api/chat request body — reasoning off, streaming on."""
    return {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": False,
        "options": {"temperature": temperature},
    }


async def chat_stream(
    messages: list, model: str, url: str, temperature: float
) -> AsyncIterator[str]:
    """POST to Ollama /api/chat and yield think-stripped content chunks from the NDJSON stream."""
    body = build_chat_request(messages, model, temperature)
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", f"{url}/api/chat", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                piece = obj.get("message", {}).get("content", "")
                if piece:
                    cleaned = strip_think(piece)
                    if cleaned:
                        yield cleaned
