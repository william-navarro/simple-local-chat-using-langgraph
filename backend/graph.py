import asyncio
import json
import logging
import platform
import re
import uuid
from typing import AsyncIterator, TypedDict, Literal

log = logging.getLogger(__name__)

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from config import settings
from providers import get_llm
from tools import ALL_TOOLS, web_search, terminal_execute, send_image


# --- State ---

class GraphState(TypedDict):
    messages: list[AnyMessage]
    new_message: str
    image_base64: str | None
    image_media_type: str | None
    message_type: Literal["simple", "summary_request", "system_instruction"]
    history_compressed: bool
    provider: str
    model: str
    thinking_mode: bool
    web_search: bool
    terminal_access: bool
    tool_calls_log: list[dict]
    tool_call_iterations: int
    has_pending_terminal: bool
    # Per-request LLM settings
    temperature: float
    top_p: float
    max_response_tokens: int | None
    max_history_tokens: int
    custom_system_prompt: str
    max_iterations_limit: int


# --- Helpers ---

def get_enabled_tools(state: dict) -> list:
    """Return the list of tools to bind based on state flags."""
    tools = []
    if state.get("web_search"):
        tools.append(web_search)
    if state.get("terminal_access"):
        tools.append(terminal_execute)
        tools.append(send_image)
    return tools


def has_tools_enabled(state: dict) -> bool:
    """Check if any tool mode is enabled."""
    return bool(state.get("web_search") or state.get("terminal_access"))


def _msg_tokens(m: AnyMessage) -> int:
    """Estimate token count for a single message (chars / 3)."""
    if isinstance(m.content, str):
        return len(m.content) // 3
    if isinstance(m.content, list):
        total = 0
        for block in m.content:
            if isinstance(block, dict) and block.get("type") == "text":
                total += len(block.get("text", ""))
        return total // 3
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
            "ALWAYS call the tool — never simulate or fabricate output. "
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


def build_llm_messages(state: dict) -> list[AnyMessage]:
    """Build the full message list for the LLM call from state."""
    system_prompt = build_system_prompt(
        state.get("message_type", "simple"),
        state.get("thinking_mode", False),
        state.get("web_search", False),
        state.get("terminal_access", False),
        state.get("custom_system_prompt", ""),
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


def node_check_history(state: GraphState) -> GraphState:
    max_hist = state.get("max_history_tokens", settings.max_history_tokens)
    compressed = estimate_tokens(state["messages"]) > max_hist
    return {**state, "history_compressed": compressed}


async def node_compress_history(state: GraphState) -> GraphState:
    history_text = "\n".join(
        f"{m.type.upper()}: {m.content}"
        for m in state["messages"]
        if isinstance(m.content, str)
    )

    llm = get_llm(state.get("provider", "lm_studio"), state["model"], temperature=0.3)
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


async def node_call_model(state: GraphState) -> GraphState:
    """Call the LLM, optionally with tools bound (non-streaming for tool detection)."""
    iteration = state.get("tool_call_iterations", 0) + 1
    max_iter = state.get("max_iterations_limit", settings.tool_call_max_iterations)
    log.info(f"[CALL_MODEL] iteration {iteration}/{max_iter}, provider={state.get('provider')}, model={state.get('model')}")
    msgs = build_llm_messages(state)
    llm = get_llm(
        state.get("provider", "lm_studio"),
        state["model"],
        temperature=state.get("temperature", 0.3),
        top_p=state.get("top_p", 1.0),
        max_tokens=state.get("max_response_tokens"),
    )

    enabled_tools = get_enabled_tools(state)
    tools_bound = False
    if enabled_tools and settings.tools_enabled:
        try:
            llm_with_tools = llm.bind_tools(enabled_tools)
            response = await llm_with_tools.ainvoke(msgs)
            tools_bound = True
            has_tc = bool(getattr(response, "tool_calls", None))
            content_preview = (response.content or "")[:200]
            log.info(f"[CALL_MODEL] bind_tools OK — tool_calls: {has_tc}, content preview: {repr(content_preview)}")
            if has_tc:
                log.info(f"[CALL_MODEL] tool_calls detail: {response.tool_calls}")
        except Exception as e:
            log.info(f"[CALL_MODEL] Tool binding failed, falling back without tools: {e}")
            # Rebuild messages WITHOUT tool instructions to prevent the model
            # from simulating tool output in plain text
            fallback_state = {**state, "web_search": False, "terminal_access": False}
            fallback_msgs = build_llm_messages(fallback_state)
            response = await llm.ainvoke(fallback_msgs)
    else:
        response = await llm.ainvoke(msgs)

    # Detect tool simulation: model wrote tool-call-like text instead of using actual tools
    content = response.content or ""
    if (
        tools_bound
        and not getattr(response, "tool_calls", None)
        and _SIMULATED_TOOL_PATTERN.search(content)
    ):
        log.info(f"[CALL_MODEL] Detected simulated tool calls in text, stripping and retrying without tools")
        # Retry without tool instructions so the model answers normally
        fallback_state = {**state, "web_search": False, "terminal_access": False}
        fallback_msgs = build_llm_messages(fallback_state)
        response = await llm.ainvoke(fallback_msgs)

    return {
        **state,
        "messages": state["messages"] + [response],
        "tool_call_iterations": state.get("tool_call_iterations", 0) + 1,
    }


async def node_tool_executor(state: GraphState) -> GraphState:
    """Execute tool calls from the last AIMessage.

    Terminal commands are NOT executed here — they are recorded as pending
    so the frontend can request user approval before actual execution.
    When a terminal command is found, the graph stops the ReAct loop
    (via has_pending_terminal flag) to avoid duplicate calls.
    """
    last_msg = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    log_entries: list[dict] = []
    found_terminal = False

    tools_by_name = {t.name: t for t in ALL_TOOLS}

    for tc in last_msg.tool_calls:
        if tc["name"] == "terminal_execute":
            # Don't execute — record as pending for frontend approval
            pending = json.dumps({
                "status": "pending_approval",
                "command": tc["args"].get("command", ""),
                "working_directory": tc["args"].get("working_directory", "."),
                "shell": tc["args"].get("shell", "cmd"),
            })
            tool_messages.append(
                ToolMessage(content=pending, tool_call_id=tc["id"])
            )
            log_entries.append({
                "name": tc["name"],
                "args": tc["args"],
                "result": pending,
            })
            found_terminal = True
            continue

        tool_fn = tools_by_name.get(tc["name"])
        if not tool_fn:
            result = json.dumps({"status": "error", "message": f"Unknown tool: {tc['name']}"})
        else:
            try:
                result = await asyncio.to_thread(tool_fn.invoke, tc["args"])
            except Exception as e:
                result = json.dumps({"status": "error", "message": f"Tool error: {e}"})

        tool_messages.append(
            ToolMessage(content=str(result), tool_call_id=tc["id"])
        )
        log_entries.append({
            "name": tc["name"],
            "args": tc["args"],
            "result": str(result),
        })

    return {
        **state,
        "messages": state["messages"] + tool_messages,
        "tool_calls_log": state.get("tool_calls_log", []) + log_entries,
        "has_pending_terminal": found_terminal,
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

def route_after_check(state: GraphState) -> str:
    if state["history_compressed"]:
        return "compress"
    # If any tools are enabled, route to call_model node (non-streaming, with tools)
    # Otherwise, route to END so streaming happens outside the graph
    if has_tools_enabled(state) and settings.tools_enabled:
        return "call_model"
    return END


def _route_after_compress(state: GraphState) -> str:
    """After compressing history, go to call_model if tools enabled, otherwise END."""
    if has_tools_enabled(state) and settings.tools_enabled:
        return "call_model"
    return END


def route_after_tool(state: GraphState) -> str:
    """Route after tool execution: if terminal is pending approval, stop the loop."""
    if state.get("has_pending_terminal"):
        return END
    return "call_model"


def route_after_model(state: GraphState) -> str:
    """Route after LLM call: if tool_calls present, go to tool_node; otherwise END."""
    last_msg = state["messages"][-1]
    max_iter = state.get("max_iterations_limit", settings.tool_call_max_iterations)
    if (
        has_tools_enabled(state)
        and hasattr(last_msg, "tool_calls")
        and last_msg.tool_calls
        and state.get("tool_call_iterations", 0) < max_iter
    ):
        return "tool_node"
    return END


# --- Graph assembly ---

memory = MemorySaver()


def build_graph():
    graph = StateGraph(GraphState)

    # Pre-processing nodes
    graph.add_node("pre_process", node_pre_process)
    graph.add_node("check_history", node_check_history)
    graph.add_node("compress_history", node_compress_history)

    # ReAct tool-calling nodes
    graph.add_node("call_model", node_call_model)
    graph.add_node("tool_node", node_tool_executor)

    # Pre-processing pipeline
    graph.set_entry_point("pre_process")
    graph.add_edge("pre_process", "check_history")
    graph.add_conditional_edges(
        "check_history",
        route_after_check,
        {
            "compress": "compress_history",
            "call_model": "call_model",
            END: END,
        },
    )
    graph.add_conditional_edges(
        "compress_history",
        _route_after_compress,
        {"call_model": "call_model", END: END},
    )

    # ReAct loop
    graph.add_conditional_edges(
        "call_model",
        route_after_model,
        {"tool_node": "tool_node", END: END},
    )
    graph.add_conditional_edges(
        "tool_node",
        route_after_tool,
        {"call_model": "call_model", END: END},
    )

    return graph.compile(checkpointer=memory)


compiled_graph = build_graph()


# --- Main streaming interface ---

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

    initial_state = {
        "messages": history,
        "new_message": new_message,
        "image_base64": image_base64,
        "image_media_type": image_media_type,
        "message_type": "simple",
        "history_compressed": False,
        "provider": provider,
        "model": model,
        "thinking_mode": thinking_mode,
        "web_search": web_search,
        "terminal_access": terminal_access,
        "tool_calls_log": [],
        "tool_call_iterations": 0,
        "has_pending_terminal": False,
        "temperature": eff_temperature,
        "top_p": eff_top_p,
        "max_response_tokens": eff_max_response,
        "max_history_tokens": eff_max_history,
        "custom_system_prompt": eff_system_prompt,
        "max_iterations_limit": eff_max_iterations,
    }

    # Use a unique thread_id per request to avoid checkpoint state accumulation.
    # The frontend already sends the full message history, so we don't need
    # the checkpointer to carry state between requests.
    config = {"configurable": {"thread_id": f"{thread_id}_{uuid.uuid4().hex[:8]}"}}

    # Emit compressing event if history will need compression
    if estimate_tokens(history) > eff_max_history:
        yield f"data: {json.dumps({'type': 'compressing'})}\n\n"

    # Always emit thinking_start so the frontend shows a loading indicator
    # while the graph runs (especially important for the non-streaming tool path)
    yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"

    # Run the graph
    try:
        final_state = await compiled_graph.ainvoke(initial_state, config=config)
    except Exception as e:
        log.error(f"[GRAPH ERROR] {type(e).__name__}: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Graph error: {e}'})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    message_type = final_state.get("message_type", "simple")
    yield f"data: {json.dumps({'type': 'message_type', 'content': message_type})}\n\n"

    tools_active = (web_search or terminal_access) and settings.tools_enabled
    if tools_active:
        # --- Tools path ---
        # The graph executed the full ReAct loop (call_model ↔ tool_node).
        # Emit tool events to the frontend, then stream the final answer.

        tool_log = final_state.get("tool_calls_log", [])
        has_pending_terminal = final_state.get("has_pending_terminal", False)

        for entry in tool_log:
            if entry["name"] == "terminal_execute":
                result_data = json.loads(entry["result"]) if isinstance(entry["result"], str) else entry["result"]
                if result_data.get("status") == "pending_approval":
                    yield f"data: {json.dumps({'type': 'terminal_pending', 'content': json.dumps({'command': result_data['command'], 'working_directory': result_data.get('working_directory', '.'), 'shell': result_data.get('shell', 'cmd')})})}\n\n"
                    continue
            if entry["name"] == "send_image":
                result_data = json.loads(entry["result"]) if isinstance(entry["result"], str) else entry["result"]
                if result_data.get("status") == "success":
                    yield f"data: {json.dumps({'type': 'image_result', 'content': json.dumps({'file_path': result_data['file_path'], 'media_type': result_data['media_type'], 'base64': result_data['base64']})})}\n\n"
                    continue
            yield f"data: {json.dumps({'type': 'tool_start', 'content': json.dumps({'name': entry['name'], 'args': entry['args']})})}\n\n"
            yield f"data: {json.dumps({'type': 'tool_result', 'content': entry['result']})}\n\n"

        if has_pending_terminal:
            # Terminal commands need user approval — don't stream final answer yet.
            # The frontend will call /chat/terminal/execute, get the result,
            # then make a follow-up chat request with the tool context injected.
            pass
        elif tool_log:
            # Tool calls were made — stream a fresh response.
            # We flatten the conversation to avoid sending AIMessage(tool_calls)
            # and ToolMessage to the LLM, which causes jinja template errors
            # in models that don't have tool-role templates.
            tool_context_parts = []
            for entry in tool_log:
                if entry["name"] == "send_image":
                    result_data = json.loads(entry["result"]) if isinstance(entry["result"], str) else entry["result"]
                    if result_data.get("status") == "success":
                        tool_context_parts.append(f"The image '{result_data['file_path']}' was successfully loaded and is now visible to the user in the chat.")
                    else:
                        tool_context_parts.append(f"Attempted to read image but failed: {entry['result']}")
                elif entry["name"] == "web_search":
                    tool_context_parts.append(f"Web search for '{entry['args'].get('query', '')}' returned:\n{_truncate_tool_result(entry['result'])}")
                else:
                    tool_context_parts.append(f"Command '{entry['args'].get('command', '')}' returned:\n{_truncate_tool_result(entry['result'])}")
            tool_context = "\n\n---\n\n".join(tool_context_parts)
            stream_msgs: list[AnyMessage] = [
                SystemMessage(content=build_system_prompt(
                    message_type, thinking_mode,
                    web_search=web_search, terminal_access=terminal_access,
                    custom_system_prompt=eff_system_prompt,
                ))
            ]
            # Keep only HumanMessage/AIMessage from history (skip tool messages)
            for m in final_state["messages"]:
                if isinstance(m, (HumanMessage, AIMessage)) and not getattr(m, "tool_calls", None):
                    stream_msgs.append(m)
            # Inject tool results as context (as HumanMessage to avoid
            # Anthropic's "non-consecutive system messages" error)
            stream_msgs.append(HumanMessage(content=(
                "[INTERNAL CONTEXT — do NOT repeat this verbatim to the user. "
                "Use the information to formulate your own natural response.]\n\n"
                + tool_context
            )))
            stream_msgs.append(HumanMessage(content=build_user_content(
                new_message, image_base64, image_media_type,
            )))

            llm = get_llm(provider, model, temperature=eff_temperature, top_p=eff_top_p, max_tokens=eff_max_response, streaming=True)
            async for chunk in llm.astream(stream_msgs):
                token = chunk.content or ""
                if token:
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        else:
            # No tool calls were made — emit the graph response directly
            # instead of making another LLM call (saves tokens & latency).
            graph_response_text = ""
            for m in reversed(final_state.get("messages", [])):
                if isinstance(m, AIMessage) and isinstance(m.content, str):
                    graph_response_text = m.content
                    break

            # Check for simulated tool calls
            if _SIMULATED_TOOL_PATTERN.search(graph_response_text):
                log.info("[STREAM] Model simulated tool calls — re-streaming without tool instructions")
                stream_msgs: list[AnyMessage] = [
                    SystemMessage(content=build_system_prompt(message_type, thinking_mode, custom_system_prompt=eff_system_prompt))
                ]
                stream_msgs.extend(history)
                stream_msgs.append(HumanMessage(content=build_user_content(
                    new_message, image_base64, image_media_type,
                )))
                llm = get_llm(provider, model, temperature=eff_temperature, top_p=eff_top_p, max_tokens=eff_max_response, streaming=True)
                async for chunk in llm.astream(stream_msgs):
                    token = chunk.content or ""
                    if token:
                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            elif graph_response_text:
                # Emit the already-generated response token by token
                # (strip <think> blocks for non-thinking mode)
                text = graph_response_text
                if not thinking_mode:
                    text = re.sub(r"<think[\s\S]*?</think>", "", text).strip()
                if text:
                    yield f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    else:
        # --- Normal streaming path (no tools) ---
        # The graph ran only pre-processing (pre_process, check_history, compress).
        # Now stream the LLM response with real-time token delivery.

        if thinking_mode:
            yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"

        sys_prompt = build_system_prompt(message_type, thinking_mode, custom_system_prompt=eff_system_prompt)
        user_content = build_user_content(new_message, image_base64, image_media_type)

        stream_msgs: list[AnyMessage] = [SystemMessage(content=sys_prompt)]
        stream_msgs.extend(final_state["messages"])
        stream_msgs.append(HumanMessage(content=user_content))

        llm = get_llm(provider, model, temperature=eff_temperature, top_p=eff_top_p, max_tokens=eff_max_response, streaming=True)

        emit_buffer = ""
        inside_think = False

        async for chunk in llm.astream(stream_msgs):
            token = chunk.content or ""
            if not token:
                continue

            if thinking_mode:
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                continue

            # Filter <think>...</think> blocks when thinking_mode is off
            emit_buffer += token

            while True:
                if inside_think:
                    close = emit_buffer.find("</think")
                    if close == -1:
                        emit_buffer = ""
                        break
                    tag_end = emit_buffer.find(">", close)
                    if tag_end == -1:
                        break
                    emit_buffer = emit_buffer[tag_end + 1:]
                    inside_think = False
                else:
                    open_pos = emit_buffer.find("<think")
                    if open_pos == -1:
                        if emit_buffer:
                            yield f"data: {json.dumps({'type': 'token', 'content': emit_buffer})}\n\n"
                            emit_buffer = ""
                        break
                    before = emit_buffer[:open_pos]
                    if before:
                        yield f"data: {json.dumps({'type': 'token', 'content': before})}\n\n"
                    tag_end = emit_buffer.find(">", open_pos)
                    if tag_end == -1:
                        emit_buffer = emit_buffer[open_pos:]
                        break
                    emit_buffer = emit_buffer[tag_end + 1:]
                    inside_think = True

        if not thinking_mode and emit_buffer and not inside_think:
            yield f"data: {json.dumps({'type': 'token', 'content': emit_buffer})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"
