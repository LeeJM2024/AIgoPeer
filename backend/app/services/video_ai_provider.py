"""Native audiovisual adapters for teacher-owned video analysis.

Provider output is advisory and must never write teacher_grades or final_grades.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import socket
import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx


class VideoAIError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_endpoint(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise VideoAIError("AI_INVALID_ENDPOINT")
    try:
        addresses = socket.getaddrinfo(parts.hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise VideoAIError("AI_NETWORK_ERROR") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
        raise VideoAIError("AI_INVALID_ENDPOINT")


def request_text(config, prompt, video=None):
    """Native audiovisual input; custom URLs must implement the selected provider protocol."""
    base = config["base_url"].rstrip("/")
    model = config["model"]
    key = config["api_key"]
    encoded = base64.b64encode(video.read_bytes()).decode() if video else None
    if encoded and len(encoded) >= 10 * 1024 * 1024:
        raise VideoAIError("AI_CLIP_TOO_LARGE")
    if config["provider"] == "qwen":
        url = base + "/chat/completions"
        content = []
        if encoded:
            content.append({"type": "video_url", "video_url": {"url": "data:;base64," + encoded}})
        content.append({"type": "text", "text": prompt})
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "stream": True,
            "modalities": ["text"],
            "max_tokens": 10000,
        }
        if model.startswith("qwen3.8-omni"):
            payload["reasoning_effort"] = "none"
        elif model.startswith("qwen3-omni"):
            payload["enable_thinking"] = False
        headers = {"Authorization": "Bearer " + key}
    else:
        url = base + "/models/" + model + ":generateContent"
        parts = []
        if encoded:
            parts.append({"inline_data": {"mime_type": "video/mp4", "data": encoded}})
        parts.append({"text": prompt})
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"maxOutputTokens": 10000},
        }
        headers = {"x-goog-api-key": key}
    validate_endpoint(url)
    try:
        # No redirect forwarding of keys; ignore host proxy environment for credentials.
        with (
            httpx.Client(
                timeout=httpx.Timeout(120, connect=15), follow_redirects=False, trust_env=False
            ) as client,
            client.stream("POST", url, json=payload, headers=headers) as response,
        ):
            if response.status_code not in range(200, 300):
                code = {
                    401: "AI_AUTH_FAILED",
                    403: "AI_AUTH_FAILED",
                    429: "AI_RATE_LIMIT",
                    400: "AI_MODEL_OR_REQUEST_INVALID",
                    404: "AI_MODEL_OR_REQUEST_INVALID",
                }
                raise VideoAIError(code.get(response.status_code, "AI_PROVIDER_ERROR"))
            started = time.monotonic()
            output, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 4 * 1024 * 1024:
                    raise VideoAIError("AI_RESPONSE_INVALID")
                if time.monotonic() - started > 180:
                    raise VideoAIError("AI_TIMEOUT")
                output.append(chunk)
            raw = b"".join(output).decode("utf-8")
        if config["provider"] == "qwen":
            fragments = []
            for line in raw.splitlines():
                if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                    continue
                part = json.loads(line[5:])
                if part.get("error"):
                    raise VideoAIError("AI_PROVIDER_ERROR")
                for choice in part.get("choices", []):
                    if choice.get("finish_reason") == "length":
                        raise VideoAIError("AI_RESPONSE_TRUNCATED")
                    fragments.append(choice.get("delta", {}).get("content") or "")
            result = "".join(fragments)
        else:
            result_json = json.loads(raw)
            candidate = result_json["candidates"][0]
            if candidate.get("finishReason") not in {None, "STOP"}:
                raise VideoAIError("AI_RESPONSE_TRUNCATED")
            result = "".join(
                p.get("text", "") for p in candidate["content"]["parts"] if not p.get("thought")
            )
        if not result.strip():
            raise VideoAIError("AI_RESPONSE_INVALID")
        return result
    except httpx.TimeoutException as exc:
        raise VideoAIError("AI_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise VideoAIError("AI_NETWORK_ERROR") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise VideoAIError("AI_RESPONSE_INVALID") from exc


@dataclass(frozen=True)
class VideoProviderStatus:
    provider: str | None
    model: str | None
    configured: bool
    enabled: bool


class VideoAnalysisProvider(Protocol):
    def analyze(self, *, storage_key: str, rubric: list[dict], input_hash: str) -> str:
        """Start analysis and return a provider job identifier."""

    def poll(self, job_id: str) -> dict:
        """Return normalized status, evidence timestamps, confidence, and suggestions."""

    def delete_remote_file(self, job_id: str) -> None:
        """Delete provider-side material after configured retention expires."""


def get_video_provider_status(settings) -> VideoProviderStatus:
    configured = bool(
        settings.ai_video_provider and settings.ai_video_api_key and settings.ai_video_model
    )
    return VideoProviderStatus(
        provider=settings.ai_video_provider or None,
        model=settings.ai_video_model or None,
        configured=configured,
        enabled=configured and settings.ai_video_enabled,
    )
