"""Thin Groq OpenAI-compatible chat client via plain HTTP (httpx) — no SDKs/frameworks."""

from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx

from .logger import GoTLogger


class LLMClient:
    """Minimal wrapper around Groq's OpenAI-compatible Chat Completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        logger: GoTLogger | None = None,
        max_retries: int = 6,
        temperature: float = 0.2,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Copy backend/.env.example to backend/.env "
                "and add your Groq API key."
            )
        self.model = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.base_url = (
            base_url or os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        ).rstrip("/")
        self.logger = logger
        self.max_retries = max_retries
        self.temperature = temperature
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_calls = 0
        self.total_latency_s = 0.0
        # Groq on_demand llama-3.3-70b-versatile is 30 RPM. Stay under it.
        self.rpm_limit = max(1, int(os.getenv("GROQ_RPM", "30")))
        self._min_interval_s = 60.0 / self.rpm_limit
        self._next_allowed_at = 0.0

    def _pace(self) -> None:
        """Block until we are inside the RPM budget (plus a small safety gap)."""
        now = time.monotonic()
        wait = self._next_allowed_at - now
        if wait > 0:
            if self.logger:
                self.logger.info(
                    f"Pacing Groq calls — sleeping {wait:.2f}s to stay under {self.rpm_limit} RPM"
                )
            time.sleep(wait)
        # 5% headroom so 30 RPM doesn't clip the limit
        self._next_allowed_at = time.monotonic() + self._min_interval_s * 1.05

    @staticmethod
    def _retry_after_s(resp: httpx.Response | None, err_text: str) -> float:
        if resp is not None:
            header = resp.headers.get("retry-after")
            if header:
                try:
                    return max(float(header), 0.5)
                except ValueError:
                    pass
        m = re.search(r"try again in (\d+(?:\.\d+)?)\s*s", err_text, flags=re.I)
        if m:
            return max(float(m.group(1)), 0.5)
        return 2.0

    def chat_completion(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._pace()
            t0 = time.time()
            resp: httpx.Response | None = None
            try:
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                latency = time.time() - t0
                if resp.status_code == 429:
                    wait = self._retry_after_s(resp, resp.text)
                    if self.logger:
                        self.logger.warning(
                            f"Groq 429 rate limit (attempt {attempt}/{self.max_retries}); "
                            f"waiting {wait:.1f}s then retrying"
                        )
                    time.sleep(wait)
                    self._next_allowed_at = time.monotonic() + self._min_interval_s
                    last_err = RuntimeError(f"Groq HTTP 429: {resp.text[:300]}")
                    continue
                if resp.status_code >= 400:
                    raise RuntimeError(
                        f"Groq HTTP {resp.status_code}: {resp.text[:500]}"
                    )
                data = resp.json()
                text = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    or ""
                ).strip()
                usage = data.get("usage") or {}
                pt = usage.get("prompt_tokens")
                ct = usage.get("completion_tokens")
                if pt:
                    self.total_prompt_tokens += int(pt)
                if ct:
                    self.total_completion_tokens += int(ct)
                self.total_calls += 1
                self.total_latency_s += latency

                if self.logger:
                    self.logger.llm_call(
                        prompt=(
                            prompt
                            if not system
                            else f"[system]\n{system}\n\n[user]\n{prompt}"
                        ),
                        response=text,
                        model=self.model,
                        latency_s=round(latency, 3),
                        prompt_tokens=pt,
                        completion_tokens=ct,
                        attempt=attempt,
                    )
                return text
            except Exception as e:  # noqa: BLE001 — retry then raise
                last_err = e
                if self.logger:
                    self.logger.warning(
                        f"LLM attempt {attempt}/{self.max_retries} failed: {e}"
                    )
                time.sleep(min(2**attempt, 8))

        raise RuntimeError(f"Groq chat_completion failed after retries: {last_err}")

    def usage_summary(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "calls": self.total_calls,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_latency_s": round(self.total_latency_s, 3),
        }
