import base64
import json
import mimetypes
import os
import platform
import subprocess

from langchain_core.tools import tool
from duckduckgo_search import DDGS

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB

IS_WINDOWS = platform.system() == "Windows"


@tool
def web_search(query: str, num_results: int = 5) -> str:
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


# --- Terminal tool ---

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
    "convertto-json", "convertfrom-json",
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


@tool
def terminal_execute(command: str, working_directory: str = ".", shell: str = "cmd") -> str:
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
        # Normalize: accept variations like "ps", "pwsh"
        if shell_lower in ("powershell", "ps", "pwsh"):
            shell_lower = "powershell"
        else:
            shell_lower = "cmd"

        # Blocklist check (on the full command string)
        for blocked in BLOCKED_TOKENS:
            if blocked in cmd_lower:
                return json.dumps({
                    "status": "blocked",
                    "command": command,
                    "message": f"Command blocked for safety: contains '{blocked.strip()}'",
                })

        # Split by top-level pipe only (ignore | inside {}, (), quotes)
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
                # Use -EncodedCommand to avoid PowerShell escape interpretation
                # (e.g. \b in paths like D:\bkp being treated as backspace)
                encoded = base64.b64encode(command.encode("utf-16-le")).decode("ascii")
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=cwd,
                    encoding="utf-8",
                    errors="replace",
                )
            else:
                # CMD mode — use cmd /C
                result = subprocess.run(
                    ["cmd", "/C", command],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    cwd=cwd,
                    encoding="utf-8",
                    errors="replace",
                )
        else:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
                cwd=cwd,
                encoding="utf-8",
                errors="replace",
            )

        stdout = result.stdout[:15000] if result.stdout else ""
        stderr = result.stderr[:10000] if result.stderr else ""
        # Filter out PowerShell CLIXML progress messages (not real errors)
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
    result_json = terminal_execute.invoke({"command": command, "working_directory": working_directory, "shell": shell})
    return json.loads(result_json)


@tool
def send_image(file_path: str) -> str:
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


ALL_TOOLS = [web_search, terminal_execute, send_image]
