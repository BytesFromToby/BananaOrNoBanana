"""Slice 6 — per-round settings in the game core (Match settings feature)."""
import pytest

from server.config import DEFAULTS
from server.game import ROUNDS, create_round, effective_settings


@pytest.fixture(autouse=True)
def reset_rounds():
    ROUNDS.clear()
    yield
    ROUNDS.clear()


def test_create_round_applies_overrides():
    r = create_round(
        dict(DEFAULTS),
        overrides={"model": "gemma4:latest", "turn_limit": 5, "temperature": 0.2},
    )
    assert r.model == "gemma4:latest"
    assert r.turn_limit == 5
    assert r.turns_remaining == 5
    assert r.temperature == 0.2


def test_omitted_fields_fall_back_to_defaults():
    r = create_round(dict(DEFAULTS), overrides={"turn_limit": 2})
    assert r.turn_limit == 2
    assert r.model == DEFAULTS["box_holder_model"]
    assert r.temperature == DEFAULTS["temperature"]


def test_no_overrides_uses_all_defaults():
    r = create_round(dict(DEFAULTS))
    assert r.model == DEFAULTS["box_holder_model"]
    assert r.turn_limit == DEFAULTS["turn_limit"]
    assert r.temperature == DEFAULTS["temperature"]


@pytest.mark.parametrize("bad", [{"turn_limit": 0}, {"turn_limit": -3}, {"turn_limit": "two"}])
def test_bad_turn_limit_raises(bad):
    with pytest.raises(ValueError):
        effective_settings(dict(DEFAULTS), bad)


@pytest.mark.parametrize("bad", [{"temperature": -1}, {"temperature": "hot"}])
def test_bad_temperature_raises(bad):
    with pytest.raises(ValueError):
        effective_settings(dict(DEFAULTS), bad)
