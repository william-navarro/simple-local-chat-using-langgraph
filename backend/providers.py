from enum import Enum

import httpx
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel

from config import settings
from model_cache import get_cloud_models


class Provider(str, Enum):
    LM_STUDIO = "lm_studio"
    OLLAMA = "ollama"
    CLI_PROXY = "cli_proxy"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"


def get_llm(
    provider: str,
    model: str,
    temperature: float = 0.3,
    top_p: float = 1.0,
    max_tokens: int | None = None,
    streaming: bool = False,
) -> BaseChatModel:
    """Factory that returns the correct LangChain chat model for any provider."""
    p = Provider(provider)

    if p == Provider.LM_STUDIO:
        return ChatOpenAI(
            base_url=settings.lm_studio_url,
            api_key="lm-studio",
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            streaming=streaming,
            request_timeout=120,
        )

    if p == Provider.OLLAMA:
        return ChatOpenAI(
            base_url=settings.ollama_url,
            api_key="ollama",
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            streaming=streaming,
            request_timeout=120,
        )

    if p == Provider.CLI_PROXY:
        return ChatOpenAI(
            base_url=settings.cli_proxy_url,
            api_key="sk-dummy",
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            streaming=streaming,
            request_timeout=120,
        )

    if p == Provider.OPENAI:
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            streaming=streaming,
            request_timeout=120,
        )

    if p == Provider.ANTHROPIC:
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            api_key=settings.anthropic_api_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens or 4096,
            top_p=top_p,
            streaming=streaming,
            default_request_timeout=120,
        )

    if p == Provider.GOOGLE:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            google_api_key=settings.google_api_key,
            model=model,
            temperature=temperature,
            max_output_tokens=max_tokens,
            top_p=top_p,
            streaming=streaming,
            timeout=120,
        )

    raise ValueError(f"Unknown provider: {provider}")


# ---------------------------------------------------------------------------
# Provider status & model listing
# ---------------------------------------------------------------------------

_LOCAL_PROVIDERS = {
    Provider.LM_STUDIO: lambda: settings.lm_studio_url,
    Provider.OLLAMA: lambda: settings.ollama_url,
    Provider.CLI_PROXY: lambda: settings.cli_proxy_url,
}

_CLOUD_API_KEYS = {
    Provider.OPENAI: lambda: settings.openai_api_key,
    Provider.ANTHROPIC: lambda: settings.anthropic_api_key,
    Provider.GOOGLE: lambda: settings.google_api_key,
}


_PROVIDER_DISPLAY_NAMES = {
    Provider.LM_STUDIO: "LM Studio",
    Provider.OLLAMA: "Ollama",
    Provider.CLI_PROXY: "CLI Proxy",
    Provider.OPENAI: "OpenAI",
    Provider.ANTHROPIC: "Anthropic",
    Provider.GOOGLE: "Google",
}


def _get_auth_headers(p: Provider) -> dict[str, str]:
    """Return auth headers needed for provider status/model checks."""
    if p == Provider.CLI_PROXY:
        return {"Authorization": "Bearer sk-dummy"}
    return {}


async def check_provider_status(provider: str) -> bool:
    p = Provider(provider)

    if p in _LOCAL_PROVIDERS:
        base_url = _LOCAL_PROVIDERS[p]()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    f"{base_url}/models",
                    headers=_get_auth_headers(p),
                )
                return resp.status_code == 200
        except Exception:
            return False

    key = _CLOUD_API_KEYS.get(p, lambda: "")()
    return bool(key and key.strip())


async def fetch_provider_models(provider: str) -> list[str]:
    p = Provider(provider)

    if p in _LOCAL_PROVIDERS:
        base_url = _LOCAL_PROVIDERS[p]()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(
                    f"{base_url}/models",
                    headers=_get_auth_headers(p),
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [m["id"] for m in data.get("data", [])]
        except Exception:
            pass
        return []

    return get_cloud_models(p.value)


async def list_all_providers() -> list[dict]:
    result = []
    for p in Provider:
        available = await check_provider_status(p.value)
        result.append({
            "id": p.value,
            "name": _PROVIDER_DISPLAY_NAMES.get(p, p.value),
            "available": available,
        })
    return result
