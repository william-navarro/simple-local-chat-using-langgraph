import json
import platform
import subprocess

from langchain_core.tools import tool
from duckduckgo_search import DDGS

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
    "dir", "type", "where", "set", "systeminfo", "tree", "ver",
    # PowerShell cmdlets (read-only)
    "get-childitem", "get-content", "get-item", "get-itemproperty",
    "get-location", "get-process", "get-service", "get-command",
    "get-help", "get-alias", "get-variable", "get-module",
    "get-host", "get-date", "get-computerinfo", "get-culture",
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
    "cmd /c", "cmd.exe",
    ">", ">>", ";", "&",
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


@tool
def terminal_execute(command: str, working_directory: str = ".") -> str:
    """Execute a read-only shell command on the user's machine.
    Use this to inspect files, check directory contents, view git status,
    read file contents, or get system information.
    Only safe, read-only commands are permitted."""
    try:
        cmd_lower = command.lower().strip()

        # Blocklist check (on the full command string)
        for blocked in BLOCKED_TOKENS:
            if blocked in cmd_lower:
                return json.dumps({
                    "status": "blocked",
                    "command": command,
                    "message": f"Command blocked for safety: contains '{blocked.strip()}'",
                })

        # Split by pipe to validate each segment of a pipeline
        segments = [s.strip() for s in cmd_lower.split("|")]

        for segment in segments:
            if not segment:
                continue
            base_cmd = segment.split()[0] if segment.split() else ""
            two_word = " ".join(segment.split()[:2]) if len(segment.split()) > 1 else ""
            allowed = base_cmd in ALLOWED_COMMANDS or two_word in ALLOWED_COMMANDS

            if not allowed:
                return json.dumps({
                    "status": "blocked",
                    "command": command,
                    "message": f"Command '{base_cmd}' is not in the allowed commands list.",
                })

        cwd = working_directory if working_directory != "." else None

        if IS_WINDOWS:
            # Run via PowerShell for richer cmdlet support
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
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

        stdout = result.stdout[:5000] if result.stdout else ""
        stderr = result.stderr[:2000] if result.stderr else ""
        truncated = len(result.stdout or "") > 5000

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


def execute_terminal_command(command: str, working_directory: str = ".") -> dict:
    """Execute a terminal command directly (used by the approval endpoint).
    Returns a parsed dict instead of a JSON string."""
    result_json = terminal_execute.invoke({"command": command, "working_directory": working_directory})
    return json.loads(result_json)


ALL_TOOLS = [web_search, terminal_execute]
