"""Free-tier model providers behind one interface, with automatic fallback.

Cloudflare Workers AI, Gemini, Groq and Ollama all expose an OpenAI-compatible
chat completions endpoint, so one small client covers all of them.
A 'demo' provider needs no key and no network: it lets anyone try the app and
lets tests run offline.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass

import requests


log = logging.getLogger("copilot.llm")


class ProviderError(Exception):
    pass


@dataclass
class Provider:
    name: str
    base_url: str
    api_key: str
    model: str
    privacy_note: str

    def _extras(self) -> dict:
        """Reasoning models (gpt-oss, qwen3...) think before answering. Keep that short so the
        token budget goes to the answer, not the thinking."""
        m = self.model.lower()
        if self.name in ("cloudflare", "groq") and ("gpt-oss" in m or "qwen3" in m):
            return {"reasoning_effort": os.environ.get("REASONING_EFFORT", "low")}
        return {}

    def chat(self, system: str, user: str, timeout: int = 90, retries: int = 1) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": self.model,
            "temperature": 0,
            # Cloudflare's default is only 256 tokens: a reasoning model spends all of it thinking
            # and returns an empty answer. Always set a real budget.
            "max_tokens": int(os.environ.get("MAX_OUTPUT_TOKENS", "8000")),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            **self._extras(),
        }
        last = ""
        for attempt in range(retries + 1):
            try:
                r = requests.post(url, headers=headers, json=body, timeout=timeout)
            except requests.RequestException as e:
                last = f"network error: {e}"
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 429:  # free-tier rate limit: back off, then give up to the next provider
                last = "rate limited (429)"
                time.sleep(min(int(r.headers.get("retry-after", 0) or 0), 20) or 3 * (attempt + 1))
                continue
            if r.status_code == 400 and "reasoning_effort" in body:
                body.pop("reasoning_effort")  # provider doesn't accept the option: retry without it
                continue
            if r.status_code >= 400:
                raise ProviderError(f"{self.name}: HTTP {r.status_code}: {r.text[:300]}")
            try:
                choice = r.json()["choices"][0]
            except (KeyError, IndexError, ValueError) as e:
                raise ProviderError(f"{self.name}: unexpected response: {e}")
            content = _text_of(choice.get("message", {}).get("content"))
            finish = choice.get("finish_reason")
            # Diagnostics only: sizes and status, never the text (contracts must not end up in logs).
            log.info("%s %s: finish=%s, answer_chars=%d, seconds=%.1f",
                     self.name, self.model, finish, len(content), r.elapsed.total_seconds() if hasattr(r, "elapsed") else -1)
            if not content.strip():
                if finish == "length":
                    raise ProviderError(f"{self.name}: the answer was cut off before it started "
                                        "(raise MAX_OUTPUT_TOKENS or lower REASONING_EFFORT)")
                raise ProviderError(f"{self.name}: empty answer (finish_reason={finish})")
            return content
        raise ProviderError(f"{self.name}: {last}")


def _text_of(content) -> str:
    """content can be a string, None, or a list of parts depending on the provider."""
    if content is None:
        return ""
    if isinstance(content, list):
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content)


DEMO = "demo"


def available_providers() -> list[Provider]:
    """Build providers from environment variables, in PROVIDER_ORDER."""
    env = os.environ.get
    candidates: dict[str, Provider | None] = {}

    if env("CLOUDFLARE_ACCOUNT_ID") and env("CLOUDFLARE_API_TOKEN"):
        candidates["cloudflare"] = Provider(
            "cloudflare",
            f"https://api.cloudflare.com/client/v4/accounts/{env('CLOUDFLARE_ACCOUNT_ID')}/ai/v1",
            env("CLOUDFLARE_API_TOKEN", ""),
            env("CLOUDFLARE_MODEL", "@cf/openai/gpt-oss-120b"),
            "Cloudflare Workers AI: not used for training.",
        )
    if env("GEMINI_API_KEY"):
        candidates["gemini"] = Provider(
            "gemini",
            "https://generativelanguage.googleapis.com/v1beta/openai",
            env("GEMINI_API_KEY", ""),
            env("GEMINI_MODEL", "gemini-2.5-flash-lite"),
            "Gemini free tier: Google may use content to improve its products (outside EEA/UK/CH).",
        )
    if env("GROQ_API_KEY"):
        candidates["groq"] = Provider(
            "groq",
            "https://api.groq.com/openai/v1",
            env("GROQ_API_KEY", ""),
            env("GROQ_MODEL", "openai/gpt-oss-120b"),
            "Groq free tier: check Groq's current data policy.",
        )
    if env("OLLAMA_BASE_URL"):
        candidates["ollama"] = Provider(
            "ollama",
            env("OLLAMA_BASE_URL", ""),
            "",
            env("OLLAMA_MODEL", "qwen2.5:7b"),
            "Self-hosted (Ollama): the contract never leaves your server.",
        )

    order = [p.strip() for p in env("PROVIDER_ORDER", "cloudflare,gemini,groq,ollama").split(",")]
    return [candidates[n] for n in order if candidates.get(n)]


def chat_with_fallback(system: str, user: str, providers: list[Provider], **kw) -> tuple[str, Provider]:
    errors = []
    for p in providers:
        try:
            return p.chat(system, user, **kw), p
        except ProviderError as e:
            errors.append(str(e))
    raise ProviderError("All providers failed:\n" + "\n".join(errors))


def parse_json(text: str) -> dict:
    """Models wrap JSON in prose or code fences, and reasoning models may add <think> blocks."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in model output")
    return json.loads(text[start : end + 1])
