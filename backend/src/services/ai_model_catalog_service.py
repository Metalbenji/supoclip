"""
Provider-backed model catalog lookup for AI settings.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterable, Optional
from urllib import error, parse, request

SUPPORTED_AI_PROVIDERS = {"openai", "google", "anthropic", "zai", "ollama"}
ZAI_OPENAI_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
HTTP_TIMEOUT_SECONDS = 15
HTTP_MAX_RETRIES = 2
HTTP_RETRY_BACKOFF_MS = 400


class ModelCatalogError(Exception):
    """Raised when a provider model catalog cannot be retrieved."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _dedupe_and_sort(values: Iterable[str]) -> list[str]:
    unique = {value.strip() for value in values if isinstance(value, str) and value.strip()}
    return sorted(unique)


def _extract_error_message(payload: Any) -> str | None:
    if isinstance(payload, dict):
        nested_error = payload.get("error")
        if isinstance(nested_error, dict):
            nested_message = nested_error.get("message")
            if isinstance(nested_message, str) and nested_message.strip():
                return nested_message.strip()
        for key in ("message", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _normalize_base_url(base_url: str | None) -> str:
    raw = (base_url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    return raw.rstrip("/")


def _normalize_timeout_seconds(value: Optional[int]) -> int:
    try:
        normalized = int(value if value is not None else HTTP_TIMEOUT_SECONDS)
    except (TypeError, ValueError):
        normalized = HTTP_TIMEOUT_SECONDS
    return max(1, min(600, normalized))


def _normalize_max_retries(value: Optional[int]) -> int:
    try:
        normalized = int(value if value is not None else HTTP_MAX_RETRIES)
    except (TypeError, ValueError):
        normalized = HTTP_MAX_RETRIES
    return max(0, min(10, normalized))


def _normalize_retry_backoff_ms(value: Optional[int]) -> int:
    try:
        normalized = int(value if value is not None else HTTP_RETRY_BACKOFF_MS)
    except (TypeError, ValueError):
        normalized = HTTP_RETRY_BACKOFF_MS
    return max(0, min(30000, normalized))


def _sleep_before_retry(attempt_index: int, retry_backoff_ms: int) -> None:
    if retry_backoff_ms <= 0:
        return
    delay_ms = retry_backoff_ms * max(1, attempt_index)
    time.sleep(delay_ms / 1000.0)


def _request_json(
    provider: str,
    url: str,
    headers: dict[str, str],
    *,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_backoff_ms: Optional[int] = None,
    allow_404: bool = False,
) -> dict[str, Any]:
    resolved_timeout = _normalize_timeout_seconds(timeout_seconds)
    resolved_retries = _normalize_max_retries(max_retries)
    resolved_backoff = _normalize_retry_backoff_ms(retry_backoff_ms)

    req = request.Request(url, headers=headers, method="GET")
    for attempt_index in range(resolved_retries + 1):
        try:
            with request.urlopen(req, timeout=resolved_timeout) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            message = ""
            if body:
                try:
                    parsed = json.loads(body)
                    message = _extract_error_message(parsed) or body
                except json.JSONDecodeError:
                    message = body
            message = (message or f"HTTP {exc.code}").strip()

            if allow_404 and exc.code == 404:
                return {}

            should_retry = exc.code >= 500 or exc.code == 429
            if should_retry and attempt_index < resolved_retries:
                _sleep_before_retry(attempt_index + 1, resolved_backoff)
                continue

            if exc.code in {401, 403}:
                unauthorized_message = (
                    f"{provider} credentials are invalid or unauthorized ({message})"
                    if provider == "ollama"
                    else f"{provider} API key is invalid or unauthorized ({message})"
                )
                raise ModelCatalogError(
                    unauthorized_message,
                    status_code=401,
                ) from exc
            if exc.code == 429:
                raise ModelCatalogError(
                    f"{provider} model listing was rate-limited ({message})",
                    status_code=429,
                ) from exc
            raise ModelCatalogError(
                f"{provider} model listing request failed ({message})",
                status_code=502,
            ) from exc
        except error.URLError as exc:
            if attempt_index < resolved_retries:
                _sleep_before_retry(attempt_index + 1, resolved_backoff)
                continue
            raise ModelCatalogError(
                f"Could not reach {provider} model endpoint ({exc.reason})",
                status_code=502,
            ) from exc

        if not raw_body.strip():
            return {}
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ModelCatalogError(
                f"{provider} model listing returned invalid JSON",
                status_code=502,
            ) from exc

        if not isinstance(payload, dict):
            raise ModelCatalogError(
                f"{provider} model listing returned an unexpected payload",
                status_code=502,
            )
        return payload

    raise ModelCatalogError(
        f"Could not reach {provider} model endpoint",
        status_code=502,
    )


def _list_openai_models(api_key: str) -> list[str]:
    payload = _request_json(
        provider="openai",
        url="https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ModelCatalogError("openai model listing did not include a data array", status_code=502)
    all_model_ids = [row.get("id") for row in rows if isinstance(row, dict)]
    ids = _dedupe_and_sort(model_id for model_id in all_model_ids if isinstance(model_id, str))
    preferred = [model_id for model_id in ids if model_id.startswith(("gpt-", "o1", "o3", "o4"))]
    return preferred or ids


def _list_google_models(api_key: str) -> list[str]:
    encoded_key = parse.urlencode({"key": api_key})
    payload = _request_json(
        provider="google",
        url=f"https://generativelanguage.googleapis.com/v1beta/models?{encoded_key}",
        headers={},
    )
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise ModelCatalogError("google model listing did not include a models array", status_code=502)

    ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        methods = row.get("supportedGenerationMethods")
        if isinstance(methods, list) and methods and "generateContent" not in methods:
            continue
        raw_name = row.get("name")
        if not isinstance(raw_name, str):
            continue
        model_id = raw_name.split("/", 1)[1] if raw_name.startswith("models/") else raw_name
        model_id = model_id.strip()
        if model_id:
            ids.append(model_id)

    deduped = _dedupe_and_sort(ids)
    preferred = [model_id for model_id in deduped if model_id.startswith("gemini-")]
    return preferred or deduped


def _list_anthropic_models(api_key: str) -> list[str]:
    payload = _request_json(
        provider="anthropic",
        url="https://api.anthropic.com/v1/models",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
    )
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ModelCatalogError("anthropic model listing did not include a data array", status_code=502)
    all_model_ids = [row.get("id") for row in rows if isinstance(row, dict)]
    ids = _dedupe_and_sort(model_id for model_id in all_model_ids if isinstance(model_id, str))
    preferred = [model_id for model_id in ids if model_id.startswith("claude-")]
    return preferred or ids


def _list_zai_models(api_key: str) -> list[str]:
    payload = _request_json(
        provider="zai",
        url=f"{ZAI_OPENAI_BASE_URL}/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ModelCatalogError("zai model listing did not include a data array", status_code=502)
    all_model_ids = [row.get("id") for row in rows if isinstance(row, dict)]
    ids = _dedupe_and_sort(model_id for model_id in all_model_ids if isinstance(model_id, str))
    preferred = [model_id for model_id in ids if model_id.startswith("glm-")]
    return preferred or ids


def _list_ollama_models(
    base_url: str | None,
    auth_headers: Optional[dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_backoff_ms: Optional[int] = None,
) -> list[str]:
    normalized_base_url = _normalize_base_url(base_url) or DEFAULT_OLLAMA_BASE_URL
    payload = _request_json(
        provider="ollama",
        url=f"{normalized_base_url}/api/tags",
        headers=dict(auth_headers or {}),
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
    )
    rows = payload.get("models")
    if not isinstance(rows, list):
        raise ModelCatalogError("ollama model listing did not include a models array", status_code=502)

    names: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_name = row.get("model")
        if not isinstance(model_name, str) or not model_name.strip():
            model_name = row.get("name")
        if isinstance(model_name, str) and model_name.strip():
            names.append(model_name.strip())

    return _dedupe_and_sort(names)


def _get_ollama_version(
    base_url: str,
    auth_headers: Optional[dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_backoff_ms: Optional[int] = None,
) -> Optional[str]:
    payload = _request_json(
        provider="ollama",
        url=f"{base_url}/api/version",
        headers=dict(auth_headers or {}),
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
        retry_backoff_ms=retry_backoff_ms,
        allow_404=True,
    )
    version = payload.get("version") if isinstance(payload, dict) else None
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None


def test_ollama_connection(
    base_url: str | None,
    auth_headers: Optional[dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_backoff_ms: Optional[int] = None,
) -> dict[str, Any]:
    normalized_base_url = _normalize_base_url(base_url) or DEFAULT_OLLAMA_BASE_URL
    resolved_timeout = _normalize_timeout_seconds(timeout_seconds)
    resolved_retries = _normalize_max_retries(max_retries)
    resolved_backoff = _normalize_retry_backoff_ms(retry_backoff_ms)

    try:
        models = _list_ollama_models(
            normalized_base_url,
            auth_headers=auth_headers,
            timeout_seconds=resolved_timeout,
            max_retries=resolved_retries,
            retry_backoff_ms=resolved_backoff,
        )
    except ModelCatalogError as exc:
        return {
            "connected": False,
            "status": "error",
            "server_url": normalized_base_url,
            "version": None,
            "model_count": 0,
            "models": [],
            "failure_reason": str(exc),
            "failure_status_code": int(exc.status_code),
            "request_controls": {
                "timeout_seconds": resolved_timeout,
                "max_retries": resolved_retries,
                "retry_backoff_ms": resolved_backoff,
            },
        }

    version: Optional[str] = None
    try:
        version = _get_ollama_version(
            normalized_base_url,
            auth_headers=auth_headers,
            timeout_seconds=resolved_timeout,
            max_retries=resolved_retries,
            retry_backoff_ms=resolved_backoff,
        )
    except Exception:
        version = None

    return {
        "connected": True,
        "status": "ok",
        "server_url": normalized_base_url,
        "version": version,
        "model_count": len(models),
        "models": models,
        "failure_reason": None,
        "failure_status_code": None,
        "request_controls": {
            "timeout_seconds": resolved_timeout,
            "max_retries": resolved_retries,
            "retry_backoff_ms": resolved_backoff,
        },
    }


def pull_ollama_model(
    base_url: str | None,
    model: str,
    auth_headers: Optional[dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_backoff_ms: Optional[int] = None,
) -> dict[str, Any]:
    normalized_base_url = _normalize_base_url(base_url) or DEFAULT_OLLAMA_BASE_URL
    normalized_model = str(model or "").strip()
    if not normalized_model:
        raise ModelCatalogError("ollama model name is required", status_code=400)

    resolved_timeout = _normalize_timeout_seconds(timeout_seconds)
    resolved_retries = _normalize_max_retries(max_retries)
    resolved_backoff = _normalize_retry_backoff_ms(retry_backoff_ms)
    request_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **dict(auth_headers or {}),
    }
    body = json.dumps({"model": normalized_model, "stream": False}).encode("utf-8")
    req = request.Request(
        f"{normalized_base_url}/api/pull",
        headers=request_headers,
        data=body,
        method="POST",
    )

    for attempt_index in range(resolved_retries + 1):
        try:
            with request.urlopen(req, timeout=resolved_timeout) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body_text = ""

            message = ""
            if body_text:
                try:
                    parsed = json.loads(body_text)
                    message = _extract_error_message(parsed) or body_text
                except json.JSONDecodeError:
                    message = body_text
            message = (message or f"HTTP {exc.code}").strip()

            should_retry = exc.code >= 500 or exc.code == 429
            if should_retry and attempt_index < resolved_retries:
                _sleep_before_retry(attempt_index + 1, resolved_backoff)
                continue

            if exc.code in {401, 403}:
                raise ModelCatalogError(
                    f"ollama credentials are invalid or unauthorized ({message})",
                    status_code=401,
                ) from exc
            if exc.code == 429:
                raise ModelCatalogError(
                    f"ollama model pull was rate-limited ({message})",
                    status_code=429,
                ) from exc
            raise ModelCatalogError(
                f"ollama model pull failed ({message})",
                status_code=502,
            ) from exc
        except error.URLError as exc:
            if attempt_index < resolved_retries:
                _sleep_before_retry(attempt_index + 1, resolved_backoff)
                continue
            raise ModelCatalogError(
                f"Could not reach ollama model endpoint ({exc.reason})",
                status_code=502,
            ) from exc

        if not raw_body.strip():
            return {"status": "ok", "message": "pull request accepted"}
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise ModelCatalogError(
                "ollama model pull returned invalid JSON",
                status_code=502,
            ) from exc
        if not isinstance(payload, dict):
            raise ModelCatalogError(
                "ollama model pull returned an unexpected payload",
                status_code=502,
            )
        error_message = _extract_error_message(payload)
        if error_message:
            raise ModelCatalogError(
                f"ollama model pull failed ({error_message})",
                status_code=502,
            )
        return payload

    raise ModelCatalogError("Could not reach ollama model endpoint", status_code=502)


def list_models_for_provider(
    provider: str,
    api_key: str,
    base_url: str | None = None,
    auth_headers: Optional[dict[str, str]] = None,
    timeout_seconds: Optional[int] = None,
    max_retries: Optional[int] = None,
    retry_backoff_ms: Optional[int] = None,
) -> list[str]:
    normalized_provider = (provider or "").strip().lower()
    normalized_key = (api_key or "").strip()
    if normalized_provider not in SUPPORTED_AI_PROVIDERS:
        raise ModelCatalogError(f"Unsupported AI provider: {provider}", status_code=400)
    if normalized_provider != "ollama" and not normalized_key:
        raise ModelCatalogError("api key is required to fetch models", status_code=400)

    if normalized_provider == "openai":
        models = _list_openai_models(normalized_key)
    elif normalized_provider == "google":
        models = _list_google_models(normalized_key)
    elif normalized_provider == "anthropic":
        models = _list_anthropic_models(normalized_key)
    elif normalized_provider == "zai":
        models = _list_zai_models(normalized_key)
    else:
        models = _list_ollama_models(
            base_url,
            auth_headers=auth_headers,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            retry_backoff_ms=retry_backoff_ms,
        )

    if not models:
        raise ModelCatalogError(f"No models returned for {normalized_provider}", status_code=502)
    return models
