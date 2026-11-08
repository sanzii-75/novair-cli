"""Minimal OpenAI-compatible chat client with SSE streaming.

Works with OpenRouter, OpenAI, Groq, Together, Ollama, llama.cpp server,
vLLM, LM Studio — anything speaking the /chat/completions dialect.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Iterator, List, Optional

import httpx

from . import __version__
from .config import Provider

MAX_RETRIES = 3


class ProviderError(RuntimeError):
    """Raised for anything that goes wrong talking to the provider."""

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class ChatClient:
    def __init__(
        self,
        provider: Provider,
        read_timeout: float = 300.0,
        connect_timeout: float = 15.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.provider = provider
        self._timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
        self._transport = transport

    # ── headers ──────────────────────────────────────────────────────────────
    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"nexa/{__version__}",
            "Accept": "application/json, text/event-stream",
        }
        if self.provider.api_key:
            headers["Authorization"] = f"Bearer {self.provider.api_key}"
        host = ""
        try:
            host = httpx.URL(self.provider.base_url).host or ""
        except Exception:
            pass
        if "openrouter" in host:
            # Recommended attribution headers for OpenRouter.
            headers["HTTP-Referer"] = "https://github.com/nexa-cli/nexa"
            headers["X-Title"] = "nexa-cli"
        if extra:
            headers.update(extra)
        return headers

    # ── public API ───────────────────────────────────────────────────────────
    def chat_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Yield normalized events:
            {"type": "chunk", "delta": {...}, "finish_reason": str|None, "usage": {...}|None}
            {"type": "message", "message": {...}, "finish_reason": str, "usage": {...}|None}

        Retries up to MAX_RETRIES on 429/5xx and connection errors — but only
        while nothing has been streamed back yet (mid-stream failures surface
        immediately, a stream cannot be resumed).
        """
        payload: Dict[str, Any] = {
            "model": self.provider.model,
            "messages": messages,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
        if temperature is not None:
            payload["temperature"] = temperature

        url = self.provider.base_url + "/chat/completions"
        received = False
        last_exc: Optional[Exception] = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                    with client.stream(
                        "POST", url, json=payload, headers=self._headers()
                    ) as resp:
                        if resp.status_code != 200:
                            retryable = resp.status_code == 429 or resp.status_code >= 500
                            if retryable and attempt < MAX_RETRIES:
                                time.sleep(min(2 * attempt, 5))
                                continue
                            raise ProviderError(
                                self._describe_http_error(resp), status=resp.status_code
                            )
                        ctype = resp.headers.get("content-type", "")
                        if "text/event-stream" not in ctype:
                            # Provider ignored stream=True — parse the whole body.
                            received = True
                            body = resp.read()
                            events = list(self._events(self._parse_json(body)))
                            yield from events
                            return
                        received = True
                        yield from self._iter_sse(resp)
                        return
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt < MAX_RETRIES and not received:
                    time.sleep(min(2 * attempt, 5))
                    continue
                raise ProviderError(
                    f"Could not reach {self.provider.base_url} ({e.__class__.__name__}). "
                    "Check your network / base URL."
                ) from e
            except httpx.HTTPError as e:
                raise ProviderError(
                    f"Connection dropped while streaming from {self.provider.base_url}: {e}"
                ) from e
            except ProviderError:
                raise
        raise ProviderError(
            f"Giving up after {MAX_RETRIES} attempts: {last_exc}", status=503
        )

    def list_models(self) -> List[Dict[str, Any]]:
        """GET /models — handy for discovering model ids on any provider."""
        url = self.provider.base_url + "/models"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                resp = client.get(url, headers=self._headers())
        except httpx.HTTPError as e:
            raise ProviderError(f"Could not list models: {e}") from e
        if resp.status_code != 200:
            raise ProviderError(self._describe_http_error(resp), status=resp.status_code)
        data = self._parse_json(resp.content)
        return data.get("data", []) if isinstance(data, dict) else []

    # ── internals ────────────────────────────────────────────────────────────
    @staticmethod
    def _parse_json(body: bytes) -> Dict[str, Any]:
        try:
            return json.loads(body.decode("utf-8", "replace"))
        except json.JSONDecodeError as e:
            snippet = body[:200].decode("utf-8", "replace")
            raise ProviderError(f"Provider returned invalid JSON: {snippet!r}") from e

    @staticmethod
    def _read_error_body(resp: httpx.Response) -> str:
        try:
            raw = resp.read().decode("utf-8", "replace")
        except Exception:
            return ""
        raw = raw.strip()
        if not raw:
            return ""
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict) and obj.get("error"):
                err = obj["error"]
                return str(err.get("message") or err) if isinstance(err, dict) else str(err)
        except json.JSONDecodeError:
            pass
        return raw[:300]

    def _describe_http_error(self, resp: httpx.Response) -> str:
        detail = self._read_error_body(resp)
        base = f"{self.provider.base_url} responded {resp.status_code}"
        if resp.status_code in (401, 403):
            return (
                f"{base} — authentication failed. Check the API key "
                f"({self.provider.key_env_hint}). {detail}".strip()
            )
        if resp.status_code == 404:
            return (
                f"{base} — endpoint not found. Make sure the base URL points at the "
                f"OpenAI-compatible root, usually ending in /v1. {detail}".strip()
            )
        if resp.status_code == 429:
            return f"{base} — rate limited or out of credits. {detail}".strip()
        if resp.status_code >= 500:
            return f"{base} — provider server error. {detail}".strip()
        return f"{base}. {detail}".strip()

    @staticmethod
    def _iter_sse(response: httpx.Response) -> Iterator[Dict[str, Any]]:
        """Parse an SSE stream of `data: {...}` lines."""
        buffer: List[str] = []
        for raw in response.iter_lines():
            if raw is None:
                continue
            line = raw.strip()
            if line.startswith("data:"):
                buffer.append(line[5:].strip())
                continue
            if not line and buffer:
                blob = "\n".join(buffer)
                buffer = []
                if blob == "[DONE]":
                    return
                try:
                    obj = json.loads(blob)
                except json.JSONDecodeError:
                    continue
                yield from ChatClient._events(obj)
        # Flush a trailing event that lacked the final blank line.
        if buffer:
            blob = "\n".join(buffer)
            if blob != "[DONE]":
                try:
                    yield from ChatClient._events(json.loads(blob))
                except json.JSONDecodeError:
                    pass

    @staticmethod
    def _events(obj: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        if not isinstance(obj, dict):
            return
        err = obj.get("error")
        if err:
            msg = err.get("message") if isinstance(err, dict) else str(err)
            raise ProviderError(str(msg or err))

        usage = obj.get("usage")
        for choice in obj.get("choices") or []:
            if "delta" in choice:
                yield {
                    "type": "chunk",
                    "delta": choice.get("delta") or {},
                    "finish_reason": choice.get("finish_reason"),
                    "usage": usage,
                }
            elif "message" in choice:
                # Whole-response fallback (provider ignored stream=True).
                yield {
                    "type": "message",
                    "message": choice["message"],
                    "finish_reason": choice.get("finish_reason") or "stop",
                    "usage": usage,
                }
            elif "text" in choice:  # legacy completions-style
                yield {
                    "type": "chunk",
                    "delta": {"content": choice["text"]},
                    "finish_reason": choice.get("finish_reason"),
                    "usage": usage,
                }
