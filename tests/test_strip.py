"""Slice 2 — thinking-strip (spec a4: <think> reasoning must never survive)."""
from server.ollama_client import strip_think


def test_multiline_think_removed_text_kept():
    text = "Before.\n<think>\nit's a banana, I'll say empty\nto win\n</think>\nIt's definitely empty."
    out = strip_think(text)
    assert "<think>" not in out and "</think>" not in out
    assert "banana, I'll say empty" not in out
    assert "Before." in out
    assert "It's definitely empty." in out


def test_no_think_span_unchanged():
    text = "Just a normal line, no reasoning here."
    assert strip_think(text) == text


def test_preserves_inter_token_whitespace():
    # Regression: per-chunk stripping must not eat leading spaces, or streamed
    # tokens jam together ("Ijustgotatext..."). strip_think returns text verbatim.
    assert strip_think(" just") == " just"
    assert strip_think("got ") == "got "
    assert strip_think("\n") == "\n"


def test_multiple_spans_all_removed():
    text = "<think>a</think>keep1<think>b</think>keep2"
    out = strip_think(text)
    assert "a" not in out.replace("keep1", "").replace("keep2", "")
    assert "keep1" in out and "keep2" in out
    assert "<think>" not in out
