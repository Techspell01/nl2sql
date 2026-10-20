"""Fallback rules and response parsing. No network: the provider calls are replaced."""

import pytest

from nl2sql import config, generator
from nl2sql.generator import Generation, GenerationError, TransientError, _parse


@pytest.fixture()
def two_providers(monkeypatch):
    monkeypatch.setattr(config, "PROVIDER", "groq")
    monkeypatch.setattr(config, "FALLBACK", "gemini")
    monkeypatch.setattr(config, "fallback_ready", lambda: True)


def fake_calls(monkeypatch, failures):
    """failures: provider -> exception to raise; any other provider answers."""
    calls = []

    def fake(provider, model, effort, system, question, retries):
        calls.append(provider)
        if provider in failures:
            raise failures[provider]
        return Generation("select 1", None, "", provider, model, 10, 5, 0.1)

    monkeypatch.setattr(generator, "_generate_with", fake)
    return calls


def test_busy_primary_falls_back(monkeypatch, two_providers):
    calls = fake_calls(monkeypatch, {"groq": TransientError("Groq is overloaded")})
    gen = generator.generate_sql("q", "catalog")
    assert calls == ["groq", "gemini"]
    assert gen.provider == "gemini" and gen.fallback_from == "groq"


def test_healthy_primary_does_not_touch_fallback(monkeypatch, two_providers):
    calls = fake_calls(monkeypatch, {})
    gen = generator.generate_sql("q", "catalog")
    assert calls == ["groq"] and gen.fallback_from is None


def test_bad_key_never_falls_back(monkeypatch, two_providers):
    calls = fake_calls(monkeypatch, {"groq": GenerationError("The Groq API key was rejected.")})
    with pytest.raises(GenerationError, match="rejected"):
        generator.generate_sql("q", "catalog")
    assert calls == ["groq"]


def test_eval_mode_disables_fallback(monkeypatch, two_providers):
    calls = fake_calls(monkeypatch, {"groq": TransientError("busy")})
    with pytest.raises(TransientError):
        generator.generate_sql("q", "catalog", allow_fallback=False)
    assert calls == ["groq"]


def test_both_failing_reports_both(monkeypatch, two_providers):
    fake_calls(monkeypatch, {"groq": TransientError("Groq busy."), "gemini": TransientError("Gemini busy.")})
    with pytest.raises(GenerationError, match="Groq busy.*fallback also failed.*Gemini busy"):
        generator.generate_sql("q", "catalog")


@pytest.mark.parametrize("text, sql, cannot", [
    ("```sql\nselect 1\n```", "select 1", None),
    ("Here you go:\n```\nselect 2\n```", "select 2", None),
    ("SELECT 3", "SELECT 3", None),
    ("CANNOT_ANSWER: there is no cost data.", None, "there is no cost data."),
    ("I am not sure.", None, None),
])
def test_parse(text, sql, cannot):
    assert _parse(text) == (sql, cannot)
