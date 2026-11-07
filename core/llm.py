"""Groq LLM client with JSON mode, retries and robust JSON parsing."""
from __future__ import annotations

import json
import re
import time
from typing import Protocol

from .config import GROQ_MODEL
from .logging_utils import logger


class LLMError(Exception):
    pass


class LLM(Protocol):
    available: bool

    def json(self, system: str, user: str) -> dict: ...


def parse_json_loose(text: str) -> dict:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMError("The model returned a response that was not valid JSON.")


class GroqLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or "").strip()
        self.model = model or GROQ_MODEL
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if self._client is None:
            from groq import Groq

            self._client = Groq(api_key=self.api_key)
        return self._client

    def json(self, system: str, user: str, max_tokens: int = 1800) -> dict:
        if not self.available:
            raise LLMError("No Groq API key configured.")
        last: Exception | None = None
        for attempt in range(3):
            try:
                resp = self._get_client().chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=0,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                )
                return parse_json_loose(resp.choices[0].message.content)
            except LLMError as exc:
                last = exc
            except Exception as exc:  # network / rate limit / auth
                last = exc
                msg = str(exc).lower()
                if "401" in msg or "invalid api key" in msg or "authentication" in msg:
                    raise LLMError("The Groq API key was rejected. Check GROQ_API_KEY.")
                logger.warning("LLM call failed (attempt %s): %s", attempt + 1, exc)
            time.sleep(1.5 * (attempt + 1))
        raise LLMError(f"The AI service is unavailable right now ({str(last)[:120]}). Please try again.")
