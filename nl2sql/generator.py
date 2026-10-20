"""Asks a language model to translate a question into one DuckDB query over the catalog it is given.

The provider is set by NL2SQL_PROVIDER. Gemini and Groq are reached through their OpenAI-compatible
endpoints with the `openai` client; Anthropic through its own SDK. The prompt is identical for all
three, so comparing providers on the eval set is a fair experiment.

If the primary provider is temporarily unavailable (overloaded, rate-limited, timed out, unreachable),
the question is retried once on NL2SQL_FALLBACK. Configuration errors such as a bad key never fall back.
"""

import re
import time
from dataclasses import dataclass

from nl2sql import config

SYSTEM_TEMPLATE = """You translate business questions about an e-commerce marketplace into a single DuckDB SQL query.

The warehouse is described below. Use only these tables and columns. When a question names a metric
listed under METRICS, use that definition exactly. Write one read-only SELECT (CTEs are fine) and give
result columns short, readable aliases. Return only the columns the question asks for.

If the question needs data listed under NOT AVAILABLE, or anything else this schema does not contain,
do not guess: reply with one line, CANNOT_ANSWER: followed by a one-sentence reason.

Otherwise reply with the query in a single ```sql code block and nothing else.

<warehouse>
{catalog}
</warehouse>"""

_SQL_BLOCK = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_CANNOT = re.compile(r"CANNOT_ANSWER:\s*(.+)", re.IGNORECASE)


@dataclass
class Generation:
    sql: str | None
    cannot_answer: str | None
    raw_text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    fallback_from: str | None = None  # the provider that failed first, when the fallback answered


class GenerationError(Exception):
    pass


class TransientError(GenerationError):
    """The provider is busy or unreachable right now; another provider may succeed."""


def build_system_prompt(catalog_text: str) -> str:
    return SYSTEM_TEMPLATE.format(catalog=catalog_text)


def _parse(text: str) -> tuple[str | None, str | None]:
    if match := _CANNOT.search(text):
        return None, match.group(1).strip()
    if match := _SQL_BLOCK.search(text):
        return match.group(1).strip(), None
    if text.lower().lstrip().startswith(("select", "with")):
        return text.strip(), None
    return None, None


def _label(provider: str) -> str:
    return config.PROVIDERS[provider]["label"]


def _require_key(provider: str) -> str:
    key = config.api_key(provider)
    if not key:
        raise GenerationError(f"No API key for {_label(provider)}. Set {config.PROVIDERS[provider]['key_env']} "
                              "in .env (see README).")
    return key


# ---------- Gemini and Groq: OpenAI-compatible endpoints ----------

_openai_clients: dict = {}


def _call_openai_compatible(provider: str, model: str, effort: str, system: str, question: str,
                            retries: int) -> tuple[str, int, int]:
    import openai

    key = _require_key(provider)
    client_key = (provider, retries)
    if client_key not in _openai_clients:
        _openai_clients[client_key] = openai.OpenAI(api_key=key, base_url=config.PROVIDERS[provider]["base_url"],
                                                    max_retries=retries, timeout=60)
    try:
        response = _openai_clients[client_key].chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": question}],
            reasoning_effort=effort,
            max_completion_tokens=8000,
        )
    except openai.AuthenticationError as e:
        raise GenerationError(f"The {_label(provider)} API key was rejected. "
                              f"Check {config.PROVIDERS[provider]['key_env']} in .env.") from e
    except openai.RateLimitError as e:
        raise TransientError(f"{_label(provider)} free-tier rate limit reached. Wait a minute and retry.") from e
    except openai.APITimeoutError as e:
        raise TransientError(f"{_label(provider)} took too long to respond.") from e
    except openai.APIConnectionError as e:
        raise TransientError(f"Could not reach {_label(provider)}. Check your internet connection.") from e
    except openai.APIStatusError as e:
        if e.status_code >= 500:
            raise TransientError(f"{_label(provider)} is overloaded right now ({e.status_code}).") from e
        raise GenerationError(f"{_label(provider)} API error {e.status_code}: {e.message}") from e

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise GenerationError("The model ran out of output tokens before finishing the query.")
    usage = response.usage
    return (choice.message.content or "").strip(), getattr(usage, "prompt_tokens", 0) or 0, \
        getattr(usage, "completion_tokens", 0) or 0


# ---------- Anthropic: official SDK ----------

_anthropic_client = None
_FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5")  # families that accept server-side refusal fallbacks


def _call_anthropic(provider: str, model: str, effort: str, system: str, question: str,
                    retries: int) -> tuple[str, int, int]:
    import anthropic

    global _anthropic_client
    key = _require_key(provider)
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=key, max_retries=retries)
    request = dict(
        model=model,
        max_tokens=16000,
        output_config={"effort": effort},
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": question}],
    )
    if model.startswith(_FALLBACK_MODELS):
        request["betas"] = ["server-side-fallback-2026-07-01"]
        request["fallbacks"] = "default"
    try:
        response = _anthropic_client.beta.messages.create(**request)
    except anthropic.AuthenticationError as e:
        raise GenerationError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in .env.") from e
    except anthropic.RateLimitError as e:
        raise TransientError("Anthropic rate limit reached. Wait a moment and retry.") from e
    except anthropic.APIConnectionError as e:
        raise TransientError("Could not reach the Anthropic API. Check your internet connection.") from e
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise TransientError(f"Anthropic is overloaded right now ({e.status_code}).") from e
        raise GenerationError(f"Anthropic API error {e.status_code}: {e.message}") from e

    if response.stop_reason == "refusal":
        raise GenerationError("The model declined this request.")
    if response.stop_reason == "max_tokens":
        raise GenerationError("The model ran out of output tokens before finishing the query.")
    text = "".join(block.text for block in response.content if block.type == "text").strip()
    u = response.usage
    tokens_in = (u.input_tokens or 0) + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0)
    return text, tokens_in, u.output_tokens or 0


# ---------- entry point ----------

def _generate_with(provider: str, model: str, effort: str, system: str, question: str, retries: int) -> Generation:
    call = _call_anthropic if provider == "anthropic" else _call_openai_compatible
    started = time.perf_counter()
    text, tokens_in, tokens_out = call(provider, model, effort, system, question, retries)
    latency = time.perf_counter() - started
    sql, cannot = _parse(text)
    return Generation(sql=sql, cannot_answer=cannot, raw_text=text, provider=provider, model=model,
                      input_tokens=tokens_in, output_tokens=tokens_out, latency_s=latency)


def generate_sql(question: str, catalog_text: str, allow_fallback: bool = True) -> Generation:
    system = build_system_prompt(catalog_text)
    use_fallback = allow_fallback and config.fallback_ready()
    started = time.perf_counter()
    try:
        # with a fallback ready, fail over quickly instead of waiting through several retries
        return _generate_with(config.PROVIDER, config.MODEL, config.EFFORT, system, question,
                              retries=1 if use_fallback else 3)
    except TransientError as first:
        if not use_fallback:
            raise
        backup = config.FALLBACK
        try:
            gen = _generate_with(backup, config.PROVIDERS[backup]["model"], config.PROVIDERS[backup]["effort"],
                                 system, question, retries=2)
        except GenerationError as second:
            raise GenerationError(f"{first} The fallback also failed: {second}") from second
        gen.fallback_from = config.PROVIDER
        gen.latency_s = time.perf_counter() - started  # the user waited for both attempts
        return gen
