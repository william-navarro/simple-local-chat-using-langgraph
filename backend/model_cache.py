"""
Cloud model cache — fetches and caches available models from cloud providers.

The cache is stored as a JSON file and refreshed:
  - Once on backend startup
  - Every 24 hours via background task
  - On demand via the /providers/refresh-models endpoint
"""

import json
import logging
import time
from pathlib import Path

import httpx

from config import settings

logger = logging.getLogger(__name__)

_CACHE_FILE = Path(__file__).parent / "data" / "models_cache.json"
_CACHE_TTL = 86_400  # 24 hours in seconds

# Fallback lists used when API fetch fails and no cache exists
_FALLBACK_MODELS: dict[str, list[str]] = {
    "openai": [
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-4o-mini",
        "o3-mini",
    ],
    "anthropic": [
        "claude-sonnet-4-5-20250514",
        "claude-haiku-3-5-20241022",
    ],
    "google": [
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ],
}


def _read_cache() -> dict:
    """Read the cache file. Returns empty dict if missing or corrupt."""
    try:
        if _CACHE_FILE.exists():
            return json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_cache(data: dict) -> None:
    """Persist cache to disk."""
    _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_cached_models(provider: str) -> list[str] | None:
    """Return cached models if they exist and are fresh (within TTL)."""
    cache = _read_cache()
    entry = cache.get(provider)
    if not entry:
        return None
    if time.time() - entry.get("fetched_at", 0) > _CACHE_TTL:
        return None
    return entry.get("models", [])


def get_cached_models_any_age(provider: str) -> list[str]:
    """Return cached models regardless of age, or fallback list."""
    cache = _read_cache()
    entry = cache.get(provider)
    if entry and entry.get("models"):
        return entry["models"]
    return list(_FALLBACK_MODELS.get(provider, []))


def _save_provider_models(provider: str, models: list[str]) -> None:
    """Save fetched models for a provider into the cache."""
    cache = _read_cache()
    cache[provider] = {
        "models": models,
        "fetched_at": time.time(),
    }
    _write_cache(cache)


# ---------------------------------------------------------------------------
# Remote fetchers per provider
# ---------------------------------------------------------------------------

_OPENAI_CHAT_PREFIXES = ("gpt-", "o1", "o3", "o4", "chatgpt-")


async def _fetch_openai_models() -> list[str]:
    """Fetch model list from OpenAI API."""
    key = settings.openai_api_key
    if not key:
        return []
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        models = [
            m["id"] for m in data.get("data", [])
            if any(m["id"].startswith(p) for p in _OPENAI_CHAT_PREFIXES)
        ]
        models.sort()
        return models


async def _fetch_anthropic_models() -> list[str]:
    """Fetch model list from Anthropic API."""
    key = settings.anthropic_api_key
    if not key:
        return []
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        models = [m["id"] for m in data.get("data", [])]
        models.sort()
        return models


async def _fetch_google_models() -> list[str]:
    """Fetch model list from Google Generative AI API."""
    key = settings.google_api_key
    if not key:
        return []
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": key},
        )
        resp.raise_for_status()
        data = resp.json()
        models = []
        for m in data.get("models", []):
            name: str = m.get("name", "")
            # Format: "models/gemini-2.5-flash" -> "gemini-2.5-flash"
            if name.startswith("models/"):
                name = name[7:]
            # Only include generateContent-capable models
            methods = m.get("supportedGenerationMethods", [])
            if "generateContent" in methods and name:
                models.append(name)
        models.sort()
        return models


_CLOUD_FETCHERS: dict[str, callable] = {
    "openai": _fetch_openai_models,
    "anthropic": _fetch_anthropic_models,
    "google": _fetch_google_models,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def refresh_provider_models(provider: str) -> list[str]:
    """Fetch fresh models from a cloud provider and update cache."""
    fetcher = _CLOUD_FETCHERS.get(provider)
    if not fetcher:
        return []
    try:
        models = await fetcher()
        if models:
            _save_provider_models(provider, models)
            logger.info(f"[MODEL_CACHE] {provider}: cached {len(models)} models")
            return models
    except Exception as e:
        logger.warning(f"[MODEL_CACHE] {provider}: fetch failed: {e}")
    return get_cached_models_any_age(provider)


async def refresh_all_cloud_models() -> dict[str, list[str]]:
    """Refresh models for all cloud providers that have API keys configured."""
    results = {}
    for provider in _CLOUD_FETCHERS:
        models = await refresh_provider_models(provider)
        if models:
            results[provider] = models
    return results


def get_cloud_models(provider: str) -> list[str]:
    """Get models for a cloud provider — cached first, fallback if no cache."""
    cached = get_cached_models(provider)
    if cached is not None:
        return cached
    return get_cached_models_any_age(provider)
