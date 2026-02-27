import json
import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import settings
from schemas import (
    ChatRequest, TitleRequest, TitleResponse, ErrorResponse,
    TerminalExecuteRequest, TerminalExecuteResponse,
)
from graph import stream_graph_response, generate_title_from_message
from tools import execute_terminal_command

app = FastAPI(
    title="LangGraph Chat API",
    description="Chat backend powered by LangGraph and LM Studio",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/lmstudio/status")
async def lmstudio_status():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.lm_studio_url}/models")
            if response.status_code == 200:
                return {"online": True}
    except Exception:
        pass
    return {"online": False}


@app.get("/lmstudio/models")
async def lmstudio_models():
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.lm_studio_url}/models")
            if response.status_code == 200:
                data = response.json()
                models = [m["id"] for m in data.get("data", [])]
                return {"models": models}
    except Exception:
        pass
    return {"models": []}


@app.post(
    "/chat/title",
    response_model=TitleResponse,
)
async def chat_title(request: TitleRequest):
    try:
        title = await generate_title_from_message(request.model, request.message)
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
                model=request.model,
                thinking_mode=request.thinking_mode,
                web_search=request.web_search,
                terminal_access=request.terminal_access,
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
    result = execute_terminal_command(request.command, request.working_directory)
    return TerminalExecuteResponse(**result)
