"""Slice 2 — Ollama request contract (spec a5: think:false, stream:true)."""
from server.ollama_client import build_chat_request


def test_request_disables_thinking_and_streams():
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    body = build_chat_request(msgs, model="qwen3:8b", temperature=0.9)
    assert body["think"] is False
    assert body["stream"] is True
    assert body["model"] == "qwen3:8b"
    assert body["options"]["temperature"] == 0.9
    assert body["messages"] == msgs
