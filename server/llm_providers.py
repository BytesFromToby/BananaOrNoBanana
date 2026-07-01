"""Unified LLM dispatch for player seats — any seat can be driven by Ollama, an
OpenAI-compatible endpoint (OpenAI itself, OpenRouter, vLLM, LM Studio, ...), or
Anthropic. One call shape in, one streamed-text shape out, regardless of provider.

Thinking-strip applies uniformly (server.ollama_client.strip_think) — belt-and-
suspenders in case a non-Ollama model also emits <think> spans.
"""
import json
from typing import AsyncIterator

import httpx

from server.ollama_client import chat_stream as _ollama_chat_stream
from server.ollama_client import strip_think
from server.players import PlayerConfig


def build_openai_request(messages: list, model: str, temperature: float) -> dict:
    """The OpenAI-compatible /chat/completions request body — streaming on."""
    return {"model": model, "messages": messages, "stream": True, "temperature": temperature}


def split_system(messages: list) -> tuple:
    """Split a system message out from the rest (Anthropic takes `system` separately)."""
    system_text = ""
    rest = []
    for m in messages:
        if m["role"] == "system" and not system_text:
            system_text = m["content"]
        else:
            rest.append(m)
    return system_text, rest


def build_anthropic_request(messages: list, model: str, temperature: float) -> dict:
    """The Anthropic /v1/messages request body — system split out, streaming on."""
    system_text, rest = split_system(messages)
    return {
        "model": model,
        "system": system_text,
        "messages": rest,
        "max_tokens": 1024,
        "temperature": temperature,
        "stream": True,
    }


async def _openai_compat_stream(
    messages: list, cfg: PlayerConfig, temperature: float
) -> AsyncIterator[str]:
    body = build_openai_request(messages, cfg.model, temperature)
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    url = f"{cfg.base_url.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]" or not data:
                    continue
                obj = json.loads(data)
                choices = obj.get("choices") or []
                if not choices:
                    continue
                piece = choices[0].get("delta", {}).get("content", "")
                if piece:
                    cleaned = strip_think(piece)
                    if cleaned:
                        yield cleaned


async def _anthropic_stream(
    messages: list, cfg: PlayerConfig, temperature: float
) -> AsyncIterator[str]:
    body = build_anthropic_request(messages, cfg.model, temperature)
    base = cfg.base_url or "https://api.anthropic.com"
    url = f"{base.rstrip('/')}/v1/messages"
    headers = {
        "x-api-key": cfg.api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream("POST", url, json=body, headers=headers) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if not data:
                    continue
                obj = json.loads(data)
                if obj.get("type") == "content_block_delta":
                    delta = obj.get("delta", {})
                    if delta.get("type") == "text_delta":
                        piece = delta.get("text", "")
                        if piece:
                            cleaned = strip_think(piece)
                            if cleaned:
                                yield cleaned


async def chat_stream(
    messages: list, cfg: PlayerConfig, temperature: float
) -> AsyncIterator[str]:
    """Dispatch to the seat's configured provider; yields think-stripped text chunks."""
    if cfg.provider == "ollama":
        async for chunk in _ollama_chat_stream(
            messages, model=cfg.model, url=cfg.base_url, temperature=temperature
        ):
            yield chunk
    elif cfg.provider == "openai_compat":
        async for chunk in _openai_compat_stream(messages, cfg, temperature):
            yield chunk
    elif cfg.provider == "anthropic":
        async for chunk in _anthropic_stream(messages, cfg, temperature):
            yield chunk
    else:
        raise ValueError(f"unknown provider: {cfg.provider}")
