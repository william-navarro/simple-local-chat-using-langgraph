import asyncio
import json
import logging
import platform
import re
import uuid
from typing import AsyncIterator, TypedDict, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import RunnableConfig

log = logging.getLogger(__name__)

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    AIMessageChunk,
    SystemMessage,
    ToolMessage,
)
from pathlib import Path
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command

from config import settings
from providers import get_llm
from tools import ALL_TOOLS, web_search, terminal_execute, send_image


# --- State (mutable execution data only) ---

class GraphState(TypedDict):
    messages: list[AnyMessage]
    new_message: str
    image_base64: str | None
    image_media_type: str | None
    message_type: Literal["simple", "summary_request", "system_instruction"]
    history_compressed: bool
    tool_calls_log: list[dict]
    tool_call_iterations: int


# --- Config (immutable per-request, passed via RunnableConfig) ---

class GraphConfig(TypedDict):
    """Passed via config['configurable']. Not part of graph state."""
    provider: str
    model: str
    temperature: float
    top_p: float
    max_response_tokens: int | None
    max_history_tokens: int
    custom_system_prompt: str
    max_iterations_limit: int
    thinking_mode: bool
    web_search: bool
    terminal_access: bool
    llm: BaseChatModel


# --- Helpers ---

def get_enabled_tools(conf: dict) -> list:
    """Return the list of tools to bind based on config flags."""
    tools = []
    if conf.get("web_search"):
        tools.append(web_search)
    if conf.get("terminal_access"):
        tools.append(terminal_execute)
        tools.append(send_image)
    return tools


def has_tools_enabled(conf: dict) -> bool:
    """Check if any tool mode is enabled."""
    return bool(conf.get("web_search") or conf.get("terminal_access"))


CHARS_PER_TOKEN = 3  # Approximate; works well for multilingual (EN+PT) content

def _msg_tokens(m: AnyMessage) -> int:
    """Estimate token count for a single message."""
    if isinstance(m.content, str):
        return len(m.content) // CHARS_PER_TOKEN
    if isinstance(m.content, list):
        total = 0
        for block in m.content:
            if isinstance(block, dict) and block.get("type") == "text":
                total += len(block.get("text", ""))
        return total // CHARS_PER_TOKEN
    return 0


def estimate_tokens(messages: list[AnyMessage]) -> int:
    return sum(_msg_tokens(m) for m in messages)


def _is_error_message(m: AnyMessage) -> bool:
    """Check if a message is a backend error (not useful for context)."""
    if isinstance(m, AIMessage) and isinstance(m.content, str):
        return m.content.startswith("[Error:") or m.content.startswith("\n\n[Error:")
    return False


def truncate_history(messages: list[AnyMessage], max_tokens: int) -> list[AnyMessage]:
    """Keep only the most recent messages that fit within max_tokens.

    Drops backend error messages and trims from the oldest end first.
    Always preserves at least the last 2 messages for minimal context.
    """
    # Filter out error messages — they waste tokens and confuse the model
    cleaned = [m for m in messages if not _is_error_message(m)]

    # If already within budget, return as-is
    if estimate_tokens(cleaned) <= max_tokens:
        return cleaned

    # Keep adding messages from the end until we exceed the budget
    result: list[AnyMessage] = []
    budget = max_tokens
    for m in reversed(cleaned):
        cost = _msg_tokens(m)
        if cost > budget and len(result) >= 2:
            break
        result.append(m)
        budget -= cost

    result.reverse()
    return result


_MAX_TOOL_RESULT_CHARS = 2000  # Max chars of tool output sent to LLM context


def _truncate_tool_result(text: str, limit: int = _MAX_TOOL_RESULT_CHARS) -> str:
    """Truncate a tool result string to fit within token budget."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (truncated, {len(text)} total chars)"


def build_system_prompt(
    message_type: str,
    thinking_mode: bool,
    web_search: bool = False,
    terminal_access: bool = False,
    custom_system_prompt: str = "",
) -> str:
    base = custom_system_prompt.strip() if custom_system_prompt else "You are a helpful and concise AI assistant."

    if message_type == "summary_request":
        base += " Provide a clear, structured summary."
    elif message_type == "system_instruction":
        base += " Follow the user's instruction precisely."

    if web_search:
        base += (
            " You have a web_search tool. Use it for current events, real-time data, "
            "or facts you're unsure about. Answer directly for general knowledge."
        )

    if terminal_access:
        os_name = platform.system()
        base += (
            " You have terminal_execute and send_image(file_path: str) tools. "
            "These are separate API tools — call them via tool_calls, NOT as shell commands. "
            "ALWAYS call the tool — never simulate or fabricate output. "
            "You can call multiple tools at once (parallel tool calls). "
            "IMPORTANT: If a task requires chaining (e.g. list files then show one), "
            "do the first step now and tell the user to ask for the next step. "
            "Retry on errors before explaining them. Avoid recursive scans on root dirs."
        )
        if os_name == "Windows":
            base += (
                " terminal_execute has a 'shell' param: 'cmd' (default) or 'powershell'. "
                "Use shell='cmd' for CMD syntax (dir /Q, type, tree, etc.). "
                "Use shell='powershell' for PowerShell cmdlets (Get-ChildItem, Get-Content, etc.). "
                "Do NOT mix syntaxes — CMD flags (/Q, /S) fail in PowerShell and vice-versa."
            )
        else:
            base += " terminal_execute runs bash commands (15s timeout)."

    # thinking_mode is handled entirely by the model's native behavior
    _ = thinking_mode

    return base


def build_user_content(
    text: str,
    image_base64: str | None = None,
    image_media_type: str | None = None,
) -> list[dict] | str:
    if not image_base64:
        return text

    media_type = image_media_type or "image/jpeg"
    return [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{media_type};base64,{image_base64}",
            },
        },
        {
            "type": "text",
            "text": text,
        },
    ]


def build_llm_messages(state: dict, conf: dict) -> list[AnyMessage]:
    """Build the full message list for the LLM call from state + config."""
    system_prompt = build_system_prompt(
        state.get("message_type", "simple"),
        conf.get("thinking_mode", False),
        conf.get("web_search", False),
        conf.get("terminal_access", False),
        conf.get("custom_system_prompt", ""),
    )
    user_content = build_user_content(
        state["new_message"],
        state.get("image_base64"),
        state.get("image_media_type"),
    )

    msgs: list[AnyMessage] = [SystemMessage(content=system_prompt)]
    msgs.extend(state["messages"])
    msgs.append(HumanMessage(content=user_content))
    return msgs


# --- Nodes ---

def node_pre_process(state: GraphState) -> GraphState:
    msg = state["new_message"].lower()

    summary_keywords = ["resumo", "resume", "summarize", "summary", "tldr", "tl;dr"]
    instruction_keywords = [
        "responda sempre", "always respond", "from now on", "a partir de agora",
        "ignore", "act as", "aja como", "you are", "voce e",
    ]

    if any(k in msg for k in summary_keywords):
        message_type: Literal["simple", "summary_request", "system_instruction"] = "summary_request"
    elif any(k in msg for k in instruction_keywords):
        message_type = "system_instruction"
    else:
        message_type = "simple"

    return {**state, "message_type": message_type}


def node_check_history(state: GraphState, config: RunnableConfig) -> GraphState:
    conf = config["configurable"]
    max_hist = conf.get("max_history_tokens", settings.max_history_tokens)
    compressed = estimate_tokens(state["messages"]) > max_hist
    return {**state, "history_compressed": compressed}


async def node_compress_history(state: GraphState, config: RunnableConfig) -> GraphState:
    conf = config["configurable"]
    history_text = "\n".join(
        f"{m.type.upper()}: {m.content}"
        for m in state["messages"]
        if isinstance(m.content, str)
    )

    llm = conf["llm"]
    response = await llm.ainvoke([
        HumanMessage(content=(
            "Summarize the following conversation history concisely, "
            f"preserving key facts and context:\n\n{history_text}"
        )),
    ])

    summary = response.content or ""

    compressed: list[AnyMessage] = [
        HumanMessage(content=f"[Previous conversation summary: {summary}]"),
        AIMessage(content="Understood. I have the context from our previous conversation."),
    ]

    return {**state, "messages": compressed, "history_compressed": True}


_SIMULATED_TOOL_PATTERN = re.compile(
    r"\[Tool call:.*?\]"           # [Tool call: name(...)]
    r"|<tool_call>.*?</tool_call>" # <tool_call>...</tool_call>
    r"|✿FUNCTION✿"                # Some models use this marker
    r"|```tool_code"               # ```tool_code blocks
    , re.IGNORECASE | re.DOTALL
)


async def node_call_model(state: GraphState, config: RunnableConfig) -> GraphState:
    """Call the LLM, optionally with tools bound for tool detection.

    Persists the HumanMessage in state so that downstream nodes
    (like final_response) have the correct message ordering.
    """
    conf = config["configurable"]
    log.info(f"[CALL_MODEL] provider={conf.get('provider')}, model={conf.get('model')}")

    msgs = build_llm_messages(state, conf)
    llm = conf["llm"]

    enabled_tools = get_enabled_tools(conf)
    tools_bound = False
    if enabled_tools and settings.tools_enabled:
        try:
            llm_with_tools = llm.bind_tools(enabled_tools)
            response = await llm_with_tools.ainvoke(msgs)
            tools_bound = True
            has_tc = bool(getattr(response, "tool_calls", None))
            raw_preview = response.content or ""
            if isinstance(raw_preview, list):
                content_preview = "".join(
                    b.get("text", "") if isinstance(b, dict) else str(b) for b in raw_preview
                )[:200]
            else:
                content_preview = raw_preview[:200]
            log.info(f"[CALL_MODEL] bind_tools OK — tool_calls: {has_tc}, content preview: {repr(content_preview)}")
            if has_tc:
                log.info(f"[CALL_MODEL] tool_calls detail: {response.tool_calls}")
        except Exception as e:
            log.info(f"[CALL_MODEL] Tool binding failed, falling back without tools: {e}")
            fallback_conf = {**conf, "web_search": False, "terminal_access": False}
            fallback_msgs = build_llm_messages(state, fallback_conf)
            response = await llm.ainvoke(fallback_msgs)
    else:
        response = await llm.ainvoke(msgs)

    # Detect tool simulation: model wrote tool-call-like text instead of using actual tools
    raw_content = response.content or ""
    if isinstance(raw_content, list):
        content = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in raw_content
        )
    else:
        content = raw_content
    if (
        tools_bound
        and not getattr(response, "tool_calls", None)
        and _SIMULATED_TOOL_PATTERN.search(content)
    ):
        log.info("[CALL_MODEL] Detected simulated tool calls in text, retrying without tools")
        fallback_conf = {**conf, "web_search": False, "terminal_access": False}
        fallback_msgs = build_llm_messages(state, fallback_conf)
        response = await llm.ainvoke(fallback_msgs)

    # Persist the HumanMessage so that final_response sees the correct order:
    # [...history, HumanMessage, AIMessage(tool_calls?), ...]
    user_content = build_user_content(
        state["new_message"],
        state.get("image_base64"),
        state.get("image_media_type"),
    )
    human_msg = HumanMessage(content=user_content)

    return {
        **state,
        "messages": state["messages"] + [human_msg, response],
    }


async def node_tool_executor(state: GraphState) -> GraphState:
    """Execute tool calls from the last AIMessage.

    Terminal commands use `interrupt()` to pause the graph and wait for
    user approval. The frontend receives the interrupt, shows an approval
    dialog, and resumes the graph via `Command(resume=...)`.

    Non-terminal tools are executed in parallel via asyncio.gather().
    """
    last_msg = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    log_entries: list[dict] = []

    tools_by_name = {t.name: t for t in ALL_TOOLS}

    # Separate terminal (needs approval) from other tools (can run in parallel)
    terminal_calls = []
    parallel_calls = []
    for tc in last_msg.tool_calls:
        if tc["name"] == "terminal_execute":
            terminal_calls.append(tc)
        else:
            parallel_calls.append(tc)

    # Execute non-terminal tools in parallel
    async def _exec_tool(tc: dict) -> tuple[dict, str]:
        tool_fn = tools_by_name.get(tc["name"])
        if not tool_fn:
            return tc, json.dumps({"status": "error", "message": f"Unknown tool: {tc['name']}"})
        try:
            result = await asyncio.to_thread(tool_fn.invoke, tc["args"])
            return tc, str(result)
        except Exception as e:
            return tc, json.dumps({"status": "error", "message": f"Tool error: {e}"})

    if parallel_calls:
        results = await asyncio.gather(*[_exec_tool(tc) for tc in parallel_calls])
        for tc, result in results:
            tool_messages.append(
                ToolMessage(content=result, tool_call_id=tc["id"])
            )
            log_entries.append({
                "name": tc["name"],
                "args": tc["args"],
                "result": result,
            })

    # Handle terminal calls — interrupt for user approval
    for tc in terminal_calls:
        command = tc["args"].get("command", "")
        working_directory = tc["args"].get("working_directory", ".")
        shell = tc["args"].get("shell", "cmd")

        # Pause graph execution until user approves/denies
        approval = interrupt({
            "tool_call_id": tc["id"],
            "command": command,
            "working_directory": working_directory,
            "shell": shell,
        })

        if approval.get("approved"):
            # User approved — execute the command
            result_data = approval.get("result")
            if result_data:
                result = json.dumps(result_data)
            else:
                # Fallback: execute here if result not provided
                tool_fn = tools_by_name.get("terminal_execute")
                try:
                    result = str(await asyncio.to_thread(tool_fn.invoke, tc["args"]))
                except Exception as e:
                    result = json.dumps({"status": "error", "message": f"Tool error: {e}"})
        else:
            result = json.dumps({"status": "denied", "message": "Command rejected by user"})

        tool_messages.append(
            ToolMessage(content=result, tool_call_id=tc["id"])
        )
        log_entries.append({
            "name": tc["name"],
            "args": tc["args"],
            "result": result,
        })

    return {
        **state,
        "messages": state["messages"] + tool_messages,
        "tool_calls_log": state.get("tool_calls_log", []) + log_entries,
    }


def _sanitize_tool_messages(msgs: list[AnyMessage]) -> list[AnyMessage]:
    """Replace large base64 content in ToolMessages with a short summary.

    Prevents context overflow when send_image results (with base64 data)
    are passed back to the LLM in the final_response node.
    """
    sanitized: list[AnyMessage] = []
    for m in msgs:
        if isinstance(m, ToolMessage):
            content = m.content or ""
            try:
                parsed = json.loads(content) if isinstance(content, str) else content
                if isinstance(parsed, dict) and "base64" in parsed:
                    # Replace base64 with a summary
                    summary = json.dumps({
                        "status": parsed.get("status", "success"),
                        "file_path": parsed.get("file_path", ""),
                        "media_type": parsed.get("media_type", ""),
                        "note": "Image was sent to the user successfully.",
                    })
                    sanitized.append(ToolMessage(content=summary, tool_call_id=m.tool_call_id))
                    continue
            except (json.JSONDecodeError, TypeError):
                pass
        sanitized.append(m)
    return sanitized


async def node_final_response(state: GraphState, config: RunnableConfig) -> GraphState:
    """Generate final text response after tool execution.

    Calls the LLM WITHOUT tools bound, so it must produce a text
    response based on the tool results already in state["messages"].
    """
    conf = config["configurable"]
    log.info("[FINAL_RESPONSE] Generating response after tool execution")

    system_prompt = build_system_prompt(
        state.get("message_type", "simple"),
        conf.get("thinking_mode", False),
        conf.get("web_search", False),
        conf.get("terminal_access", False),
        conf.get("custom_system_prompt", ""),
    )

    # state["messages"] has: [...history, HumanMessage, AIMessage(tool_calls), ToolMessage(s)]
    # Sanitize to remove large base64 payloads from ToolMessages
    clean_msgs = _sanitize_tool_messages(state["messages"])
    msgs: list[AnyMessage] = [SystemMessage(content=system_prompt)]
    msgs.extend(clean_msgs)

    llm = conf["llm"]
    response = await llm.ainvoke(msgs)  # NO bind_tools — forces text response

    return {
        **state,
        "messages": state["messages"] + [response],
    }


# --- Title generation ---

def _clean_title(raw: str) -> str:
    """Extract a clean title from model output, stripping all reasoning."""
    if not raw:
        return ""

    last_close = raw.rfind("</think>")
    if last_close != -1:
        raw = raw[last_close + 8:]
    elif "<think" in raw.lower():
        idx = raw.lower().find("<think")
        raw = raw[:idx]

    raw = re.sub(r"<[^>]*>", "", raw)
    raw = raw.strip().strip("\"'")

    for line in raw.splitlines():
        line = line.strip()
        if line:
            return line[:80]

    return ""


async def generate_title_from_message(provider: str, model: str, user_message: str) -> str:
    """Generate a title based solely on the user message."""
    llm = get_llm(provider, model, temperature=0.6)

    try:
        response = await llm.ainvoke([
            SystemMessage(content=(
                "You are a title generator. "
                "Reply with ONLY the title text, maximum 6 words. "
                "No quotes, no explanation, no tags, no punctuation at the end."
            )),
            HumanMessage(content=(
                "Generate a short title for this message. "
                "The title MUST be in the SAME language as the message.\n\n"
                f"Message: {user_message[:300]}"
            )),
        ])
        raw = response.content or ""
        title = _clean_title(raw)
    except Exception:
        title = ""

    if not title:
        words = user_message.split()[:6]
        title = " ".join(words)
        if len(title) > 60:
            title = title[:57] + "..."

    return title


# --- Routing ---

def route_after_check(state: GraphState, config: RunnableConfig) -> str:
    if state["history_compressed"]:
        return "compress"
    return "call_model"


def route_after_model(state: GraphState, config: RunnableConfig) -> str:
    """Route after LLM call: if tool_calls present, go to tool_node; otherwise END."""
    conf = config["configurable"]
    last_msg = state["messages"][-1]
    if (
        has_tools_enabled(conf)
        and hasattr(last_msg, "tool_calls")
        and last_msg.tool_calls
    ):
        return "tool_node"
    return END


# --- Graph assembly ---

_CHECKPOINT_DB = Path(__file__).parent / "data" / "checkpoints.db"

# Lazy-initialized async checkpointer and compiled graph
_checkpointer = None
_compiled_graph = None


def _build_graph(checkpointer):
    graph = StateGraph(GraphState)

    # Pre-processing nodes
    graph.add_node("pre_process", node_pre_process)
    graph.add_node("check_history", node_check_history)
    graph.add_node("compress_history", node_compress_history)

    # Core nodes
    graph.add_node("call_model", node_call_model)
    graph.add_node("tool_node", node_tool_executor)
    graph.add_node("final_response", node_final_response)

    # Pre-processing pipeline
    graph.set_entry_point("pre_process")
    graph.add_edge("pre_process", "check_history")
    graph.add_conditional_edges(
        "check_history",
        route_after_check,
        {
            "compress": "compress_history",
            "call_model": "call_model",
        },
    )
    graph.add_edge("compress_history", "call_model")

    # Single-round tool pattern (NO loop back to call_model)
    graph.add_conditional_edges(
        "call_model",
        route_after_model,
        {"tool_node": "tool_node", END: END},
    )
    graph.add_edge("tool_node", "final_response")
    graph.add_edge("final_response", END)

    return graph.compile(checkpointer=checkpointer)


async def get_compiled_graph():
    """Lazy-init the checkpointer and compiled graph (async for SQLite)."""
    global _checkpointer, _compiled_graph
    if _compiled_graph is not None:
        return _compiled_graph

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        _CHECKPOINT_DB.parent.mkdir(parents=True, exist_ok=True)
        _checkpointer = AsyncSqliteSaver.from_conn_string(str(_CHECKPOINT_DB))
        await _checkpointer.setup()
        log.info(f"[CHECKPOINT] Using AsyncSqliteSaver at {_CHECKPOINT_DB}")
    except ImportError:
        from langgraph.checkpoint.memory import MemorySaver
        _checkpointer = MemorySaver()
        log.warning("[CHECKPOINT] langgraph-checkpoint-sqlite not installed, falling back to MemorySaver")

    _compiled_graph = _build_graph(_checkpointer)
    return _compiled_graph


async def close_checkpointer():
    """Close the checkpointer connection (call on shutdown)."""
    global _checkpointer
    if _checkpointer and hasattr(_checkpointer, "conn"):
        await _checkpointer.conn.close()
        _checkpointer = None


# --- Main streaming interface ---

def _sse(event_type: str, content: str | None = None) -> str:
    """Build an SSE data line."""
    payload: dict = {"type": event_type}
    if content is not None:
        payload["content"] = content
    return f"data: {json.dumps(payload)}\n\n"


class _ThinkFilter:
    """Filters <think>...</think> blocks from streaming token content.

    In thinking_mode, tokens pass through unchanged.
    Otherwise, content inside <think>...</think> tags is stripped.
    """

    def __init__(self, thinking_mode: bool):
        self.thinking_mode = thinking_mode
        self._buffer = ""
        self._inside = False

    _TAG_OPEN = "<think"

    def feed(self, token: str) -> list[str]:
        """Feed a token and return list of SSE strings to emit."""
        if not token:
            return []
        if self.thinking_mode:
            return [_sse("token", token)]

        results: list[str] = []
        self._buffer += token
        while True:
            if self._inside:
                close = self._buffer.find("</think")
                if close == -1:
                    self._buffer = ""
                    break
                tag_end = self._buffer.find(">", close)
                if tag_end == -1:
                    break
                self._buffer = self._buffer[tag_end + 1:]
                self._inside = False
            else:
                open_pos = self._buffer.find("<think")
                if open_pos == -1:
                    # Hold back any trailing chars that could be a partial "<think"
                    safe = self._buffer
                    held = ""
                    for i in range(min(len(self._TAG_OPEN), len(safe)), 0, -1):
                        if safe.endswith(self._TAG_OPEN[:i]):
                            held = safe[-i:]
                            safe = safe[:-i]
                            break
                    if safe:
                        results.append(_sse("token", safe))
                    self._buffer = held
                    break
                before = self._buffer[:open_pos]
                if before:
                    results.append(_sse("token", before))
                tag_end = self._buffer.find(">", open_pos)
                if tag_end == -1:
                    self._buffer = self._buffer[open_pos:]
                    break
                self._buffer = self._buffer[tag_end + 1:]
                self._inside = True
        return results

    def flush(self) -> list[str]:
        """Flush any remaining buffered content."""
        if not self.thinking_mode and self._buffer and not self._inside:
            result = [_sse("token", self._buffer)]
            self._buffer = ""
            return result
        return []


def _emit_tool_message(msg: ToolMessage) -> str | None:
    """Convert a ToolMessage to an SSE event (image_result or tool_result)."""
    content = msg.content or ""
    try:
        result = json.loads(content) if isinstance(content, str) else content
        if isinstance(result, dict) and result.get("status") == "success" and "base64" in result:
            return _sse("image_result", json.dumps({
                "file_path": result["file_path"],
                "media_type": result["media_type"],
                "base64": result["base64"],
            }))
    except (json.JSONDecodeError, TypeError, KeyError):
        pass
    return _sse("tool_result", content)


async def _stream_graph_messages(
    graph,
    input_data,
    config: RunnableConfig,
    thinking_mode: bool,
    graph_thread_id: str | None = None,
) -> AsyncIterator[str]:
    """Unified streaming loop using astream(stream_mode="messages").

    Streams tokens from the LLM in real-time, emits tool_start/tool_result
    events as tools are called, and handles interrupts for terminal approval.
    Works for both initial requests and resumed graphs.
    """
    think_filter = _ThinkFilter(thinking_mode)
    emitted_tool_calls: set[str] = set()  # track tool call IDs already announced

    try:
        async for event, metadata in graph.astream(
            input_data, config=config, stream_mode="messages"
        ):
            node = metadata.get("langgraph_node", "")

            if isinstance(event, AIMessageChunk):
                # Tool call chunks — emit tool_start when we first see each tool call
                if event.tool_call_chunks:
                    for tc_chunk in event.tool_call_chunks:
                        tc_id = tc_chunk.get("id", "")
                        tc_name = tc_chunk.get("name", "")
                        if tc_name and tc_id and tc_id not in emitted_tool_calls:
                            emitted_tool_calls.add(tc_id)
                            # args may be a JSON string or partial; try to parse it
                            raw_args = tc_chunk.get("args", "")
                            try:
                                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) and raw_args else {}
                            except (json.JSONDecodeError, TypeError):
                                parsed_args = {}
                            yield _sse("tool_start", json.dumps({
                                "name": tc_name,
                                "args": parsed_args,
                            }))

                # Text content — stream tokens in real-time
                raw_content = event.content
                if isinstance(raw_content, list):
                    # Multimodal format: [{"type": "text", "text": "..."}]
                    content = "".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in raw_content
                    )
                else:
                    content = raw_content or ""
                if content and node in ("call_model", "final_response"):
                    for sse_line in think_filter.feed(content):
                        yield sse_line

            elif isinstance(event, ToolMessage):
                result = _emit_tool_message(event)
                if result:
                    yield result

    except Exception as e:
        log.error(f"[GRAPH ERROR] {type(e).__name__}: {e}")
        yield _sse("error", f"Graph error: {e}")
        yield _sse("done")
        return

    # Flush any remaining think-filter buffer
    for sse_line in think_filter.flush():
        yield sse_line

    # Check for interrupt (terminal command awaiting approval)
    state_snapshot = await graph.aget_state(config)
    if state_snapshot.tasks and any(
        hasattr(t, "interrupts") and t.interrupts for t in state_snapshot.tasks
    ):
        for task in state_snapshot.tasks:
            for intr in getattr(task, "interrupts", []):
                payload = {**intr.value}
                if graph_thread_id:
                    payload["graph_thread_id"] = graph_thread_id
                yield _sse("terminal_interrupt", json.dumps(payload))
        yield _sse("done")
        return

    # Emit message type from final state
    final_state = state_snapshot.values or {}
    message_type = final_state.get("message_type", "simple")
    yield _sse("message_type", message_type)

    yield _sse("done")


async def stream_graph_response(
    thread_id: str,
    messages: list[dict],
    new_message: str,
    image_base64: str | None,
    image_media_type: str | None,
    provider: str,
    model: str,
    thinking_mode: bool,
    web_search: bool = False,
    terminal_access: bool = False,
    temperature: float | None = None,
    top_p: float | None = None,
    max_response_tokens: int | None = None,
    max_history_tokens: int | None = None,
    system_prompt: str | None = None,
    tool_call_max_iterations: int | None = None,
) -> AsyncIterator[str]:

    from settings_store import get_settings as _get_settings
    defaults = _get_settings()

    eff_temperature = temperature if temperature is not None else defaults["temperature"]
    eff_top_p = top_p if top_p is not None else defaults["top_p"]
    eff_max_response = max_response_tokens if max_response_tokens is not None else defaults["max_response_tokens"]
    eff_max_history = max_history_tokens if max_history_tokens is not None else defaults["max_history_tokens"]
    eff_system_prompt = system_prompt if system_prompt is not None else defaults["system_prompt"]
    eff_max_iterations = tool_call_max_iterations if tool_call_max_iterations is not None else defaults["tool_call_max_iterations"]

    def deserialize(m: dict) -> AnyMessage:
        if m["role"] == "user":
            return HumanMessage(content=m["content"])
        if m["role"] == "assistant":
            return AIMessage(content=m["content"])
        return HumanMessage(content=m["content"])

    raw_history = [deserialize(m) for m in messages]
    history = truncate_history(raw_history, eff_max_history)
    if len(history) < len(raw_history):
        log.info(f"[HISTORY] Truncated {len(raw_history)} → {len(history)} messages ({estimate_tokens(history)} tokens)")

    llm = get_llm(provider, model, temperature=eff_temperature, top_p=eff_top_p, max_tokens=eff_max_response, streaming=True)

    initial_state: GraphState = {
        "messages": history,
        "new_message": new_message,
        "image_base64": image_base64,
        "image_media_type": image_media_type,
        "message_type": "simple",
        "history_compressed": False,
        "tool_calls_log": [],
        "tool_call_iterations": 0,
    }

    graph_thread_id = f"{thread_id}_{uuid.uuid4().hex[:8]}"

    config: RunnableConfig = {"configurable": {
        "thread_id": graph_thread_id,
        "provider": provider,
        "model": model,
        "temperature": eff_temperature,
        "top_p": eff_top_p,
        "max_response_tokens": eff_max_response,
        "max_history_tokens": eff_max_history,
        "custom_system_prompt": eff_system_prompt,
        "max_iterations_limit": eff_max_iterations,
        "thinking_mode": thinking_mode,
        "web_search": web_search,
        "terminal_access": terminal_access,
        "llm": llm,
    }}

    if estimate_tokens(history) > eff_max_history:
        yield _sse("compressing")

    yield _sse("thinking_start")

    graph = await get_compiled_graph()

    async for sse_line in _stream_graph_messages(
        graph, initial_state, config, thinking_mode, graph_thread_id
    ):
        yield sse_line


async def resume_graph_response(
    thread_id: str,
    approved: bool,
    result: dict | None = None,
    provider: str = "lm_studio",
    model: str = "local-model",
) -> AsyncIterator[str]:
    """Resume graph after terminal interrupt, streaming the final response."""
    from settings_store import get_settings as _get_settings
    defaults = _get_settings()

    llm = get_llm(
        provider, model,
        temperature=defaults["temperature"],
        top_p=defaults["top_p"],
        max_tokens=defaults["max_response_tokens"],
        streaming=True,
    )

    graph = await get_compiled_graph()
    config: RunnableConfig = {"configurable": {
        "thread_id": thread_id,
        "provider": provider,
        "model": model,
        "temperature": defaults["temperature"],
        "top_p": defaults["top_p"],
        "max_response_tokens": defaults["max_response_tokens"],
        "max_history_tokens": defaults["max_history_tokens"],
        "custom_system_prompt": defaults["system_prompt"],
        "max_iterations_limit": defaults["tool_call_max_iterations"],
        "thinking_mode": False,
        "web_search": True,
        "terminal_access": True,
        "llm": llm,
    }}

    yield _sse("thinking_start")

    resume_value: dict = {"approved": approved}
    if result:
        resume_value["result"] = result

    async for sse_line in _stream_graph_messages(
        graph, Command(resume=resume_value), config, thinking_mode=False
    ):
        yield sse_line
