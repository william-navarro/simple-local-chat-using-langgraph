import type { ChatRequest, StreamEvent, TerminalResult } from "../types"

const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  })

  if (!response.ok) {
    throw new Error(`Backend error: ${response.status} ${response.statusText}`)
  }

  if (!response.body) {
    throw new Error("No response body")
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split("\n")
    buffer = lines.pop() ?? ""

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const raw = line.slice(6).trim()
        if (!raw) continue
        try {
          yield JSON.parse(raw) as StreamEvent
        } catch {
          // malformed chunk, skip
        }
      }
    }
  }
}

export async function generateTitle(message: string, model: string): Promise<string> {
  try {
    const res = await fetch(`${BASE_URL}/chat/title`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, model }),
    })
    if (!res.ok) return ""
    const data = await res.json()
    return data.title ?? ""
  } catch {
    return ""
  }
}

export async function executeTerminalCommand(
  command: string,
  workingDirectory = ".",
): Promise<TerminalResult & { status: string; message?: string }> {
  const res = await fetch(`${BASE_URL}/chat/terminal/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command, working_directory: workingDirectory }),
  })
  if (!res.ok) {
    return {
      status: "error",
      command,
      exit_code: -1,
      stdout: "",
      stderr: "",
      truncated: false,
      message: `Backend error: ${res.status}`,
    }
  }
  return res.json()
}

export async function fetchLMStudioStatus(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE_URL}/lmstudio/status`)
    if (!res.ok) return false
    const data = await res.json()
    return data.online === true
  } catch {
    return false
  }
}

export async function fetchLMStudioModels(): Promise<string[]> {
  try {
    const res = await fetch(`${BASE_URL}/lmstudio/models`)
    if (!res.ok) return []
    const data = await res.json()
    return data.models ?? []
  } catch {
    return []
  }
}
