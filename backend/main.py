import json
import logging
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

from config import settings
from pathlib import Path

from schemas import (
    ChatRequest, TitleRequest, TitleResponse, ErrorResponse,
    TerminalExecuteRequest, TerminalExecuteResponse,
    ResumeRequest,
    GlobalSettings, ApiKeysUpdate, ApiKeysResponse,
    ProviderUrlsUpdate, ProviderUrlsResponse,
)
from graph import stream_graph_response, resume_graph_response, generate_title_from_message, get_compiled_graph, close_checkpointer
from providers import check_provider_status, fetch_provider_models, list_all_providers
from model_cache import refresh_all_cloud_models
from settings_store import get_settings, update_settings
from tools import execute_terminal_command

app = FastAPI(
    title="LangGraph Chat API",
    description="Chat backend powered by LangGraph with multi-provider LLM support",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    """Initialize checkpointer and refresh cloud model lists on backend startup."""
    await get_compiled_graph()
    logging.info("[STARTUP] LangGraph checkpointer initialized")
    results = await refresh_all_cloud_models()
    for provider, models in results.items():
        logging.info(f"[STARTUP] {provider}: {len(models)} models cached")


@app.on_event("shutdown")
async def on_shutdown():
    """Close checkpointer connection on shutdown."""
    await close_checkpointer()
    logging.info("[SHUTDOWN] Checkpointer closed")


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/providers")
async def providers_list():
    return await list_all_providers()


@app.get("/providers/{provider}/status")
async def provider_status(provider: str):
    online = await check_provider_status(provider)
    return {"online": online}


@app.get("/providers/{provider}/models")
async def provider_models(provider: str):
    models = await fetch_provider_models(provider)
    return {"models": models}


@app.post("/providers/refresh-models")
async def providers_refresh_models():
    """Force refresh of cloud provider model lists."""
    results = await refresh_all_cloud_models()
    return {
        provider: len(models)
        for provider, models in results.items()
    }


# Backward-compat aliases
@app.get("/lmstudio/status")
async def lmstudio_status():
    online = await check_provider_status("lm_studio")
    return {"online": online}


@app.get("/lmstudio/models")
async def lmstudio_models():
    models = await fetch_provider_models("lm_studio")
    return {"models": models}


@app.post(
    "/chat/title",
    response_model=TitleResponse,
)
async def chat_title(request: TitleRequest):
    try:
        title = await generate_title_from_message(request.provider, request.model, request.message)
    except Exception as e:
        print(f"[TITLE ENDPOINT] Error: {e}")
        words = request.message.split()[:6]
        title = " ".join(words)
    return TitleResponse(title=title)


@app.post(
    "/chat/stream",
    responses={500: {"model": ErrorResponse}},
)

async def chat_stream(request: ChatRequest):
    async def event_generator():
        try:
            async for chunk in stream_graph_response(
                thread_id=request.thread_id,
                messages=[m.model_dump() for m in request.messages],
                new_message=request.new_message,
                image_base64=request.image_base64,
                image_media_type=request.image_media_type,
                provider=request.provider,
                model=request.model,
                thinking_mode=request.thinking_mode,
                web_search=request.web_search,
                terminal_access=request.terminal_access,
                temperature=request.temperature,
                top_p=request.top_p,
                max_response_tokens=request.max_response_tokens,
                max_history_tokens=request.max_history_tokens,
                system_prompt=request.system_prompt,
                tool_call_max_iterations=request.tool_call_max_iterations,
            ):
                yield chunk
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/chat/resume")
async def chat_resume(request: ResumeRequest):
    async def event_generator():
        try:
            async for chunk in resume_graph_response(
                thread_id=request.thread_id,
                approved=request.approved,
                result=request.result,
                provider=request.provider,
                model=request.model,
            ):
                yield chunk
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post(
    "/chat/terminal/execute",
    response_model=TerminalExecuteResponse,
)
async def terminal_execute_endpoint(request: TerminalExecuteRequest):
    result = execute_terminal_command(request.command, request.working_directory, request.shell)
    return TerminalExecuteResponse(**result)


# --- Settings endpoints ---

def _mask_key(key: str) -> str:
    if not key or len(key) < 8:
        return "***" if key else ""
    return key[:3] + "..." + key[-4:]


def _patch_env_file(key_map: dict[str, str | None]) -> None:
    """Patch .env file with updated values."""
    env_path = Path(__file__).parent / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []

    updated_keys: set[str] = set()
    new_lines: list[str] = []
    for line in lines:
        replaced = False
        for env_key, value in key_map.items():
            if value is not None and line.strip().startswith(f"{env_key}="):
                new_lines.append(f"{env_key}={value}")
                updated_keys.add(env_key)
                replaced = True
                break
        if not replaced:
            new_lines.append(line)

    for env_key, value in key_map.items():
        if value is not None and env_key not in updated_keys:
            new_lines.append(f"{env_key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@app.get("/settings")
async def settings_get():
    return GlobalSettings(**get_settings())


@app.put("/settings")
async def settings_put(body: GlobalSettings):
    updated = update_settings(body.model_dump())
    return GlobalSettings(**updated)


# --- API Keys ---

@app.get("/settings/keys", response_model=ApiKeysResponse)
async def settings_keys_get():
    return ApiKeysResponse(
        openai_api_key=_mask_key(settings.openai_api_key),
        anthropic_api_key=_mask_key(settings.anthropic_api_key),
        google_api_key=_mask_key(settings.google_api_key),
    )


@app.put("/settings/keys")
async def settings_keys_put(body: ApiKeysUpdate):
    if body.openai_api_key is not None:
        settings.openai_api_key = body.openai_api_key
    if body.anthropic_api_key is not None:
        settings.anthropic_api_key = body.anthropic_api_key
    if body.google_api_key is not None:
        settings.google_api_key = body.google_api_key
    _patch_env_file({
        "OPENAI_API_KEY": body.openai_api_key,
        "ANTHROPIC_API_KEY": body.anthropic_api_key,
        "GOOGLE_API_KEY": body.google_api_key,
    })
    return {"status": "ok"}


# --- Provider URLs ---

@app.get("/settings/urls", response_model=ProviderUrlsResponse)
async def settings_urls_get():
    return ProviderUrlsResponse(
        lm_studio_url=settings.lm_studio_url,
        ollama_url=settings.ollama_url,
        cli_proxy_url=settings.cli_proxy_url,
    )


@app.put("/settings/urls")
async def settings_urls_put(body: ProviderUrlsUpdate):
    if body.lm_studio_url is not None:
        settings.lm_studio_url = body.lm_studio_url
    if body.ollama_url is not None:
        settings.ollama_url = body.ollama_url
    if body.cli_proxy_url is not None:
        settings.cli_proxy_url = body.cli_proxy_url
    _patch_env_file({
        "LM_STUDIO_URL": body.lm_studio_url,
        "OLLAMA_URL": body.ollama_url,
        "CLI_PROXY_URL": body.cli_proxy_url,
    })
    return {"status": "ok"}


# --- CLI Proxy auth ---

@app.get("/cli-proxy/auth-status")
async def cli_proxy_auth_status():
    """Check if CLI Proxy is running and authenticated (token valid)."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                f"{settings.cli_proxy_url}/models",
                headers={"Authorization": "Bearer sk-dummy"},
            )
            if resp.status_code == 200:
                return {"authenticated": True, "running": True}
            return {"authenticated": False, "running": True, "status_code": resp.status_code}
    except Exception:
        return {"authenticated": False, "running": False}


@app.post("/cli-proxy/login")
async def cli_proxy_login():
    """Trigger CLI Proxy OAuth login (opens browser on the server machine)."""
    import asyncio
    import shutil

    exe = shutil.which("cli-proxy-api") or shutil.which("cli-proxy-api.exe")
    if not exe:
        # Try relative bin/ path
        bin_dir = Path(__file__).parent.parent / "bin"
        for name in ("cli-proxy-api.exe", "cli-proxy-api"):
            candidate = bin_dir / name
            if candidate.exists():
                exe = str(candidate)
                break

    if not exe:
        return {"status": "error", "message": "cli-proxy-api binary not found"}

    try:
        proc = await asyncio.create_subprocess_exec(
            exe, "-login",
            cwd=str(Path(exe).parent),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Wait up to 120s for the OAuth flow to complete
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        if proc.returncode == 0:
            return {"status": "ok", "message": "Login successful"}
        return {
            "status": "error",
            "message": stderr.decode(errors="replace").strip() or "Login failed",
        }
    except asyncio.TimeoutError:
        return {"status": "error", "message": "Login timed out (120s). Try again."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
