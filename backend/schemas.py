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
    model: str = "local-model"
    thinking_mode: bool = False
    web_search: bool = False
    terminal_access: bool = False


class TitleRequest(BaseModel):
    message: str
    model: str = "local-model"


class TitleResponse(BaseModel):
    title: str


class TerminalExecuteRequest(BaseModel):
    command: str
    working_directory: str = "."


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
