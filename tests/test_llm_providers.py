"""Provider-agnostic request shaping (no live network) — Ollama's own request shape is
covered by test_ollama_request.py; this covers the OpenAI-compatible and Anthropic
request builders, plus the dispatch-by-provider-name contract.
"""
import asyncio

import pytest

from server.llm_providers import build_anthropic_request, build_openai_request, chat_stream, split_system
from server.players import PlayerConfig


def test_build_openai_request_shape():
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    body = build_openai_request(messages, model="gpt-x", temperature=0.7)
    assert body == {"model": "gpt-x", "messages": messages, "stream": True, "temperature": 0.7}


def test_split_system_pulls_out_leading_system_message():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "kickoff"},
        {"role": "assistant", "content": "reply"},
    ]
    system_text, rest = split_system(messages)
    assert system_text == "sys"
    assert rest == messages[1:]


def test_split_system_empty_when_no_system_message():
    messages = [{"role": "user", "content": "hi"}]
    system_text, rest = split_system(messages)
    assert system_text == ""
    assert rest == messages


def test_build_anthropic_request_shape():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    body = build_anthropic_request(messages, model="claude-x", temperature=0.5)
    assert body["model"] == "claude-x"
    assert body["system"] == "sys"
    assert body["messages"] == [{"role": "user", "content": "hi"}]
    assert body["stream"] is True
    assert body["temperature"] == 0.5
    assert "max_tokens" in body


def test_chat_stream_dispatches_to_ollama(monkeypatch):
    calls = []

    async def fake_ollama(messages, model, url, temperature):
        calls.append((model, url, temperature))
        yield "hi"

    monkeypatch.setattr("server.llm_providers._ollama_chat_stream", fake_ollama)
    cfg = PlayerConfig(seat="left", kind="ai", provider="ollama", model="qwen3:8b", base_url="http://x")

    async def _collect():
        return [c async for c in chat_stream([{"role": "user", "content": "hi"}], cfg, 0.9)]

    out = asyncio.run(_collect())
    assert out == ["hi"]
    assert calls == [("qwen3:8b", "http://x", 0.9)]


def test_chat_stream_unknown_provider_raises():
    cfg = PlayerConfig(seat="left", kind="ai", provider="not_a_provider", model="x", base_url="http://x")

    async def _collect():
        async for _ in chat_stream([{"role": "user", "content": "hi"}], cfg, 0.9):
            pass

    with pytest.raises(ValueError):
        asyncio.run(_collect())
