"""Text-only Chat Completions adapter. No tools or code execution."""

import json
import time

import httpx

from app.services.video_ai_provider import VideoAIError, validate_endpoint


def complete(config, messages, *, max_tokens=4000):
    url = config["base_url"].rstrip("/") + "/chat/completions"
    validate_endpoint(url)
    payload = {
        "model": config["model"],
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if config["model"].startswith("deepseek"):
        payload["thinking"] = {"type": "disabled"}
    try:
        with (
            httpx.Client(
                timeout=httpx.Timeout(90, connect=15), trust_env=False, follow_redirects=False
            ) as client,
            client.stream(
                "POST", url, headers={"Authorization": "Bearer " + config["api_key"]}, json=payload
            ) as response,
        ):
            if response.status_code not in range(200, 300):
                codes = {
                    401: "AI_AUTH_FAILED",
                    403: "AI_AUTH_FAILED",
                    429: "AI_RATE_LIMIT",
                    400: "AI_MODEL_OR_REQUEST_INVALID",
                    404: "AI_MODEL_OR_REQUEST_INVALID",
                }
                raise VideoAIError(codes.get(response.status_code, "AI_PROVIDER_ERROR"))
            chunks, size, started = [], 0, time.monotonic()
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 1024 * 1024:
                    raise VideoAIError("AI_RESPONSE_INVALID")
                if time.monotonic() - started > 120:
                    raise VideoAIError("AI_TIMEOUT")
                chunks.append(chunk)
        data = json.loads(b"".join(chunks))
        choice = data["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise VideoAIError("AI_RESPONSE_TRUNCATED")
        answer = choice["message"]["content"]
        if not isinstance(answer, str) or not answer.strip() or len(answer) > 60000:
            raise VideoAIError("AI_RESPONSE_INVALID")
        raw_usage = data.get("usage") or {}
        if not isinstance(raw_usage, dict):
            raise VideoAIError("AI_RESPONSE_INVALID")
        usage = {
            key: value
            for key, value in raw_usage.items()
            if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
            and isinstance(value, int)
            and value >= 0
        }
        return answer.strip(), usage
    except httpx.TimeoutException as exc:
        raise VideoAIError("AI_TIMEOUT") from exc
    except httpx.HTTPError as exc:
        raise VideoAIError("AI_NETWORK_ERROR") from exc
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
        raise VideoAIError("AI_RESPONSE_INVALID") from exc
