from pydantic import BaseModel
from typing import Literal


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    image_base64: str | None = None
    image_media_type: str | None = None


class ChatRequest(BaseModel):
    thread_id: str
    messages: list[Message]
    new_message: str
    image_base64: str | None = None
    image_media_type: str | None = None
    provider: str = "lm_studio"
    model: str = "local-model"
    thinking_mode: bool = False
    web_search: bool = False
    terminal_access: bool = False
    # Per-request overrides (None = use server defaults)
    temperature: float | None = None
    top_p: float | None = None
    max_response_tokens: int | None = None
    max_history_tokens: int | None = None
    system_prompt: str | None = None
    tool_call_max_iterations: int | None = None


class TitleRequest(BaseModel):
    message: str
    provider: str = "lm_studio"
    model: str = "local-model"


class TitleResponse(BaseModel):
    title: str


class TerminalExecuteRequest(BaseModel):
    command: str
    working_directory: str = "."
    shell: str = "cmd"


class TerminalExecuteResponse(BaseModel):
    status: str
    command: str
    exit_code: int | None = None
    stdout: str | None = None
    stderr: str | None = None
    truncated: bool = False
    message: str | None = None


class ErrorResponse(BaseModel):
    detail: str


class GlobalSettings(BaseModel):
    temperature: float = 0.3
    top_p: float = 1.0
    max_response_tokens: int = 4096
    max_history_tokens: int = 2000
    system_prompt: str = ""
    tool_call_max_iterations: int = 8
    tool_call_timeout: int = 120


class ApiKeysUpdate(BaseModel):
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None


class ApiKeysResponse(BaseModel):
    openai_api_key: str
    anthropic_api_key: str
    google_api_key: str


class ProviderUrlsUpdate(BaseModel):
    lm_studio_url: str | None = None
    ollama_url: str | None = None
    cli_proxy_url: str | None = None


class ProviderUrlsResponse(BaseModel):
    lm_studio_url: str
    ollama_url: str
    cli_proxy_url: str
