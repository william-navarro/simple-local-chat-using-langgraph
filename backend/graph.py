import asyncio
import json
import platform
import re
from typing import AsyncIterator, TypedDict, Literal

from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from config import settings
from tools import ALL_TOOLS, web_search, terminal_execute


# --- State ---

class GraphState(TypedDict):
    messages: list[AnyMessage]
    new_message: str
    image_base64: str | None
    image_media_type: str | None
    message_type: Literal["simple", "summary_request", "system_instruction"]
    history_compressed: bool
    model: str
    thinking_mode: bool
    web_search: bool
    terminal_access: bool
    tool_calls_log: list[dict]
    tool_call_iterations: int
    has_pending_terminal: bool


# --- Helpers ---

def get_enabled_tools(state: dict) -> list:
    """Return the list of tools to bind based on state flags."""
    tools = []
    if state.get("web_search"):
        tools.append(web_search)
    if state.get("terminal_access"):
        tools.append(terminal_execute)
    return tools


def has_tools_enabled(state: dict) -> bool:
    """Check if any tool mode is enabled."""
    return bool(state.get("web_search") or state.get("terminal_access"))


def get_llm(model: str, temperature: float = 0.7, streaming: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.lm_studio_url,
        api_key="lm-studio",
        model=model,
        temperature=temperature,
        streaming=streaming,
        request_timeout=120,
    )


def estimate_tokens(messages: list[AnyMessage]) -> int:
    total = 0
    for m in messages:
        if isinstance(m.content, str):
            total += len(m.content)
        elif isinstance(m.content, list):
            for block in m.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    total += len(block.get("text", ""))
    return total // 4


def build_system_prompt(
    message_type: str,
    thinking_mode: bool,
    web_search: bool = False,
    terminal_access: bool = False,
) -> str:
    base = "You are a helpful and concise AI assistant."

    if message_type == "summary_request":
        base += " The user is asking for a summary. Provide a clear, structured, and concise summary."
    elif message_type == "system_instruction":
        base += " The user is giving you an instruction about how you should behave. Acknowledge and follow it precisely."

    if web_search:
        base += (
            " You have access to a web_search tool. Use it ONLY when the user's question "
            "requires up-to-date information, recent events, real-time data, current prices, "
            "weather, news, or facts you are not confident about. For general knowledge, "
            "coding help, or creative tasks, answer directly without searching."
        )

    if terminal_access:
        os_name = platform.system()
        if os_name == "Windows":
            os_hint = (
                "The user is on Windows and commands run via PowerShell. "
                "Use PowerShell cmdlets: Get-ChildItem (list files), Get-Content (read file), "
                "Get-Process, Get-Service, Get-ComputerInfo, Test-Path, Select-Object, "
                "Sort-Object, Format-Table, etc. Pipelines with | are allowed "
                "(e.g. Get-ChildItem | Select-Object Name, Length). "
                "Classic commands like dir, type, tree, git also work."
            )
        elif os_name == "Darwin":
            os_hint = "The user is on macOS. Use Unix commands like ls, cat, grep, find."
        else:
            os_hint = f"The user is on {os_name}. Use Unix commands like ls, cat, grep, find."
        base += (
            " You have access to a terminal_execute tool that can run read-only "
            "shell commands on the user's machine. Use it when the user asks to "
            "inspect files, check directory contents, view git status, read file "
            "contents, or get system information. Only safe, read-only commands "
            "are allowed. Commands have a 15-second timeout, so keep them fast. "
            "NEVER use -Recurse on root directories (C:\\, D:\\, /) as it will "
            "timeout scanning thousands of files. Always scope commands to specific "
            "folders. If the user asks about a broad location, list the top-level "
            "first, then drill down into specific subdirectories as needed. "
            + os_hint +
            " IMPORTANT: If a command fails or returns an error, do NOT give up. "
            "Analyze the error, fix the command, and try again with the corrected version. "
            "Only explain the error to the user if you have exhausted all alternatives."
        )

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
    compressed = estimate_tokens(state["messages"]) > settings.max_history_tokens
    return {**state, "history_compressed": compressed}


async def node_compress_history(state: GraphState) -> GraphState:
    history_text = "\n".join(
        f"{m.type.upper()}: {m.content}"
        for m in state["messages"]
        if isinstance(m.content, str)
    )

    llm = get_llm(state["model"])
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


async def node_call_model(state: GraphState) -> GraphState:
    """Call the LLM, optionally with tools bound (non-streaming for tool detection)."""
    msgs = build_llm_messages(state)
    llm = get_llm(state["model"])

    enabled_tools = get_enabled_tools(state)
    if enabled_tools and settings.tools_enabled:
        try:
            llm_with_tools = llm.bind_tools(enabled_tools)
            response = await llm_with_tools.ainvoke(msgs)
        except Exception as e:
            print(f"[CALL_MODEL] Tool binding failed, falling back: {e}")
            response = await llm.ainvoke(msgs)
    else:
        response = await llm.ainvoke(msgs)

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
            result = await asyncio.to_thread(tool_fn.invoke, tc["args"])

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


async def generate_title_from_message(model: str, user_message: str) -> str:
    """Generate a title based solely on the user message."""
    llm = get_llm(model, temperature=0.1)

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
    if (
        has_tools_enabled(state)
        and hasattr(last_msg, "tool_calls")
        and last_msg.tool_calls
        and state.get("tool_call_iterations", 0) < settings.tool_call_max_iterations
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
    model: str,
    thinking_mode: bool,
    web_search: bool = False,
    terminal_access: bool = False,
) -> AsyncIterator[str]:

    def deserialize(m: dict) -> AnyMessage:
        if m["role"] == "user":
            return HumanMessage(content=m["content"])
        if m["role"] == "assistant":
            return AIMessage(content=m["content"])
        return SystemMessage(content=m["content"])

    history = [deserialize(m) for m in messages]

    initial_state = {
        "messages": history,
        "new_message": new_message,
        "image_base64": image_base64,
        "image_media_type": image_media_type,
        "message_type": "simple",
        "history_compressed": False,
        "model": model,
        "thinking_mode": thinking_mode,
        "web_search": web_search,
        "terminal_access": terminal_access,
        "tool_calls_log": [],
        "tool_call_iterations": 0,
        "has_pending_terminal": False,
    }

    config = {"configurable": {"thread_id": thread_id}}

    # Emit compressing event if history will need compression
    if estimate_tokens(history) > settings.max_history_tokens:
        yield f"data: {json.dumps({'type': 'compressing'})}\n\n"

    # Run the graph
    final_state = await compiled_graph.ainvoke(initial_state, config=config)

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
                    # Emit pending event — frontend must approve before execution
                    yield f"data: {json.dumps({'type': 'terminal_pending', 'content': json.dumps({'command': result_data['command'], 'working_directory': result_data.get('working_directory', '.')})})}\n\n"
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
            tool_context = "\n\n".join(
                f"[Tool call: {entry['name']}({entry['args']})]\n{entry['result']}"
                for entry in tool_log
            )
            stream_msgs: list[AnyMessage] = [
                SystemMessage(content=build_system_prompt(
                    message_type, thinking_mode,
                    web_search=web_search, terminal_access=terminal_access,
                ))
            ]
            # Keep only HumanMessage/AIMessage from history (skip tool messages)
            for m in final_state["messages"]:
                if isinstance(m, (HumanMessage, AIMessage)) and not getattr(m, "tool_calls", None):
                    stream_msgs.append(m)
            # Inject tool results as context, then the user's question
            stream_msgs.append(SystemMessage(content=(
                "The following tool results were retrieved. "
                "Use them to answer the user's question:\n\n" + tool_context
            )))
            stream_msgs.append(HumanMessage(content=build_user_content(
                new_message, image_base64, image_media_type,
            )))

            llm = get_llm(model, streaming=True)
            async for chunk in llm.astream(stream_msgs):
                token = chunk.content or ""
                if token:
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        else:
            # No tool calls were made (model answered directly even with tools available).
            # Stream a fresh response so the user sees real token-by-token output.
            if thinking_mode:
                yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"

            stream_msgs: list[AnyMessage] = [
                SystemMessage(content=build_system_prompt(
                    message_type, thinking_mode,
                    web_search=web_search, terminal_access=terminal_access,
                ))
            ]
            stream_msgs.extend(history)
            stream_msgs.append(HumanMessage(content=build_user_content(
                new_message, image_base64, image_media_type,
            )))

            llm = get_llm(model, streaming=True)

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

    else:
        # --- Normal streaming path (no tools) ---
        # The graph ran only pre-processing (pre_process, check_history, compress).
        # Now stream the LLM response with real-time token delivery.

        if thinking_mode:
            yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"

        system_prompt = build_system_prompt(message_type, thinking_mode)
        user_content = build_user_content(new_message, image_base64, image_media_type)

        stream_msgs: list[AnyMessage] = [SystemMessage(content=system_prompt)]
        stream_msgs.extend(final_state["messages"])
        stream_msgs.append(HumanMessage(content=user_content))

        llm = get_llm(model, streaming=True)

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
