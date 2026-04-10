import asyncio
import json
import logging
import platform
import re
import uuid
from typing import Annotated, AsyncIterator, TypedDict, Literal

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
from langgraph.graph.message import add_messages, RemoveMessage
from langgraph.types import interrupt, Command

from config import settings
from providers import get_llm
from tools import (
    ALL_TOOLS, TOOL_RISK,
    WebSearchTool, TerminalTool, SendImageTool,
    ReadFileTool, WriteFileTool, GlobTool,
    explain_command,
)


# --- State (mutable execution data only) ---

class GraphState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
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
        tools.append(WebSearchTool)
    if conf.get("terminal_access"):
        tools.append(TerminalTool)
        tools.append(SendImageTool)
        tools.append(ReadFileTool)
        tools.append(WriteFileTool)
        tools.append(GlobTool)
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
            " You have WebSearchTool. Use it for current events, real-time data, "
            "or facts you're unsure about. Answer directly for general knowledge."
        )

    if terminal_access:
        os_name = platform.system()
        base += (
            " You have these tools — call them via tool_calls, NOT as shell commands. "
            "ALWAYS call the tool — never simulate or fabricate output. "
            "You can call multiple tools at once (parallel tool calls). "
            "You can chain tool calls across multiple rounds."
            "\n- TerminalTool: run read-only shell commands (requires user approval)."
            "\n- SendImageTool(file_path): display an image — do NOT write markdown image links after calling it."
            "\n- ReadFileTool(file_path, max_lines): read a text file directly — prefer this over TerminalTool for file reads."
            "\n- WriteFileTool(file_path, content, create_dirs): create or overwrite a text file (requires user approval)."
            "\n- GlobTool(pattern, base_path): find files by glob pattern (e.g. '**/*.py') — prefer this over TerminalTool for file discovery."
            "\nRetry on errors before explaining them. Avoid recursive scans on root dirs."
        )
        if os_name == "Windows":
            base += (
                " TerminalTool has a 'shell' param: 'cmd' (default) or 'powershell'. "
                "Use shell='cmd' for CMD syntax (dir /Q, type, tree, etc.). "
                "Use shell='powershell' for PowerShell cmdlets (Get-ChildItem, Get-Content, etc.). "
                "Do NOT mix syntaxes — CMD flags (/Q, /S) fail in PowerShell and vice-versa."
            )
        else:
            base += " TerminalTool runs bash commands (15s timeout)."

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


def build_llm_messages(state: dict, conf: dict, *, include_human: bool = True) -> list[AnyMessage]:
    """Build the full message list for the LLM call from state + config.

    Args:
        include_human: If True, appends a new HumanMessage at the end.
            Set to False on iteration 2+ when HumanMessage is already in state.
    """
    system_prompt = build_system_prompt(
        state.get("message_type", "simple"),
        conf.get("thinking_mode", False),
        conf.get("web_search", False),
        conf.get("terminal_access", False),
        conf.get("custom_system_prompt", ""),
    )

    msgs: list[AnyMessage] = [SystemMessage(content=system_prompt)]
    msgs.extend(_sanitize_tool_messages(state["messages"]))

    if include_human:
        user_content = build_user_content(
            state["new_message"],
            state.get("image_base64"),
            state.get("image_media_type"),
        )
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

    return {"message_type": message_type}


def node_check_history(state: GraphState, config: RunnableConfig) -> dict:
    conf = config["configurable"]
    max_hist = conf.get("max_history_tokens", settings.max_history_tokens)
    compressed = estimate_tokens(state["messages"]) > max_hist
    return {"history_compressed": compressed}


async def node_compress_history(state: GraphState, config: RunnableConfig) -> dict:
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

    # With add_messages reducer, we must explicitly remove old messages
    # then add the compressed ones. RemoveMessage tells the reducer to delete by id.
    removals = [RemoveMessage(id=m.id) for m in state["messages"]]
    compressed: list[AnyMessage] = [
        HumanMessage(content=f"[Previous conversation summary: {summary}]"),
        AIMessage(content="Understood. I have the context from our previous conversation."),
    ]

    return {"messages": removals + compressed, "history_compressed": True}


_SIMULATED_TOOL_PATTERN = re.compile(
    r"\[Tool call:.*?\]"           # [Tool call: name(...)]
    r"|<tool_call>.*?</tool_call>" # <tool_call>...</tool_call>
    r"|✿FUNCTION✿"                # Some models use this marker
    r"|```tool_code"               # ```tool_code blocks
    , re.IGNORECASE | re.DOTALL
)


async def node_call_model(state: GraphState, config: RunnableConfig) -> GraphState:
    """Call the LLM, optionally with tools bound for tool detection.

    On iteration 0 (first call): persists HumanMessage + AIMessage in state.
    On iteration 1+ (after tool results): only persists AIMessage (HumanMessage already in state).
    """
    conf = config["configurable"]
    iteration = state.get("tool_call_iterations", 0)
    max_iter = conf.get("max_iterations_limit", 3)
    log.info(f"[CALL_MODEL] iteration={iteration}/{max_iter}, provider={conf.get('provider')}, model={conf.get('model')}")

    is_first_call = iteration == 0
    msgs = build_llm_messages(state, conf, include_human=is_first_call)
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
            fallback_msgs = build_llm_messages(state, fallback_conf, include_human=is_first_call)
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
        fallback_msgs = build_llm_messages(state, fallback_conf, include_human=is_first_call)
        response = await llm.ainvoke(fallback_msgs)

    # With add_messages reducer, return only NEW messages (reducer appends)
    if is_first_call:
        user_content = build_user_content(
            state["new_message"],
            state.get("image_base64"),
            state.get("image_media_type"),
        )
        human_msg = HumanMessage(content=user_content)
        new_messages = [human_msg, response]
    else:
        new_messages = [response]

    return {
        "messages": new_messages,
        "tool_call_iterations": iteration + 1,
    }


async def node_tool_executor(state: GraphState) -> GraphState:
    """Execute tool calls from the last AIMessage.

    Structured in 3 phases to avoid re-execution bugs with LangGraph's
    interrupt() mechanism (which re-runs the entire node on resume):
      1. Collect all interrupt() approvals FIRST (no side effects)
      2. Execute non-terminal tools in parallel
      3. Process approved terminal commands

    This ensures parallel tools (WebSearchTool, SendImageTool, ReadFileTool, GlobTool)
    run only once, even when the node is re-executed after an interrupt resume.
    """
    last_msg = state["messages"][-1]
    tool_messages: list[ToolMessage] = []
    log_entries: list[dict] = []

    tools_by_name = {t.name: t for t in ALL_TOOLS}

    # Tools that require user approval before execution
    APPROVAL_TOOLS = {"TerminalTool", "WriteFileTool"}

    approval_calls = []
    parallel_calls = []
    for tc in last_msg.tool_calls:
        if tc["name"] in APPROVAL_TOOLS:
            approval_calls.append(tc)
        else:
            parallel_calls.append(tc)

    # --- Phase 1: Collect ALL interrupt approvals (no side effects) ---
    pending_approvals: list[tuple[dict, dict]] = []
    for tc in approval_calls:
        risk = TOOL_RISK.get(tc["name"], "high")
        command = tc["args"].get("command", "")
        shell = tc["args"].get("shell", "cmd")
        explanation = explain_command(command, shell) if tc["name"] == "TerminalTool" else (
            f"Write file: {tc['args'].get('file_path', '')}"
        )
        approval = interrupt({
            "tool_call_id": tc["id"],
            "tool_name": tc["name"],
            "command": command,
            "working_directory": tc["args"].get("working_directory", "."),
            "shell": shell,
            "explanation": explanation,
            "risk_level": risk,
            # WriteFileTool extras
            "file_path": tc["args"].get("file_path", ""),
        })
        pending_approvals.append((tc, approval))

    # --- Phase 2: Execute non-approval tools in parallel ---
    async def _exec_tool(tc: dict) -> tuple[dict, str]:
        tool_fn = tools_by_name.get(tc["name"])
        if not tool_fn:
            return tc, json.dumps({"status": "error", "message": f"Unknown tool: {tc['name']}"})
        risk = TOOL_RISK.get(tc["name"], "low")
        log.info(f"[TOOL] {tc['name']} risk={risk} args={list(tc['args'].keys())}")
        try:
            result = await asyncio.to_thread(tool_fn.invoke, tc["args"])
            return tc, _truncate_tool_result(str(result))
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
                "risk_level": TOOL_RISK.get(tc["name"], "low"),
            })

    # --- Phase 3: Execute approved tools ---
    for tc, approval in pending_approvals:
        risk = TOOL_RISK.get(tc["name"], "high")
        log.warning(f"[TOOL] {tc['name']} risk={risk} approved={approval.get('approved')} args={list(tc['args'].keys())}")
        if approval.get("approved"):
            result_data = approval.get("result")
            if result_data:
                result = _truncate_tool_result(json.dumps(result_data))
            else:
                tool_fn = tools_by_name.get(tc["name"])
                try:
                    result = _truncate_tool_result(
                        str(await asyncio.to_thread(tool_fn.invoke, tc["args"]))
                    )
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
            "risk_level": risk,
        })

    return {
        "messages": tool_messages,
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

    If the last message is an empty/think-only AIMessage (from call_model
    that decided not to use tools), it is dropped so the LLM sees a clean
    context ending with ToolMessage results.
    """
    conf = config["configurable"]
    log.info("[FINAL_RESPONSE] Generating response after tool execution")

    state_msgs = list(state["messages"])

    # Drop trailing AIMessage if it has no useful content (think-only or empty).
    # This happens when call_model iteration 2+ produced <think> but no text/tools,
    # and route_after_model sent us here instead of END.
    if state_msgs and isinstance(state_msgs[-1], AIMessage):
        last_ai = state_msgs[-1]
        has_tool_calls = bool(getattr(last_ai, "tool_calls", None))
        raw = last_ai.content or ""
        if isinstance(raw, list):
            text = "".join(
                b.get("text", "") if isinstance(b, dict) else str(b) for b in raw
            )
        else:
            text = raw
        # Strip <think> blocks to check if there's real content
        stripped = re.sub(r"<think[\s\S]*?</think>", "", text, flags=re.IGNORECASE).strip()
        if not has_tool_calls and not stripped:
            log.info("[FINAL_RESPONSE] Dropping empty/think-only AIMessage from context")
            state_msgs = state_msgs[:-1]

    system_prompt = build_system_prompt(
        state.get("message_type", "simple"),
        conf.get("thinking_mode", False),
        conf.get("web_search", False),
        conf.get("terminal_access", False),
        conf.get("custom_system_prompt", ""),
    )

    # Sanitize to remove large base64 payloads from ToolMessages
    clean_msgs = _sanitize_tool_messages(state_msgs)
    msgs: list[AnyMessage] = [SystemMessage(content=system_prompt)]
    msgs.extend(clean_msgs)

    llm = conf["llm"]
    response = await llm.ainvoke(msgs)  # NO bind_tools — forces text response

    return {"messages": [response]}


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
    """Route after LLM call: tool_calls → tool_node, else END or final_response.

    On iteration 0 (first call) with no tool_calls → END (normal text response).
    On iteration 1+ (after tool execution) with no tool_calls → final_response,
    because the LLM may produce only <think> content or an empty response when
    it has tools bound. final_response calls LLM without tools to force clean text.
    """
    conf = config["configurable"]
    last_msg = state["messages"][-1]
    if (
        has_tools_enabled(conf)
        and hasattr(last_msg, "tool_calls")
        and last_msg.tool_calls
    ):
        return "tool_node"

    iteration = state.get("tool_call_iterations", 0)
    if iteration > 1:
        # After tool execution: LLM decided not to call more tools but may have
        # produced only <think> content. Route to final_response for a clean answer.
        log.info(f"[ROUTE] iteration={iteration}, no tool_calls → final_response")
        return "final_response"

    return END


def route_after_tool(state: GraphState, config: RunnableConfig) -> str:
    """Route after tool execution: loop back to call_model or go to final_response.

    Loops back if under the iteration limit, goes to final_response otherwise.
    """
    conf = config["configurable"]
    iterations = state.get("tool_call_iterations", 0)
    max_iter = conf.get("max_iterations_limit", 3)
    if iterations >= max_iter:
        log.info(f"[ROUTE] Iteration limit reached ({iterations}/{max_iter}) → final_response")
        return "final_response"
    log.info(f"[ROUTE] Iteration {iterations}/{max_iter} → call_model (next round)")
    return "call_model"


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

    # Multi-round tool pattern: call_model ↔ tool_node (max N iterations) → final_response
    graph.add_conditional_edges(
        "call_model",
        route_after_model,
        {"tool_node": "tool_node", "final_response": "final_response", END: END},
    )
    graph.add_conditional_edges(
        "tool_node",
        route_after_tool,
        {"call_model": "call_model", "final_response": "final_response"},
    )
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
    conversation_id: str,
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
    from conversation_store import get_messages, add_message, log_tool_execution
    from settings_store import get_settings as _get_settings
    defaults = _get_settings()

    eff_temperature = temperature if temperature is not None else defaults["temperature"]
    eff_top_p = top_p if top_p is not None else defaults["top_p"]
    eff_max_response = max_response_tokens if max_response_tokens is not None else defaults["max_response_tokens"]
    eff_max_history = max_history_tokens if max_history_tokens is not None else defaults["max_history_tokens"]
    eff_system_prompt = system_prompt if system_prompt is not None else defaults["system_prompt"]
    eff_max_iterations = tool_call_max_iterations if tool_call_max_iterations is not None else defaults["tool_call_max_iterations"]

    # Save user message to DB
    user_msg_data: dict = {"role": "user", "content": new_message}
    if image_base64:
        user_msg_data["image_base64"] = image_base64
        user_msg_data["image_media_type"] = image_media_type
    await add_message(conversation_id, user_msg_data)

    # Load history from DB (includes the user message we just saved)
    db_messages = await get_messages(conversation_id)

    def deserialize(m: dict) -> AnyMessage:
        if m["role"] == "user":
            return HumanMessage(content=m["content"])
        if m["role"] == "assistant":
            return AIMessage(content=m["content"])
        return HumanMessage(content=m["content"])

    # Exclude the last message (current user message) — it will be added by node_call_model
    raw_history = [deserialize(m) for m in db_messages[:-1]]
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

    graph_thread_id = f"{conversation_id}_{uuid.uuid4().hex[:8]}"

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

    # Save assistant response to DB after streaming completes
    try:
        state_snapshot = await graph.aget_state(config)
        final_state = state_snapshot.values or {}
        final_messages = final_state.get("messages", [])

        # Find the last AIMessage — that's the assistant response
        assistant_content = ""
        tool_calls_log = final_state.get("tool_calls_log", [])
        images: list[dict] = []

        for m in reversed(final_messages):
            if isinstance(m, AIMessage):
                raw = m.content or ""
                if isinstance(raw, list):
                    assistant_content = "".join(
                        b.get("text", "") if isinstance(b, dict) else str(b) for b in raw
                    )
                else:
                    assistant_content = raw
                break

        # Extract images from tool_calls_log (SendImageTool results with base64)
        for entry in tool_calls_log:
            if entry.get("name") == "SendImageTool":
                try:
                    result = json.loads(entry["result"]) if isinstance(entry["result"], str) else entry["result"]
                    if isinstance(result, dict) and result.get("status") == "success" and "base64" in result:
                        images.append({
                            "file_path": result.get("file_path", ""),
                            "media_type": result.get("media_type", ""),
                            "base64": result["base64"],
                        })
                except (json.JSONDecodeError, TypeError, KeyError):
                    pass

        assistant_msg_data: dict = {
            "role": "assistant",
            "content": assistant_content,
        }
        if tool_calls_log:
            assistant_msg_data["tool_calls"] = tool_calls_log
        if images:
            assistant_msg_data["images"] = images

        await add_message(conversation_id, assistant_msg_data)

        # Audit log: persist each tool execution to tool_executions table
        for entry in tool_calls_log:
            tool_name = entry.get("name", "unknown")
            result_raw = entry.get("result", "")
            try:
                result_parsed = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
                status = result_parsed.get("status", "") if isinstance(result_parsed, dict) else ""
                # Build a concise summary (no base64)
                if isinstance(result_parsed, dict) and "base64" in result_parsed:
                    summary = f"status={status} file={result_parsed.get('file_path', '')}"
                else:
                    summary = result_raw[:300]
            except (json.JSONDecodeError, TypeError):
                summary = str(result_raw)[:300]

            await log_tool_execution(
                conv_id=conversation_id,
                tool_name=tool_name,
                risk_level=entry.get("risk_level", TOOL_RISK.get(tool_name, "low")),
                args=entry.get("args", {}),
                result_summary=summary,
            )
    except Exception as e:
        log.error(f"[SAVE] Failed to save assistant message: {e}")


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
