import base64
import json
import mimetypes
import os
import pathlib
import platform
import subprocess

from langchain_core.tools import tool
from duckduckgo_search import DDGS

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_FILE_READ_BYTES = 500 * 1024   # 500 KB for ReadFileTool

IS_WINDOWS = platform.system() == "Windows"


# --- Risk classification ---

TOOL_RISK: dict[str, str] = {
    "WebSearchTool": "low",
    "SendImageTool": "low",
    "ReadFileTool": "low",
    "GlobTool": "low",
    "WriteFileTool": "high",
    "TerminalTool": "high",
}


# ---------------------------------------------------------------------------
# WebSearchTool
# ---------------------------------------------------------------------------

@tool
def WebSearchTool(query: str, num_results: int = 5) -> str:
    """Search the web for current information. Use this when the user asks about
    recent events, real-time data, current prices, weather, news, or anything
    that may require up-to-date information beyond your training. Consider data
    ONLY from english and brazilian portuguese websites."""
    try:
        num_results = max(1, min(10, num_results))
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))

        if not results:
            return json.dumps(
                {"status": "no_results", "message": f"No results found for: {query}"}
            )

        formatted = [
            {
                "position": i,
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for i, r in enumerate(results, 1)
        ]

        return json.dumps({"status": "success", "query": query, "results": formatted})

    except Exception as e:
        return json.dumps({"status": "error", "message": f"Search failed: {str(e)}"})


# ---------------------------------------------------------------------------
# TerminalTool
# ---------------------------------------------------------------------------

ALLOWED_COMMANDS = {
    # Cross-platform / basic
    "echo", "cd", "pwd", "whoami", "hostname", "date",
    # Unix / Git Bash / macOS
    "ls", "cat", "head", "tail", "find", "grep", "wc", "file",
    "which", "env", "printenv", "df", "du", "uname",
    # Windows CMD
    "dir", "type", "where", "set", "systeminfo", "tree", "ver", "if",
    # PowerShell cmdlets (read-only)
    "get-childitem", "get-content", "get-item", "get-itemproperty",
    "get-location", "get-process", "get-service", "get-command",
    "get-help", "get-alias", "get-variable", "get-module",
    "get-host", "get-date", "get-random", "get-computerinfo", "get-culture",
    "get-executionpolicy", "get-hotfix", "get-netadapter",
    "get-netipaddress", "get-netipconfiguration", "get-disk",
    "get-volume", "get-partition", "get-psdrive",
    "test-path", "test-connection", "resolve-path",
    "select-object", "select-string", "where-object",
    "sort-object", "format-table", "format-list",
    "measure-object", "group-object", "out-string",
    "convertto-json", "convertfrom-json", "foreach-object", "Get-FullName"
    # PowerShell aliases that map to read-only cmdlets
    "gci", "gc", "gi", "gl", "gps", "gsv", "gal",
    # Git (read-only)
    "git status", "git log", "git diff", "git branch", "git remote",
    "git show", "git ls-files", "git rev-parse", "git describe", "git tag",
    # Runtime versions
    "python --version", "python3 --version", "node --version",
    "npm --version", "pip --version", "pip list", "pip freeze",
    # dotnet
    "dotnet --version", "dotnet --list-sdks", "dotnet --list-runtimes",
}

BLOCKED_TOKENS = {
    # Destructive Unix
    "rm ", "rm\t", "rmdir", "del ", "del\t", "erase",
    "format c", "format d", "format e", "format f",
    "shutdown", "reboot", "mkfs",
    "dd ", "dd\t", ":(){", "fork",
    "chmod", "chown", "chgrp",
    "mv ", "mv\t", "ren ", "rename",
    # Destructive PowerShell cmdlets
    "remove-item", "remove-variable", "remove-module",
    "set-content", "set-item", "set-itemproperty",
    "new-item", "new-object", "copy-item", "move-item",
    "start-process", "stop-process", "stop-service",
    "restart-service", "restart-computer", "stop-computer",
    "invoke-webrequest", "invoke-restmethod",
    "invoke-expression", "invoke-command",
    "set-executionpolicy", "unblock-file",
    "add-content", "clear-content", "clear-item",
    "register-", "unregister-",
    # Shell escape / chaining
    ">", ">>", "&",
    "sudo", "su ",
    # Subexpression / script blocks (prevent arbitrary code)
    "$(", "${", ".{",
    # Windows system
    "reg ", "regedit",
    "net ", "netsh",
    "taskkill", "kill",
    # Downloads
    "wget", "curl",
    "iwr ", "irm ",
}


def _split_pipeline(cmd: str) -> list[str]:
    """Split a command string by top-level pipe operators only.

    Pipes inside curly braces {}, parentheses (), single quotes '',
    and double quotes "" are ignored so that PowerShell expressions
    like `Where-Object { $_.Extension -in '.jpg', '.jpeg' }` are
    kept as a single segment.
    """
    segments: list[str] = []
    current: list[str] = []
    depth_curly = 0
    depth_paren = 0
    in_single = False
    in_double = False
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == "{":
                depth_curly += 1
            elif ch == "}":
                depth_curly = max(0, depth_curly - 1)
            elif ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren = max(0, depth_paren - 1)
            elif ch == "|" and depth_curly == 0 and depth_paren == 0:
                segments.append("".join(current).strip())
                current = []
                i += 1
                continue
        current.append(ch)
        i += 1
    segments.append("".join(current).strip())
    return segments


# Static explanation hints for common command patterns (avoids LLM call)
_CMD_HINTS: list[tuple[str, str]] = [
    ("git log", "Viewing git commit history"),
    ("git diff", "Showing uncommitted changes"),
    ("git status", "Checking git working tree status"),
    ("git branch", "Listing git branches"),
    ("git show", "Showing a git commit or object"),
    ("git ls-files", "Listing files tracked by git"),
    ("dir ", "Listing directory contents"),
    ("dir/", "Listing directory contents"),
    ("ls ", "Listing directory contents"),
    ("ls\n", "Listing directory contents"),
    ("get-childitem", "Listing directory contents"),
    ("gci ", "Listing directory contents"),
    ("cat ", "Reading file contents"),
    ("type ", "Reading file contents"),
    ("get-content", "Reading file contents"),
    ("gc ", "Reading file contents"),
    ("head ", "Reading first lines of a file"),
    ("tail ", "Reading last lines of a file"),
    ("find ", "Searching for files"),
    ("grep ", "Searching file contents"),
    ("select-string", "Searching file contents"),
    ("tree ", "Showing directory tree structure"),
    ("tree\n", "Showing directory tree structure"),
    ("pwd", "Showing current working directory"),
    ("get-location", "Showing current working directory"),
    ("whoami", "Checking current user identity"),
    ("systeminfo", "Reading system information"),
    ("get-computerinfo", "Reading system information"),
    ("df ", "Checking disk space usage"),
    ("du ", "Checking directory size"),
    ("get-disk", "Checking disk information"),
    ("get-volume", "Checking volume information"),
    ("pip list", "Listing installed Python packages"),
    ("pip freeze", "Listing installed Python packages"),
    ("python --version", "Checking Python version"),
    ("node --version", "Checking Node.js version"),
    ("npm --version", "Checking npm version"),
    ("dotnet --version", "Checking .NET version"),
    ("get-process", "Listing running processes"),
    ("get-service", "Listing system services"),
    ("wc ", "Counting lines/words/characters"),
    ("echo ", "Printing text output"),
    ("set ", "Listing environment variables"),
    ("env", "Listing environment variables"),
    ("printenv", "Listing environment variables"),
]


def explain_command(command: str, shell: str = "cmd") -> str:
    """Return a short human-readable explanation of what a command does.

    Matches against static hints first; falls back to a generic description.
    """
    lower = command.lower().strip()
    for pattern, explanation in _CMD_HINTS:
        if lower.startswith(pattern.strip()) or pattern.strip() in lower:
            return explanation
    # Generic fallback based on first token
    first = lower.split()[0] if lower.split() else lower
    return f"Running '{first}' command in {shell.upper()}"


@tool
def TerminalTool(command: str, working_directory: str = ".", shell: str = "cmd") -> str:
    """Execute a read-only shell command on the user's machine.
    Use this to inspect files, check directory contents, view git status,
    read file contents, or get system information.
    Only safe, read-only commands are permitted.
    On Windows, set shell="cmd" for CMD syntax (dir /Q, type, etc.)
    or shell="powershell" for PowerShell cmdlets (Get-ChildItem, Get-Content, etc.).
    Default is "cmd"."""
    try:
        cmd_lower = command.lower().strip()
        shell_lower = shell.lower().strip() if shell else "cmd"
        if shell_lower in ("powershell", "ps", "pwsh"):
            shell_lower = "powershell"
        else:
            shell_lower = "cmd"

        for blocked in BLOCKED_TOKENS:
            if blocked in cmd_lower:
                return json.dumps({
                    "status": "blocked",
                    "command": command,
                    "message": f"Command blocked for safety: contains '{blocked.strip()}'",
                })

        segments = _split_pipeline(cmd_lower)

        for segment in segments:
            if not segment:
                continue
            base_cmd = segment.split()[0].lstrip("({") if segment.split() else ""
            two_word = " ".join(segment.split()[:2]) if len(segment.split()) > 1 else ""
            two_word_clean = two_word.lstrip("({")
            allowed = base_cmd in ALLOWED_COMMANDS or two_word in ALLOWED_COMMANDS or two_word_clean in ALLOWED_COMMANDS

            if not allowed:
                return json.dumps({
                    "status": "blocked",
                    "command": command,
                    "message": f"Command '{base_cmd}' is not in the allowed commands list.",
                })

        cwd = working_directory if working_directory and working_directory != "." else None

        if IS_WINDOWS:
            if shell_lower == "powershell":
                encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                    capture_output=True, text=True, timeout=15, cwd=cwd,
                    encoding="utf-8", errors="replace",
                )
            else:
                result = subprocess.run(
                    ["cmd", "/C", command],
                    capture_output=True, text=True, timeout=15, cwd=cwd,
                    encoding="utf-8", errors="replace",
                )
        else:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=15, cwd=cwd, encoding="utf-8", errors="replace",
            )

        stdout = result.stdout[:15000] if result.stdout else ""
        stderr = result.stderr[:10000] if result.stderr else ""
        if stderr.startswith("#< CLIXML"):
            stderr = ""
        truncated = len(result.stdout or "") > 15000

        return json.dumps({
            "status": "success",
            "command": command,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": truncated,
        })

    except subprocess.TimeoutExpired:
        return json.dumps({
            "status": "error",
            "command": command,
            "message": f"Command timed out after 15 seconds: {command}",
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "command": command,
            "message": f"Execution failed: {str(e)}",
        })


def execute_terminal_command(command: str, working_directory: str = ".", shell: str = "cmd") -> dict:
    """Execute a terminal command directly (used by the approval endpoint).
    Returns a parsed dict instead of a JSON string."""
    result_json = TerminalTool.invoke({"command": command, "working_directory": working_directory, "shell": shell})
    return json.loads(result_json)


# ---------------------------------------------------------------------------
# SendImageTool
# ---------------------------------------------------------------------------

@tool
def SendImageTool(file_path: str) -> str:
    """Send an image file from the user's machine to display in the chat.
    Use this when the user asks you to show, display, or retrieve an image
    from a local path. Supported formats: JPG, JPEG, PNG, GIF, BMP, WEBP, SVG."""
    try:
        file_path = os.path.expanduser(file_path)

        if not os.path.isabs(file_path):
            return json.dumps({
                "status": "error",
                "message": "Please provide an absolute file path.",
            })

        if not os.path.exists(file_path):
            return json.dumps({
                "status": "error",
                "message": f"File not found: {file_path}",
            })

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_IMAGE_EXTENSIONS:
            return json.dumps({
                "status": "error",
                "message": f"Unsupported image format '{ext}'. Supported: {', '.join(SUPPORTED_IMAGE_EXTENSIONS)}",
            })

        file_size = os.path.getsize(file_path)
        if file_size > MAX_IMAGE_SIZE:
            return json.dumps({
                "status": "error",
                "message": f"File too large ({file_size // 1024 // 1024}MB). Max: {MAX_IMAGE_SIZE // 1024 // 1024}MB.",
            })

        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

        media_type = mimetypes.guess_type(file_path)[0] or "image/jpeg"

        return json.dumps({
            "status": "success",
            "file_path": file_path,
            "media_type": media_type,
            "base64": data,
        })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to send image: {str(e)}",
        })


# ---------------------------------------------------------------------------
# ReadFileTool
# ---------------------------------------------------------------------------

@tool
def ReadFileTool(file_path: str, max_lines: int = 200) -> str:
    """Read the contents of a text file from the user's machine.
    Prefer this over TerminalTool when you only need to read a file —
    it is faster, safer, and does not require user approval.
    Returns the file content with line numbers. Use max_lines to limit output."""
    try:
        file_path = os.path.expanduser(file_path)

        # Require absolute path to prevent traversal ambiguity
        if not os.path.isabs(file_path):
            return json.dumps({
                "status": "error",
                "message": "Please provide an absolute file path.",
            })

        # Resolve and guard against path traversal
        resolved = pathlib.Path(file_path).resolve()
        if not resolved.exists():
            return json.dumps({
                "status": "error",
                "message": f"File not found: {file_path}",
            })

        if not resolved.is_file():
            return json.dumps({
                "status": "error",
                "message": f"Path is not a file: {file_path}",
            })

        file_size = resolved.stat().st_size
        if file_size > MAX_FILE_READ_BYTES:
            return json.dumps({
                "status": "error",
                "message": (
                    f"File too large ({file_size // 1024}KB). "
                    f"Max: {MAX_FILE_READ_BYTES // 1024}KB. "
                    "Use max_lines to read a portion, or use GlobTool to inspect structure."
                ),
            })

        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        max_lines = max(1, min(max_lines, 2000))
        truncated = total_lines > max_lines
        content = "".join(
            f"{i + 1}: {line}" for i, line in enumerate(lines[:max_lines])
        )

        return json.dumps({
            "status": "success",
            "file_path": str(resolved),
            "total_lines": total_lines,
            "lines_returned": min(total_lines, max_lines),
            "truncated": truncated,
            "content": content,
        })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to read file: {str(e)}",
        })


# ---------------------------------------------------------------------------
# WriteFileTool
# ---------------------------------------------------------------------------

@tool
def WriteFileTool(file_path: str, content: str, create_dirs: bool = False) -> str:
    """Write (create or overwrite) a text file on the user's machine.
    Requires user approval before executing.
    Set create_dirs=True to automatically create parent directories if missing."""
    try:
        file_path = os.path.expanduser(file_path)

        if not os.path.isabs(file_path):
            return json.dumps({
                "status": "error",
                "message": "Please provide an absolute file path.",
            })

        resolved = pathlib.Path(file_path).resolve()

        if create_dirs:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        elif not resolved.parent.exists():
            return json.dumps({
                "status": "error",
                "message": (
                    f"Parent directory does not exist: {resolved.parent}. "
                    "Set create_dirs=True to create it automatically."
                ),
            })

        existed = resolved.exists()
        resolved.write_text(content, encoding="utf-8")

        return json.dumps({
            "status": "success",
            "file_path": str(resolved),
            "action": "overwritten" if existed else "created",
            "bytes_written": len(content.encode("utf-8")),
        })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Failed to write file: {str(e)}",
        })


# ---------------------------------------------------------------------------
# GlobTool
# ---------------------------------------------------------------------------

@tool
def GlobTool(pattern: str, base_path: str = ".", max_results: int = 100) -> str:
    """Find files matching a glob pattern relative to a base path.
    Examples: '**/*.py', 'src/**/*.ts', '*.json', 'docs/**/*.md'.
    Use this to explore project structure without running shell commands.
    Results are sorted by path. Use max_results to limit output (default 100)."""
    try:
        base = pathlib.Path(os.path.expanduser(base_path)).resolve()

        if not base.exists():
            return json.dumps({
                "status": "error",
                "message": f"Base path does not exist: {base_path}",
            })

        if not base.is_dir():
            return json.dumps({
                "status": "error",
                "message": f"Base path is not a directory: {base_path}",
            })

        max_results = max(1, min(max_results, 500))
        matches = sorted(base.glob(pattern))
        # Filter to files only (exclude directories from results)
        file_matches = [p for p in matches if p.is_file()]
        truncated = len(file_matches) > max_results
        returned = file_matches[:max_results]

        return json.dumps({
            "status": "success",
            "pattern": pattern,
            "base_path": str(base),
            "total_matches": len(file_matches),
            "truncated": truncated,
            "files": [str(p) for p in returned],
        })

    except Exception as e:
        return json.dumps({
            "status": "error",
            "message": f"Glob failed: {str(e)}",
        })


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

ALL_TOOLS = [WebSearchTool, TerminalTool, SendImageTool, ReadFileTool, WriteFileTool, GlobTool]
